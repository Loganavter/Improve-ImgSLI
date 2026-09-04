"""Chrome input handling for multi-compare canvas (zoom/pan/keys/context).

Feature-specific gestures (dividers, slot drag) stay in
``canvas/features/*/input/`` and are routed via ``gesture_resolver``.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt
from PySide6.QtGui import QContextMenuEvent, QDrag, QMouseEvent, QWheelEvent
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
    """No-op: pan is unrestricted, matching image_compare's free pan/zoom
    (``ui/canvas_infra/viewport/zoom.py``'s ``compute_zoom_pan_drag_transform``/
    ``compute_zoom_wheel_transform``, neither of which clamps pan)."""
    return pan_x, pan_y


def fit_scale_for(slot: CompareSlot, rect: QRect, source=None) -> tuple[float, float]:
    """Fit scale from the slot's cached tier (B1: ``source`` passed by the caller).

    ``None`` source (imageless slot) reads as ``(1.0, 1.0)``, same as an
    imageless slot before B1.
    """
    if source is None or rect.width() <= 0 or rect.height() <= 0:
        return 1.0, 1.0
    from shared.image_processing.tiled_pixel_store import pixel_source_size

    w, h = pixel_source_size(source)
    if h <= 0 or w <= 0:
        return 1.0, 1.0
    img_ar = w / h
    cell_ar = rect.width() / rect.height()
    if img_ar > cell_ar:
        return 1.0, cell_ar / img_ar
    return img_ar / cell_ar, 1.0


def _source_for(widget, slot):
    """Cached tier for hit-test math (canvas owns the ``pixel_cache`` ref)."""
    try:
        from tabs.multi_compare.pipeline.cache import resolve_slot_source

        return resolve_slot_source(getattr(widget, "pixel_cache", None), slot)
    except Exception:
        return None


def leaf_at(pos: QPoint, leaf_rects) -> tuple[LeafNode, QRect] | None:
    for leaf, rect in leaf_rects:
        if rect.contains(pos):
            return leaf, rect
    return None


def _focused_image_rect(widget) -> QRect | None:
    """Widget-px rect of the actually displayed image while focused.

    Mirrors ``canvas/features/focus_dim/passes.py``'s letterbox math (same
    ``_canvas_layout()`` the renderer's own hit-testing uses) so clicks
    outside it are recognized as landing on the dimmed chrome, not the image.
    """
    layout = widget._canvas_layout()
    if layout is None:
        return None
    canvas_w, canvas_h, sr, ox, oy = layout
    return QRect(
        int(round(ox)),
        int(round(oy)),
        max(1, int(round(canvas_w * sr))),
        max(1, int(round(canvas_h * sr))),
    )


def _swallow_focus_dim_click(widget, pos: QPoint) -> bool:
    """If focused and ``pos`` lands outside the image (on the dimmed
    letterbox chrome), exit focus and report the click as consumed."""
    if not widget.state.is_focused:
        return False
    rect = _focused_image_rect(widget)
    if rect is not None and rect.contains(pos):
        return False
    widget._do_dispatch(actions.set_focus(None))
    return True


def handle_wheel_event(widget, event: QWheelEvent) -> None:
    from ui.canvas_infra.rhi.rhi_present_sync import ensure_window_active_for_qrhi

    # Wayland+Vulkan often marks the app Inactive while the user still
    # scrolls the MC canvas; keep the window active so presents stay visible.
    ensure_window_active_for_qrhi(widget)
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
    assert rect is not None

    slot = next((s for s in widget.state.slots if s.id == leaf.slot_id), None)
    if slot is None:
        event.ignore()
        return

    fit_x, fit_y = fit_scale_for(slot, rect, _source_for(widget, slot))
    cell_u = (pos.x() - rect.x()) / rect.width()
    cell_v = (pos.y() - rect.y()) / rect.height()

    if delta == 0:
        event.accept()
        return
    # Scale by delta magnitude (Qt's 120-units-per-notch convention), not
    # just sign -- see docs/dev/rendering/tile-array-atlas-plan.md Findings
    # (image_compare's compute_zoom_wheel_transform had the same fixed-step-
    # per-event bug: a coalesced multi-notch burst produced the same tiny
    # step as a single click).
    notches = delta / 120.0
    factor = widget.ZOOM_STEP**notches
    z1 = widget.state.zoom
    z2 = max(widget.ZOOM_MIN, min(widget.ZOOM_MAX, z1 * factor))
    if z2 == z1:
        event.accept()
        return

    if z2 <= widget.ZOOM_MIN:
        # At the zoom floor there's no meaningful cursor-anchored offset left
        # (the whole cell is in view) -- snap pan to origin instead of
        # carrying over the last wheel step's clamped remainder, which would
        # otherwise leave a tiny nonzero pan that keeps the zoom indicator
        # visible even though zoom is back at its default.
        new_pan_x, new_pan_y = 0.0, 0.0
    else:
        new_pan_x = widget.state.pan_x + (cell_u - 0.5) / max(fit_x, 1e-6) * (
            1.0 / z2 - 1.0 / z1
        )
        new_pan_y = widget.state.pan_y + (cell_v - 0.5) / max(fit_y, 1e-6) * (
            1.0 / z2 - 1.0 / z1
        )
        new_pan_x, new_pan_y = clamp_pan_values(new_pan_x, new_pan_y, z2)
    widget._do_dispatch(actions.set_zoom(z2, new_pan_x, new_pan_y))
    event.accept()


def _rmb_surface_override():
    """Optional A/B: ``IMGSLI_MC_RMB_SURFACE=in_window|popup``."""
    import os

    raw = os.environ.get("IMGSLI_MC_RMB_SURFACE", "").strip().lower()
    if raw in ("in_window", "popup"):
        return raw
    return None


def handle_context_menu_event(widget, event: QContextMenuEvent) -> None:
    """Open the slot menu on Qt's context-menu request (not RMB press).

    Match Image Compare: manager defaults (``popup`` on Linux) with the QRhi
    canvas as the toolkit parent. Do **not** set ``menu_parent`` to MainWindow —
    that caused a one-frame clear wipe on Wayland while IC (canvas parent)
    stays stable.

    Optional A/B: ``IMGSLI_MC_RMB_SURFACE=in_window|popup``.
    """
    pos = event.pos()
    if _swallow_focus_dim_click(widget, pos):
        event.accept()
        return
    picked = leaf_at(pos, widget._leaf_rects())
    if picked is None:
        event.ignore()
        return
    leaf, rect = picked
    slot = next((s for s in widget.state.slots if s.id == leaf.slot_id), None)

    from ui.canvas_infra.rhi.rhi_present_sync import ensure_window_active_for_qrhi

    ensure_window_active_for_qrhi(widget)

    menu = open_context_menu(
        ContextMenuRequest(
            source_widget=widget,
            global_pos=event.globalPos(),
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
            surface=_rmb_surface_override(),
        )
    )
    if menu is None:
        event.ignore()
        return

    event.accept()


def handle_mouse_press_event(widget, event: QMouseEvent) -> None:
    pos = event.position().toPoint()

    if _swallow_focus_dim_click(widget, pos):
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
                fit_scale_for(slot, rect, _source_for(widget, slot))
                if slot is not None
                else (1.0, 1.0)
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
        if _swallow_focus_dim_click(widget, pos):
            event.accept()
            return
        div = divider_at(widget, event.position())
        if div is not None:
            split_path, _idx, _drect, _direction, weights = div
            n = len(weights)
            if n > 0:
                from tabs.multi_compare.pipeline.cache import sizes_for_slots
                from tabs.multi_compare.scene import actions as _mc_actions

                sizes = None
                try:
                    sizes = sizes_for_slots(
                        getattr(widget, "pixel_cache", None),
                        getattr(getattr(widget, "state", None), "slots", None),
                    )
                except Exception:
                    sizes = None
                widget._do_dispatch(
                    _mc_actions.set_split_weights(split_path, [1.0] * n, sizes=sizes)
                )
            event.accept()


from shared.canvas.keyboard_constants import (
    KEY_PAN as _KEY_PAN,
    KEY_PAN_NUDGE as _KEY_PAN_NUDGE,
    KEY_ZOOM_IN as _KEY_ZOOM_IN,
    KEY_ZOOM_OUT as _KEY_ZOOM_OUT,
)


def _keyboard_pan_reference(widget) -> tuple[QRect, tuple[float, float]]:
    """Reference rect + fit used to convert a screen nudge into pan units.

    Mirrors the middle-button pan reference: the focused slot's leaf when a
    slot is focused, otherwise the whole widget rect with fit ``(1, 1)``.
    """
    if widget.state.is_focused:
        for leaf, rect in widget._leaf_rects():
            slot = next(
                (s for s in widget.state.slots if s.id == leaf.slot_id), None
            )
            if slot is not None:
                return rect, fit_scale_for(slot, rect, _source_for(widget, slot))
    return widget.rect(), (1.0, 1.0)


def _apply_keyboard_pan(widget, key) -> None:
    _rect, (fit_x, fit_y) = _keyboard_pan_reference(widget)
    z = max(widget.state.zoom, 1e-6)
    dx = -1 if key == Qt.Key.Key_Left else (1 if key == Qt.Key.Key_Right else 0)
    dy = -1 if key == Qt.Key.Key_Up else (1 if key == Qt.Key.Key_Down else 0)
    dpan_x = dx * _KEY_PAN_NUDGE / (max(fit_x, 1e-6) * z)
    dpan_y = dy * _KEY_PAN_NUDGE / (max(fit_y, 1e-6) * z)
    new_x, new_y = clamp_pan_values(
        widget.state.pan_x + dpan_x,
        widget.state.pan_y + dpan_y,
        z,
    )
    if new_x != widget.state.pan_x or new_y != widget.state.pan_y:
        widget._do_dispatch(actions.set_pan(new_x, new_y))


def _apply_keyboard_zoom(widget, key) -> None:
    factor = widget.ZOOM_STEP if key in _KEY_ZOOM_IN else 1.0 / widget.ZOOM_STEP
    z1 = widget.state.zoom
    z2 = max(widget.ZOOM_MIN, min(widget.ZOOM_MAX, z1 * factor))
    if z2 == z1:
        return
    if z2 <= widget.ZOOM_MIN:
        new_pan_x, new_pan_y = 0.0, 0.0
    else:
        # Anchor at the reference cell's center (cell_u == cell_v == 0.5), so
        # the center stays fixed and pan is unchanged — same result as wheel
        # zoom over the middle of the cell.
        new_pan_x, new_pan_y = widget.state.pan_x, widget.state.pan_y
    widget._do_dispatch(actions.set_zoom(z2, new_pan_x, new_pan_y))


def handle_key_press_event(widget, event) -> None:
    key = event.key()
    if key == Qt.Key.Key_Escape and widget.state.is_focused:
        widget._do_dispatch(actions.set_focus(None))
        event.accept()
    elif key == Qt.Key.Key_0:
        widget._do_dispatch(actions.reset_view())
        event.accept()
    elif key in _KEY_PAN:
        _apply_keyboard_pan(widget, key)
        event.accept()
    elif key in _KEY_ZOOM_IN or key in _KEY_ZOOM_OUT:
        _apply_keyboard_zoom(widget, key)
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
    if rect is not None and slot is not None:
        from PySide6.QtGui import QPixmap

        from shared.image_processing.tiled_pixel_store import qimage_from_pixel_source

        source = _source_for(widget, slot)
        if source is not None:
            qimg = qimage_from_pixel_source(source)
            preview = QPixmap.fromImage(qimg).scaledToWidth(
                160, Qt.TransformationMode.SmoothTransformation
            )
            drag.setPixmap(preview)
            drag.setHotSpot(QPoint(preview.width() // 2, preview.height() // 2))
    drag.exec(Qt.DropAction.MoveAction)