from __future__ import annotations

import logging

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt

_log = logging.getLogger("ImproveImgSLI.feature_overlay.interaction")

from ui.canvas_infra.viewport.state import (
    get_pan_offset_x,
    get_pan_offset_y,
    get_zoom_level,
    set_pan_offsets,
    set_zoom_level,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
from ui.canvas_infra.viewport.contract import (
    PanDragRequest,
    SplitPositionForViewTransformRequest,
    WheelZoomRequest,
)
from ui.canvas_infra.viewport.pipeline import (
    compute_pan_drag_transform,
    compute_split_position_for_view_transform as compute_split_position_for_view_transform_via_feature,
    compute_wheel_zoom_transform,
)
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
    command = get_canvas_feature_command_by_alias("splitter.sync_split_position")
    if command is not None:
        command(type("WidgetActions", (), {"store": store})(), split)
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
    return compute_split_position_for_view_transform_via_feature(
        SplitPositionForViewTransformRequest(
            widget_width=widget_width,
            widget_height=widget_height,
            image_width=image_width,
            image_height=image_height,
            is_horizontal=is_horizontal,
            split_position_visual=split_position_visual,
            current_zoom=current_zoom,
            current_pan_x=current_pan_x,
            current_pan_y=current_pan_y,
            new_zoom=new_zoom,
            new_pan_x=new_pan_x,
            new_pan_y=new_pan_y,
        )
    )

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
        current_zoom=get_zoom_level(widget),
        current_pan_x=get_pan_offset_x(widget),
        current_pan_y=get_pan_offset_y(widget),
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
                logging.getLogger("ImproveImgSLI").exception(
                    "Split sync callback failed during view transform"
                )
        if not synced:
            _sync_split_to_store(widget, new_split)

def set_guides_params(widget, visible: bool, color, thickness: int):
    state = widget.runtime_state
    if (
        bool(state._show_guides) == bool(visible)
        and state._laser_color == color
        and int(state._guides_thickness or 0) == int(thickness or 0)
    ):
        return
    state._show_guides = visible
    state._laser_color = color
    state._guides_thickness = thickness
    widget._request_update()

def set_capture_color(widget, color):
    if widget.runtime_state._capture_color == color:
        return
    widget.runtime_state._capture_color = color
    widget._request_update()

def set_capture_area(widget, center: QPoint | None, size: int, color=None):
    state = widget.runtime_state
    if center:
        capture_center = QPointF(center)
        capture_radius = size / 2.0
        content_rect = state._content_rect_px

        if content_rect is not None:
            rect_x, rect_y, rect_w, rect_h = content_rect
            left = float(rect_x)
            top = float(rect_y)
            right = float(rect_x + rect_w)
            bottom = float(rect_y + rect_h)

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
    overlay_centers: list[QPointF],
    overlay_radius: float,
):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    current_capture_center = state._capture_center
    current_overlay_centers = overlay._centers
    same_capture_center = (
        (current_capture_center is None and capture_center is None)
        or (
            current_capture_center is not None
            and capture_center is not None
            and abs(current_capture_center.x() - capture_center.x()) <= 1e-6
            and abs(current_capture_center.y() - capture_center.y()) <= 1e-6
        )
    )
    same_overlay_centers = len(current_overlay_centers) == len(overlay_centers) and all(
        abs(existing.x() - incoming.x()) <= 1e-6
        and abs(existing.y() - incoming.y()) <= 1e-6
        for existing, incoming in zip(current_overlay_centers, overlay_centers)
    )
    if (
        same_capture_center
        and abs(float(state._capture_radius or 0.0) - float(capture_radius or 0.0)) <= 1e-6
        and same_overlay_centers
        and abs(float(overlay._radius or 0.0) - float(overlay_radius or 0.0)) <= 1e-6
    ):
        return
    state._capture_center = capture_center
    state._capture_radius = capture_radius
    overlay._centers = overlay_centers
    overlay._radius = overlay_radius
    if capture_center is None:
        state._capture_circles = []
        state._guide_sets = []
        state._occluded_capture_arcs = []
        for i in range(len(overlay._quads)):
            overlay._quads[i] = None
        for i in range(len(overlay._combined_params)):
            overlay._combined_params[i] = None
        state._feature_overlay_quad_ndc = None
    widget._request_update()

