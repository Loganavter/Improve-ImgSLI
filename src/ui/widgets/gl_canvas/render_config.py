from OpenGL import GL as gl
from PyQt6.QtCore import QRect

from .render_common import widget_px_to_screen_px
from .render_context import GLRenderRuntimeContext

def get_divider_clip_uv(widget) -> tuple[float, float, float, float]:
    state = widget.runtime_state
    scene = state._render_scene
    clip_rect = getattr(scene, "divider_clip_rect", None)
    img = state._stored_pil_images[0] if state._stored_pil_images else None
    if clip_rect and img is not None and getattr(img, "width", 0) > 0 and getattr(img, "height", 0) > 0:
        x, y, w, h = clip_rect
        return (
            x / float(img.width),
            y / float(img.height),
            (x + w) / float(img.width),
            (y + h) / float(img.height),
        )
    if hasattr(widget, "get_letterbox_params"):
        lb = widget.get_letterbox_params(0)
        return (lb[0], lb[1], lb[0] + lb[2], lb[1] + lb[3])
    return (0.0, 0.0, 1.0, 1.0)

def get_divider_clip_rect_px(widget) -> tuple[int, int, int, int] | None:
    state = widget.runtime_state
    content_rect = state._content_rect_px
    if not content_rect:
        return None

    x, y, w, h = content_rect
    scene = state._render_scene
    clip_rect = getattr(scene, "divider_clip_rect", None)
    img = state._stored_pil_images[0] if state._stored_pil_images else None

    if clip_rect and img is not None and getattr(img, "width", 0) > 0 and getattr(img, "height", 0) > 0:
        clip_x, clip_y, clip_w, clip_h = clip_rect
        x = x + int(round((clip_x / float(img.width)) * w))
        y = y + int(round((clip_y / float(img.height)) * h))
        w = int(round((clip_w / float(img.width)) * w))
        h = int(round((clip_h / float(img.height)) * h))

    x0, y0 = widget_px_to_screen_px(widget, x, y)
    x1, y1 = widget_px_to_screen_px(widget, x + w, y + h)
    left = int(round(min(x0, x1)))
    top = int(round(min(y0, y1)))
    width = max(0, int(round(abs(x1 - x0))))
    height = max(0, int(round(abs(y1 - y0))))
    return (left, top, width, height)

def get_content_rect_screen_px(widget) -> tuple[int, int, int, int] | None:
    content_rect = widget.runtime_state._content_rect_px
    if not content_rect:
        return None

    x, y, w, h = content_rect
    if w <= 0 or h <= 0:
        return None

    x0, y0 = widget_px_to_screen_px(widget, x, y)
    x1, y1 = widget_px_to_screen_px(widget, x + w, y + h)
    left = int(round(min(x0, x1)))
    top = int(round(min(y0, y1)))
    width = max(0, int(round(abs(x1 - x0))))
    height = max(0, int(round(abs(y1 - y0))))
    if width <= 0 or height <= 0:
        return None
    return (left, top, width, height)

def get_local_visible_image_rect(
    widget,
    *,
    img_x: int,
    img_y: int,
    img_w: int,
    img_h: int,
) -> QRect | None:
    visible_left = max(0, img_x)
    visible_top = max(0, img_y)
    visible_right = min(widget.width(), img_x + img_w)
    visible_bottom = min(widget.height(), img_y + img_h)
    if visible_right <= visible_left or visible_bottom <= visible_top:
        return None
    return QRect(
        int(visible_left - img_x),
        int(visible_top - img_y),
        int(visible_right - visible_left),
        int(visible_bottom - visible_top),
    )

def compute_render_config(widget, ctx: GLRenderRuntimeContext):
    scene = ctx.viewport.render_scene
    if scene is None:
        return {
            "show_div": ctx.overlays.show_divider,
            "div_color": ctx.overlays.divider_color,
            "div_thickness": ctx.overlays.divider_thickness,
            "render_magnifiers": True,
            "border_color": ctx.magnifier.magnifier_border_color,
            "capture_color": ctx.overlays.capture_color,
            "channel_mode_int": 0,
            "diff_mode_active": False,
            "laser_color": ctx.overlays.laser_color,
            "show_guides": ctx.overlays.show_guides,
            "guides_thickness": ctx.overlays.guides_thickness,
            "interactive_mode": False,
            "optimize_laser_smoothing": False,
            "is_horizontal": ctx.viewport.is_horizontal,
            "split_position_visual": ctx.viewport.split_position,
        }

    widget.is_horizontal = scene.is_horizontal
    w, h = ctx.viewport.width, ctx.viewport.height
    img1 = ctx.textures.stored_pil_images[0]
    if img1 and w > 0 and h > 0:
        ratio = min(w / img1.width, h / img1.height)
        nw = max(1, int(img1.width * ratio))
        nh = max(1, int(img1.height * ratio))
        img_x = (w - nw) // 2
        img_y = (h - nh) // 2

        if scene.is_horizontal:
            base = (img_y + nh * scene.split_position_visual) / h
            pan = ctx.viewport.pan_offset_y
        else:
            base = (img_x + nw * scene.split_position_visual) / w
            pan = ctx.viewport.pan_offset_x
        widget.split_position = (base - 0.5 + pan) * ctx.viewport.zoom_level + 0.5
    else:
        widget.split_position = scene.split_position_visual

    return {
        "show_div": scene.show_divider,
        "div_color": scene.divider_color,
        "div_thickness": scene.divider_thickness,
        "render_magnifiers": scene.render_magnifiers,
        "border_color": scene.border_color,
        "capture_color": scene.capture_color,
        "channel_mode_int": scene.channel_mode_int,
        "diff_mode_active": scene.diff_mode_active,
        "laser_color": scene.laser_color,
        "show_guides": scene.show_guides,
        "guides_thickness": scene.guides_thickness,
        "interactive_mode": scene.interactive_mode,
        "optimize_laser_smoothing": scene.optimize_laser_smoothing,
        "is_horizontal": scene.is_horizontal,
        "split_position_visual": scene.split_position_visual,
    }

def begin_content_scissor(widget, force: bool = False):
    state = widget.runtime_state
    if not force and not state._clip_overlays_to_content_rect:
        return False
    if state._content_scissor_depth > 0:
        state._content_scissor_depth += 1
        return True
    rect = get_content_rect_screen_px(widget)
    if not rect:
        return False

    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return False

    visible_left = max(0, x)
    visible_top = max(0, y)
    visible_right = min(widget.width(), x + w)
    visible_bottom = min(widget.height(), y + h)
    if visible_right <= visible_left or visible_bottom <= visible_top:
        return False

    x = visible_left
    y = visible_top
    w = visible_right - visible_left
    h = visible_bottom - visible_top

    dpr = widget.devicePixelRatio()
    physical_h = int(widget.height() * dpr)
    gl.glEnable(gl.GL_SCISSOR_TEST)
    gl.glScissor(
        int(x * dpr),
        int(max(0, physical_h - int((y + h) * dpr))),
        int(w * dpr),
        int(h * dpr),
    )
    state._content_scissor_depth = 1
    return True

def end_content_scissor(widget, enabled):
    if not enabled:
        return
    state = widget.runtime_state
    if state._content_scissor_depth <= 0:
        return
    state._content_scissor_depth -= 1
    if state._content_scissor_depth == 0:
        gl.glDisable(gl.GL_SCISSOR_TEST)
