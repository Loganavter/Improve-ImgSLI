from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QShader,
)

from ..texture_parts.tile_geometry import (
    _apron_rect,
    _TILE_APRON_PX,
    _TILE_RESIDENCY_MARGIN,
    _visible_side_image_rect,
)
from ..texture_parts.tile_texture_service import TileTextureService
from ..texture_parts.upload_queue import queue_texture_upload
from ._debug import rhi_render_debug
from .uniforms import _UNIFORM_BLOCK_SIZE

_SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders"
# docs/dev/TILED_RENDERING_DESIGN.md Phase 2 "Open questions: Tile size" —
# fixed constant rather than backend-derived, so tile count (and therefore
# eviction/residency behavior) is deterministic across machines. Clamped to
# the backend's real max at construction time (see initialize()) as a
# defensive floor only; every real backend supports far more than 2048px.
_LIVE_TILE_EXTENT = 8192
# docs/dev/TILED_RENDERING_DESIGN.md Phase 2 "Open questions: Cache budget"
# -- byte budget over resident-tile pixel bytes (RGBA8, post-apron), not a
# tile count: matches how production tile caches (image editors, tiled map
# renderers) bound GPU memory, since per-tile byte cost varies at grid
# edges. Global across all resident tiles (image1/image2/diff sides
# combined) since GPU memory is one shared resource, not three independent
# ones. 512MiB fits roughly 32 fully-apron'd 2048x2048 RGBA8 tiles resident
# at once -- enough slack beyond the visible+margin ring that ordinary
# pan/zoom doesn't thrash the cache, while still bounding memory during a
# "pan all over a huge image" session.
_TILE_CACHE_BUDGET_BYTES = 512 * 1024 * 1024
_VERTICES = struct.pack(
    "<16f",
    -1.0,
    1.0,
    0.0,
    0.0,
    -1.0,
    -1.0,
    0.0,
    1.0,
    1.0,
    1.0,
    1.0,
    0.0,
    1.0,
    -1.0,
    1.0,
    1.0,
)


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


