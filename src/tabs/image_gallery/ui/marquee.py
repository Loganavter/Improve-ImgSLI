"""Marquee band-select for the gallery grid.

Thin gesture shell over the shared drag plumbing
(``ui.widgets.shelf.marquee_plumbing``): the elimination gate, press /
filter entry points and public re-exports live here; band geometry +
preview/commit callbacks live in ``marquee_select`` (bound into
``GALLERY_WIRING``). Mirrors ``tabs/session_picker/recent/marquee.py``,
which binds the same plumbing to the recent shelf.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtGui import QMouseEvent

from sli_ui_toolkit.widgets import MarqueeState
from tabs.image_gallery.ui.marquee_select import GALLERY_WIRING
from tabs.image_gallery.ui.marquee_select import on_rect_finish, on_rect_update
from tabs.image_gallery.ui.marquee_select import paths_for_marquee_rect as paths_for_marquee_rect
from tabs.image_gallery.ui.marquee_select import paths_for_rect as paths_for_rect
from ui.widgets.shelf import marquee_plumbing as _plumbing

__all__ = [
    "ensure_marquee_gesture",
    "event_filter",
    "host_mouse_press",
    "marquee_disabled",
    "on_rect_finish",
    "on_rect_update",
    "paths_for_marquee_rect",
    "paths_for_rect",
]


def ensure_marquee_gesture(view) -> MarqueeState:  # type: ignore[no-untyped-def]
    """Lazily create the toolkit ``MarqueeState`` holder for *view*."""
    return _plumbing.ensure_gesture(view, GALLERY_WIRING)


def _mdbg(msg: str, *args) -> None:
    """Marquee trace via gallery_debug (env-gated, fail-open)."""
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(msg, *args)
    except Exception:
        pass


def marquee_disabled() -> bool:
    """Elimination gate (bisect, not a feature).

    ``IMGSLI_GALLERY_NO_MARQUEE=1`` makes empty-host presses fall through,
    killing gesture + preview + commit in ONE toggle. Used to decide
    whether the host-click hover-loss lives anywhere in this chain.
    Parsing via shared ``env_flag`` (see plan-host-debug-flags).
    """
    try:
        from shared.debug_flags import env_flag

        return bool(env_flag("IMGSLI_GALLERY_NO_MARQUEE"))
    except Exception:
        return False


def host_mouse_press(view, event: QMouseEvent) -> bool:  # type: ignore[no-untyped-def]
    if marquee_disabled():
        _mdbg("marquee press SKIP (elimination gate IMGSLI_GALLERY_NO_MARQUEE=1)")
        return False
    return _plumbing.host_mouse_press(view, event, GALLERY_WIRING)


def event_filter(view, watched: QObject, event: QEvent) -> bool:  # type: ignore[no-untyped-def]
    return _plumbing.event_filter(view, watched, event, GALLERY_WIRING)
