import math

from OpenGL import GL as gl
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from .render_common import (
    clear_with_widget_background,
    draw_qimage_overlay_texture,
    draw_supersampled_line,
    get_zoom_texture_filter,
    new_overlay_image,
    should_render_blank_white,
    widget_px_to_screen_px,
)
from .render_config import (
    begin_content_scissor,
    compute_render_config,
    end_content_scissor,
    get_divider_clip_rect_px,
    get_divider_clip_uv,
)
from .render_context import build_render_runtime_context, get_magnifier_shader_program
from .render_overlays import (
    paint_drag_overlay_pass,
    paint_filename_overlay_pass,
    paint_paste_overlay_pass,
)
from .shaders import MagnifierShaderVariantKey

def _build_magnifier_shader_key(ctx, gpu_slot, combined: bool) -> MagnifierShaderVariantKey:
    if gpu_slot:
        source_mode = int(gpu_slot.get("source", 0) or 0)
        diff_mode = int(ctx.mag_gpu_diff_mode or 0) if source_mode == 2 and not combined else 0
        return MagnifierShaderVariantKey(
            gpu_sampling=True,
            combined=combined,
            interp_mode=(
                int(ctx.mag_gpu_interp_mode)
                if ctx.mag_gpu_interp_mode is not None
                else 1
            ),
            diff_mode=diff_mode,
            channel_mode=int(ctx.mag_gpu_channel_mode or 0),
            source_mode=source_mode if not combined else 0,
        )
    return MagnifierShaderVariantKey(gpu_sampling=False, combined=combined)

def paint_capture_ring_pass(widget, ctx, capture_color):
    w, h = ctx.width, ctx.height
    if not (widget._circle_shader and w > 0 and h > 0 and ctx.capture_center and ctx.capture_radius > 0):
        return

    scissor_enabled = begin_content_scissor(
        widget,
        force=bool(getattr(ctx.render_scene, "clip_overlays_to_image_bounds", False)),
    )
    pid = widget._circle_shader.programId()
    widget._circle_shader.bind()
    widget.vao.bind()

    cx, cy = widget_px_to_screen_px(widget, ctx.capture_center.x(), ctx.capture_center.y())
    scaled_radius = ctx.capture_radius * ctx.zoom_level
    line_width_px = max(2.0, float(scaled_radius * 2.0) * 0.0105)

    gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(w), float(h))
    gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"), float(cx), float(cy))
    gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(scaled_radius))
    gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), float(line_width_px))
    gl.glUniform4f(
        gl.glGetUniformLocation(pid, "color"),
        capture_color.redF(),
        capture_color.greenF(),
        capture_color.blueF(),
        capture_color.alphaF(),
    )
    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

    widget.vao.release()
    widget._circle_shader.release()
    end_content_scissor(widget, scissor_enabled)

