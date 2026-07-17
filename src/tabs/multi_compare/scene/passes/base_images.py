"""Base image tile QRhi pass for Multi Compare."""

from __future__ import annotations

import struct

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiViewport,
)

from shared.image_processing.tiled_pixel_store import (
    TiledPixelStore,
    qimage_from_pixel_source,
)
from shared.rendering.host_texture_cache import cache_for_host
from shared.rendering.tile_geometry import (
    _TILE_APRON_PX,
    _TILE_RESIDENCY_MARGIN,
    crop_apron_tile,
)
from tabs.multi_compare.scene.projection import build_screen_quad_vertices
from tabs.multi_compare.scene.resources import (
    FULLSCREEN_VERTICES,
    SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES,
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


def _slot_host_key(slot_id: int) -> str:
    return f"slot_{int(slot_id)}"


def _slot_tile_host_key(slot_id: int, row: int, col: int) -> str:
    return f"slot_{int(slot_id)}_{int(row)}_{int(col)}"


class BaseImagesPass(CanvasRenderPass):
    """Owns image textures, tile pipeline, uniforms, and draw recording.

    Full-res slot pixels live in :class:`TiledPixelStore` (session state).
    This pass keeps GPU residency via ``TileTextureService`` and a bounded
    host-side ``HostTextureUploadCache`` on the canvas widget for decoded
    QImage uploads — never an uncapped full-res QImage dict.
    """

    def __init__(self) -> None:
        self.pipeline = None
        self.slot_textures: dict[object, object] = {}
        self.slot_texture_sizes: dict[object, tuple[int, int]] = {}
        self.slot_pixel_sources: dict[int, TiledPixelStore] = {}
        self.slot_vertex_buffers: list[object] = []
        self.slot_uniform_buffers: list[object] = []
        self._tile_srbs: dict[tuple[int, object], tuple[object, object]] = {}
        self.layer_draw_items: list[list[SlotDrawItem]] = []
        self.pending_uploads: list[tuple[int, TiledPixelStore]] = []
        self.pending_removes: list[int] = []

    def has_slot_texture(self, slot_id: int) -> bool:
        return int(slot_id) in self.slot_pixel_sources

    def slot_texture_ids(self) -> list[int]:
        return list(self.slot_pixel_sources)

    def queue_upload(self, slot_id: int, source: TiledPixelStore) -> None:
        self.pending_uploads.append((int(slot_id), source))

    def queue_remove(self, slot_id: int) -> None:
        self.pending_removes.append(int(slot_id))

    def _host_cache(self, renderer):
        return cache_for_host(
            renderer.host,
            budget_bytes=SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES,
        )

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
        for sid, source in self.pending_uploads:
            self._upload_slot(renderer, tile_service, sid, source, updates)
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

    def _release_slot(self, tile_service, sid: int) -> None:
        self.slot_pixel_sources.pop(sid, None)
        tile_service.invalidate_source(sid)
        self._destroy_slot_textures(sid, keep=frozenset())
        self._purge_tile_srbs_for_slot(sid)

    def _upload_slot(
        self, renderer, tile_service, sid: int, source: TiledPixelStore, updates
    ) -> None:
        size = source.size
        grid = tile_service.register_source(sid, size)
        self.slot_pixel_sources[sid] = source
        self._purge_tile_srbs_for_slot(sid)
        host_cache = self._host_cache(renderer)
        if grid.rows == 1 and grid.columns == 1:
            tile_key = tile_service.tile_key(sid, 0, 0)
            self._destroy_slot_textures(sid, keep={tile_key})
            qimage = host_cache.qimage_from_source(source, _slot_host_key(sid))
            self._upload_tile(renderer, tile_key, qimage, updates)
            return
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
        tile_service = renderer.tile_service
        host_cache = self._host_cache(renderer)
        protected_host: set[str] = set()
        protected_by_key: dict[object, set[tuple[int, int]]] = {}
        for layer in ctx.projected_layers:
            sid = int(layer.slot_id)
            protected_host.add(_slot_host_key(sid))
            grid = tile_service.grid_for(sid)
            if grid is None or (grid.rows == 1 and grid.columns == 1):
                continue
            pixel_source = self.slot_pixel_sources.get(sid)
            if pixel_source is None:
                continue
            pan = (layer.pan_x, layer.pan_y)
            fit = (max(layer.fit_x, 1e-6), max(layer.fit_y, 1e-6))
            visible_rect = _visible_slot_image_rect(pan, fit, layer.zoom, grid)
            target = tile_service.resolve_visible_tiles(
                sid, visible_rect, _TILE_RESIDENCY_MARGIN
            )
            protected_by_key[sid] = target
            regions = {(row, col): region for row, col, region in grid.iter_regions()}
            for row, col in target:
                protected_host.add(_slot_tile_host_key(sid, row, col))
                if tile_service.is_resident(sid, (row, col)):
                    tile_service.touch(sid, (row, col))
                    continue
                region = regions.get((row, col))
                if region is None:
                    continue
                cropped = crop_apron_tile(
                    pixel_source,
                    region.left,
                    region.top,
                    region.right,
                    region.bottom,
                    _TILE_APRON_PX,
                )
                tile_key = tile_service.tile_key(sid, row, col)
                tile_image = qimage_from_pixel_source(cropped)
                host_cache.store(_slot_tile_host_key(sid, row, col), tile_image)
                self._upload_tile(renderer, tile_key, tile_image, updates)
                tile_service.mark_resident(
                    sid, (row, col), cropped.width * cropped.height * 4
                )
        evicted = tile_service.evict_over_budget(
            protected_by_key, SLOT_TILE_CACHE_BUDGET_BYTES
        )
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
        host_cache.evict_over_budget(protected_host, SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES)

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
