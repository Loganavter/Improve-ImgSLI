from __future__ import annotations

import logging

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt

CAPTURE_RING_AA_PX = 1.15
logger = logging.getLogger("ImproveImgSLI")

def _float_attr(obj, attr: str, default: float) -> float:
    if obj is None:
        return float(default)
    value = getattr(obj, attr, None)
    if value is None:
        return float(default)
    return float(value)

def _image_dimensions(image) -> tuple[int, int] | None:
    if image is None:
        return None
    width = getattr(image, "width", None)
    height = getattr(image, "height", None)
    if callable(width):
        width = width()
    if callable(height):
        height = height()
    if width is None or height is None:
        return None
    return int(width), int(height)

def _sync_split_to_store(widget, split_position: float) -> bool:
    state = widget.runtime_state
    store = getattr(state, "_store", None)
    viewport = getattr(store, "viewport", None) if store is not None else None
    view_state = getattr(viewport, "view_state", None) if viewport is not None else None
    if view_state is None:
        return False
    split = max(0.0, min(1.0, float(split_position)))
    old_split = _float_attr(view_state, "split_position", 0.5)
    old_split_visual = _float_attr(view_state, "split_position_visual", 0.5)
    if (
        abs(old_split - split) <= 1e-6
        and abs(old_split_visual - split) <= 1e-6
    ):
        return True
    view_state.split_position = split
    view_state.split_position_visual = split
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change("interaction")
    return True

def compute_split_position_for_view_transform(
    *,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
    is_horizontal: bool,
    split_position_visual: float,
    current_zoom: float,
    current_pan_x: float,
    current_pan_y: float,
    new_zoom: float,
    new_pan_x: float,
    new_pan_y: float,
) -> float | None:
    if image_width <= 0 or image_height <= 0 or widget_width <= 0 or widget_height <= 0:
        return None

    ratio = min(widget_width / image_width, widget_height / image_height)
    scaled_width = max(1, int(image_width * ratio))
    scaled_height = max(1, int(image_height * ratio))
    image_x = (widget_width - scaled_width) // 2
    image_y = (widget_height - scaled_height) // 2

    if is_horizontal:
        base = (image_y + scaled_height * split_position_visual) / widget_height
        old_pan = current_pan_y
    else:
        base = (image_x + scaled_width * split_position_visual) / widget_width
        old_pan = current_pan_x

    axis_widget_size = float(widget_height if is_horizontal else widget_width)
    axis_content_size = float(scaled_height if is_horizontal else scaled_width)
    axis_content_offset = float(image_y if is_horizontal else image_x)
    current_pan = float(current_pan_y if is_horizontal else current_pan_x)
    new_pan = float(new_pan_y if is_horizontal else new_pan_x)

    def _visible_axis_range(zoom: float, pan: float) -> tuple[float, float]:
        local_start = ((0.0 - 0.5) / max(float(zoom), 1e-6)) + 0.5 - pan
        local_end = ((1.0 - 0.5) / max(float(zoom), 1e-6)) + 0.5 - pan
        rel_start = ((local_start * axis_widget_size) - axis_content_offset) / max(axis_content_size, 1.0)
        rel_end = ((local_end * axis_widget_size) - axis_content_offset) / max(axis_content_size, 1.0)
        lo = max(0.0, min(1.0, min(rel_start, rel_end)))
        hi = max(0.0, min(1.0, max(rel_start, rel_end)))
        return lo, hi

    current_visible_min, current_visible_max = _visible_axis_range(current_zoom, current_pan)
    edge_epsilon = max(0.0025, 3.0 / max(axis_content_size, 1.0))
    explicit_edge_epsilon = 1e-6
    if split_position_visual <= explicit_edge_epsilon:
        new_visible_min, _ = _visible_axis_range(new_zoom, new_pan)
        return max(0.0, min(1.0, new_visible_min))
    if split_position_visual >= 1.0 - explicit_edge_epsilon:
        _, new_visible_max = _visible_axis_range(new_zoom, new_pan)
        return max(0.0, min(1.0, new_visible_max))

    screen_pos = (base - 0.5 + old_pan) * current_zoom + 0.5
    new_base = (screen_pos - 0.5) / new_zoom + 0.5 - new_pan

    if is_horizontal:
        new_split = (new_base * widget_height - image_y) / scaled_height if scaled_height > 0 else 0.5
    else:
        new_split = (new_base * widget_width - image_x) / scaled_width if scaled_width > 0 else 0.5

    clamped_split = max(0.0, min(1.0, new_split))
    return clamped_split

