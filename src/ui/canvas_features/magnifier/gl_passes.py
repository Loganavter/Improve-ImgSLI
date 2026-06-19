from __future__ import annotations

from OpenGL import GL as gl
from PySide6.QtGui import QColor
from PySide6.QtOpenGL import QOpenGLShaderProgram

from ui.canvas_infra.scene.gl_pass_contract import (
    CanvasGLRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.canvas_features.magnifier.shaders import (
    ARC_FRAG,
    ARC_VERT,
    BORDER_DISK_FRAG,
    MAG_VERT,
    MagShaderKey,
    build_mag_frag,
    compile_shader_program,
    shader_prolog,
)
from ui.widgets.gl_canvas.render_common import (
    widget_px_to_screen_px,
)
from ui.widgets.gl_canvas.render_config import begin_content_scissor, end_content_scissor

import logging
_log = logging.getLogger("ImproveImgSLI")

def _ensure_qcolor(c) -> QColor:
    if isinstance(c, QColor):
        return c
    r = int(getattr(c, "r", 255) if hasattr(c, "r") else getattr(c, "red", lambda: 255)())
    g = int(getattr(c, "g", 255) if hasattr(c, "g") else getattr(c, "green", lambda: 255)())
    b = int(getattr(c, "b", 255) if hasattr(c, "b") else getattr(c, "blue", lambda: 255)())
    a = int(getattr(c, "a", 255) if hasattr(c, "a") else getattr(c, "alpha", lambda: 255)())
    return QColor(r, g, b, a)

class OccludedArcPass(CanvasGLRenderPass):
    """Draws the occluded arc segments of the capture ring when dragging."""

    stack_role = CanvasStackRole.ANNOTATION_BORDER
    visibility = SceneVisibility.INTERACTIVE

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

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        self._shader = compile_shader_program(
            widget,
            f"{shader_prolog(is_gles)}\n{ARC_VERT}",
            f"{shader_prolog(is_gles, fragment=True)}\n{ARC_FRAG}",
            "OccludedArcPass",
        )

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_occluded_capture_arcs(ctx))

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        w, h = ctx.width, ctx.height
        overlay = getattr(ctx, "feature_overlay", None)
        arcs = list(self._resolve_occluded_capture_arcs(ctx))
        if not (arcs and w > 0 and h > 0):
            return

        scissor_enabled = begin_content_scissor(
            widget,
            force=bool(getattr(overlay, "clip_to_content", False)),
        )
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()

        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(w), float(h))

        for arc in arcs:
            if len(arc) < 5:
                continue
            center, radius, start_deg, span_deg, is_active = arc
            if radius <= 0 or span_deg <= 0.25:
                continue
            base_color = QColor(255, 105, 170, 255 if is_active else 210)
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            scaled_radius  = float(radius) * ctx.zoom_level
            line_width_px = max(1.0, float(ctx.resolved_style.annotation_arc_stroke_px))
            gl.glUniform4f(
                gl.glGetUniformLocation(pid, "color"),
                base_color.redF(), base_color.greenF(),
                base_color.blueF(), base_color.alphaF(),
            )
            gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"),    float(cx), float(cy))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"),    float(scaled_radius))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), float(line_width_px))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "startAngleDeg"), float(start_deg))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "spanAngleDeg"),  float(span_deg))
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        widget.vao.release()
        self._shader.release()
        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader = None

