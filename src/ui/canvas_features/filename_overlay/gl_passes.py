from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPen,
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

from ui.canvas_features.filename_overlay.labels import (
    draw_round_rect,
    draw_text_bold_supersampled,
    fit_text,
    font_for_style,
    label_rects,
    limit_name,
    qcolor,
    snap_rect_to_pixels,
)
from ui.canvas_infra.scene.gl_pass_contract import CanvasRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.canvas_presentation.render_arch import FilenameOverlayStyle
from ui.widgets.gl_canvas.render_common import new_overlay_image
from ui.widgets.gl_canvas.rhi_feature_common import load_qshader

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_SIZE = 64
_VERTEX_STRIDE = 16
_VERTEX_BUFFER_SIZE = _VERTEX_STRIDE * 4


class _LabelSlot:
    def __init__(self) -> None:
        self.vertex_buffer = None
        self.texture = None
        self.texture_size: QSize | None = None
        self.srb_nearest = None
        self.srb_linear = None
        self.content_key: object = None
        self.active: bool = False
        self.smooth: bool = False
        self.vertices: bytes | None = None

    def release(self) -> None:
        for res in (self.srb_nearest, self.srb_linear, self.texture, self.vertex_buffer):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.vertex_buffer = None
        self.texture = None
        self.texture_size = None
        self.srb_nearest = None
        self.srb_linear = None
        self.content_key = None
        self.active = False
        self.vertices = None


