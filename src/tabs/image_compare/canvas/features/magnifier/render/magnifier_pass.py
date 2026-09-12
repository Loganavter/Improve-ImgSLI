"""The magnifier's own QRhi render pass: disk border + GPU-sampled content.

Split out of ``passes.py`` — this is the one pass in the magnifier feature
that is not further decomposed: it is a single QRhi pipeline (uber ``mag``
shader) plus its border-disk companion pipeline, and the two are only
separable in the sense that they're two draw loops sharing one pass's
resource lifecycle. Splitting the border/content halves into separate
``CanvasRenderPass`` classes would not reduce complexity, only relocate it
behind an extra resource-lifecycle indirection.

File-Size-Exempt: single QRhi pass, one resource lifecycle (border-disk
pipeline + uber mag pipeline); splitting the class would relocate, not
reduce, complexity — see module docstring above.

GPU sampling (``magGpuSampling=1``) reuses the canvas base-image QRhi
textures looked up through ``widget._rhi_renderer.textures``. Legacy
raster-overlay entry points remain on ``CanvasWidget`` for compatibility,
but the active magnifier runtime does not use them.
"""

from __future__ import annotations

import struct

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiTexture,
    QRhiViewport,
)

from tabs.image_compare.canvas.features.magnifier.render.tile_capture import (
    build_tile_records,
    intersect_widget_rects,
    is_full_tc,
    tc_rect_to_widget_px,
    tile_uv_slices,
)
from tabs.image_compare.canvas.rhi_feature_common import (
    FULLSCREEN_VERTICES,
    FullscreenUniformPassResources,
    build_fullscreen_quad_pipeline,
    content_clip_rect_widget_px,
    resolve_rhi_scissor,
    scissor_from_widget_rect,
)
from tabs.image_compare.canvas.rhi_renderer import _TILE_APRON_PX, _apron_rect
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.canvas.render_common import widget_px_to_screen_px

from tabs.image_compare.canvas.features.magnifier.render.passes_common import ensure_qcolor, pack_border_disk_uniform
from tabs.image_compare.canvas.features.magnifier.render.shader_layout import BORDER_DISK_UNIFORM_SIZE, MAG_UNIFORM_SIZE, SHADER_DIR


def _source_slices(renderer, source_key, uv_rect):
    """Tile-aware uv_rect slicing for one magnifier source (see tile_capture.py)."""
    tile_service = getattr(renderer, "tile_service", None) if renderer is not None else None
    grid = tile_service.grid_for(source_key) if tile_service is not None else None
    return tile_uv_slices(
        grid,
        tile_service.tile_key if tile_service is not None else None,
        source_key,
        uv_rect,
        apron_px=_TILE_APRON_PX,
        apron_rect_fn=_apron_rect,
        visible_tiles_fn=(
            (lambda rect: tile_service.visible_tiles(source_key, rect))
            if tile_service is not None
            else None
        ),
    )


def _comb_divider_thickness_uv(
    params, content_radius: float, fallback: float = 0.005
) -> float:
    if not params:
        return 0.0
    dpx = float(params.get("divider_thickness_px", 0.0) or 0.0)
    if dpx <= 0.0:
        return float(params.get("divider_thickness_uv", 0.0) or 0.0)
    diam = max(1.0, content_radius * 2.0)
    return (dpx / diam) * 0.5 if diam > 0.0 else fallback


