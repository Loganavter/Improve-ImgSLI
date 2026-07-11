from __future__ import annotations

import logging

from PySide6.QtGui import QRhiCommandBuffer, QRhiDepthStencilClearValue, QRhiViewport

from ui.widgets.canvas.rhi_backend import query_max_texture_size
from ui.widgets.canvas.render_common import should_render_blank_white
from ui.widgets.canvas.render_executor import iter_active_render_passes
from ..render_context import build_render_runtime_context
from ..texture_parts.tile_geometry import (
    _apron_rect,
    _TILE_APRON_PX,
    _tile_indices_with_margin,
    _viewport_zoom_offset_for_tile,
    _visible_side_image_rect,
)
from ..texture_parts.tile_texture_service import TileTextureService
from ._debug import rhi_render_debug
from .draw_plan import build_draw_plan
from .resources import _LIVE_TILE_EXTENT, _TILE_CACHE_BUDGET_BYTES, RhiResources
from .uniforms import pack_base_uniforms

logger = logging.getLogger("ImproveImgSLI")

__all__ = [
    "RhiCanvasRenderer",
    "pack_base_uniforms",
    "_apron_rect",
    "_TILE_APRON_PX",
    "_TILE_CACHE_BUDGET_BYTES",
    "_tile_indices_with_margin",
    "_viewport_zoom_offset_for_tile",
    "_visible_side_image_rect",
]