class MagnifierPass(CanvasGLRenderPass):
    """Renders all magnifier circles using GPU sampling or pre-rendered textures."""

    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._shader_cache: dict[object, QOpenGLShaderProgram] = {}
        self._is_gles: bool = False

    def initialize(self, widget) -> None:
        self._is_gles = bool(widget.context().isOpenGLES())
        self._shader_cache = {}

    def _draw_slot_frame(
        self,
        widget,
        ctx,
        *,
        center_x: float,
        center_y: float,
        radius: float,
        border_width: float,
        border_color: QColor,
    ) -> None:
        shader = self._get_disk_shader(widget)
        if not shader or not shader.programId():
            return
        cx, cy = widget_px_to_screen_px(widget, center_x, center_y)
        scaled_radius = float(radius) * float(ctx.zoom_level or 1.0)
        draw_color = _ensure_qcolor(border_color)

        pid = shader.programId()
        shader.bind()
        widget.vao.bind()
        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(ctx.width), float(ctx.height))
        gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"), float(cx), float(cy))
        gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(scaled_radius))
        gl.glUniform1f(
            gl.glGetUniformLocation(pid, "borderWidth_px"),
            float(border_width) * float(ctx.zoom_level or 1.0),
        )
        gl.glUniform4f(
            gl.glGetUniformLocation(pid, "color"),
            draw_color.redF(), draw_color.greenF(),
            draw_color.blueF(), 1.0,
        )
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        shader.release()

    def _get_disk_shader(self, widget) -> QOpenGLShaderProgram | None:
        key = "_disk_shader"
        prog = self._shader_cache.get(key)
        if prog is not None and prog.isLinked():
            return prog
        vert_src = f"{shader_prolog(self._is_gles)}\n{ARC_VERT}"
        frag_src = f"{shader_prolog(self._is_gles, fragment=True)}\n{BORDER_DISK_FRAG}"
        prog = compile_shader_program(widget, vert_src, frag_src, "MagnifierSlotFrame")
        if prog is not None:
            self._shader_cache[key] = prog
        return prog

    def _get_shader(self, widget, key: MagShaderKey) -> QOpenGLShaderProgram | None:
        prog = self._shader_cache.get(key)
        if prog is not None and prog.isLinked():
            return prog
        prog = compile_shader_program(
            widget,
            f"{shader_prolog(self._is_gles)}\n{MAG_VERT}",
            build_mag_frag(key, is_gles=self._is_gles),
            f"MagnifierPass[{key}]",
        )
        if prog is not None:
            self._shader_cache[key] = prog
        return prog

    def _build_key(self, ctx, gpu_slot, combined: bool) -> MagShaderKey:
        overlay = getattr(ctx, "feature_overlay", None)
        if gpu_slot:
            source_mode = int(gpu_slot.get("source", 0) or 0)
            diff_mode = (
                int(getattr(overlay, "gpu_diff_mode", 0) or 0)
                if source_mode == 2 and not combined
                else 0
            )
            return MagShaderKey(
                gpu_sampling=True,
                combined=combined,
                interp_mode=int(getattr(overlay, "gpu_interp_mode", 1))
                if getattr(overlay, "gpu_interp_mode", None) is not None
                else 1,
                diff_mode=diff_mode,
                channel_mode=int(getattr(overlay, "gpu_channel_mode", 0) or 0),
                source_mode=source_mode if not combined else 0,
            )
        return MagShaderKey(gpu_sampling=False, combined=combined)

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None or not bool(getattr(overlay, "render_enabled", False)):
            return False
        return bool(getattr(overlay, "quads", ()))

    def paint(self, widget, ctx) -> None:
        try:
            self._paint_inner(widget, ctx)
        except Exception:
            _log.exception("MagnifierPass paint failed")
            self._shader_cache.clear()

    def _paint_inner(self, widget, ctx) -> None:
        w, h = ctx.width, ctx.height
        if not (w > 0 and h > 0):
            return

        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None:
            return

        scissor_enabled = begin_content_scissor(
            widget,
            force=bool(getattr(overlay, "clip_to_content", False)),
        )

        is_gpu = bool(overlay.gpu_active)
        use_source_textures = bool(
            is_gpu
            and ctx.shader_letterbox_mode
            and ctx.source_images_ready
            and ctx.source_texture_ids[0]
            and ctx.source_texture_ids[1]
        )
        bg_filter = gl.GL_LINEAR if overlay.gpu_interp_mode == 1 else gl.GL_NEAREST
        zoom  = ctx.zoom_level
        pan_x = ctx.pan_offset_x
        pan_y = ctx.pan_offset_y

        for i, quad in enumerate(overlay.quads):
            if not quad:
                continue
            x0, y0, x1, y1, _cx_px, _cy_px, r_px = quad

            gpu_slot = (
                overlay.gpu_slots[i]
                if is_gpu and i < len(overlay.gpu_slots)
                else None
            )
            if not gpu_slot:
                tid = (
                    widget._feature_overlay_tex_ids[i]
                    if i < len(widget._feature_overlay_tex_ids)
                    else 0
                )
                if not tid:
                    continue

            if gpu_slot:
                combined   = bool(gpu_slot.get("is_combined", False))
                comb_params = None
            else:
                comb_params = (
                    overlay.combined_params[i]
                    if i < len(overlay.combined_params)
                    else None
                )
                combined    = comb_params is not None

            shader = self._get_shader(widget, self._build_key(ctx, gpu_slot, combined))
            if shader is None:
                continue
            pid = shader.programId()

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
                self._draw_slot_frame(
                    widget,
                    ctx,
                    center_x=float(_cx_px),
                    center_y=float(_cy_px),
                    radius=float(r_px),
                    border_width=float(border_width),
                    border_color=_ensure_qcolor(slot_border_color),
                )

            def _comb_divider_thickness_uv(params, fallback: float = 0.005) -> float:
                if not params:
                    return 0.0
                dpx = float(params.get("divider_thickness_px", 0.0) or 0.0)
                if dpx <= 0.0:
                    return float(params.get("divider_thickness_uv", 0.0) or 0.0)
                diam = max(1.0, content_radius * 2.0)
                return (dpx / diam) * 0.5 if diam > 0.0 else fallback

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
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"),   content_radius)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "borderWidth"), 0.0)
            gl.glUniform4f(gl.glGetUniformLocation(pid, "borderColor"),  0.0, 0.0, 0.0, 0.0)
            if gpu_slot:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "diffThreshold"), overlay.gpu_diff_threshold)
                uv1 = gpu_slot.get("uv_rect", (0, 0, 1, 1))
                uv2 = gpu_slot.get("uv_rect2", uv1)
                tex1 = ctx.source_texture_ids[0] if use_source_textures else ctx.texture_ids[0]
                tex2 = ctx.source_texture_ids[1] if use_source_textures else ctx.texture_ids[1]
                gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect1"), *uv1)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect2"), *uv2)
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
                gl.glActiveTexture(gl.GL_TEXTURE0)
                gl.glBindTexture(gl.GL_TEXTURE_2D, widget._feature_overlay_tex_ids[i])
                gl.glUniform1i(gl.glGetUniformLocation(pid, "magTex"), 0)
                if combined:
                    comb_tid = (
                        widget._feature_overlay_aux_tex_ids[i]
                        if i < len(widget._feature_overlay_aux_tex_ids)
                        else 0
                    )
                    gl.glActiveTexture(gl.GL_TEXTURE2)
                    gl.glBindTexture(gl.GL_TEXTURE_2D, comb_tid)
                    gl.glUniform1i(gl.glGetUniformLocation(pid, "magTex2"), 2)

            if gpu_slot and combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      gpu_slot.get("internal_split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     int(gpu_slot.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    int(gpu_slot.get("divider_visible", True)))
                dc = gpu_slot.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),     *dc)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), _comb_divider_thickness_uv(gpu_slot))
            elif gpu_slot:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),   1.0, 1.0, 1.0, 0.9)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)
            elif combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      comb_params.get("split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     int(comb_params.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    int(comb_params.get("divider_visible", True)))
                dc = comb_params.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),     *dc)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), _comb_divider_thickness_uv(comb_params))
            else:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),     1.0, 1.0, 1.0, 0.9)
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

        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader_cache.clear()

class HiddenSelectionPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.DEBUG_VIS
    visibility = SceneVisibility.INTERACTIVE

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

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        vert_src = f"{shader_prolog(is_gles)}\n{ARC_VERT}"
        frag_src = f"{shader_prolog(is_gles, fragment=True)}\n{ARC_FRAG}"
        self._shader = compile_shader_program(
            widget, vert_src, frag_src, "HiddenSelectionPass"
        )

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        hidden_capture_circles = list(self._resolve_hidden_capture_circles(ctx))
        hidden_overlay_circles = list(self._resolve_hidden_overlay_circles(ctx))
        return bool(hidden_capture_circles or hidden_overlay_circles)

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        hidden_capture_circles = list(self._resolve_hidden_capture_circles(ctx))
        hidden_overlay_circles = list(self._resolve_hidden_overlay_circles(ctx))
        if not hidden_capture_circles and not hidden_overlay_circles:
            return

        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()
        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(ctx.width), float(ctx.height))

        stroke_px = max(1.0, float(ctx.resolved_style.annotation_selection_stroke_px))

        def _draw_ring(center, radius, *, active: bool, capture: bool):
            if center is None or radius <= 0:
                return
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            scaled_radius = float(radius) * ctx.zoom_level
            if scaled_radius <= 0:
                return
            if capture:
                c = QColor(255, 105, 170, 255 if active else 210)
            else:
                c = QColor(70, 190, 255, 255 if active else 210)
            gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"), float(cx), float(cy))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(scaled_radius))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), stroke_px)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "startAngleDeg"), 0.0)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "spanAngleDeg"), 360.0)
            gl.glUniform4f(
                gl.glGetUniformLocation(pid, "color"),
                c.redF(), c.greenF(), c.blueF(), c.alphaF(),
            )
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        for center, radius, is_active in hidden_capture_circles:
            _draw_ring(center, radius, active=bool(is_active), capture=True)
        for center, radius, is_active in hidden_overlay_circles:
            _draw_ring(center, radius, active=bool(is_active), capture=False)

        widget.vao.release()
        self._shader.release()

    def cleanup(self, widget) -> None:
        self._shader = None

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [
    MagnifierPass(),
    OccludedArcPass(),
    HiddenSelectionPass(),
]