class MagnifierPass(CanvasRenderPass):
    """Renders magnifier disks: slot frame (border) + circle content.

    The active magnifier path samples canvas textures on the GPU.
    """

    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.rhi = None
        self.border = FullscreenUniformPassResources(BORDER_DISK_UNIFORM_SIZE)
        self._border_items: list[bytes] = []
        self.mag_vertex_buffer = None
        self.mag_uniform_buffers: list[object] = []
        self.mag_srbs: list[object] = []
        self.mag_pipeline = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.placeholder_texture = None
        self._mag_items: list[dict] = []
        self._target = None

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi
        self._target = target
        self.border.initialize(rhi, target, SHADER_DIR, "border_disk")

        self.mag_vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.mag_vertex_buffer.create():
            raise RuntimeError("Failed to create magnifier vertex buffer")

        self.sampler_linear = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        self.sampler_linear.create()
        self.sampler_nearest = rhi.newSampler(
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        self.sampler_nearest.create()

        self.placeholder_texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        self.placeholder_texture.create()

        self.mag_pipeline = build_fullscreen_quad_pipeline(
            rhi, target, SHADER_DIR, "mag"
        )

        first_uniform = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            MAG_UNIFORM_SIZE,
        )
        first_uniform.create()
        self.mag_uniform_buffers.append(first_uniform)

        first_srb = self._build_mag_srb(
            self.placeholder_texture,
            self.placeholder_texture,
            self.placeholder_texture,
            uniform=first_uniform,
        )
        self.mag_srbs.append(first_srb)
        self.mag_pipeline.setShaderResourceBindings(first_srb)
        if not self.mag_pipeline.create():
            raise RuntimeError("Failed to create magnifier QRhi pipeline")

    def _build_mag_srb(self, bg1, bg2, bg_diff, *, uniform=None):
        if uniform is None:
            uniform = self.mag_uniform_buffers[0] if self.mag_uniform_buffers else None
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        bindings = []
        if uniform is not None:
            bindings.append(QRhiShaderResourceBinding.uniformBuffer(0, stages, uniform))
        bindings.extend(
            [
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, bg1, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    2, fragment, bg2, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    3, fragment, bg_diff, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    4, fragment, self.placeholder_texture, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    5, fragment, self.placeholder_texture, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    6, fragment, self.placeholder_texture, self.sampler_linear
                ),
            ]
        )
        srb.setBindings(bindings)
        if not srb.create():
            raise RuntimeError("Failed to create magnifier SRB")
        return srb

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None or not bool(getattr(overlay, "render_enabled", False)):
            return False
        return bool(getattr(overlay, "quads", ()))

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._border_items = []
        self._mag_items = []
        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None:
            return
        matrix = tuple(float(v) for v in self.rhi.clipSpaceCorrMatrix().data())
        w, h = float(ctx.width), float(ctx.height)
        zoom = float(ctx.zoom_level or 1.0)
        pan_x = float(ctx.pan_offset_x or 0.0)
        pan_y = float(ctx.pan_offset_y or 0.0)

        rhi_renderer = getattr(widget, "_rhi_renderer", None)
        textures_dict = getattr(rhi_renderer, "textures", {}) if rhi_renderer else {}
        placeholder = textures_dict.get("placeholder", self.placeholder_texture)
        use_source = bool(
            overlay.gpu_active
            and ctx.shader_letterbox_mode
            and ctx.source_images_ready
            and ctx.source_texture_ids[0]
            and ctx.source_texture_ids[1]
        )
        tex_key_1 = ctx.source_texture_ids[0] if use_source else ctx.texture_ids[0]
        tex_key_2 = ctx.source_texture_ids[1] if use_source else ctx.texture_ids[1]
        diff_key = (
            ctx.diff_source_texture_id
            if ctx.diff_source_ready and ctx.diff_source_texture_id
            else "placeholder"
        )
        def _resolve_tex(key):
            return textures_dict.get(key, placeholder) if key else placeholder

        for i, quad in enumerate(overlay.quads):
            if not quad:
                continue
            x0, y0, x1, y1, cx_px, cy_px, r_px = quad
            gpu_slot = (
                overlay.gpu_slots[i]
                if overlay.gpu_active and i < len(overlay.gpu_slots)
                else None
            )
            combined = bool(gpu_slot.get("is_combined", False)) if gpu_slot else False

            slot_border_width = (
                float(gpu_slot.get("border_width", overlay.border_width))
                if gpu_slot
                else float(overlay.border_width)
            )
            border_width = max(0.0, slot_border_width)
            content_radius = max(1.0, r_px - border_width + 1.0)

            if border_width > 0.0:
                slot_border_color = (
                    gpu_slot.get("border_color", overlay.border_color)
                    if gpu_slot
                    else overlay.border_color
                )
                bcx, bcy = widget_px_to_screen_px(widget, float(cx_px), float(cy_px))
                self._border_items.append(
                    pack_border_disk_uniform(
                        matrix,
                        w,
                        h,
                        float(bcx),
                        float(bcy),
                        float(r_px) * zoom,
                        float(border_width) * zoom,
                        ensure_qcolor(slot_border_color),
                    )
                )

            if gpu_slot:
                gpu_sampling = 1
                source_mode = int(gpu_slot.get("source", 0) or 0)
                interp_mode = (
                    int(getattr(overlay, "gpu_interp_mode", 1))
                    if getattr(overlay, "gpu_interp_mode", None) is not None
                    else 1
                )
                channel_mode = int(getattr(overlay, "gpu_channel_mode", 0) or 0)
                diff_mode = (
                    int(getattr(overlay, "gpu_diff_mode", 0) or 0)
                    if source_mode == 2 and not combined
                    else 0
                )
                uv_rect1 = gpu_slot.get("uv_rect", (0.0, 0.0, 1.0, 1.0))
                uv_rect2 = gpu_slot.get("uv_rect2", uv_rect1)
            else:
                gpu_sampling = 0
                source_mode = 0
                interp_mode = 1
                channel_mode = 0
                diff_mode = 0
                uv_rect1 = (0.0, 0.0, 1.0, 1.0)
                uv_rect2 = (0.0, 0.0, 1.0, 1.0)

            if gpu_slot and combined:
                internal_split = float(gpu_slot.get("internal_split", 0.5))
                comb_horizontal = int(gpu_slot.get("horizontal", False))
                show_comb_divider = int(gpu_slot.get("divider_visible", True))
                comb_div_color = gpu_slot.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                comb_div_thickness = _comb_divider_thickness_uv(
                    gpu_slot, content_radius
                )
            else:
                internal_split = 0.5
                comb_horizontal = 0
                show_comb_divider = 0
                comb_div_color = (1.0, 1.0, 1.0, 0.9)
                comb_div_thickness = 0.0

            content_x0 = ((cx_px - content_radius) / w) * 2.0 - 1.0
            content_x1 = ((cx_px + content_radius) / w) * 2.0 - 1.0
            content_y1 = 1.0 - (((cy_px - content_radius) / h) * 2.0)
            content_y0 = 1.0 - (((cy_px + content_radius) / h) * 2.0)

            if gpu_slot:
                records = build_tile_records(
                    source_slices_fn=lambda key, rect: _source_slices(
                        rhi_renderer, key, rect
                    ),
                    combined=combined,
                    source_mode=source_mode,
                    diff_mode=diff_mode,
                    uv_rect1=uv_rect1,
                    uv_rect2=uv_rect2,
                    tex_key_1=tex_key_1,
                    tex_key_2=tex_key_2,
                    diff_key=diff_key,
                    internal_split=internal_split,
                    comb_horizontal=bool(comb_horizontal),
                )
            else:
                records = [
                    {
                        "tc_x": (0.0, 1.0),
                        "tc_y": (0.0, 1.0),
                        "uv_rect1": uv_rect1,
                        "uv_rect2": uv_rect2,
                        "tex1_key": tex_key_1,
                        "tex2_key": tex_key_2,
                        "texd_key": diff_key,
                    }
                ]
            if not records:
                continue

            for record in records:
                rec_uv1 = record["uv_rect1"]
                rec_uv2 = record["uv_rect2"]
                block = struct.pack(
                    "<16f 4f 2f 2f f f f f 4f 4f f f i i i i i i i i i i 4f 4f",
                    *matrix,
                    content_x0,
                    content_y0,
                    content_x1,
                    content_y1,
                    pan_x,
                    pan_y,
                    0.0,
                    0.0,
                    zoom,
                    content_radius,
                    0.0,
                    internal_split,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    float(comb_div_color[0]),
                    float(comb_div_color[1]),
                    float(comb_div_color[2]),
                    float(comb_div_color[3]),
                    float(comb_div_thickness),
                    float(getattr(overlay, "gpu_diff_threshold", 20.0 / 255.0) or 0.0),
                    int(comb_horizontal),
                    int(show_comb_divider),
                    1,
                    int(gpu_sampling),
                    int(combined),
                    int(source_mode),
                    int(diff_mode),
                    int(channel_mode),
                    int(interp_mode),
                    0,
                    float(rec_uv1[0]),
                    float(rec_uv1[1]),
                    float(rec_uv1[2]),
                    float(rec_uv1[3]),
                    float(rec_uv2[0]),
                    float(rec_uv2[1]),
                    float(rec_uv2[2]),
                    float(rec_uv2[3]),
                )
                scissor_px = (
                    None
                    if is_full_tc(record["tc_x"], record["tc_y"])
                    else tc_rect_to_widget_px(
                        float(cx_px),
                        float(cy_px),
                        content_radius,
                        record["tc_x"],
                        record["tc_y"],
                    )
                )
                self._mag_items.append(
                    {
                        "block": block,
                        "tex1": _resolve_tex(record["tex1_key"]),
                        "tex2": _resolve_tex(record["tex2_key"]),
                        "tex_diff": _resolve_tex(record["texd_key"]),
                        "scissor_px": scissor_px,
                    }
                )

        self.border.ensure_items(len(self._border_items))
        if self._border_items:
            self.border.prepare_vertex_buffer(resource_updates)
            for index, block in enumerate(self._border_items):
                resource_updates.updateDynamicBuffer(
                    self.border.uniform_buffers[index], 0, block
                )

        while len(self.mag_uniform_buffers) < len(self._mag_items):
            buf = self.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                MAG_UNIFORM_SIZE,
            )
            buf.create()
            self.mag_uniform_buffers.append(buf)
        while len(self.mag_srbs) < len(self._mag_items):
            self.mag_srbs.append(None)

        # SRBs are rebuilt every frame regardless (bound textures can change
        # frame to frame), so a newly grown slot is built once here, not
        # once on growth and again immediately below.
        for index, item in enumerate(self._mag_items):
            if self.mag_srbs[index] is not None:
                try:
                    self.mag_srbs[index].destroy()
                except RuntimeError:
                    pass
            self.mag_srbs[index] = self._build_mag_srb(
                item["tex1"],
                item["tex2"],
                item["tex_diff"],
                uniform=self.mag_uniform_buffers[index],
            )

        if self._mag_items:
            resource_updates.updateDynamicBuffer(
                self.mag_vertex_buffer, 0, FULLSCREEN_VERTICES
            )
            for index, item in enumerate(self._mag_items):
                resource_updates.updateDynamicBuffer(
                    self.mag_uniform_buffers[index], 0, item["block"]
                )

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        target_size = widget.renderTarget().pixelSize()
        viewport = QRhiViewport(
            0.0, 0.0, float(target_size.width()), float(target_size.height())
        )
        scissor = resolve_rhi_scissor(
            widget,
            self.rhi,
            ctx,
            clip_to_content=bool(
                getattr(widget.runtime_state, "_clip_overlays_to_content_rect", False)
            ),
        )
        if self._border_items:
            command_buffer.setGraphicsPipeline(self.border.pipeline)
            command_buffer.setViewport(viewport)
            command_buffer.setScissor(scissor)
            command_buffer.setVertexInput(0, [(self.border.vertex_buffer, 0)])
            for index in range(len(self._border_items)):
                command_buffer.setShaderResources(self.border.srbs[index])
                command_buffer.draw(4)

        if self._mag_items:
            clip_to_content = bool(
                getattr(widget.runtime_state, "_clip_overlays_to_content_rect", False)
            )
            content_clip_widget_px = content_clip_rect_widget_px(
                widget, ctx, clip_to_content=clip_to_content
            )
            command_buffer.setGraphicsPipeline(self.mag_pipeline)
            command_buffer.setViewport(viewport)
            command_buffer.setVertexInput(0, [(self.mag_vertex_buffer, 0)])
            for index, item in enumerate(self._mag_items):
                item_scissor = scissor
                scissor_px = item["scissor_px"]
                if scissor_px is not None:
                    clipped = intersect_widget_rects(scissor_px, content_clip_widget_px)
                    if clipped[2] <= 0.0 or clipped[3] <= 0.0:
                        continue
                    item_scissor = scissor_from_widget_rect(
                        widget, self.rhi, ctx, *clipped
                    )
                command_buffer.setScissor(item_scissor)
                command_buffer.setShaderResources(self.mag_srbs[index])
                command_buffer.draw(4)

    def release(self) -> None:
        self.border.release()
        for res in (
            self.mag_pipeline,
            *self.mag_srbs,
            *self.mag_uniform_buffers,
            self.mag_vertex_buffer,
            self.sampler_linear,
            self.sampler_nearest,
            self.placeholder_texture,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.mag_pipeline = None
        self.mag_srbs = []
        self.mag_uniform_buffers = []
        self.mag_vertex_buffer = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.placeholder_texture = None
        self.rhi = None
        self._target = None
        self._border_items = []
        self._mag_items = []
