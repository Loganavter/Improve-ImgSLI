from __future__ import annotations

import struct

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFontMetrics, QRhiCommandBuffer, QRhiViewport

from ui.canvas_presentation.filename_labels import (
    font_for_style,
    label_rects,
    limit_name,
    qcolor,
    snap_rect_to_pixels,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from tabs.image_compare.canvas.features.filename_overlay.render.gpu_resources import (
    FilenameOverlayGpuResources,
)
from tabs.image_compare.canvas.features.filename_overlay.render.label_raster import (
    build_quad_vertices,
    rasterize_label,
)


class FilenameOverlayPass(CanvasRenderPass):
    """Renders filename labels as screen-positioned textured quads."""

    stack_role = CanvasStackRole.HUD_LABEL
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._gpu = FilenameOverlayGpuResources()

    def initialize(self, rhi, target) -> None:
        self._gpu.initialize(rhi, target)

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
        # Pivot/pan scale off the logical canvas center (== widget center
        # outside tiled export), then shift into this render target's
        # tile-local pixel space via canvas_offset_x/y so _build_quad_vertices
        # (which uses the actual ctx.width/height for NDC) gets tile-local
        # coordinates.
        canvas_w = float(ctx.canvas_width)
        canvas_h = float(ctx.canvas_height)
        wcx = canvas_w / 2.0
        wcy = canvas_h / 2.0

        def _to_screen_rect(r: QRectF) -> QRectF:
            if not apply_transform:
                left = r.left() - ctx.canvas_offset_x
                top = r.top() - ctx.canvas_offset_y
                return QRectF(left, top, r.width(), r.height())
            left = wcx + (r.left() - wcx) * zoom + pan_x * canvas_w - ctx.canvas_offset_x
            top = wcy + (r.top() - wcy) * zoom + pan_y * canvas_h - ctx.canvas_offset_y
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

        text_color = qcolor(
            getattr(cfg, "file_name_color", None), QColor(255, 0, 0, 255)
        )
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
            "<16f", *tuple(float(v) for v in self._gpu.rhi.clipSpaceCorrMatrix().data())
        )
        resource_updates.updateDynamicBuffer(self._gpu.uniform_buffer, 0, matrix)

        for i, (name, rect) in enumerate([(name1, rect1), (name2, rect2)]):
            slot = self._gpu.slots[i]
            if not name or rect is None:
                slot.content_key = None
                continue
            rw = max(1, int(rect.width()))
            rh = max(1, int(rect.height()))
            dpr = max(1.0, float(widget.devicePixelRatioF()))
            cache_key = (name, rw, rh, font_key, round(dpr, 3))

            if slot.content_key != cache_key:
                image = rasterize_label(
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
                self._gpu.ensure_slot_texture(slot, phys_size)
                resource_updates.uploadTexture(slot.texture, image)
                slot.content_key = cache_key

            screen_rect = _to_screen_rect(rect)
            vertices = build_quad_vertices(ctx, screen_rect)
            resource_updates.updateDynamicBuffer(slot.vertex_buffer, 0, vertices)
            slot.vertices = vertices
            slot.smooth = bool(apply_transform)
            slot.active = True

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        if self._gpu.pipeline is None:
            return
        dpr = max(1.0, float(widget.devicePixelRatioF()))
        fb_width = float(int(ctx.width) * dpr)
        fb_height = float(int(ctx.height) * dpr)
        command_buffer.setGraphicsPipeline(self._gpu.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_width, fb_height))
        for slot in self._gpu.slots:
            if not slot.active:
                continue
            srb = slot.srb_linear if slot.smooth else slot.srb_nearest
            command_buffer.setShaderResources(srb)
            command_buffer.setVertexInput(0, [(slot.vertex_buffer, 0)])
            command_buffer.draw(4)

    def release(self) -> None:
        self._gpu.release()

RENDER_PASSES: list[CanvasRenderPass] = [FilenameOverlayPass()]
RENDER_PASSES = RENDER_PASSES
