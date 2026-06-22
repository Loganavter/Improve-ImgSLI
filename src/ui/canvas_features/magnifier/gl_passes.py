"""QRhi feature passes for the magnifier.

Three sub-passes share this module:

* ``OccludedArcPass`` — dashed arcs around capture rings when occluded.
* ``HiddenSelectionPass`` — selection rings for hidden magnifier circles.
* ``MagnifierPass`` — magnifier circle content. Renders disk borders and
  circular GPU-sampled content via an uber shader.

The two arc passes share a single per-primitive arc shader. The magnifier
pass uses a separate border-disk pipeline for the slot frame plus the
uber ``mag`` pipeline for the circle content.

GPU sampling (``magGpuSampling=1``) reuses the canvas base-image QRhi
textures looked up through ``widget._rhi_renderer.textures``. Legacy
raster-overlay entry points remain on ``GLCanvas`` for compatibility,
but the active magnifier runtime does not use them.
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QColor,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
)

from ui.canvas_infra.scene.gl_pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.gl_canvas.render_common import widget_px_to_screen_px
from ui.widgets.gl_canvas.rhi_feature_common import (
    FullscreenUniformPassResources,
    FULLSCREEN_VERTICES,
    load_qshader,
    resolve_rhi_scissor,
)

_log = logging.getLogger("ImproveImgSLI.magnifier")

_SHADER_DIR = Path(__file__).resolve().parent / "shaders" / "qrhi"
_ARC_UNIFORM_SIZE = 112
_BORDER_DISK_UNIFORM_SIZE = 128
_MAG_UNIFORM_SIZE = 256


def _ensure_qcolor(c) -> QColor:
    if isinstance(c, QColor):
        return c
    r = int(getattr(c, "r", 255) if hasattr(c, "r") else getattr(c, "red", lambda: 255)())
    g = int(getattr(c, "g", 255) if hasattr(c, "g") else getattr(c, "green", lambda: 255)())
    b = int(getattr(c, "b", 255) if hasattr(c, "b") else getattr(c, "blue", lambda: 255)())
    a = int(getattr(c, "a", 255) if hasattr(c, "a") else getattr(c, "alpha", lambda: 255)())
    return QColor(r, g, b, a)


def _pack_arc_uniform(
    matrix: tuple[float, ...],
    width: float,
    height: float,
    center_x: float,
    center_y: float,
    radius_px: float,
    line_width_px: float,
    start_angle_deg: float,
    span_angle_deg: float,
    color: QColor,
) -> bytes:
    return struct.pack(
        "<16f 2f 2f 4f 4f",
        *matrix,
        width, height,
        center_x, center_y,
        radius_px, line_width_px, start_angle_deg, span_angle_deg,
        color.redF(), color.greenF(), color.blueF(), color.alphaF(),
    )


class OccludedArcPass(CanvasRenderPass):
    """Draws the occluded arc segments of the capture ring when dragging."""

    stack_role = CanvasStackRole.ANNOTATION_BORDER
    visibility = SceneVisibility.INTERACTIVE

    def __init__(self) -> None:
        self.resources = FullscreenUniformPassResources(_ARC_UNIFORM_SIZE)
        self._items: list[bytes] = []

    @staticmethod
    def _resolve_occluded_capture_arcs(ctx) -> tuple[object, ...]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        arcs = payloads.get("occluded_capture_arcs")
        if arcs:
            return tuple(arcs)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "occluded_capture_arcs", ()) or ())

    def initialize(self, rhi, target) -> None:
        self.resources.initialize(rhi, target, _SHADER_DIR, "arc")

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_occluded_capture_arcs(ctx))

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        line_width_px = max(1.0, float(ctx.resolved_style.annotation_arc_stroke_px))
        for arc in self._resolve_occluded_capture_arcs(ctx):
            if len(arc) < 5:
                continue
            center, radius, start_deg, span_deg, is_active = arc
            if radius is None or radius <= 0 or span_deg is None or span_deg <= 0.25:
                continue
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            scaled_radius = float(radius) * float(ctx.zoom_level)
            color = QColor(255, 105, 170, 255 if bool(is_active) else 210)
            self._items.append(_pack_arc_uniform(
                matrix,
                float(ctx.width), float(ctx.height),
                float(cx), float(cy),
                scaled_radius, line_width_px,
                float(start_deg), float(span_deg),
                color,
            ))
        self.resources.ensure_items(len(self._items))
        self.resources.prepare_vertex_buffer(resource_updates)
        for index, block in enumerate(self._items):
            resource_updates.updateDynamicBuffer(
                self.resources.uniform_buffers[index], 0, block
            )

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        if not self._items:
            return
        command_buffer.setGraphicsPipeline(self.resources.pipeline)
        target_size = widget.renderTarget().pixelSize()
        command_buffer.setViewport(
            QRhiViewport(0.0, 0.0, float(target_size.width()), float(target_size.height()))
        )
        command_buffer.setScissor(
            resolve_rhi_scissor(
                widget,
                self.resources.rhi,
                ctx,
                clip_to_content=bool(getattr(widget.runtime_state, "_clip_overlays_to_content_rect", False)),
            )
        )
        command_buffer.setVertexInput(0, [(self.resources.vertex_buffer, 0)])
        for index in range(len(self._items)):
            command_buffer.setShaderResources(self.resources.srbs[index])
            command_buffer.draw(4)

    def release(self) -> None:
        self.resources.release()
        self._items = []


class HiddenSelectionPass(CanvasRenderPass):
    """Selection rings for hidden capture & magnifier circles."""

    stack_role = CanvasStackRole.DEBUG_VIS
    visibility = SceneVisibility.INTERACTIVE

    def __init__(self) -> None:
        self.resources = FullscreenUniformPassResources(_ARC_UNIFORM_SIZE)
        self._items: list[bytes] = []

    @staticmethod
    def _resolve_hidden_capture_circles(ctx) -> tuple[object, ...]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("hidden_capture_circles")
        if circles:
            return tuple(circles)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "hidden_capture_circles", ()) or ())

    @staticmethod
    def _resolve_hidden_overlay_circles(ctx) -> tuple[object, ...]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("hidden_magnifier_circles")
        if circles:
            return tuple(circles)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "hidden_overlay_circles", ()) or ())

    def initialize(self, rhi, target) -> None:
        self.resources.initialize(rhi, target, _SHADER_DIR, "arc")

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(
            self._resolve_hidden_capture_circles(ctx)
            or self._resolve_hidden_overlay_circles(ctx)
        )

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        stroke_px = max(1.0, float(ctx.resolved_style.annotation_selection_stroke_px))

        def _emit(center, radius, *, active: bool, capture: bool) -> None:
            if center is None or radius is None or radius <= 0:
                return
            scaled_radius = float(radius) * float(ctx.zoom_level)
            if scaled_radius <= 0:
                return
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            color = (
                QColor(255, 105, 170, 255 if active else 210)
                if capture
                else QColor(70, 190, 255, 255 if active else 210)
            )
            self._items.append(_pack_arc_uniform(
                matrix,
                float(ctx.width), float(ctx.height),
                float(cx), float(cy),
                scaled_radius, stroke_px,
                0.0, 360.0,
                color,
            ))

        for center, radius, is_active in self._resolve_hidden_capture_circles(ctx):
            _emit(center, radius, active=bool(is_active), capture=True)
        for center, radius, is_active in self._resolve_hidden_overlay_circles(ctx):
            _emit(center, radius, active=bool(is_active), capture=False)

        self.resources.ensure_items(len(self._items))
        self.resources.prepare_vertex_buffer(resource_updates)
        for index, block in enumerate(self._items):
            resource_updates.updateDynamicBuffer(
                self.resources.uniform_buffers[index], 0, block
            )

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        if not self._items:
            return
        command_buffer.setGraphicsPipeline(self.resources.pipeline)
        target_size = widget.renderTarget().pixelSize()
        command_buffer.setViewport(
            QRhiViewport(0.0, 0.0, float(target_size.width()), float(target_size.height()))
        )
        command_buffer.setVertexInput(0, [(self.resources.vertex_buffer, 0)])
        for index in range(len(self._items)):
            command_buffer.setShaderResources(self.resources.srbs[index])
            command_buffer.draw(4)

    def release(self) -> None:
        self.resources.release()
        self._items = []


class _BorderDiskResources:
    """Per-disk uniform buffer + SRB for the magnifier slot frame."""

    def __init__(self) -> None:
        self.rhi = None
        self.vertex_buffer = None
        self.pipeline = None
        self.uniform_buffers: list[object] = []
        self.srbs: list[object] = []
        self._pipeline_created = False

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi
        self.vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.vertex_buffer.create():
            raise RuntimeError("Failed to create magnifier border-disk vertex buffer")

        self.pipeline = rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    load_qshader(_SHADER_DIR / "border_disk.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    load_qshader(_SHADER_DIR / "border_disk.frag.qsb"),
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        self.pipeline.setTargetBlends([blend])
        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(16)])
        layout.setAttributes(
            [
                QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
                QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
            ]
        )
        self.pipeline.setVertexInputLayout(layout)

    def ensure_items(self, count: int) -> None:
        stage = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        while len(self.uniform_buffers) < count:
            buf = self.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                _BORDER_DISK_UNIFORM_SIZE,
            )
            if not buf.create():
                raise RuntimeError("Failed to create border-disk uniform buffer")
            srb = self.rhi.newShaderResourceBindings()
            srb.setBindings(
                [QRhiShaderResourceBinding.uniformBuffer(0, stage, buf)]
            )
            if not srb.create():
                raise RuntimeError("Failed to create border-disk SRB")
            self.uniform_buffers.append(buf)
            self.srbs.append(srb)
        if not self._pipeline_created and self.srbs:
            self.pipeline.setShaderResourceBindings(self.srbs[0])
            if not self.pipeline.create():
                raise RuntimeError("Failed to create border-disk pipeline")
            self._pipeline_created = True

    def prepare_vertex_buffer(self, updates) -> None:
        updates.updateDynamicBuffer(self.vertex_buffer, 0, FULLSCREEN_VERTICES)

    def release(self) -> None:
        for res in (self.pipeline, *self.srbs, *self.uniform_buffers, self.vertex_buffer):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.rhi = None
        self.vertex_buffer = None
        self.pipeline = None
        self.uniform_buffers = []
        self.srbs = []
        self._pipeline_created = False


def _pack_border_disk_uniform(
    matrix: tuple[float, ...],
    width: float,
    height: float,
    center_x: float,
    center_y: float,
    radius_px: float,
    border_width_px: float,
    color: QColor,
) -> bytes:
    return struct.pack(
        "<16f 2f 2f 4f 4f 4f",
        *matrix,
        width, height,
        center_x, center_y,
        radius_px, border_width_px, 0.0, 0.0,
        color.redF(), color.greenF(), color.blueF(), 1.0,
        0.0, 0.0, 0.0, 0.0,
    )


class MagnifierPass(CanvasRenderPass):
    """Renders magnifier disks: slot frame (border) + circle content.

    The active magnifier path samples canvas textures on the GPU.
    """

    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.rhi = None
        self.border = _BorderDiskResources()
        self._border_items: list[bytes] = []
        self.mag_vertex_buffer = None
        self.mag_uniform_buffers: list[object] = []
        self.mag_srbs: list[object] = []
        self.mag_pipeline = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.placeholder_texture = None
        self._mag_items: list[tuple[bytes, str]] = []
        self._target = None

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi
        self._target = target
        self.border.initialize(rhi, target)

        self.mag_vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.mag_vertex_buffer.create():
            raise RuntimeError("Failed to create magnifier vertex buffer")

        self.sampler_linear = rhi.newSampler(
            QRhiSampler.Filter.Linear, QRhiSampler.Filter.Linear, QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge, QRhiSampler.AddressMode.ClampToEdge,
        )
        self.sampler_linear.create()
        self.sampler_nearest = rhi.newSampler(
            QRhiSampler.Filter.Nearest, QRhiSampler.Filter.Nearest, QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge, QRhiSampler.AddressMode.ClampToEdge,
        )
        self.sampler_nearest.create()

        self.placeholder_texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        self.placeholder_texture.create()

        self.mag_pipeline = rhi.newGraphicsPipeline()
        self.mag_pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    load_qshader(_SHADER_DIR / "mag.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    load_qshader(_SHADER_DIR / "mag.frag.qsb"),
                ),
            ]
        )
        self.mag_pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.mag_pipeline.setSampleCount(target.sampleCount())
        self.mag_pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        self.mag_pipeline.setTargetBlends([blend])
        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(16)])
        layout.setAttributes(
            [
                QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
                QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
            ]
        )
        self.mag_pipeline.setVertexInputLayout(layout)

        first_srb = self._build_mag_srb(self.placeholder_texture, self.placeholder_texture, self.placeholder_texture)
        self.mag_srbs.append(first_srb)
        self.mag_pipeline.setShaderResourceBindings(first_srb)
        if not self.mag_pipeline.create():
            raise RuntimeError("Failed to create magnifier QRhi pipeline")
        # one uniform buffer paired with the first SRB
        first_uniform = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _MAG_UNIFORM_SIZE,
        )
        first_uniform.create()
        self.mag_uniform_buffers.append(first_uniform)
        # rebuild srb[0] with proper uniform buffer
        try:
            first_srb.destroy()
        except RuntimeError:
            pass
        self.mag_srbs[0] = self._build_mag_srb(
            self.placeholder_texture, self.placeholder_texture, self.placeholder_texture,
            uniform=first_uniform,
        )

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
                QRhiShaderResourceBinding.sampledTexture(1, fragment, bg1, self.sampler_linear),
                QRhiShaderResourceBinding.sampledTexture(2, fragment, bg2, self.sampler_linear),
                QRhiShaderResourceBinding.sampledTexture(3, fragment, bg_diff, self.sampler_linear),
                QRhiShaderResourceBinding.sampledTexture(4, fragment, self.placeholder_texture, self.sampler_linear),
                QRhiShaderResourceBinding.sampledTexture(5, fragment, self.placeholder_texture, self.sampler_linear),
                QRhiShaderResourceBinding.sampledTexture(6, fragment, self.placeholder_texture, self.sampler_linear),
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
        matrix = tuple(
            float(v) for v in self.rhi.clipSpaceCorrMatrix().data()
        )
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
        tex_key_1 = (
            ctx.source_texture_ids[0] if use_source else ctx.texture_ids[0]
        )
        tex_key_2 = (
            ctx.source_texture_ids[1] if use_source else ctx.texture_ids[1]
        )
        diff_key = (
            ctx.diff_source_texture_id
            if ctx.diff_source_ready and ctx.diff_source_texture_id
            else "placeholder"
        )
        bg1 = textures_dict.get(tex_key_1, placeholder)
        bg2 = textures_dict.get(tex_key_2, placeholder)
        bg_diff = textures_dict.get(diff_key, placeholder)

        for i, quad in enumerate(overlay.quads):
            if not quad:
                continue
            x0, y0, x1, y1, cx_px, cy_px, r_px = quad
            gpu_slot = overlay.gpu_slots[i] if overlay.gpu_active and i < len(overlay.gpu_slots) else None
            if gpu_slot:
                combined = bool(gpu_slot.get("is_combined", False))
                comb_params = None
            else:
                comb_params = (
                    overlay.combined_params[i]
                    if i < len(overlay.combined_params)
                    else None
                )
                combined = comb_params is not None

            slot_border_width = (
                float(gpu_slot.get("border_width", overlay.border_width))
                if gpu_slot else float(overlay.border_width)
            )
            border_width = max(0.0, slot_border_width)
            content_radius = max(1.0, r_px - border_width + 1.0)

            if border_width > 0.0:
                slot_border_color = (
                    gpu_slot.get("border_color", overlay.border_color)
                    if gpu_slot else overlay.border_color
                )
                bcx, bcy = widget_px_to_screen_px(widget, float(cx_px), float(cy_px))
                self._border_items.append(_pack_border_disk_uniform(
                    matrix,
                    w, h,
                    float(bcx), float(bcy),
                    float(r_px) * zoom,
                    float(border_width) * zoom,
                    _ensure_qcolor(slot_border_color),
                ))

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
                comb_div_thickness = _comb_divider_thickness_uv(gpu_slot, content_radius)
            elif (not gpu_slot) and combined and comb_params:
                internal_split = float(comb_params.get("split", 0.5))
                comb_horizontal = int(comb_params.get("horizontal", False))
                show_comb_divider = int(comb_params.get("divider_visible", True))
                comb_div_color = comb_params.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                comb_div_thickness = _comb_divider_thickness_uv(comb_params, content_radius)
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

            block = struct.pack(
                "<16f 4f 2f 2f f f f f 4f 4f f f i i i i i i i i i i 4f 4f",
                *matrix,
                content_x0, content_y0, content_x1, content_y1,
                pan_x, pan_y,
                0.0, 0.0,
                zoom,
                content_radius,
                0.0,
                internal_split,
                0.0, 0.0, 0.0, 0.0,
                float(comb_div_color[0]), float(comb_div_color[1]),
                float(comb_div_color[2]), float(comb_div_color[3]),
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
                float(uv_rect1[0]), float(uv_rect1[1]), float(uv_rect1[2]), float(uv_rect1[3]),
                float(uv_rect2[0]), float(uv_rect2[1]), float(uv_rect2[2]), float(uv_rect2[3]),
            )
            self._mag_items.append((block, "linear"))

        # ensure resources match item counts
        self.border.ensure_items(len(self._border_items))
        if self._border_items:
            self.border.prepare_vertex_buffer(resource_updates)
            for index, block in enumerate(self._border_items):
                resource_updates.updateDynamicBuffer(
                    self.border.uniform_buffers[index], 0, block
                )

        # ensure mag uniform buffers and SRBs scale to item count
        while len(self.mag_uniform_buffers) < len(self._mag_items):
            buf = self.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                _MAG_UNIFORM_SIZE,
            )
            buf.create()
            self.mag_uniform_buffers.append(buf)
        while len(self.mag_srbs) < len(self._mag_items):
            srb = self._build_mag_srb(
                bg1, bg2, bg_diff,
                uniform=self.mag_uniform_buffers[len(self.mag_srbs)],
            )
            self.mag_srbs.append(srb)
        # always rebuild srbs[0..n] for current bg textures so binding stays fresh
        for index in range(len(self._mag_items)):
            try:
                self.mag_srbs[index].destroy()
            except RuntimeError:
                pass
            self.mag_srbs[index] = self._build_mag_srb(
                bg1, bg2, bg_diff,
                uniform=self.mag_uniform_buffers[index],
            )

        if self._mag_items:
            resource_updates.updateDynamicBuffer(
                self.mag_vertex_buffer, 0, FULLSCREEN_VERTICES
            )
            for index, (block, _filter) in enumerate(self._mag_items):
                resource_updates.updateDynamicBuffer(
                    self.mag_uniform_buffers[index], 0, block
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
            clip_to_content=bool(getattr(widget.runtime_state, "_clip_overlays_to_content_rect", False)),
        )
        if self._border_items:
            command_buffer.setGraphicsPipeline(self.border.pipeline)
            command_buffer.setViewport(viewport)
            command_buffer.setVertexInput(0, [(self.border.vertex_buffer, 0)])
            for index in range(len(self._border_items)):
                command_buffer.setShaderResources(self.border.srbs[index])
                command_buffer.draw(4)

        if self._mag_items:
            command_buffer.setGraphicsPipeline(self.mag_pipeline)
            command_buffer.setViewport(viewport)
            command_buffer.setScissor(scissor)
            command_buffer.setVertexInput(0, [(self.mag_vertex_buffer, 0)])
            for index in range(len(self._mag_items)):
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


def _comb_divider_thickness_uv(params, content_radius: float, fallback: float = 0.005) -> float:
    if not params:
        return 0.0
    dpx = float(params.get("divider_thickness_px", 0.0) or 0.0)
    if dpx <= 0.0:
        return float(params.get("divider_thickness_uv", 0.0) or 0.0)
    diam = max(1.0, content_radius * 2.0)
    return (dpx / diam) * 0.5 if diam > 0.0 else fallback


RENDER_PASSES: list[CanvasRenderPass] = [
    MagnifierPass(),
    OccludedArcPass(),
    HiddenSelectionPass(),
]
GL_RENDER_PASSES = RENDER_PASSES
