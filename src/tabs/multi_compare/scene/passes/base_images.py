"""Base image tile QRhi pass for Multi Compare."""

from __future__ import annotations

import struct

from PySide6.QtCore import QRect, QRectF, QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiViewport,
)

from shared.rendering.tile_geometry import _apron_rect, _TILE_APRON_PX, _TILE_RESIDENCY_MARGIN
from tabs.multi_compare.scene.projection import build_screen_quad_vertices
from tabs.multi_compare.scene.resources import (
    FULLSCREEN_VERTICES,
    SLOT_TILE_CACHE_BUDGET_BYTES,
    SLOT_UNIFORM_SIZE,
    load_shader,
    vertex_input_layout,
)
from tabs.multi_compare.scene.tile_geometry import (
    SlotDrawItem,
    _visible_slot_image_rect,
    build_slot_draw_plan,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass


def _pack_slot_uniforms(
    clip_matrix: tuple[float, ...],
    layer,
    tile_rect: tuple[float, float, float, float],
) -> bytes:
    return struct.pack(
        "<16f 2f 2f f 3f 4f",
        *clip_matrix,
        layer.pan_x,
        layer.pan_y,
        max(layer.fit_x, 1e-6),
        max(layer.fit_y, 1e-6),
        layer.zoom,
        0.0,
        0.0,
        0.0,
        *tile_rect,
    )


def _tile_key_slot_id(tile_key: object) -> object:
    if isinstance(tile_key, tuple):
        return tile_key[0]
    return tile_key


class BaseImagesPass(CanvasRenderPass):
    """Owns image textures, tile pipeline, uniforms, and draw recording.

    Core-owned, not a discoverable feature (see MULTI_COMPARE_QRHI_REFACTOR.md
    A6): wired directly by ``MultiCompareRhiRenderer``, never through
    ``get_canvas_render_passes()``, so it declares no ``stack_role`` — nothing
    ever resolves this pass's stacking order against the shared registry.

    Slots larger than one GPU texture are backed by
    ``shared.rendering.tile_texture_service.TileTextureService`` (the same
    service image_compare uses for its base image), keyed by slot id: a
    normal slot gets a 1x1 grid and is uploaded as a single whole-image
    texture exactly like before; an oversized slot gets an NxM grid whose
    tiles are lazily cropped from ``slot_full_images`` and drawn as one
    extra ``command_buffer.draw(4)`` per GPU-resident tile, each carrying
    its own ``tileRect`` uniform (see ``multi_compare.frag``).
    """

    def __init__(self) -> None:
        self.pipeline = None
        self.slot_textures: dict[object, object] = {}
        self.slot_texture_sizes: dict[object, tuple[int, int]] = {}
        self.slot_full_images: dict[int, QImage] = {}
        self.slot_vertex_buffers: list[object] = []
        self.slot_uniform_buffers: list[object] = []
        # (layer index, tile key) -> (srb, bound texture). Keyed by layer
        # index (not slot id) because the uniform buffer a tile's SRB binds
        # is itself per-layer-index (see _ensure_slot_resources).
        self._tile_srbs: dict[tuple[int, object], tuple[object, object]] = {}
        self.layer_draw_items: list[list[SlotDrawItem]] = []
        self.pending_uploads: list[tuple[int, QImage]] = []
        self.pending_removes: list[int] = []

    def has_slot_texture(self, slot_id: int) -> bool:
        return int(slot_id) in self.slot_full_images

    def slot_texture_ids(self) -> list[int]:
        return list(self.slot_full_images)

    def queue_upload(self, slot_id: int, image: QImage) -> None:
        self.pending_uploads.append((int(slot_id), image))

    def queue_remove(self, slot_id: int) -> None:
        self.pending_removes.append(int(slot_id))

    def initialize(self, renderer, target) -> None:
        self.pipeline = renderer.rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, load_shader("multi_compare.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, load_shader("multi_compare.frag.qsb")
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        first_srb = self._build_slot_srb(renderer, renderer.placeholder, None)
        self.pipeline.setShaderResourceBindings(first_srb)
        self.pipeline.setVertexInputLayout(vertex_input_layout())
        if not self.pipeline.create():
            raise RuntimeError("Failed to create multi_compare slot pipeline")
        try:
            first_srb.destroy()
        except RuntimeError:
            pass

    def release(self) -> None:
        for res in (
            self.pipeline,
            *self.slot_vertex_buffers,
            *self.slot_uniform_buffers,
            *(srb for srb, _texture in self._tile_srbs.values()),
            *self.slot_textures.values(),
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.__init__()

    def apply_pending_texture_ops(self, renderer, updates) -> None:
        tile_service = renderer.tile_service
        for sid in self.pending_removes:
            self._release_slot(tile_service, sid)
        self.pending_removes.clear()
        for sid, image in self.pending_uploads:
            self._upload_slot(renderer, tile_service, sid, image, updates)
        self.pending_uploads.clear()

    def prepare(self, renderer, ctx, updates) -> None:
        fb_w, fb_h = ctx.framebuffer_size
        self._ensure_slot_resources(renderer, len(ctx.projected_layers))
        self._realize_tile_residency(renderer, ctx, updates)
        self.layer_draw_items = []
        for index, layer in enumerate(ctx.projected_layers):
            vx, vy, vw, vh = layer.rect_fb
            updates.updateDynamicBuffer(
                self.slot_vertex_buffers[index],
                0,
                build_screen_quad_vertices(QRectF(vx, vy, vw, vh), fb_w, fb_h),
            )
            pan = (layer.pan_x, layer.pan_y)
            fit = (max(layer.fit_x, 1e-6), max(layer.fit_y, 1e-6))
            items = build_slot_draw_plan(
                renderer.tile_service, int(layer.slot_id), pan, fit, layer.zoom
            )
            self.layer_draw_items.append(items)

    def record(self, renderer, ctx, command_buffer) -> None:
        if not ctx.projected_layers:
            return
        fb_w, fb_h = ctx.framebuffer_size
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
        for index, layer in enumerate(ctx.projected_layers):
            command_buffer.setVertexInput(0, [(self.slot_vertex_buffers[index], 0)])
            # One draw call per GPU-resident tile this slot needs this frame
            # (docs/dev/TILED_RENDERING_DESIGN.md pattern): the common case
            # (slot fits in one texture) runs this loop exactly once with
            # tileRect == (0,0,1,1), unchanged from pre-tiling behavior.
            for item in self.layer_draw_items[index]:
                texture = self.slot_textures.get(item.tile_key)
                if texture is None:
                    continue
                srb = self._ensure_tile_srb(renderer, index, item.tile_key, texture)
                command_buffer.setShaderResources(srb)
                tile_updates = renderer.rhi.nextResourceUpdateBatch()
                tile_updates.updateDynamicBuffer(
                    self.slot_uniform_buffers[index],
                    0,
                    _pack_slot_uniforms(ctx.clip_matrix, layer, item.tile_rect),
                )
                command_buffer.resourceUpdate(tile_updates)
                command_buffer.draw(4)

    # -- texture upload / residency -----------------------------------

    def _release_slot(self, tile_service, sid: int) -> None:
        self.slot_full_images.pop(sid, None)
        tile_service.invalidate_source(sid)
        self._destroy_slot_textures(sid, keep=frozenset())
        self._purge_tile_srbs_for_slot(sid)

    def _upload_slot(self, renderer, tile_service, sid: int, image: QImage, updates) -> None:
        size = (image.width(), image.height())
        grid = tile_service.register_source(sid, size)
        self.slot_full_images[sid] = image
        self._purge_tile_srbs_for_slot(sid)
        if grid.rows == 1 and grid.columns == 1:
            tile_key = tile_service.tile_key(sid, 0, 0)
            self._destroy_slot_textures(sid, keep={tile_key})
            self._upload_tile(renderer, tile_key, image, updates)
            return
        # Multi-tile: nothing uploaded eagerly here -- _realize_tile_residency
        # (called every frame from prepare()) lazily crops+uploads only
        # whichever tiles the current viewport actually needs, from
        # slot_full_images[sid].
        self._destroy_slot_textures(sid, keep=frozenset())

    def _upload_tile(self, renderer, tile_key: object, image: QImage, updates) -> None:
        size = (image.width(), image.height())
        existing = self.slot_textures.get(tile_key)
        if existing is None or self.slot_texture_sizes.get(tile_key) != size:
            if existing is not None:
                try:
                    existing.destroy()
                except RuntimeError:
                    pass
            tex = renderer.rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(*size))
            tex.create()
            self.slot_textures[tile_key] = tex
            self.slot_texture_sizes[tile_key] = size
        updates.uploadTexture(self.slot_textures[tile_key], image)

    def _realize_tile_residency(self, renderer, ctx, updates) -> None:
        """Viewport-driven partial residency for oversized slots (docs/dev/
        TILED_RENDERING_DESIGN.md Phase 2): crops+uploads whichever tiles
        each multi-tile slot's current viewport needs (visible rect plus a
        ``_TILE_RESIDENCY_MARGIN`` ring) and aren't already resident, then
        evicts whatever ``tile_service.evict_over_budget()`` decides to
        evict across every slot combined."""
        tile_service = renderer.tile_service
        protected_by_key: dict[object, set[tuple[int, int]]] = {}
        for layer in ctx.projected_layers:
            sid = int(layer.slot_id)
            grid = tile_service.grid_for(sid)
            if grid is None or (grid.rows == 1 and grid.columns == 1):
                continue
            full_image = self.slot_full_images.get(sid)
            if full_image is None:
                continue
            pan = (layer.pan_x, layer.pan_y)
            fit = (max(layer.fit_x, 1e-6), max(layer.fit_y, 1e-6))
            visible_rect = _visible_slot_image_rect(pan, fit, layer.zoom, grid)
            target = tile_service.resolve_visible_tiles(
                sid, visible_rect, _TILE_RESIDENCY_MARGIN
            )
            protected_by_key[sid] = target
            regions = {(row, col): region for row, col, region in grid.iter_regions()}
            for index in target:
                if tile_service.is_resident(sid, index):
                    tile_service.touch(sid, index)
                    continue
                region = regions.get(index)
                if region is None:
                    continue
                left, top, right, bottom = _apron_rect(
                    grid.total_width, grid.total_height, region, _TILE_APRON_PX
                )
                tile_key = tile_service.tile_key(sid, *index)
                tile_image = full_image.copy(QRect(left, top, right - left, bottom - top))
                self._upload_tile(renderer, tile_key, tile_image, updates)
                tile_service.mark_resident(sid, index, (right - left) * (bottom - top) * 4)
        evicted = tile_service.evict_over_budget(protected_by_key, SLOT_TILE_CACHE_BUDGET_BYTES)
        for sid, index in evicted:
            tile_key = tile_service.tile_key(sid, *index)
            texture = self.slot_textures.pop(tile_key, None)
            if texture is not None:
                try:
                    texture.destroy()
                except RuntimeError:
                    pass
            self.slot_texture_sizes.pop(tile_key, None)
            self._purge_tile_srb_entry(tile_key)

    def _destroy_slot_textures(self, sid: int, *, keep: frozenset | set) -> None:
        stale = [
            key
            for key in self.slot_textures
            if _tile_key_slot_id(key) == sid and key not in keep
        ]
        for key in stale:
            texture = self.slot_textures.pop(key, None)
            if texture is not None:
                try:
                    texture.destroy()
                except RuntimeError:
                    pass
            self.slot_texture_sizes.pop(key, None)

    # -- GPU resources: buffers / shader resource bindings --------------

    def _build_slot_srb(self, renderer, texture, uniform):
        srb = renderer.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        bindings = []
        if uniform is not None:
            bindings.append(QRhiShaderResourceBinding.uniformBuffer(0, stages, uniform))
        else:
            placeholder_uniform = renderer.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                SLOT_UNIFORM_SIZE,
            )
            placeholder_uniform.create()
            self.slot_uniform_buffers.append(placeholder_uniform)
            bindings.append(
                QRhiShaderResourceBinding.uniformBuffer(0, stages, placeholder_uniform)
            )
        bindings.append(
            QRhiShaderResourceBinding.sampledTexture(
                1, fragment, texture, renderer.sampler
            )
        )
        srb.setBindings(bindings)
        if not srb.create():
            raise RuntimeError("Failed to create multi_compare slot SRB")
        return srb

    def _ensure_slot_resources(self, renderer, count: int) -> None:
        while len(self.slot_vertex_buffers) < count:
            buf = renderer.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.VertexBuffer,
                len(FULLSCREEN_VERTICES),
            )
            buf.create()
            self.slot_vertex_buffers.append(buf)
        while len(self.slot_uniform_buffers) < count:
            buf = renderer.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                SLOT_UNIFORM_SIZE,
            )
            buf.create()
            self.slot_uniform_buffers.append(buf)

    def _ensure_tile_srb(self, renderer, index: int, tile_key: object, texture):
        """Returns a ready-to-bind SRB for (layer index, tile) -- cached
        across frames and only rebuilt when the bound texture object
        identity changes (a fresh upload/resize, or a tile that got
        evicted-then-recreated)."""
        cache_key = (index, tile_key)
        cached = self._tile_srbs.get(cache_key)
        if cached is not None and cached[1] is texture:
            return cached[0]
        if cached is not None:
            try:
                cached[0].destroy()
            except RuntimeError:
                pass
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb = renderer.rhi.newShaderResourceBindings()
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(
                    0, stages, self.slot_uniform_buffers[index]
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, texture, renderer.sampler
                ),
            ]
        )
        srb.create()
        self._tile_srbs[cache_key] = (srb, texture)
        return srb

    def _purge_tile_srbs_for_slot(self, sid: int) -> None:
        stale = [
            cache_key
            for cache_key in self._tile_srbs
            if _tile_key_slot_id(cache_key[1]) == sid
        ]
        for cache_key in stale:
            srb, _texture = self._tile_srbs.pop(cache_key)
            try:
                srb.destroy()
            except RuntimeError:
                pass

    def _purge_tile_srb_entry(self, tile_key: object) -> None:
        stale = [cache_key for cache_key in self._tile_srbs if cache_key[1] == tile_key]
        for cache_key in stale:
            srb, _texture = self._tile_srbs.pop(cache_key)
            try:
                srb.destroy()
            except RuntimeError:
                pass