def update_paste_overlay_rects(widget):
    state = widget.runtime_state
    width = float(widget.width())
    height = float(widget.height())
    if width <= 0 or height <= 0:
        return

    center_x = width / 2.0
    center_y = height / 2.0
    button_size = state._paste_overlay_button_size
    spacing = state._paste_overlay_spacing
    center_size = state._paste_overlay_center_size

    empty = QRectF()
    state._paste_overlay_rects["up"] = empty
    state._paste_overlay_rects["down"] = empty
    state._paste_overlay_rects["left"] = empty
    state._paste_overlay_rects["right"] = empty

    if state._paste_overlay_horizontal:
        state._paste_overlay_rects["up"] = QRectF(
            center_x - button_size / 2.0,
            center_y - button_size - spacing / 2.0 - center_size / 2.0,
            button_size,
            button_size,
        )
        state._paste_overlay_rects["down"] = QRectF(
            center_x - button_size / 2.0,
            center_y + spacing / 2.0 + center_size / 2.0,
            button_size,
            button_size,
        )
    else:
        state._paste_overlay_rects["left"] = QRectF(
            center_x - button_size - spacing / 2.0 - center_size / 2.0,
            center_y - button_size / 2.0,
            button_size,
            button_size,
        )
        state._paste_overlay_rects["right"] = QRectF(
            center_x + spacing / 2.0 + center_size / 2.0,
            center_y - button_size / 2.0,
            button_size,
            button_size,
        )

    state._paste_overlay_rects["cancel"] = QRectF(
        center_x - center_size / 2.0,
        center_y - center_size / 2.0,
        center_size,
        center_size,
    )

def set_paste_overlay_state(
    widget,
    visible: bool,
    is_horizontal: bool = False,
    texts: dict | None = None,
):
    state = widget.runtime_state
    state._paste_overlay_visible = visible
    state._paste_overlay_horizontal = is_horizontal
    if texts is not None:
        state._paste_overlay_texts = {
            "up": texts.get("up", ""),
            "down": texts.get("down", ""),
            "left": texts.get("left", ""),
            "right": texts.get("right", ""),
        }
    if not visible:
        state._paste_overlay_hovered_button = None
        widget.unsetCursor()
    update_paste_overlay_rects(widget)
    widget.update()

def set_drag_overlay_state(
    widget,
    visible: bool,
    horizontal: bool = False,
    text1: str = "",
    text2: str = "",
):
    state = widget.runtime_state
    visible = bool(visible)
    new_texts = (text1, text2)
    if (
        state._drag_overlay_visible == visible
        and state._drag_overlay_horizontal == horizontal
        and state._drag_overlay_texts == new_texts
    ):
        return

    state._drag_overlay_visible = visible
    state._drag_overlay_horizontal = horizontal
    state._drag_overlay_texts = new_texts
    state._drag_overlay_cache_key = None
    state._drag_overlay_cached_image = None
    widget.update()

def paste_overlay_button_at(widget, pos: QPointF | QPoint) -> str | None:
    state = widget.runtime_state
    if not state._paste_overlay_visible:
        return None

    point = QPointF(pos)
    for direction in ("up", "down", "left", "right", "cancel"):
        rect = state._paste_overlay_rects.get(direction)
        if rect is not None and not rect.isNull() and rect.contains(point):
            return direction
    return None

def set_paste_overlay_hover(widget, hovered: str | None):
    state = widget.runtime_state
    if state._paste_overlay_hovered_button == hovered:
        return
    state._paste_overlay_hovered_button = hovered
    if hovered is None:
        widget.unsetCursor()
    else:
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.update()

def update_split_for_zoom(widget, new_zoom, new_pan_x, new_pan_y):
    state = widget.runtime_state
    scene = state._render_scene
    sync_callback = state._split_position_sync
    store = getattr(state, "_store", None)
    view_state = getattr(getattr(store, "viewport", None), "view_state", None) if store is not None else None
    if scene is None and view_state is None:
        return

    w, h = widget.width(), widget.height()
    img1 = state._stored_pil_images[0] if state._stored_pil_images else None
    dims = _image_dimensions(img1)
    if dims is None or w <= 0 or h <= 0:
        return
    image_width, image_height = dims
    is_horizontal = bool(
        getattr(scene, "is_horizontal", getattr(view_state, "is_horizontal", False))
    )
    scene_split_visual = _float_attr(
        scene,
        "split_position_visual",
        _float_attr(widget, "split_position", 0.5),
    )
    view_split = _float_attr(view_state, "split_position", scene_split_visual)
    view_split_visual = _float_attr(
        view_state,
        "split_position_visual",
        scene_split_visual,
    )
    split_visual = view_split_visual

    new_split = compute_split_position_for_view_transform(
        widget_width=w,
        widget_height=h,
        image_width=image_width,
        image_height=image_height,
        is_horizontal=is_horizontal,
        split_position_visual=split_visual,
        current_zoom=float(widget.zoom_level),
        current_pan_x=float(widget.pan_offset_x),
        current_pan_y=float(widget.pan_offset_y),
        new_zoom=float(new_zoom),
        new_pan_x=float(new_pan_x),
        new_pan_y=float(new_pan_y),
    )
    if new_split is not None:
        synced = False
        if sync_callback is not None:
            try:
                sync_callback(new_split)
                synced = True
            except Exception:
                logger.exception("Split sync callback failed during view transform")
        if not synced:
            _sync_split_to_store(widget, new_split)