class FilenameOverlayPass(CanvasRenderPass):
    """Renders filename labels as screen-positioned textured quads."""

    stack_role = CanvasStackRole.HUD_LABEL
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.rhi = None
        self.uniform_buffer = None
        self.sampler_nearest = None
        self.sampler_linear = None
        self.pipeline = None
        self._slots: list[_LabelSlot] = [_LabelSlot(), _LabelSlot()]

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi

        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_SIZE,
        )
        if not self.uniform_buffer.create():
            raise RuntimeError("Failed to create filename_overlay uniform buffer")

        self.sampler_nearest = rhi.newSampler(
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler_nearest.create():
            raise RuntimeError("Failed to create filename_overlay nearest sampler")

        self.sampler_linear = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler_linear.create():
            raise RuntimeError("Failed to create filename_overlay linear sampler")

        for slot in self._slots:
            slot.vertex_buffer = rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.VertexBuffer,
                _VERTEX_BUFFER_SIZE,
            )
            if not slot.vertex_buffer.create():
                raise RuntimeError("Failed to create filename_overlay vertex buffer")
            slot.texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
            if not slot.texture.create():
                raise RuntimeError("Failed to create filename_overlay placeholder texture")
            slot.texture_size = QSize(1, 1)
            slot.srb_nearest = self._build_srb(slot.texture, self.sampler_nearest)
            slot.srb_linear = self._build_srb(slot.texture, self.sampler_linear)

        self.pipeline = rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    load_qshader(_SHADER_DIR / "filename_overlay.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    load_qshader(_SHADER_DIR / "filename_overlay.frag.qsb"),
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setShaderResourceBindings(self._slots[0].srb_linear)
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())

        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        self.pipeline.setTargetBlends([blend])

        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(_VERTEX_STRIDE)])
        layout.setAttributes(
            [
                QRhiVertexInputAttribute(
                    0, 0, QRhiVertexInputAttribute.Format.Float2, 0
                ),
                QRhiVertexInputAttribute(
                    0, 1, QRhiVertexInputAttribute.Format.Float2, 8
                ),
            ]
        )
        self.pipeline.setVertexInputLayout(layout)
        if not self.pipeline.create():
            raise RuntimeError("Failed to create filename_overlay QRhi pipeline")

    def _build_srb(self, texture, sampler):
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(1, fragment, texture, sampler),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create filename_overlay SRB")
        return srb

    def _ensure_slot_texture(self, slot: _LabelSlot, size: QSize) -> None:
        if slot.texture_size == size:
            return
        if slot.texture is not None:
            try:
                slot.texture.destroy()
            except RuntimeError:
                pass
        slot.texture = self.rhi.newTexture(QRhiTexture.Format.RGBA8, size)
        if not slot.texture.create():
            raise RuntimeError("Failed to resize filename_overlay texture")
        slot.texture_size = size
        for srb_attr, sampler in (
            ("srb_nearest", self.sampler_nearest),
            ("srb_linear", self.sampler_linear),
        ):
            srb = getattr(slot, srb_attr)
            if srb is not None:
                try:
                    srb.destroy()
                except RuntimeError:
                    pass
            setattr(slot, srb_attr, self._build_srb(slot.texture, sampler))

    def should_paint(self, ctx) -> bool:
        cfg = (
            ctx.scene_frame.feature_payloads.get("filename_overlay")
            if isinstance(ctx.scene_frame.feature_payloads, dict)
            else None
        )
        if cfg is None:
            return False
        single_preview = int(getattr(ctx.scene_frame, "single_image_preview", 0) or 0)
        if not bool(getattr(cfg, "enabled", False)) and single_preview == 0:
            return False
        images_uploaded = list(getattr(ctx, "images_uploaded", ()) or ())
        has_slot1 = bool(images_uploaded[0]) if len(images_uploaded) > 0 else False
        has_slot2 = bool(images_uploaded[1]) if len(images_uploaded) > 1 else False
        raw_name1 = str(getattr(cfg, "name1", "") or "").strip()
        raw_name2 = str(getattr(cfg, "name2", "") or "").strip()
        if single_preview == 1:
            if not has_slot1 or not raw_name1:
                return False
        elif single_preview == 2:
            if not has_slot2 or not raw_name2:
                return False
        else:
            if not (has_slot1 and has_slot2):
                return False
            if not (raw_name1 or raw_name2):
                return False
        render_mode = str(
            getattr(getattr(ctx, "render_metrics", None), "mode", "") or ""
        )
        zoom = float(getattr(ctx, "zoom_level", 1.0) or 1.0)
        if render_mode == "interactive" and single_preview == 0 and zoom > 1.0 + 1e-6:
            return False
        return ctx.width > 0 and ctx.height > 0

    def prepare(self, widget, ctx, resource_updates) -> None:
        for slot in self._slots:
            slot.active = False
            slot.vertices = None

        cfg = (
            ctx.scene_frame.feature_payloads.get("filename_overlay")
            if isinstance(ctx.scene_frame.feature_payloads, dict)
            else None
        )
        if cfg is None:
            return

        content_rect = ctx.scene_frame.image_rect_px
        if content_rect is None or content_rect[2] <= 0 or content_rect[3] <= 0:
            return

        split_override = ctx.scene_frame.split_override
        zoom = float(getattr(ctx, "zoom_level", 1.0) or 1.0)
        pan_x = float(getattr(ctx, "pan_offset_x", 0.0) or 0.0)
        pan_y = float(getattr(ctx, "pan_offset_y", 0.0) or 0.0)
        single_preview = int(getattr(ctx.scene_frame, "single_image_preview", 0) or 0)
        render_mode = str(
            getattr(getattr(ctx, "render_metrics", None), "mode", "") or ""
        )
        is_interactive_live = render_mode == "interactive"
        image_anchored = not (single_preview != 0 and is_interactive_live)
        apply_transform = image_anchored and (
            abs(zoom - 1.0) > 1e-6 or abs(pan_x) > 1e-9 or abs(pan_y) > 1e-9
        )
        wcx = ctx.width / 2.0
        wcy = ctx.height / 2.0

        def _to_screen_rect(r: QRectF) -> QRectF:
            if not apply_transform:
                return r
            left = wcx + (r.left() - wcx) * zoom + pan_x * float(ctx.width)
            top = wcy + (r.top() - wcy) * zoom + pan_y * float(ctx.height)
            return QRectF(left, top, r.width() * zoom, r.height() * zoom)

        name1 = str(getattr(cfg, "name1", "") or "")
        name2 = str(getattr(cfg, "name2", "") or "")
        divider_thickness_px = float(
            (
                ctx.scene_frame.feature_payloads.get("filename_divider_thickness", 0)
                if isinstance(ctx.scene_frame.feature_payloads, dict)
                else 0
            )
            or 0
        )
        max_name_length = int(getattr(cfg, "max_name_length", 50))
        if single_preview == 1:
            name1 = limit_name(name1, max_name_length)
            name2 = ""
            split_override = 1.0
        elif single_preview == 2:
            name1 = ""
            name2 = limit_name(name2, max_name_length)
            split_override = 0.0
        else:
            name1 = limit_name(name1, max_name_length)
            name2 = limit_name(name2, max_name_length)

        overlay_style = ctx.resolved_style.filename_overlay
        font = font_for_style(widget, overlay_style)
        font_metrics = QFontMetrics(font)
        rect1, rect2 = label_rects(
            cfg,
            content_rect,
            font_metrics,
            name1,
            name2,
            overlay_style,
            split_override,
            divider_thickness_wx=divider_thickness_px,
        )
        rect1 = snap_rect_to_pixels(rect1)
        rect2 = snap_rect_to_pixels(rect2)

        text_color = qcolor(getattr(cfg, "file_name_color", None), QColor(255, 0, 0, 255))
        raw_alpha = max(0, min(255, int(text_color.alpha() * overlay_style.text_alpha)))
        text_color.setAlpha(raw_alpha)
        bg_color = qcolor(getattr(cfg, "file_name_bg_color", None), QColor(0, 0, 0, 80))
        bg_color.setAlpha(
            max(0, min(255, int(bg_color.alpha() * overlay_style.text_alpha)))
        )
        draw_bg = bool(getattr(cfg, "draw_text_background", True))
        font_weight = int(getattr(cfg, "font_weight", 0) or 0)
        font_key = (
            int(overlay_style.font_pixel_size),
            font_weight,
            text_color.rgba(),
            bg_color.rgba(),
            draw_bg,
        )

        matrix = struct.pack(
            "<16f", *tuple(float(v) for v in self.rhi.clipSpaceCorrMatrix().data())
        )
        resource_updates.updateDynamicBuffer(self.uniform_buffer, 0, matrix)

        for i, (name, rect) in enumerate([(name1, rect1), (name2, rect2)]):
            slot = self._slots[i]
            if not name or rect is None:
                slot.content_key = None
                continue
            rw = max(1, int(rect.width()))
            rh = max(1, int(rect.height()))
            dpr = max(1.0, float(widget.devicePixelRatioF()))
            cache_key = (name, rw, rh, font_key, round(dpr, 3))

            if slot.content_key != cache_key:
                image = self._rasterize_label(
                    name,
                    rw,
                    rh,
                    font,
                    font_metrics,
                    text_color,
                    bg_color,
                    draw_bg,
                    overlay_style,
                    font_weight,
                    dpr,
                )
                phys_size = image.size()
                self._ensure_slot_texture(slot, phys_size)
                resource_updates.uploadTexture(slot.texture, image)
                slot.content_key = cache_key

            screen_rect = _to_screen_rect(rect)
            vertices = self._build_quad_vertices(ctx, screen_rect)
            resource_updates.updateDynamicBuffer(slot.vertex_buffer, 0, vertices)
            slot.vertices = vertices
            slot.smooth = bool(apply_transform)
            slot.active = True

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        if self.pipeline is None:
            return
        dpr = max(1.0, float(widget.devicePixelRatioF()))
        fb_width = float(int(ctx.width) * dpr)
        fb_height = float(int(ctx.height) * dpr)
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_width, fb_height))
        for slot in self._slots:
            if not slot.active:
                continue
            srb = slot.srb_linear if slot.smooth else slot.srb_nearest
            command_buffer.setShaderResources(srb)
            command_buffer.setVertexInput(0, [(slot.vertex_buffer, 0)])
            command_buffer.draw(4)

    def release(self) -> None:
        for slot in self._slots:
            slot.release()
        for res in (self.pipeline, self.sampler_linear, self.sampler_nearest, self.uniform_buffer):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.pipeline = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.uniform_buffer = None
        self.rhi = None

    @staticmethod
    def _build_quad_vertices(ctx, rect: QRectF) -> bytes:
        w = float(ctx.width)
        h = float(ctx.height)
        x0 = rect.left() / w * 2.0 - 1.0
        x1 = rect.right() / w * 2.0 - 1.0
        y0 = 1.0 - rect.top() / h * 2.0
        y1 = 1.0 - rect.bottom() / h * 2.0
        return struct.pack(
            "<16f",
            x0, y0, 0.0, 0.0,
            x0, y1, 0.0, 1.0,
            x1, y0, 1.0, 0.0,
            x1, y1, 1.0, 1.0,
        )

    @staticmethod
    def _rasterize_label(
        name: str,
        rw: int,
        rh: int,
        font: QFont,
        metrics: QFontMetrics,
        text_color: QColor,
        bg_color: QColor,
        draw_bg: bool,
        style: FilenameOverlayStyle,
        font_weight: int,
        dpr: float,
    ) -> QImage:
        dpr = max(1.0, float(dpr))
        phys_w = max(1, int(round(rw * dpr)))
        phys_h = max(1, int(round(rh * dpr)))
        img = new_overlay_image(phys_w, phys_h)
        painter = QPainter(img)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.scale(dpr, dpr)
            painter.setFont(font)
            label_rect = QRectF(0.0, 0.0, float(rw), float(rh))
            if draw_bg:
                draw_round_rect(
                    painter,
                    label_rect.adjusted(0.5, 0.5, -0.5, -0.5),
                    bg_color,
                    style,
                )
            text_inset = float(style.text_inset_px)
            text_str = fit_text(name, metrics, float(rw) - (text_inset * 2.0))
            if font_weight > 0:
                draw_text_bold_supersampled(
                    painter,
                    text_str,
                    font,
                    text_color,
                    font_weight,
                    rw,
                    rh,
                    text_inset,
                )
            else:
                painter.setPen(QPen(text_color))
                painter.drawText(
                    label_rect.adjusted(text_inset, 0.0, -text_inset, 0.0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text_str,
                )
        finally:
            painter.end()
        return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)


RENDER_PASSES: list[CanvasRenderPass] = [FilenameOverlayPass()]
GL_RENDER_PASSES = RENDER_PASSES