def paint_guides_pass(widget, ctx):
    if not (
        ctx.show_guides
        and ctx.guides_thickness > 0
        and ctx.capture_center is not None
        and ctx.capture_radius > 0
        and ctx.magnifier_centers
        and ctx.magnifier_radius > 0
    ):
        return

    def draw_line(painter, p1, p2, r1, r2, color, interactive, thickness):
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = math.hypot(dx, dy)
        if dist <= (r1 + r2) or dist <= 1e-6:
            return

        nx, ny = dx / dist, dy / dist
        ax, ay = p1.x() + nx * r1, p1.y() + ny * r1
        bx, by = p2.x() - nx * r2, p2.y() - ny * r2

        if interactive:
            pen = QPen(color, float(thickness))
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(ax, ay), QPointF(bx, by))
            return

        draw_supersampled_line(
            painter,
            QPointF(ax, ay),
            QPointF(bx, by),
            color,
            float(thickness),
        )

    scene = ctx.render_scene
    is_interactive = bool(getattr(scene, "interactive_mode", False))
    optimize_smoothing = bool(getattr(scene, "optimize_laser_smoothing", False))
    interactive_line = bool(is_interactive and not optimize_smoothing)

    w = ctx.width
    h = ctx.height
    overlay = new_overlay_image(w, h)
    painter = QPainter(overlay)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    base_color = getattr(scene, "laser_color", ctx.laser_color)
    color = QColor(base_color.red(), base_color.green(), base_color.blue(), 255)
    zoom = ctx.zoom_level
    cc_x, cc_y = widget_px_to_screen_px(widget, ctx.capture_center.x(), ctx.capture_center.y())
    cap_center = QPointF(cc_x, cc_y)
    cap_radius = float(ctx.capture_radius) * zoom
    mag_radius = float(ctx.magnifier_radius) * zoom
    thickness = max(1, int(ctx.guides_thickness))
    try:
        for mag_center in ctx.magnifier_centers:
            if mag_center is None:
                continue
            mc_x, mc_y = widget_px_to_screen_px(widget, mag_center.x(), mag_center.y())
            draw_line(
                painter,
                QPointF(mc_x, mc_y),
                cap_center,
                mag_radius,
                cap_radius,
                color,
                interactive_line,
                thickness,
            )
    finally:
        painter.end()

    if not getattr(widget, "_guides_tex_id", 0):
        return

    qimg = overlay.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.constBits()
    ptr.setsize(qimg.sizeInBytes())
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._guides_tex_id)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(
        gl.GL_TEXTURE_2D,
        0,
        gl.GL_RGBA,
        qimg.width(),
        qimg.height(),
        0,
        gl.GL_RGBA,
        gl.GL_UNSIGNED_BYTE,
        bytes(ptr),
    )

    widget.shader_program.bind()
    widget.vao.bind()

    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._guides_tex_id)
    widget.shader_program.setUniformValue("image1", 0)
    gl.glActiveTexture(gl.GL_TEXTURE1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._guides_tex_id)
    widget.shader_program.setUniformValue("image2", 1)

    widget.shader_program.setUniformValue("splitPosition", 1.0)
    widget.shader_program.setUniformValue("isHorizontal", False)
    widget.shader_program.setUniformValue("zoom", 1.0)
    widget.shader_program.setUniformValue("offset", 0.0, 0.0)
    widget.shader_program.setUniformValue("showDivider", False)
    widget.shader_program.setUniformValue("dividerColor", 0.0, 0.0, 0.0, 0.0)
    widget.shader_program.setUniformValue("dividerThickness", 0.0)
    widget.shader_program.setUniformValue("dividerClip", 0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("channelMode", 0)
    widget.shader_program.setUniformValue("useSourceTex", False)
    widget.shader_program.setUniformValue("letterbox1", 0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("letterbox2", 0.0, 0.0, 1.0, 1.0)

    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
    widget.vao.release()
    widget.shader_program.release()

def paint_divider_overlay_pass(widget, cfg):
    if not cfg.get("show_div", False):
        return

    clip_rect = get_divider_clip_rect_px(widget)
    if not clip_rect:
        return

    clip_x, clip_y, clip_w, clip_h = clip_rect
    if clip_w <= 0 or clip_h <= 0:
        return

    w = widget.width()
    h = widget.height()
    if w <= 0 or h <= 0:
        return

    overlay = new_overlay_image(w, h)
    painter = QPainter(overlay)
    try:
        color = cfg["div_color"]
        thickness = max(1, int(round(cfg["div_thickness"])))
        display_split = float(
            getattr(widget, "display_split_position", getattr(widget, "split_position", 0.5))
            or 0.5
        )
        if widget.is_horizontal:
            y = int(round(display_split * h))
            painter.fillRect(clip_x, y - thickness // 2, clip_w, thickness, color)
        else:
            x = int(round(display_split * w))
            painter.fillRect(x - thickness // 2, clip_y, thickness, clip_h, color)
    finally:
        painter.end()

    draw_qimage_overlay_texture(widget, overlay)

def paint_magnifier_pass(widget, ctx, border_color, render_magnifiers):
    w, h = ctx.width, ctx.height
    if not (w > 0 and h > 0 and render_magnifiers):
        return

    is_gpu = ctx.mag_gpu_active
    use_source_textures = is_gpu and ctx.source_images_ready
    bg_filter = gl.GL_LINEAR if ctx.mag_gpu_interp_mode == 1 else gl.GL_NEAREST

    zoom = ctx.zoom_level
    pan_x = ctx.pan_offset_x
    pan_y = ctx.pan_offset_y

    for i, quad in enumerate(ctx.mag_quads):
        if not quad:
            continue
        x0, y0, x1, y1, _cx_px, _cy_px, r_px = quad

        gpu_slot = ctx.mag_gpu_slots[i] if is_gpu and i < len(ctx.mag_gpu_slots) else None
        if not gpu_slot:
            tid = widget._mag_tex_ids[i] if i < len(widget._mag_tex_ids) else 0
            if not tid:
                continue

        comb_params = None
        if gpu_slot:
            combined = bool(gpu_slot.get("is_combined", False))
        else:
            comb_params = ctx.mag_combined_params[i] if i < len(ctx.mag_combined_params) else None
            combined = comb_params is not None

        shader = get_magnifier_shader_program(
            widget,
            _build_magnifier_shader_key(ctx, gpu_slot, combined),
        )
        pid = shader.programId()

        border_width = max(float(ctx.magnifier_border_width), float(r_px * 2.0) * 0.0105)
        content_radius = max(1.0, r_px - border_width + 1.0)

        def _combined_divider_thickness_uv(params, fallback_uv: float = 0.005) -> float:
            if not params:
                return 0.0
            divider_px = float(params.get("divider_thickness_px", 0.0) or 0.0)
            if divider_px <= 0.0:
                return float(params.get("divider_thickness_uv", 0.0) or 0.0)
            content_diameter_px = max(1.0, content_radius * 2.0)
            return (divider_px / content_diameter_px) * 0.5 if content_diameter_px > 0.0 else fallback_uv

        shader.bind()
        shader.setUniformValue("quadBounds", x0, y0, x1, y1)
        shader.setUniformValue("magZoom", zoom)
        gl.glUniform2f(gl.glGetUniformLocation(pid, "magPan"), pan_x, pan_y)
        shader.setUniformValue("useCircleMask", True)
        gl.glActiveTexture(gl.GL_TEXTURE4)
        gl.glBindTexture(gl.GL_TEXTURE_2D, widget._circle_mask_tex_id)
        gl.glUniform1i(gl.glGetUniformLocation(pid, "circleMaskTex"), 4)

        gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), r_px)
        gl.glUniform1f(gl.glGetUniformLocation(pid, "borderWidth"), border_width)
        gl.glUniform4f(
            gl.glGetUniformLocation(pid, "borderColor"),
            border_color.redF(),
            border_color.greenF(),
            border_color.blueF(),
            border_color.alphaF(),
        )

        if gpu_slot:
            gl.glUniform1f(gl.glGetUniformLocation(pid, "diffThreshold"), ctx.mag_gpu_diff_threshold)

            uv1 = gpu_slot.get("uv_rect", (0, 0, 1, 1))
            uv2 = gpu_slot.get("uv_rect2", uv1)
            gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect1"), *uv1)
            gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect2"), *uv2)

            if combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), gpu_slot.get("internal_split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), int(gpu_slot.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), 0)
                dc2 = gpu_slot.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), *dc2)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)
            else:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), 0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), 0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), 0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), 1.0, 1.0, 1.0, 0.9)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)

            tex1 = ctx.source_texture_ids[0] if use_source_textures else ctx.texture_ids[0]
            tex2 = ctx.source_texture_ids[1] if use_source_textures else ctx.texture_ids[1]
            gl.glActiveTexture(gl.GL_TEXTURE2)
            widget._set_texture_filter(tex1, bg_filter)
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex1)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTex1"), 2)
            gl.glActiveTexture(gl.GL_TEXTURE3)
            widget._set_texture_filter(tex2, bg_filter)
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex2)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTex2"), 3)
            gl.glActiveTexture(gl.GL_TEXTURE5)
            if ctx.diff_source_ready and ctx.diff_source_texture_id:
                widget._set_texture_filter(ctx.diff_source_texture_id, bg_filter)
                gl.glBindTexture(gl.GL_TEXTURE_2D, ctx.diff_source_texture_id)
            else:
                gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTexDiff"), 5)
        else:
            gl.glActiveTexture(gl.GL_TEXTURE5)
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTexDiff"), 5)

            if combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), comb_params.get("split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), int(comb_params.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), int(comb_params.get("divider_visible", True)))
                dc2 = comb_params.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), *dc2)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), comb_params.get("divider_thickness_uv", 0.005))
            else:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), 0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), 0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), 0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), 1.0, 1.0, 1.0, 0.9)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)

            gl.glActiveTexture(gl.GL_TEXTURE0)
            gl.glBindTexture(gl.GL_TEXTURE_2D, widget._mag_tex_ids[i])
            gl.glUniform1i(gl.glGetUniformLocation(pid, "magTex"), 0)
            if combined:
                comb_tid = widget._mag_combined_tex_ids[i] if i < len(widget._mag_combined_tex_ids) else 0
                gl.glActiveTexture(gl.GL_TEXTURE2)
                gl.glBindTexture(gl.GL_TEXTURE_2D, comb_tid)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "magTex2"), 2)

        widget.vao.bind()
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        shader.release()

        content_x0 = ((_cx_px - content_radius) / w) * 2.0 - 1.0
        content_x1 = ((_cx_px + content_radius) / w) * 2.0 - 1.0
        content_y1 = 1.0 - (((_cy_px - content_radius) / h) * 2.0)
        content_y0 = 1.0 - (((_cy_px + content_radius) / h) * 2.0)

        shader.bind()
        shader.setUniformValue("quadBounds", content_x0, content_y0, content_x1, content_y1)
        shader.setUniformValue("magZoom", zoom)
        gl.glUniform2f(gl.glGetUniformLocation(pid, "magPan"), pan_x, pan_y)
        shader.setUniformValue("useCircleMask", True)
        gl.glActiveTexture(gl.GL_TEXTURE4)
        gl.glBindTexture(gl.GL_TEXTURE_2D, widget._circle_mask_tex_id)
        gl.glUniform1i(gl.glGetUniformLocation(pid, "circleMaskTex"), 4)
        gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), content_radius)
        gl.glUniform1f(gl.glGetUniformLocation(pid, "borderWidth"), 0.0)
        gl.glUniform4f(gl.glGetUniformLocation(pid, "borderColor"), 0.0, 0.0, 0.0, 0.0)
        if gpu_slot and combined:
            gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), gpu_slot.get("internal_split", 0.5))
            gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), int(gpu_slot.get("horizontal", False)))
            gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), int(gpu_slot.get("divider_visible", True)))
            dc2 = gpu_slot.get("divider_color", (1.0, 1.0, 1.0, 0.9))
            gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), *dc2)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), _combined_divider_thickness_uv(gpu_slot))
        elif combined:
            gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), comb_params.get("split", 0.5))
            gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), int(comb_params.get("horizontal", False)))
            gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), int(comb_params.get("divider_visible", True)))
            dc2 = comb_params.get("divider_color", (1.0, 1.0, 1.0, 0.9))
            gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), *dc2)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), _combined_divider_thickness_uv(comb_params))
        else:
            gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), 0.5)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), 0)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), 0)
            gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), 1.0, 1.0, 1.0, 0.9)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)

        widget.vao.bind()
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        shader.release()

    if is_gpu:
        tex1 = ctx.source_texture_ids[0] if use_source_textures else ctx.texture_ids[0]
        tex2 = ctx.source_texture_ids[1] if use_source_textures else ctx.texture_ids[1]
        widget._set_texture_filter(tex1, gl.GL_LINEAR)
        widget._set_texture_filter(tex2, gl.GL_LINEAR)