class RhiResources:
    """Owns every ``rhi.new*()`` / ``.create()`` / ``.destroy()`` call for
    the base-image renderer: vertex buffer, uniform buffer, samplers, the
    resident textures, the pipeline, and shader resource bindings. Tile
    *residency decisions* belong to ``TileTextureService``; this class only
    executes them against real QRhi resources -- see ``realize_tile_plan``.
    """

    def __init__(self) -> None:
        self.rhi = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.samplers: dict[str, object] = {}
        self.textures: dict[object, object] = {}
        self.texture_sizes: dict[object, QSize] = {}
        self.srb = None
        self.pipeline = None
        self._srb_signature = None
        self._render_pass_descriptor = None

    def initialize(self, rhi, widget, command_buffer) -> None:
        self.rhi = rhi

        self.vertex_buffer = self.rhi.newBuffer(
            QRhiBuffer.Type.Immutable,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(_VERTICES),
        )
        self.vertex_buffer.setName(b"canvas-quad")
        if not self.vertex_buffer.create():
            raise RuntimeError("Failed to create canvas vertex buffer")

        self.uniform_buffer = self.rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_BLOCK_SIZE,
        )
        self.uniform_buffer.setName(b"canvas-uniforms")
        if not self.uniform_buffer.create():
            raise RuntimeError("Failed to create canvas uniform buffer")

        for name, filter_mode in (
            ("nearest", QRhiSampler.Filter.Nearest),
            ("linear", QRhiSampler.Filter.Linear),
        ):
            sampler = self.rhi.newSampler(
                filter_mode,
                filter_mode,
                QRhiSampler.Filter.None_,
                QRhiSampler.AddressMode.ClampToEdge,
                QRhiSampler.AddressMode.ClampToEdge,
            )
            sampler.setName(f"canvas-{name}-sampler".encode())
            if not sampler.create():
                raise RuntimeError(f"Failed to create {name} sampler")
            self.samplers[name] = sampler

        placeholder = QImage(1, 1, QImage.Format.Format_RGBA8888)
        placeholder.fill(0)
        updates = self.rhi.nextResourceUpdateBatch()
        updates.uploadStaticBuffer(self.vertex_buffer, _VERTICES)
        self._replace_texture("placeholder", placeholder, updates)
        command_buffer.resourceUpdate(updates)
        self.ensure_pipeline(widget)

    def release(self) -> None:
        resources = [
            self.pipeline,
            self.srb,
            *self.textures.values(),
            *self.samplers.values(),
            self.uniform_buffer,
            self.vertex_buffer,
        ]
        for resource in resources:
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self.__init__()

    def _replace_texture(self, key, image: QImage, updates) -> None:
        if self.srb is not None:
            self.srb.destroy()
            self.srb = None
            self._srb_signature = None
        old_texture = self.textures.pop(key, None)
        if old_texture is not None:
            old_texture.destroy()

        texture = self.rhi.newTexture(
            QRhiTexture.Format.RGBA8,
            image.size(),
        )
        texture.setName(f"canvas-{key}".encode())
        if not texture.create():
            raise RuntimeError(f"Failed to create texture {key} at {image.size()}")
        self.textures[key] = texture
        self.texture_sizes[key] = image.size()
        updates.uploadTexture(texture, image)

    def upload_whole(self, key, image: QImage, updates) -> None:
        size_changed = self.texture_sizes.get(key) != image.size()
        if key not in self.textures or size_changed:
            self._replace_texture(key, image, updates)
        else:
            updates.uploadTexture(self.textures[key], image)

    def _evict_stale_tiles(self, source_key, live_keys: set[object]) -> None:
        stale = [
            existing_key
            for existing_key in self.textures
            if existing_key not in live_keys
            and (
                existing_key == source_key
                or (
                    isinstance(existing_key, tuple)
                    and len(existing_key) == 3
                    and existing_key[0] == source_key
                )
            )
        ]
        for stale_key in stale:
            texture = self.textures.pop(stale_key, None)
            if texture is not None:
                texture.destroy()
            self.texture_sizes.pop(stale_key, None)

    def upload_source(self, tile_service: TileTextureService, key, image: QImage, updates) -> None:
        """Registers ``key`` with ``tile_service``. A grid that stays 1x1
        (the common case: image fits within one ``_LIVE_TILE_EXTENT`` tile)
        is uploaded immediately as a single whole-image texture, unchanged
        from pre-tiling behavior. A multi-tile grid uploads nothing here --
        old tiles for this key (which may belong to a since-replaced image
        or a different grid shape) are evicted, and ``realize_tile_plan``
        (called from ``render()`` every frame) lazily crops+uploads only
        whatever tiles the current viewport actually needs, from the full
        QImage already retained in
        ``widget.runtime_state._texture_upload_cache``."""
        grid = tile_service.register_source(key, (image.width(), image.height()))
        rhi_render_debug(
            "upload_source key=%s image=%dx%d -> grid=%dx%d (tile_total=%dx%d)",
            key,
            image.width(),
            image.height(),
            grid.rows,
            grid.columns,
            grid.total_width,
            grid.total_height,
        )
        if grid.rows == 1 and grid.columns == 1:
            self.upload_whole(key, image, updates)
            self._evict_stale_tiles(key, {key})
            return
        self._evict_stale_tiles(key, set())

    def apply_pending_uploads(self, widget, tile_service: TileTextureService, updates) -> None:
        pending = widget.runtime_state._pending_texture_uploads
        while pending:
            key, image, _slot = pending.pop(0)
            if not isinstance(image, QImage) or image.isNull():
                continue
            self.upload_source(tile_service, key, image, updates)

    @staticmethod
    def restore_texture_uploads(widget) -> None:
        state = widget.runtime_state
        if state._pending_texture_uploads:
            return
        cache = getattr(state, "_texture_upload_cache", {}) or {}
        for slot, texture_key in enumerate(widget.texture_ids):
            cached = cache.get(texture_key)
            if cached is not None:
                state._pending_texture_uploads.append((texture_key, cached, slot))
                state._images_uploaded[slot] = True
            else:
                image = state._stored_pil_images[slot]
                queue_texture_upload(widget, image, texture_key, slot)
        for slot, texture_key in enumerate(widget._source_texture_ids):
            cached = cache.get(texture_key)
            if cached is not None:
                state._pending_texture_uploads.append((texture_key, cached, None))
            else:
                image = state._source_pil_images[slot]
                queue_texture_upload(widget, image, texture_key)
        diff_key = widget._diff_source_texture_id
        cached_diff = cache.get(diff_key)
        if cached_diff is not None:
            state._pending_texture_uploads.append((diff_key, cached_diff, None))
        elif state._diff_source_pil_image is not None:
            queue_texture_upload(widget, state._diff_source_pil_image, diff_key)
        rhi_render_debug(
            "restore texture uploads widget=%s pending=%d",
            f"{type(widget).__name__}@{id(widget):x}",
            len(state._pending_texture_uploads),
        )

    def realize_tile_plan(
        self,
        tile_service: TileTextureService,
        widget,
        texture_keys: tuple[object, object],
        base_image,
        updates,
        *,
        diff_key: object | None = None,
        viewport_zoom: tuple[float, float] | None = None,
        viewport_offset: tuple[float, float] | None = None,
    ) -> None:
        """Viewport-driven partial residency (docs/dev/
        TILED_RENDERING_DESIGN.md Phase 2): for each side whose grid is
        multi-tile, crops+uploads whichever tiles ``tile_service`` decides
        should be resident (visible rect plus a ``_TILE_RESIDENCY_MARGIN``
        ring) and aren't already, and destroys the GPU textures for
        whatever ``tile_service.evict_over_budget()`` decides to evict.
        Tiles are cropped from the full-resolution QImage already cached at
        ``widget.runtime_state._texture_upload_cache`` (the same cache
        ``restore_texture_uploads`` uses to survive context loss), not
        re-decoded. This method reads residency decisions from
        ``tile_service`` and performs them -- it never decides on its own
        which indices should be resident.

        ``diff_key`` (Phase 4): the diff overlay is treated as a third
        "side" positioned like image1 (same letterbox), since diff is
        always computed at image1's aspect/content window regardless of
        which pixel resolution either happens to be at right now."""
        letterboxes = (tuple(base_image.letterbox1), tuple(base_image.letterbox2))
        pairs = list(zip(texture_keys, letterboxes))
        if diff_key is not None:
            pairs.append((diff_key, letterboxes[0]))
        cache = getattr(widget.runtime_state, "_texture_upload_cache", {}) or {}
        protected_by_key: dict[object, set[tuple[int, int]]] = {}
        for key, letterbox in pairs:
            grid = tile_service.grid_for(key)
            if grid is None or (grid.rows == 1 and grid.columns == 1):
                continue
            full_image = cache.get(key)
            if full_image is None:
                continue
            visible_rect = _visible_side_image_rect(
                base_image,
                letterbox,
                grid,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
            )
            target = tile_service.resolve_visible_tiles(
                key, visible_rect, _TILE_RESIDENCY_MARGIN
            )
            rhi_render_debug(
                "realize_tile_plan key=%s grid=%dx%d(%dx%d) visible_rect=%s target=%s",
                key,
                grid.rows,
                grid.columns,
                grid.total_width,
                grid.total_height,
                visible_rect,
                target,
            )
            protected_by_key[key] = target
            regions = {(row, col): region for row, col, region in grid.iter_regions()}
            for index in target:
                if tile_service.is_resident(key, index):
                    tile_service.touch(key, index)
                    continue
                region = regions.get(index)
                if region is None:
                    continue
                left, top, right, bottom = _apron_rect(
                    grid.total_width, grid.total_height, region, _TILE_APRON_PX
                )
                tile_key = tile_service.tile_key(key, *index)
                tile_image = full_image.copy(
                    QRect(left, top, right - left, bottom - top)
                )
                self.upload_whole(tile_key, tile_image, updates)
                tile_service.mark_resident(
                    key, index, (right - left) * (bottom - top) * 4
                )
        evicted = tile_service.evict_over_budget(
            protected_by_key, _TILE_CACHE_BUDGET_BYTES
        )
        for source_key, index in evicted:
            tile_key = tile_service.tile_key(source_key, *index)
            texture = self.textures.pop(tile_key, None)
            if texture is not None:
                texture.destroy()
            self.texture_sizes.pop(tile_key, None)

    def ensure_srb_for(self, texture_keys: tuple[object, object, object], sampler_name: str):
        """Returns a ready-to-bind QRhiShaderResourceBindings for this exact
        (texture_keys, sampler_name) signature. Must not be called between
        beginPass and endPass -- see docs/dev/QRHI_CANVAS_FEATURES.md's
        CanvasRenderPass contract (initialize/prepare create resources,
        record() only draws)."""
        signature = (*texture_keys, sampler_name)
        if self.srb is not None and signature == self._srb_signature:
            return self.srb

        if self.srb is not None:
            self.srb.destroy()
        sampler = self.samplers[sampler_name]
        placeholder = self.textures["placeholder"]
        textures = [self.textures.get(key, placeholder) for key in texture_keys]
        rhi_render_debug(
            "ensure_srb keys=%s missing=%s resident_texture_keys=%d",
            texture_keys,
            [key for key in texture_keys if key not in self.textures],
            len(self.textures),
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        self.srb = self.rhi.newShaderResourceBindings()
        self.srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, textures[0], sampler
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    2, fragment, textures[1], sampler
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    3, fragment, textures[2], sampler
                ),
            ]
        )
        if not self.srb.create():
            raise RuntimeError("Failed to create canvas shader resource bindings")
        self._srb_signature = signature
        return self.srb

    def ensure_pipeline(self, widget) -> None:
        target = widget.renderTarget()
        if target is None:
            return
        descriptor = target.renderPassDescriptor()
        if self.pipeline is not None and descriptor is self._render_pass_descriptor:
            return
        if self.pipeline is not None:
            self.pipeline.destroy()

        self.ensure_srb_for(("placeholder", "placeholder", "placeholder"), "linear")
        pipeline = self.rhi.newGraphicsPipeline()
        pipeline.setName(b"canvas-base-pipeline")
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("base.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, _load_shader("base.frag.qsb")
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(target.sampleCount())
        pipeline.setShaderResourceBindings(self.srb)
        pipeline.setRenderPassDescriptor(descriptor)

        input_layout = QRhiVertexInputLayout()
        input_layout.setBindings([QRhiVertexInputBinding(16)])
        input_layout.setAttributes(
            [
                QRhiVertexInputAttribute(
                    0, 0, QRhiVertexInputAttribute.Format.Float2, 0
                ),
                QRhiVertexInputAttribute(
                    0, 1, QRhiVertexInputAttribute.Format.Float2, 8
                ),
            ]
        )
        pipeline.setVertexInputLayout(input_layout)

        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        pipeline.setTargetBlends([blend])

        if not pipeline.create():
            raise RuntimeError("Failed to create canvas graphics pipeline")
        self.pipeline = pipeline
        self._render_pass_descriptor = descriptor
