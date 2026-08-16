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
from sli_ui_toolkit.widgets import MarqueeBandGesture

from tabs.session_picker.recent.selection import (
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


def ensure_marquee_gesture(view) -> MarqueeBandGesture:
    if view._marquee_gesture is None:
        view._marquee_gesture = MarqueeBandGesture(
            view.items_host,
            parent=view,
            clip_widget=view.scroll_area.viewport(),
            on_update=lambda rect: on_marquee_rect_update(view, rect),
            on_finish=lambda rect: on_marquee_rect_finish(view, rect),
        )
    else:
        view._marquee_gesture.set_clip_widget(view.scroll_area.viewport())
    view._marquee_gesture.set_accent(view._selection_accent)
    return view._marquee_gesture


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


def on_marquee_rect_update(view, rect: QRect) -> None:
    paths = paths_for_marquee_rect(view, rect)
    if view._on_marquee_preview is not None:
        view._on_marquee_preview(paths, view._marquee_additive)
    else:
        preview = preview_selection(
            view._marquee_base, paths, additive=view._marquee_additive
        )
        view.apply_selection(preview)


def on_marquee_rect_finish(view, rect: QRect) -> None:
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
    # Live clear (non-additive) so the band starts empty immediately.
    if view._on_marquee_preview is not None:
        view._on_marquee_preview(set(), view._marquee_additive)
    return True