def paint_magnifier_shadow_pass(widget, render_magnifiers):
    return

def _flush_pending_uploads(widget):
    state = widget.runtime_state
    if not state._pending_texture_uploads:
        return
    for raw, w, h, tex_id, _slot in state._pending_texture_uploads:
        gl.glBindTexture(gl.GL_TEXTURE_2D, tex_id)
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, raw)
    state._pending_texture_uploads.clear()

def paint_gl(widget):
    if not widget.shader_program:
        from .render_context import logger
        logger.error(
            "paint_gl: shader_program is None (initializeGL did not run or failed). "
            "context=%s isValid=%s",
            widget.context(),
            widget.context().isValid() if widget.context() else "no-ctx",
        )
        return

    _flush_pending_uploads(widget)
    ctx = build_render_runtime_context(widget)

    if should_render_blank_white(widget):
        clear_with_widget_background(widget)
        paint_drag_overlay_pass(widget)
        paint_paste_overlay_pass(widget)
        return

    clear_with_widget_background(widget)
    if not any(ctx.images_uploaded):
        paint_drag_overlay_pass(widget)
        paint_paste_overlay_pass(widget)
        return

    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    widget.shader_program.bind()
    widget.vao.bind()

    cfg = compute_render_config(widget, ctx)
    ctx = build_render_runtime_context(widget)
    diff_mode_active = bool(cfg["diff_mode_active"])
    use_hires = bool(
        ctx.shader_letterbox_mode
        and not diff_mode_active
        and ctx.zoom_level > 1.0
        and ctx.source_images_ready
        and ctx.source_texture_ids[0]
        and ctx.source_texture_ids[1]
    )
    use_diff_hires = bool(
        diff_mode_active
        and ctx.zoom_level > 1.0
        and ctx.diff_source_ready
        and ctx.diff_source_texture_id
    )
    if use_diff_hires:
        tex1 = ctx.diff_source_texture_id
        tex2 = ctx.diff_source_texture_id
    else:
        tex1 = ctx.source_texture_ids[0] if use_hires else ctx.texture_ids[0]
        tex2 = ctx.source_texture_ids[1] if use_hires else ctx.texture_ids[1]
    zoom_filter = get_zoom_texture_filter(widget)
    widget._set_texture_filter(tex1, zoom_filter)
    widget._set_texture_filter(tex2, zoom_filter)

    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex1)
    widget.shader_program.setUniformValue("image1", 0)

    gl.glActiveTexture(gl.GL_TEXTURE1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex2)
    widget.shader_program.setUniformValue("image2", 1)

    widget.shader_program.setUniformValue(
        "splitPosition",
        float(
            getattr(widget, "display_split_position", getattr(widget, "split_position", ctx.split_position))
            or ctx.split_position
        ),
    )
    widget.shader_program.setUniformValue("isHorizontal", ctx.is_horizontal)
    widget.shader_program.setUniformValue("zoom", ctx.zoom_level)
    widget.shader_program.setUniformValue("offset", ctx.pan_offset_x, ctx.pan_offset_y)
    widget.shader_program.setUniformValue("showDivider", False)

    dc = cfg["div_color"]
    dim = ctx.height if ctx.is_horizontal else ctx.width
    thickness_ndc = ((cfg["div_thickness"] * 0.5) / dim) if dim > 0 else 0.001
    divider_clip = get_divider_clip_uv(widget)
    widget.shader_program.setUniformValue("dividerColor", dc.redF(), dc.greenF(), dc.blueF(), dc.alphaF())
    widget.shader_program.setUniformValue("dividerThickness", thickness_ndc)
    widget.shader_program.setUniformValue("dividerClip", *divider_clip)
    widget.shader_program.setUniformValue("channelMode", cfg["channel_mode_int"])
    widget.shader_program.setUniformValue("useSourceTex", use_hires or use_diff_hires)
    if ctx.shader_letterbox_mode:
        lb1 = widget.get_letterbox_params(0) if hasattr(widget, "get_letterbox_params") else (0.0, 0.0, 1.0, 1.0)
        lb2 = widget.get_letterbox_params(1) if hasattr(widget, "get_letterbox_params") else (0.0, 0.0, 1.0, 1.0)
    else:
        lb1 = (0.0, 0.0, 1.0, 1.0)
        lb2 = (0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("letterbox1", *lb1)
    widget.shader_program.setUniformValue("letterbox2", *lb2)

    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
    widget.vao.release()
    widget.shader_program.release()

    overlay_scissor_enabled = begin_content_scissor(
        widget,
        force=bool(getattr(ctx.render_scene, "clip_overlays_to_image_bounds", False)),
    )
    paint_divider_overlay_pass(widget, cfg)
    paint_guides_pass(widget, ctx)
    paint_capture_ring_pass(widget, ctx, cfg["capture_color"])
    paint_magnifier_shadow_pass(widget, cfg["render_magnifiers"])
    paint_magnifier_pass(widget, ctx, cfg["border_color"], cfg["render_magnifiers"])
    paint_filename_overlay_pass(widget)
    end_content_scissor(widget, overlay_scissor_enabled)
    paint_drag_overlay_pass(widget)
    paint_paste_overlay_pass(widget)
