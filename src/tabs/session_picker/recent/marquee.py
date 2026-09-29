"""Marquee band-select gesture for ``RecentItemsView``.

Thin shell over the shared drag plumbing
(``ui.widgets.shelf.marquee_plumbing``): the recent-shelf hit-test and
preview/commit callbacks are bound into ``RECENT_WIRING``; everything
about the gesture, band widget and scroll compensation lives in the
shared module (same plumbing the gallery grid uses).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtGui import QMouseEvent
from sli_ui_toolkit.widgets import MarqueeState

from ui.widgets.shelf.marquee_plumbing import MarqueeWiring
from ui.widgets.shelf.marquee_plumbing import ensure_gesture as _ensure
from ui.widgets.shelf.marquee_plumbing import event_filter as _event_filter
from ui.widgets.shelf.marquee_plumbing import host_mouse_press as _press
from ui.widgets.shelf.marquee_plumbing import on_rect_finish as _finish
from ui.widgets.shelf.marquee_plumbing import on_rect_update as _update
from ui.widgets.shelf.selection import (
    paths_intersecting_rect,
    preview_selection,
)


def _hit_test(view, rect: QRect) -> set[str]:  # type: ignore[no-untyped-def]
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


def _base_snapshot(view) -> set[str]:  # type: ignore[no-untyped-def]
    return set(view._selection_paths())


def _press_preview(view, additive: bool) -> None:  # type: ignore[no-untyped-def]
    # Live clear (non-additive) so the band starts empty immediately.
    if view._on_marquee_preview is not None:
        view._on_marquee_preview(set(), additive)


def _preview(view, paths: set[str], additive: bool) -> None:  # type: ignore[no-untyped-def]
    if view._on_marquee_preview is not None:
        view._on_marquee_preview(paths, additive)
    else:
        preview = preview_selection(
            view._marquee_base, paths, additive=additive
        )
        view.apply_selection(preview)


def _commit(view, paths: set[str], additive: bool) -> None:  # type: ignore[no-untyped-def]
    if not paths and additive:
        # Additive empty finish keeps the selection — no hook call (legacy).
        return
    if view._on_marquee_commit is not None:
        view._on_marquee_commit(paths, additive)


RECENT_WIRING = MarqueeWiring(
    hit_test=_hit_test,
    preview=_preview,
    commit=_commit,
    base_snapshot=_base_snapshot,
    press_preview=_press_preview,
)


def event_filter(view, watched: QObject, event: QEvent) -> bool:
    return _event_filter(view, watched, event, RECENT_WIRING)


def ensure_marquee_gesture(view) -> MarqueeState:
    """Lazily create the toolkit ``MarqueeState`` holder for *view*."""
    return _ensure(view, RECENT_WIRING)


def paths_for_marquee_rect(view, rect: QRect) -> set[str]:
    return _hit_test(view, rect)


def on_marquee_rect_update(view, rect: QRect) -> None:
    _update(view, rect, RECENT_WIRING)


def on_marquee_rect_finish(view, rect: QRect) -> None:
    _finish(view, rect, RECENT_WIRING)


def host_mouse_press(view, event: QMouseEvent) -> bool:
    return _press(view, event, RECENT_WIRING)
