"""Marquee band-select gesture for ``RecentItemsView`` -- split out to keep
that class down to the card-pool/virtualization pipeline itself (mirrors
the ``use_cases`` split, see docs/dev/CODE_PATTERNS.md). Every function
here takes the items view as its first argument and reads/writes its
``_marquee_gesture``/``_marquee_additive``/``_marquee_base`` instance state
directly, analogous to ``tabs/multi_compare/ui/drag_drop.py``.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QMouseEvent
from sli_ui_toolkit.widgets import MarqueeState

from ui.widgets.shelf.selection import (
    ctrl_held,
    paths_intersecting_rect,
    preview_selection,
)


def event_filter(view, watched: QObject, event: QEvent) -> bool:
    if watched is view.items_host:
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(
            event, QMouseEvent
        ):
            return host_mouse_press(view, event)
    return False


def ensure_marquee_gesture(view) -> MarqueeState:
    """Lazily create the toolkit ``MarqueeState`` holder for *view*."""
    gesture = getattr(view, "_marquee_gesture", None)
    host = getattr(view, "items_host", None)
    if gesture is not None and not isinstance(gesture, MarqueeState):
        # Pre-unify holder: drop it so the shelf never mixes visuals.
        try:
            gesture.cancel()
        except Exception:
            pass
        gesture = None
    if gesture is None:
        gesture = MarqueeState(
            host,
            parent=view,
            on_update=lambda rect: on_marquee_rect_update(view, rect),
            on_finish=lambda rect: on_marquee_rect_finish(view, rect),
        )
        try:
            view._marquee_gesture = gesture  # type: ignore[attr-defined]
        except Exception:
            pass
    accent = getattr(view, "_selection_accent", None)
    if accent is not None:
        try:
            gesture.set_accent(accent)
        except Exception:
            pass
        try:
            band = _band_widget(view)
            if band is not None:
                band.set_accent(accent)
        except Exception:
            pass
    return gesture


def paths_for_marquee_rect(view, rect: QRect) -> set[str]:
    if rect.isEmpty():
        return set()
    host_w = max(view.items_host.width(), view._content_width_provider())
    return paths_intersecting_rect(
        view._records,
        rect,
        view_mode=view._view_mode,
        columns=view._grid_columns,
        host_width=host_w,
    )


def _scroll_offset(view):  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QPoint as _QP

    try:
        area = getattr(view, "scroll_area", None)
        h = v = 0
        if area is not None:
            try:
                bar_h = area.horizontalScrollBar()
                h = int(bar_h.value()) if bar_h is not None else 0
            except Exception:
                pass
            try:
                bar_v = area.verticalScrollBar()
                v = int(bar_v.value()) if bar_v is not None else 0
            except Exception:
                pass
        return _QP(h, v)
    except Exception:
        from PySide6.QtCore import QPoint as _QP2

        return _QP2(0, 0)


def _band_widget(view):  # type: ignore[no-untyped-def]
    """Lazy viewport band widget (floats above host + cards)."""
    band = getattr(view, "_marquee_band", None)
    if band is None:
        try:
            from sli_ui_toolkit.widgets import MarqueeBandWidget

            viewport = view.scroll_area.viewport()
            band = MarqueeBandWidget(viewport)
            try:
                accent = getattr(view, "_selection_accent", None)
                if accent is not None:
                    band.set_accent(accent)
            except Exception:
                pass
            view._marquee_band = band  # type: ignore[attr-defined]
        except Exception:
            return None
    return band


def _band_rects(view, rect):  # type: ignore[no-untyped-def]
    from sli_ui_toolkit.widgets import resolve_band_rects

    try:
        return resolve_band_rects(
            getattr(view, "_marquee_press_pos", None),
            getattr(view, "_marquee_press_scroll", None),
            rect,
            _scroll_offset(view),
        )
    except Exception:
        from PySide6.QtCore import QRect as _QR

        return _QR(rect), _QR(rect)


def on_marquee_rect_update(view, rect: QRect) -> None:
    try:
        viewport_rect, rect = _band_rects(view, rect)
    except Exception:
        viewport_rect = rect
    try:
        band = _band_widget(view)
        if band is not None:
            band.set_band(viewport_rect)
    except Exception:
        pass
    paths = paths_for_marquee_rect(view, rect)
    if view._on_marquee_preview is not None:
        view._on_marquee_preview(paths, view._marquee_additive)
    else:
        preview = preview_selection(
            view._marquee_base, paths, additive=view._marquee_additive
        )
        view.apply_selection(preview)


def on_marquee_rect_finish(view, rect: QRect) -> None:
    try:
        band = _band_widget(view)
        if band is not None:
            band.set_active(False)
    except Exception:
        pass
    if not rect.isEmpty():
        try:
            _, rect = _band_rects(view, rect)
        except Exception:
            pass
    if rect.isEmpty():
        if view._on_marquee_commit is not None and not view._marquee_additive:
            view._on_marquee_commit(set(), False)
        return
    paths = paths_for_marquee_rect(view, rect)
    if view._on_marquee_commit is not None:
        view._on_marquee_commit(paths, view._marquee_additive)


def host_mouse_press(view, event: QMouseEvent) -> bool:
    if event.button() != Qt.MouseButton.LeftButton:
        return False
    child = view.items_host.childAt(event.position().toPoint())
    if child is not None:
        return False
    view._marquee_additive = ctrl_held(event.modifiers())
    view._marquee_base = set(view._selection_paths())
    gesture = ensure_marquee_gesture(view)
    if not gesture.start(event.position().toPoint()):
        return False
    try:
        view._marquee_press_pos = event.position().toPoint()  # type: ignore[attr-defined]
        view._marquee_press_scroll = _scroll_offset(view)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        band = _band_widget(view)
        if band is not None:
            band.set_active(True)
    except Exception:
        pass
    # Live clear (non-additive) so the band starts empty immediately.
    if view._on_marquee_preview is not None:
        view._on_marquee_preview(set(), view._marquee_additive)
    return True