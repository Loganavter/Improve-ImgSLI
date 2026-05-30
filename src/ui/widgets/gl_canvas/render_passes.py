from OpenGL import GL as gl

from .render_common import clear_with_widget_background, get_zoom_texture_filter, should_render_blank_white
from .render_executor import execute_render_passes
from .render_context import build_render_runtime_context

def _reset_frame_gl_state(widget) -> None:
    state = widget.runtime_state
    state._content_scissor_depth = 0
    dpr = max(1.0, float(widget.devicePixelRatioF()))
    framebuffer_w = max(1, int(round(widget.width() * dpr)))
    framebuffer_h = max(1, int(round(widget.height() * dpr)))
    gl.glDisable(gl.GL_SCISSOR_TEST)
    gl.glViewport(0, 0, framebuffer_w, framebuffer_h)

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

    _reset_frame_gl_state(widget)
    _flush_pending_uploads(widget)
    ctx = build_render_runtime_context(widget)

    if should_render_blank_white(ctx.scene_frame):
        clear_with_widget_background(widget)
        execute_render_passes(widget, ctx, getattr(widget, "_feature_gl_passes", ()))
        return

    clear_with_widget_background(widget)
    if not any(ctx.images_uploaded):
        execute_render_passes(widget, ctx, getattr(widget, "_feature_gl_passes", ()))
        return

    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFuncSeparate(
        gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA,
        gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA,
    )

    base_image = getattr(ctx.render_list, "base_image", None)
    if base_image is None:
        return

    widget.shader_program.bind()
    widget.vao.bind()

    tex1 = ctx.source_texture_ids[0] if base_image.use_hires else ctx.texture_ids[0]
    tex2 = ctx.source_texture_ids[1] if base_image.use_hires else ctx.texture_ids[1]
    zoom_filter = get_zoom_texture_filter(ctx.scene_frame)
    widget._set_texture_filter(tex1, zoom_filter)
    widget._set_texture_filter(tex2, zoom_filter)
    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex1)
    widget.shader_program.setUniformValue("image1", 0)

    gl.glActiveTexture(gl.GL_TEXTURE1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex2)
    widget.shader_program.setUniformValue("image2", 1)

    gl.glActiveTexture(gl.GL_TEXTURE2)
    if ctx.diff_source_ready and ctx.diff_source_texture_id:
        gl.glBindTexture(gl.GL_TEXTURE_2D, ctx.diff_source_texture_id)
    else:
        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    widget.shader_program.setUniformValue("imageDiff", 2)

    widget.shader_program.setUniformValue("splitPosition", float(base_image.split_position))
    widget.shader_program.setUniformValue("isHorizontal", bool(base_image.is_horizontal))
    widget.shader_program.setUniformValue("zoom", float(base_image.zoom))
    widget.shader_program.setUniformValue("offset", float(base_image.pan_offset_x), float(base_image.pan_offset_y))
    widget.shader_program.setUniformValue("diffMode", int(base_image.diff_mode_int))
    widget.shader_program.setUniformValue("diffSourceReady", bool(ctx.diff_source_ready))
    widget.shader_program.setUniformValue("diffThreshold", 20.0 / 255.0)

    widget.shader_program.setUniformValue("channelMode", int(base_image.channel_mode_int))
    widget.shader_program.setUniformValue("useSourceTex", bool(base_image.use_hires))
    widget.shader_program.setUniformValue("letterbox1", *base_image.letterbox1)
    widget.shader_program.setUniformValue("letterbox2", *base_image.letterbox2)

    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
    widget.vao.release()
    widget.shader_program.release()

    execute_render_passes(widget, ctx, getattr(widget, "_feature_gl_passes", ()))
