from __future__ import annotations

import struct
import time
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QRhi,
    QImage,
    QRhiBuffer,
    QRhiSampler,
    QRhiTexture,
    QShader,
)

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.mip_cascade import MipCascadeGenerator
from shared.rendering.tile_texture_service import DEFAULT_MAX_ARRAY_SIZE, TileTextureService
from shared.rendering.uniform_layout import assert_uniform_size

from ..texture_parts.tile_geometry import _TILE_APRON_PX
from ..texture_parts.upload_queue import (
    queue_texture_upload,
    touch_texture_upload_cache,
)
from ._debug import rhi_render_debug
from .array_resources import ArrayResources
from .residency import _TILE_CACHE_BUDGET_BYTES, TileResidencyRealizer

_SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders"
# Clamped to the backend's real max at construction time (see initialize())
# as a defensive floor only; every real backend supports far more than 2048px.
from shared.rendering.tile_constants import LIVE_TILE_EXTENT as _LIVE_TILE_EXTENT
# docs/dev/rendering/tile-array-atlas-plan.md Phase 2 -- every layer of the
# texture array must share one pixel size (a hard cross-backend constraint,
# not addressed by the plan's original per-tile-heterogeneous-size design),
# so tile content (at most LIVE_TILE_EXTENT + 2*apron px, the same bound
# `_apron_rect` already enforces for individual tile textures) is uploaded
# 1:1, unresampled, into the top-left corner of a layer this size; unused
# padding is never sampled because the shader always scales UV by each
# tile's own content-scale (contentPx / this size) before sampling.
_ARRAY_LAYER_PX = _LIVE_TILE_EXTENT + 2 * _TILE_APRON_PX
_ARRAY_LAYER_BYTES = _ARRAY_LAYER_PX * _ARRAY_LAYER_PX * 4
# A flat floor here (an earlier version of this constant used a bare "12")
# can't actually guarantee anything: the real requirement scales with how
# many LIVE_TILE_EXTENT tiles can be visible on screen at once, which
# depends on canvas size, not a guess. Derive it instead (bug found via a
# user report of tiles vanishing/returning above ~765% zoom, then landing
# on visibly wrong/neighboring tile content ("разные грани") once a first
# fix merely raised the floor without fixing the underlying math -- see
# docs/dev/rendering/tile-array-atlas-plan.md Phase 2 Findings):
# `select_level` (lod.py) always picks the pyramid level whose *effective*
# dest_scale (dest_scale * 2**level) is in [0.5, 1.0) -- i.e. one tile
# never spans less than half of `_LIVE_TILE_EXTENT` screen pixels. So the
# number of tiles visible along one axis is bounded by
# `ceil(2 * canvas_px / LIVE_TILE_EXTENT) + 1` (the "+1" covers
# straddling a tile boundary). `_MAX_EXPECTED_CANVAS_PX` bounds canvas_px
# to a single 4K-ish monitor -- an ultra-wide/multi-monitor-spanning
# canvas beyond that is a known follow-up, not covered here. The result
# is squared (both axes) and multiplied by 3 -- image1 + image2 + diff,
# since diff mode registers its own independent grid/residency and can
# need a tile at every position image1/image2 do (`base_array.frag`
# always samples image1/image2 even in diff-only draw modes).
_MAX_EXPECTED_CANVAS_PX = 4096
_MAX_TILES_PER_AXIS = -(-(2 * _MAX_EXPECTED_CANVAS_PX) // _LIVE_TILE_EXTENT) + 1
# Capped at DEFAULT_MAX_ARRAY_SIZE (the measured cross-backend
# TextureArraySizeMax -- see tile-array-atlas-plan.md Phase 0/1, and
# TileTextureService's _TileSlotAllocator, which is what actually decides
# when to open a new array): a single QRhiTextureArray can't exceed the
# backend's real layer limit regardless of how big the byte budget or
# canvas-size bound below computes to, and _TileSlotAllocator already opens
# additional arrays past this cap instead of overflowing one array, so
# growing past it here would only reserve GPU memory for layers this array
# could never actually use.
_ARRAY_CAPACITY = min(
    DEFAULT_MAX_ARRAY_SIZE,
    max(
        3 * _MAX_TILES_PER_AXIS * _MAX_TILES_PER_AXIS,
        _TILE_CACHE_BUDGET_BYTES // _ARRAY_LAYER_BYTES,
    ),
)
# Per-instance vertex layout for the array pipeline (base_array.vert):
# iRect1(vec4,16) + iRect2(vec4,16) + iContentScale(vec4,16) +
# iContentScaleDiff(vec2,8) + iLayers(ivec3,12) + iBBox(vec4,16) +
# iRectDiff(vec4,16) = 100 bytes. Plain vertex attribute packing -- no
# std140 alignment rules apply here (that's a uniform-buffer-only
# constraint), just consistency between this stride and
# _pack_array_instance's struct.pack format below. iBBox is the
# content-space rect (docs/dev/rendering/tile-array-atlas-plan.md Phase 10)
# each instance's geometry is clipped to, instead of every instance emitting
# a shared fullscreen quad and relying entirely on the fragment shader's
# per-pixel tileUV1/tileUV2 discard to "clip" it down. iRectDiff is that
# same idea for a multi-tile diff/SSIM source: the assigned diff tile's own
# content-space rect, subtracted from sampleUV in the fragment shader before
# addressing that tile's array layer (identity (0,0,1,1) when diff isn't
# split -- see docs/dev/rendering/qrhi-gotchas.md
# #ssim-diff-blocky-mosaic-at-coarse-lod).
_ARRAY_INSTANCE_STRIDE = 100
_ARRAY_INSTANCE_FMT = "<4f4f4f2f3i4f4f"
assert_uniform_size(
    _ARRAY_INSTANCE_FMT, _ARRAY_INSTANCE_STRIDE, label="_pack_array_instance"
)
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


def pack_array_instance(
    *,
    rect1: tuple[float, float, float, float],
    rect2: tuple[float, float, float, float],
    content_scale: tuple[float, float, float, float],
    content_scale_diff: tuple[float, float],
    layer1: int,
    layer2: int,
    layer_diff: int,
    bbox: tuple[float, float, float, float],
    rect_diff: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> bytes:
    """One instance's worth of ``base_array.vert``'s per-instance vertex
    attributes -- byte-for-byte matching ``_ARRAY_INSTANCE_STRIDE``/the
    pipeline's ``QRhiVertexInputAttribute`` offsets in ``ensure_array_pipeline``."""
    return struct.pack(
        _ARRAY_INSTANCE_FMT,
        *rect1,
        *rect2,
        *content_scale,
        *content_scale_diff,
        layer1,
        layer2,
        layer_diff,
        *bbox,
        *rect_diff,
    )


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


class RhiResources:
    """Owns vertex buffer/samplers/placeholder texture setup and the
    whole-image (non-array/non-tiled) upload path for the base-image
    renderer. The texture-array tile-residency path lives in
    ``self.array_resources`` (``ArrayResources``), viewport-driven partial
    tile residency (crop+upload decisions) lives in ``self.residency``
    (``TileResidencyRealizer``), and per-layer mip generation lives in
    ``self._mip_cascade`` (``MipCascadeGenerator``).
    """

    def __init__(self) -> None:
        self.rhi: QRhi | None = None
        self.vertex_buffer: QRhiBuffer | None = None
        self.samplers: dict[str, QRhiSampler] = {}
        self.textures: dict[object, QRhiTexture] = {}
        self.texture_sizes: dict[object, QSize] = {}

        # Texture-array instanced-draw path (docs/dev/rendering/
        # tile-array-atlas-plan.md) -- every grid, including a 1x1 one,
        # renders through this. One array per `TileSlot.array_index` (in
        # practice always just index 0 -- see _ARRAY_CAPACITY).
        self.array_resources = ArrayResources(
            rhi_getter=lambda: self.rhi,
            sampler_getter=lambda name: self.samplers[name],
            load_shader=_load_shader,
            layer_px=_ARRAY_LAYER_PX,
            array_capacity=_ARRAY_CAPACITY,
            name_prefix="canvas",
        )

        # Per-layer mip generation (docs/dev/rendering/tile-array-atlas-plan.md
        # Phase 9) -- replaces the whole-array `updates.generateMips` call for
        # tile_arrays with a manual cascade of single-layer downsample passes.
        # Shared with multi_compare's BaseImagesPass (identical logic, only
        # _ARRAY_LAYER_PX/sampler differ per tab; the mip_downsample shader
        # itself is loaded by MipCascadeGenerator from a shared shader dir).
        self._mip_cascade = MipCascadeGenerator(
            rhi_getter=lambda: self.rhi,
            tile_arrays=self.array_resources.tile_arrays,
            ensure_tile_array=self.array_resources._ensure_tile_array,
            sampler_getter=lambda: self.samplers["linear"],
            layer_px=_ARRAY_LAYER_PX,
            name_prefix="canvas",
        )

        # Viewport-driven partial tile residency (docs/dev/TILED_RENDERING_DESIGN.md
        # Phase 2) -- decides which tiles should be resident, crops/uploads
        # them into self.array_resources, and evicts the rest.
        self.residency = TileResidencyRealizer(
            array_resources=self.array_resources,
            evict_stale_tiles=self._evict_stale_tiles,
        )

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

        for name, filter_mode, mipmap_mode in (
            # "nearest" stays mip-less: it exists for pixel-perfect zoom-in
            # (magnification), where there is no minification to alias.
            ("nearest", QRhiSampler.Filter.Nearest, QRhiSampler.Filter.None_),
            # "linear" is also used far below 1:1 (e.g. the pyramid's
            # coarsest level, 1024px cap, still shown smaller on a small
            # zoomed-out canvas) where a mip-less bilinear sample aliases
            # badly on high-frequency content -- trilinear via mipmaps fixes
            # the residual minification the pyramid doesn't cover.
            ("linear", QRhiSampler.Filter.Linear, QRhiSampler.Filter.Linear),
        ):
            sampler = self.rhi.newSampler(
                filter_mode,
                filter_mode,
                mipmap_mode,
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

    def release(self) -> None:
        self._mip_cascade.release()
        self.array_resources.release()
        resources = [
            *self.textures.values(),
            *self.samplers.values(),
            self.vertex_buffer,
        ]
        for resource in resources:
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self.__init__()  # type: ignore[misc]  # resource-reset reinit

    def _replace_texture(self, key, image: QImage, updates) -> None:
        assert self.rhi is not None
        old_texture = self.textures.pop(key, None)
        if old_texture is not None:
            old_texture.destroy()

        texture = self.rhi.newTexture(
            QRhiTexture.Format.RGBA8,
            image.size(),
            1,
            QRhiTexture.Flag.MipMapped | QRhiTexture.Flag.UsedWithGenerateMips,
        )
        texture.setName(f"canvas-{key}".encode())
        if not texture.create():
            raise RuntimeError(f"Failed to create texture {key} at {image.size()}")
        self.textures[key] = texture
        self.texture_sizes[key] = image.size()
        updates.uploadTexture(texture, image)
        updates.generateMips(texture)

    def upload_whole(self, key, image: QImage, updates) -> None:
        size_changed = self.texture_sizes.get(key) != image.size()
        if key not in self.textures or size_changed:
            self._replace_texture(key, image, updates)
        else:
            updates.uploadTexture(self.textures[key], image)
            updates.generateMips(self.textures[key])

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
        ``widget.runtime_state._texture_upload_cache``.

        This is the *eager* upload path -- reached whenever a caller
        queues a whole new image for a role that reuses a stable slot key
        (`"stored_0"`, `"diff"`, ...) across content swaps, e.g. a fresh
        SSIM diff map replacing the previous pair's diff. Every call here
        means that role's content genuinely changed (callers only queue
        when their own before/after identity check says so -- see
        ``upload_diff_source_pil_image``'s ``image_id`` guard), so
        ``key``'s previous content (if a multi-tile grid had any tiles
        already resident) is always rekeyed to a fallback key first,
        exactly like ``realize_tile_plan``'s lazy re-register branch --
        without this, a diff/base role whose grid is multi-tile would have
        every resident tile dropped the instant a new image lands, then
        refill tile-by-tile from blank over several frames instead of the
        old diff staying visible until the new one is ready (docs/dev/
        rendering/qrhi-gotchas.md same-slot-swap SSIM follow-up)."""
        self.residency.rekey_stale_content(tile_service, key)
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
        for slot, texture_key in enumerate(widget.texture_ids):
            cached = touch_texture_upload_cache(widget, texture_key)
            if cached is not None:
                state._pending_texture_uploads.append((texture_key, cached, slot))
                state._images_uploaded[slot] = True
            else:
                image = state._stored_pil_images[slot]
                if isinstance(image, TiledPixelStore):
                    state._images_uploaded[slot] = True
                    continue
                queue_texture_upload(widget, image, texture_key, slot)
        for slot, texture_key in enumerate(widget._source_texture_ids):
            cached = touch_texture_upload_cache(widget, texture_key)
            if cached is not None:
                state._pending_texture_uploads.append((texture_key, cached, None))
            else:
                image = state._source_pil_images[slot]
                if isinstance(image, TiledPixelStore):
                    continue
                queue_texture_upload(widget, image, texture_key)
        diff_key = widget._diff_source_texture_id
        cached_diff = touch_texture_upload_cache(widget, diff_key)
        if cached_diff is not None:
            state._pending_texture_uploads.append((diff_key, cached_diff, None))
        elif state._diff_source_pil_image is not None:
            queue_texture_upload(widget, state._diff_source_pil_image, diff_key)
        rhi_render_debug(
            "restore texture uploads widget=%s pending=%d",
            f"{type(widget).__name__}@{id(widget):x}",
            len(state._pending_texture_uploads),
        )

    def generate_all_dirty_mips(
        self,
        command_buffer,
        dirty_layers: dict[int, set[int]],
        time_budget_ms: float | None = None,
    ) -> dict[int, set[int]]:
        return self._mip_cascade.generate_all_dirty_mips(
            command_buffer, self.vertex_buffer, dirty_layers, time_budget_ms
        )