def set_split_line_params(
    widget,
    visible: bool,
    pos: int,
    is_horizontal: bool,
    color,
    thickness: int,
):
    state = widget.runtime_state
    state._show_divider = visible
    state._split_pos = pos
    state._is_horizontal_split = is_horizontal
    state._divider_color = color
    state._divider_thickness = thickness

    widget.is_horizontal = is_horizontal
    if visible:
        widget_size = widget.width() if not is_horizontal else widget.height()
        if widget_size > 0:
            widget.display_split_position = pos / widget_size

    widget._request_update()

def set_guides_params(widget, visible: bool, color, thickness: int):
    state = widget.runtime_state
    state._show_guides = visible
    state._laser_color = color
    state._guides_thickness = thickness
    widget._request_update()

def set_capture_color(widget, color):
    widget.runtime_state._capture_color = color
    widget._request_update()

def set_capture_area(widget, center: QPoint | None, size: int, color=None):
    state = widget.runtime_state
    if center:
        capture_center = QPointF(center)
        capture_radius = size / 2.0
        content_rect = state._content_rect_px
        zoom_level = float(getattr(widget, "zoom_level", 1.0) or 1.0)
        scaled_radius = capture_radius * zoom_level
        line_width_px = max(2.0, float(scaled_radius * 2.0) * 0.0105)
        stroke_margin_widget = ((line_width_px / 2.0) + CAPTURE_RING_AA_PX) / max(
            zoom_level, 1e-6
        )

        if content_rect is not None:
            rect_x, rect_y, rect_w, rect_h = content_rect
            left = float(rect_x) + stroke_margin_widget
            top = float(rect_y) + stroke_margin_widget
            right = float(rect_x + rect_w) - stroke_margin_widget
            bottom = float(rect_y + rect_h) - stroke_margin_widget

            max_radius_x = max(0.0, (right - left) / 2.0)
            max_radius_y = max(0.0, (bottom - top) / 2.0)
            capture_radius = min(capture_radius, max_radius_x, max_radius_y)

            capture_center = QPointF(
                min(max(capture_center.x(), left + capture_radius), right - capture_radius),
                min(max(capture_center.y(), top + capture_radius), bottom - capture_radius),
            )

        state._capture_center = capture_center
        state._capture_radius = capture_radius
    else:
        state._capture_center = None
        state._capture_radius = 0
    if color:
        state._capture_color = color
    widget._request_update()

def set_overlay_coords(
    widget,
    capture_center: QPointF | None,
    capture_radius: float,
    mag_centers: list[QPointF],
    mag_radius: float,
):
    state = widget.runtime_state
    state._capture_center = capture_center
    state._capture_radius = capture_radius
    state._magnifier_centers = mag_centers
    state._magnifier_radius = mag_radius
    if capture_center is None:
        state._mag_quads[0] = None
        state._mag_quads[1] = None
        state._mag_quads[2] = None
        state._mag_combined_params[0] = None
        state._mag_combined_params[1] = None
        state._mag_combined_params[2] = None
        state._mag_quad_ndc = None
    widget._request_update()

def set_zoom(widget, zoom: float):
    new_zoom = max(1.0, min(zoom, 50.0))
    if abs(new_zoom - widget.zoom_level) <= 1e-6:
        return
    update_split_for_zoom(
        widget,
        new_zoom,
        float(getattr(widget, "pan_offset_x", 0.0) or 0.0),
        float(getattr(widget, "pan_offset_y", 0.0) or 0.0),
    )
    widget.zoom_level = new_zoom
    widget.zoomChanged.emit(widget.zoom_level)
    widget.update()

def set_pan(widget, x: float, y: float):
    new_pan_x = float(x or 0.0)
    new_pan_y = float(y or 0.0)
    update_split_for_zoom(
        widget,
        float(getattr(widget, "zoom_level", 1.0) or 1.0),
        new_pan_x,
        new_pan_y,
    )
    widget.pan_offset_x = x
    widget.pan_offset_y = y
    widget.update()

def reset_view(widget):
    zoom_changed = abs(widget.zoom_level - 1.0) > 1e-6
    widget.zoom_level = 1.0
    widget.pan_offset_x = 0.0
    widget.pan_offset_y = 0.0
    if zoom_changed:
        widget.zoomChanged.emit(widget.zoom_level)
    widget.update()