class RhiCanvasRenderer:
    """Composition root: constructs/tears down ``RhiResources`` +
    ``TileTextureService`` + feature passes, and sequences each frame's
    render(). Every line here is sequencing, not logic -- decisions
    (residency, eviction, geometry, uniform layout, SRB caching) live in
    exactly one of ``RhiResources``/``TileTextureService``/``draw_plan``/
    ``uniforms``, never partially here. See docs/dev/RHI_RENDERER_REFACTOR.md.
    """

    def __init__(self) -> None:
        self.rhi = None
        self.resources = RhiResources()
        self.tile_service = TileTextureService()
        self.feature_passes: list[object] = []

    # -- backward-compatible views onto RhiResources' GPU state, used by
    # feature passes (e.g. magnifier) that read tile textures directly. --
    @property
    def textures(self) -> dict[object, object]:
        return self.resources.textures

    @property
    def texture_sizes(self) -> dict[object, object]:
        return self.resources.texture_sizes

    def initialize(self, widget, command_buffer: QRhiCommandBuffer) -> None:
        self.release()
        self.rhi = widget.rhi()
        if self.rhi is None:
            raise RuntimeError("QRhiWidget.initialize called without QRhi")
        # docs/dev/TILED_RENDERING_DESIGN.md Phase 2: fixed tile size
        # (_LIVE_TILE_EXTENT), clamped by the backend's real max texture size
        # as a defensive floor only — real backends support far more than
        # 2048px, so this clamp should never actually bind in practice.
        self.tile_service = TileTextureService(
            max_tile_extent=min(_LIVE_TILE_EXTENT, query_max_texture_size(self.rhi))
        )
        self.resources.initialize(self.rhi, widget, command_buffer)

        from tabs.image_compare.canvas.registry import registry

        self.feature_passes = [
            type(render_pass)() for render_pass in registry().get_render_passes()
        ]
        target = widget.renderTarget()
        rhi_render_debug(
            "initialize widget=%s size=%dx%d target_px=%s api=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target.pixelSize() if target is not None else None,
            getattr(widget.api(), "name", "unknown"),
        )
        for render_pass in self.feature_passes:
            render_pass.initialize(self.rhi, target)
        self.resources.restore_texture_uploads(widget)

    def release(self) -> None:
        self.resources.release()
        for render_pass in self.feature_passes:
            render_pass.release()
        self.__init__()

    def render(self, widget, command_buffer, clear_color) -> None:
        target = widget.renderTarget()
        if target is None or self.rhi is None:
            rhi_render_debug(
                "render skip widget=%s target=%r rhi=%r",
                f"{type(widget).__name__}@{id(widget):x}",
                target,
                self.rhi,
            )
            return
        self.resources.ensure_pipeline(widget)

        updates = self.rhi.nextResourceUpdateBatch()
        self.resources.apply_pending_uploads(widget, self.tile_service, updates)
        ctx = build_render_runtime_context(widget)
        base_image = getattr(ctx.render_list, "base_image", None)
        should_draw = (
            base_image is not None
            and any(ctx.images_uploaded)
            and not should_render_blank_white(ctx.scene_frame)
        )
        target_size = target.pixelSize()
        rhi_render_debug(
            "render begin widget=%s widget=%dx%d target_px=%dx%d clear=rgba(%d,%d,%d,%d) "
            "images=%s should_draw=%s passes=%d fixed=%dx%d",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target_size.width(),
            target_size.height(),
            clear_color.red(),
            clear_color.green(),
            clear_color.blue(),
            clear_color.alpha(),
            list(ctx.images_uploaded),
            should_draw,
            len(self.feature_passes),
            widget.fixedColorBufferSize().width(),
            widget.fixedColorBufferSize().height(),
        )

        # Phase 3 (docs/dev/TILED_RENDERING_DESIGN.md): resolves to exactly
        # (base_image.zoom, base_image.zoom)/(pan_x, pan_y) — a no-op — when
        # ctx.canvas_* equals widget.width()/height()/0/0 (every render
        # outside tiled export). Safe to always compute and pass through.
        viewport_zoom, viewport_offset = _viewport_zoom_offset_for_tile(
            ctx.canvas_width,
            ctx.canvas_height,
            (
                ctx.canvas_offset_x,
                ctx.canvas_offset_y,
                ctx.canvas_offset_x + widget.width(),
                ctx.canvas_offset_y + widget.height(),
            ),
            base_zoom=(base_image.zoom, base_image.zoom) if base_image else (1.0, 1.0),
            base_offset=(
                (base_image.pan_offset_x, base_image.pan_offset_y)
                if base_image
                else (0.0, 0.0)
            ),
        )

        draw_plan: list = []
        if should_draw:
            texture_keys = (
                tuple(ctx.source_texture_ids)
                if base_image.use_hires
                else tuple(ctx.texture_ids)
            )
            diff_source_key = (
                ctx.diff_source_texture_id if ctx.diff_source_ready else None
            )
            sampler_name = (
                "nearest"
                if str(ctx.scene_frame.zoom_interpolation_method).upper() == "NEAREST"
                else "linear"
            )
            self.resources.realize_tile_plan(
                self.tile_service,
                widget,
                texture_keys,
                base_image,
                updates,
                diff_key=diff_source_key,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
            )
            draw_plan = build_draw_plan(
                self.tile_service,
                texture_keys,
                base_image,
                diff_key=diff_source_key,
                sampler_name=sampler_name,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
            )
            rhi_render_debug("render draw_plan=%d entries", len(draw_plan))
        active_feature_passes = iter_active_render_passes(ctx, self.feature_passes)
        for render_pass in active_feature_passes:
            render_pass.prepare(widget, ctx, updates)

        command_buffer.beginPass(
            target,
            clear_color,
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )
        if draw_plan:
            size = target.pixelSize()
            command_buffer.setGraphicsPipeline(self.resources.pipeline)
            command_buffer.setViewport(
                QRhiViewport(0.0, 0.0, float(size.width()), float(size.height()))
            )
            command_buffer.setVertexInput(0, [(self.resources.vertex_buffer, 0)])
            # Phase 1/2 (docs/dev/TILED_RENDERING_DESIGN.md): one draw call
            # per visible (image1 tile, image2 tile) pair — only the tiles
            # the current viewport actually needs (Phase 2), not the whole
            # grid. Each pair carries its own tileRect1/tileRect2 in
            # per-side normalized-image space, so the uniform buffer is
            # repacked and pushed via a mid-pass resourceUpdate() before
            # every draw call. Images that fit within one _LIVE_TILE_EXTENT
            # tile (the common case) run this loop exactly once with
            # tileRect == (0,0,1,1), unchanged from pre-tiling behavior.
            for item in draw_plan:
                srb = self.resources.ensure_srb_for(
                    (item.key1, item.key2, item.diff_key), item.sampler_name
                )
                command_buffer.setShaderResources(srb)
                tile_updates = self.rhi.nextResourceUpdateBatch()
                tile_updates.updateDynamicBuffer(
                    self.resources.uniform_buffer,
                    0,
                    pack_base_uniforms(
                        self.rhi,
                        base_image,
                        diff_source_ready=ctx.diff_source_ready,
                        tile_rect1=item.rect1,
                        tile_rect2=item.rect2,
                        viewport_zoom=viewport_zoom,
                        viewport_offset=viewport_offset,
                    ),
                )
                command_buffer.resourceUpdate(tile_updates)
                command_buffer.draw(4)
        for render_pass in active_feature_passes:
            render_pass.record(command_buffer, widget, ctx)
        command_buffer.endPass()
        rhi_render_debug(
            "render end widget=%s target_px=%dx%d should_draw=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            target_size.width(),
            target_size.height(),
            should_draw,
        )
