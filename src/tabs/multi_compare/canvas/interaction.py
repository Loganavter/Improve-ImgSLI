"""Chrome input handling for multi-compare canvas (zoom/pan/keys/context).

Feature-specific gestures (dividers, slot drag) stay in
``canvas/features/*/input/`` and are routed via ``gesture_resolver``.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QWidget

from tabs.multi_compare.canvas.features.grid_dividers.input.hit import divider_at
from tabs.multi_compare.canvas.gesture_resolver import (
    GesturePressContext,
    iter_active,
    resolve_press,
)
from tabs.multi_compare.models import CompareSlot, LeafNode
from tabs.multi_compare.scene import actions
from tabs.multi_compare.ui.canvas_helpers import INTERNAL_SLOT_MIME, _dividers_locked
from ui.context_menu.manager import open_context_menu
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget


def clamp_pan_values(
    pan_x: float, pan_y: float, zoom: float
) -> tuple[float, float]:
    """Clamp pan so the image edges never reveal more than allowed travel.

    Derivation for zoom > 1: img_uv = (cell_uv − 0.5)/(fit·zoom) + 0.5 − pan.
    The visible image region in cell-uv is [0.5 ± fit/2], at whose ends
    img_uv = 0 or 1 before pan. Forcing img_uv ∈ [0, 1] across that range
    yields |pan| ≤ (zoom − 1) / (2·zoom), independent of fit.

    At zoom ≤ 1 that classic limit is 0; allow half-cell travel so
    middle-button pan still works at fit zoom (may reveal letterbox).
    """
    z = max(float(zoom), 1e-6)
    if z <= 1.0:
        limit = 0.5
    else:
        limit = (z - 1.0) / (2.0 * z)
    return max(-limit, min(limit, pan_x)), max(-limit, min(limit, pan_y))


def fit_scale_for(slot: CompareSlot, rect) -> tuple[float, float]:
    if slot.image is None or rect.width() <= 0 or rect.height() <= 0:
        return 1.0, 1.0
    w, h = slot.image.width, slot.image.height
    if h <= 0 or w <= 0:
        return 1.0, 1.0
    img_ar = w / h
    cell_ar = rect.width() / rect.height()
    if img_ar > cell_ar:
        return 1.0, cell_ar / img_ar
    return img_ar / cell_ar, 1.0


def leaf_at(pos: QPoint, leaf_rects) -> tuple[LeafNode, object] | None:
    for leaf, rect in leaf_rects:
        if rect.contains(pos):
            return leaf, rect
    return None


def handle_wheel_event(widget, event: QWheelEvent) -> None:
    delta = event.angleDelta().y()
    leaf_rects = widget._leaf_rects()
    if not leaf_rects:
        event.ignore()
        return

    pos = event.position().toPoint()
    picked = leaf_at(pos, leaf_rects)
    leaf, rect = picked or (None, None)
    if leaf is None:
        event.ignore()
        return

    slot = next((s for s in widget.state.slots if s.id == leaf.slot_id), None)
    if slot is None:
        event.ignore()
        return

    fit_x, fit_y = fit_scale_for(slot, rect)
    cell_u = (pos.x() - rect.x()) / rect.width()
    cell_v = (pos.y() - rect.y()) / rect.height()

    if delta == 0:
        event.accept()
        return
    factor = widget.ZOOM_STEP if delta > 0 else 1.0 / widget.ZOOM_STEP
    z1 = widget.state.zoom
    z2 = max(widget.ZOOM_MIN, min(widget.ZOOM_MAX, z1 * factor))
    if z2 == z1:
        event.accept()
        return

    new_pan_x = widget.state.pan_x + (cell_u - 0.5) / max(fit_x, 1e-6) * (
        1.0 / z2 - 1.0 / z1
    )
    new_pan_y = widget.state.pan_y + (cell_v - 0.5) / max(fit_y, 1e-6) * (
        1.0 / z2 - 1.0 / z1
    )
    new_pan_x, new_pan_y = clamp_pan_values(new_pan_x, new_pan_y, z2)
    widget._do_dispatch(actions.set_zoom(z2, new_pan_x, new_pan_y))
    event.accept()


def handle_mouse_press_event(widget, event: QMouseEvent) -> None:
    pos = event.position().toPoint()

    if event.button() == Qt.MouseButton.RightButton:
        picked = leaf_at(pos, widget._leaf_rects())
        if picked is None:
            return
        leaf, rect = picked
        slot = next((s for s in widget.state.slots if s.id == leaf.slot_id), None)
        open_context_menu(
            ContextMenuRequest(
                source_widget=widget,
                global_pos=event.globalPosition().toPoint(),
                local_pos=pos,
                session_type="multi_compare",
                target=ContextMenuTarget(
                    kind="multi_compare_slot",
                    id=leaf.slot_id,
                    payload={
                        "rect": rect,
                        "path": slot.path if slot is not None else None,
                        "label": slot.label if slot is not None else "",
                    },
                ),
            )
        )
        event.accept()
        return

    if event.button() == Qt.MouseButton.LeftButton:
        ctx = GesturePressContext(
            handler=widget,
            local_pos=event.position(),
            button=event.button().value,
            modifiers=int(event.modifiers().value),
        )
        binding = resolve_press(ctx)
        if binding is not None:
            if binding.begin is not None:
                binding.begin(widget, event.position())
            event.accept()
            return

    if event.button() == Qt.MouseButton.MiddleButton:
        widget._panning = True
        widget._pan_start_pos = event.position()
        widget._pan_start_state = (widget.state.pan_x, widget.state.pan_y)
        leaf_rects = widget._leaf_rects()
        picked = leaf_at(pos, leaf_rects)
        if picked is not None:
            leaf, rect = picked
            slot = next((s for s in widget.state.slots if s.id == leaf.slot_id), None)
            widget._pan_ref_rect = rect
            widget._pan_ref_fit = (
                fit_scale_for(slot, rect) if slot is not None else (1.0, 1.0)
            )
        else:
            widget._pan_ref_rect = widget.rect()
            widget._pan_ref_fit = (1.0, 1.0)
        widget.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()
        return


def handle_mouse_move_event(widget, event: QMouseEvent) -> None:
    active = iter_active(widget)
    if active:
        buttons = event.buttons()
        consumed = False
        for binding in active:
            if not (buttons & Qt.MouseButton(binding.button)):
                continue
            if binding.update is not None:
                binding.update(widget, event.position())
                consumed = True
        if consumed:
            event.accept()
            return

    if widget._panning:
        ref = widget._pan_ref_rect
        if ref.width() <= 0 or ref.height() <= 0:
            return
        fit_x, fit_y = widget._pan_ref_fit
        z = max(widget.state.zoom, 1e-6)
        delta = event.position() - widget._pan_start_pos
        new_pan_x = widget._pan_start_state[0] + (delta.x() / ref.width()) / (
            max(fit_x, 1e-6) * z
        )
        new_pan_y = widget._pan_start_state[1] + (delta.y() / ref.height()) / (
            max(fit_y, 1e-6) * z
        )
        new_pan_x, new_pan_y = clamp_pan_values(
            new_pan_x, new_pan_y, widget.state.zoom
        )
        widget._do_dispatch(actions.set_pan(new_pan_x, new_pan_y))
        event.accept()
        return

    div = divider_at(widget, event.position())
    if div is not None and not _dividers_locked(widget.state):
        _path, _idx, _rect, direction, _ws = div
        widget.setCursor(
            Qt.CursorShape.SplitHCursor
            if direction == "h"
            else Qt.CursorShape.SplitVCursor
        )
    else:
        widget.setCursor(Qt.CursorShape.ArrowCursor)


def handle_mouse_release_event(widget, event: QMouseEvent) -> None:
    released_button = event.button().value
    ended_any = False
    for binding in iter_active(widget):
        if binding.button != released_button:
            continue
        if binding.end is not None:
            binding.end(widget)
        ended_any = True
    if ended_any:
        event.accept()
        return
    if event.button() == Qt.MouseButton.MiddleButton and widget._panning:
        widget._panning = False
        widget.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()


def handle_mouse_double_click_event(widget, event: QMouseEvent) -> None:
    if event.button() == Qt.MouseButton.LeftButton:
        pos = event.position().toPoint()
        div = divider_at(widget, event.position())
        if div is not None:
            split_path, _idx, _drect, _direction, weights = div
            n = len(weights)
            if n > 0:
                widget._do_dispatch(actions.set_split_weights(split_path, [1.0] * n))
            event.accept()
            return
        leaf_rects = widget._leaf_rects()
        picked = leaf_at(pos, leaf_rects)
        if picked is not None:
            leaf, _ = picked
            new_focus = None if widget.state.is_focused else leaf.slot_id
            widget._do_dispatch(actions.set_focus(new_focus))
        event.accept()


def handle_key_press_event(widget, event) -> None:
    key = event.key()
    if key == Qt.Key.Key_Escape and widget.state.is_focused:
        widget._do_dispatch(actions.set_focus(None))
        event.accept()
    elif key == Qt.Key.Key_0:
        widget._do_dispatch(actions.reset_view())
        event.accept()
    else:
        QWidget.keyPressEvent(widget, event)


def start_internal_drag(widget, slot_id: int) -> None:
    slot = next((s for s in widget.state.slots if s.id == slot_id), None)
    mime = QMimeData()
    mime.setData(INTERNAL_SLOT_MIME, str(slot_id).encode("utf-8"))
    drag = QDrag(widget)
    drag.setMimeData(mime)

    rects = widget._leaf_rects()
    rect = next((r for l, r in rects if l.slot_id == slot_id), None)
    if rect is not None and slot is not None and slot.image is not None:
        from PySide6.QtGui import QPixmap

        from shared.image_processing.tiled_pixel_store import qimage_from_pixel_source

        qimg = qimage_from_pixel_source(slot.image)
        preview = QPixmap.fromImage(qimg).scaledToWidth(
            160, Qt.TransformationMode.SmoothTransformation
        )
        drag.setPixmap(preview)
        drag.setHotSpot(QPoint(preview.width() // 2, preview.height() // 2))
    drag.exec(Qt.DropAction.MoveAction)