def set_zoom(widget, zoom: float):
    if bool(getattr(widget.runtime_state, "_read_only", False)):
        return
    new_zoom = max(0.1, min(zoom, 50.0))
    if abs(new_zoom - get_zoom_level(widget)) <= 1e-6:
        return
    update_split_for_zoom(
        widget,
        new_zoom,
        get_pan_offset_x(widget),
        get_pan_offset_y(widget),
    )
    set_zoom_level(widget, new_zoom)
    widget.zoomChanged.emit(get_zoom_level(widget))
    widget.update()

def set_pan(widget, x: float, y: float):
    if bool(getattr(widget.runtime_state, "_read_only", False)):
        return
    new_pan_x = float(x or 0.0)
    new_pan_y = float(y or 0.0)
    update_split_for_zoom(
        widget,
        get_zoom_level(widget),
        new_pan_x,
        new_pan_y,
    )
    set_pan_offsets(widget, x, y)
    widget.update()

def reset_view(widget):
    zoom_changed = abs(get_zoom_level(widget) - 1.0) > 1e-6
    pan_changed = (
        abs(get_pan_offset_x(widget)) > 1e-9
        or abs(get_pan_offset_y(widget)) > 1e-9
    )
    set_zoom_level(widget, 1.0)
    set_pan_offsets(widget, 0.0, 0.0)
    if zoom_changed or pan_changed:
        widget.zoomChanged.emit(get_zoom_level(widget))
    widget.update()

def handle_wheel_event(widget, event):
    if bool(getattr(widget.runtime_state, "_read_only", False)):
        event.accept()
        return

    modifiers = event.modifiers()

    if modifiers & Qt.KeyboardModifier.ControlModifier:
        result = compute_wheel_zoom_transform(
            WheelZoomRequest(
                widget_width=widget.width(),
                widget_height=widget.height(),
                mouse_x=float(event.position().x()),
                mouse_y=float(event.position().y()),
                current_zoom=get_zoom_level(widget),
                current_pan_x=get_pan_offset_x(widget),
                current_pan_y=get_pan_offset_y(widget),
                angle_delta_y=int(event.angleDelta().y()),
            )
        )
        if result is not None:
            new_zoom, new_pan_x, new_pan_y = result
            update_split_for_zoom(widget, new_zoom, new_pan_x, new_pan_y)
            set_pan_offsets(widget, new_pan_x, new_pan_y)
            set_zoom_level(widget, new_zoom)
            widget.zoomChanged.emit(get_zoom_level(widget))
            widget.update()

        event.accept()
        return

    widget.wheelScrolled.emit(event)

def handle_mouse_press_event(widget, event):
    if bool(getattr(widget.runtime_state, "_read_only", False)):
        event.accept()
        return

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
    if bool(getattr(widget.runtime_state, "_read_only", False)):
        widget._pan_dragging = False
        event.accept()
        return

    if event.button() == Qt.MouseButton.MiddleButton and getattr(widget, "_pan_dragging", False):
        widget._pan_dragging = False
        widget.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()
        return
    widget.mouseReleased.emit(event)

def handle_mouse_move_event(widget, event):
    if bool(getattr(widget.runtime_state, "_read_only", False)):
        event.accept()
        return

    if getattr(widget, "_pan_dragging", False):
        result = compute_pan_drag_transform(
            PanDragRequest(
                widget_width=widget.width(),
                widget_height=widget.height(),
                current_zoom=get_zoom_level(widget),
                current_pan_x=get_pan_offset_x(widget),
                current_pan_y=get_pan_offset_y(widget),
                last_mouse_x=float(widget._pan_last_pos.x()),
                last_mouse_y=float(widget._pan_last_pos.y()),
                mouse_x=float(event.position().x()),
                mouse_y=float(event.position().y()),
            )
        )
        if result is not None:
            new_pan_x, new_pan_y = result
            update_split_for_zoom(widget, get_zoom_level(widget), new_pan_x, new_pan_y)
            set_pan_offsets(widget, new_pan_x, new_pan_y)
            widget._pan_last_pos = event.position()
            widget.zoomChanged.emit(get_zoom_level(widget))
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