def handle_wheel_event(widget, event):
    modifiers = event.modifiers()

    if modifiers & Qt.KeyboardModifier.ControlModifier:
        angle = event.angleDelta().y()
        factor = 1.1 if angle > 0 else 0.9
        new_zoom = max(1.0, min(widget.zoom_level * factor, 50.0))

        if new_zoom != widget.zoom_level:
            w, h = widget.width(), widget.height()
            if w > 0 and h > 0:
                mx = event.position().x() / w
                my = event.position().y() / h

                uv_x = (mx - 0.5) / widget.zoom_level + 0.5 - widget.pan_offset_x
                uv_y = (my - 0.5) / widget.zoom_level + 0.5 - widget.pan_offset_y
                uv_x = max(0.0, min(1.0, uv_x))
                uv_y = max(0.0, min(1.0, uv_y))

                new_pan_x = 0.5 - uv_x + (mx - 0.5) / new_zoom
                new_pan_y = 0.5 - uv_y + (my - 0.5) / new_zoom

                if new_zoom < 1.5:
                    t = max(0.0, (new_zoom - 1.0) / 0.5)
                    new_pan_x *= t
                    new_pan_y *= t

                update_split_for_zoom(widget, new_zoom, new_pan_x, new_pan_y)

                widget.pan_offset_x = new_pan_x
                widget.pan_offset_y = new_pan_y

            widget.zoom_level = new_zoom
            widget.zoomChanged.emit(widget.zoom_level)
            widget.update()

        event.accept()
        return

    widget.wheelScrolled.emit(event)

def handle_mouse_press_event(widget, event):
    if widget.runtime_state._paste_overlay_visible and event.button() == Qt.MouseButton.LeftButton:
        button = paste_overlay_button_at(widget, event.position())
        if button == "cancel" or button is None:
            set_paste_overlay_state(widget, False)
            widget.pasteOverlayCancelled.emit()
        else:
            set_paste_overlay_state(widget, False)
            widget.pasteOverlayDirectionSelected.emit(button)
        event.accept()
        return
    if event.button() == Qt.MouseButton.MiddleButton:
        widget._pan_dragging = True
        widget._pan_last_pos = event.position()
        widget.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()
        return
    widget.mousePressed.emit(event)

def handle_mouse_release_event(widget, event):
    if event.button() == Qt.MouseButton.MiddleButton and getattr(widget, "_pan_dragging", False):
        widget._pan_dragging = False
        widget.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()
        return
    widget.mouseReleased.emit(event)

def handle_mouse_move_event(widget, event):
    if getattr(widget, "_pan_dragging", False) and widget.zoom_level > 1.0:
        w, h = widget.width(), widget.height()
        if w > 0 and h > 0:
            dx = (event.position().x() - widget._pan_last_pos.x()) / (w * widget.zoom_level)
            dy = (event.position().y() - widget._pan_last_pos.y()) / (h * widget.zoom_level)
            new_pan_x = widget.pan_offset_x + dx
            new_pan_y = widget.pan_offset_y + dy
            update_split_for_zoom(widget, widget.zoom_level, new_pan_x, new_pan_y)
            widget.pan_offset_x = new_pan_x
            widget.pan_offset_y = new_pan_y
            widget._pan_last_pos = event.position()
            widget.update()
        event.accept()
        return
    if widget.runtime_state._paste_overlay_visible:
        set_paste_overlay_hover(widget, paste_overlay_button_at(widget, event.position()))
        event.accept()
        return
    widget.mouseMoved.emit(event)

def handle_key_press_event(widget, event):
    state = widget.runtime_state
    if state._paste_overlay_visible:
        key_to_direction = {
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_W: "up",
            Qt.Key.Key_Down: "down",
            Qt.Key.Key_S: "down",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_A: "left",
            Qt.Key.Key_Right: "right",
            Qt.Key.Key_D: "right",
        }
        if event.key() == Qt.Key.Key_Escape:
            set_paste_overlay_state(widget, False)
            widget.pasteOverlayCancelled.emit()
            event.accept()
            return
        direction = key_to_direction.get(event.key())
        if direction and not state._paste_overlay_rects[direction].isNull():
            set_paste_overlay_state(widget, False)
            widget.pasteOverlayDirectionSelected.emit(direction)
            event.accept()
            return
    widget.keyPressed.emit(event)

def handle_key_release_event(widget, event):
    widget.keyReleased.emit(event)

def handle_leave_event(widget, event):
    if widget.runtime_state._paste_overlay_visible:
        set_paste_overlay_hover(widget, None)
    super(type(widget), widget).leaveEvent(event)
