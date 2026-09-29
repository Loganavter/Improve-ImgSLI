"""Marquee band-select for the gallery grid.

Mirrors ``tabs/session_picker/recent/marquee.py`` but for the 4-column
gallery grid. Functions take the grid view as first arg and read/write its
``_marquee_gesture``/``_marquee_additive``/``_marquee_base`` state, same as
the session picker pattern.

Public API:
  ensure_marquee_gesture(view) -> MarqueeState (toolkit tracker)
  paths_for_rect(view, rect) -> set[Path]
  on_rect_update / on_rect_finish (re-exported from marquee_select: gesture
  vs selection seam — press/ensure/filter here, preview/commit there)
  event_filter(view, watched, event) -> bool  (host mouse press → start band)
  host_mouse_press(view, event) -> bool

The band is a toolkit ``MarqueeBandWidget`` child of the scroll viewport
(Dolphin foreground parity) — no overlay widget, no restack, no window
round-trip, and the visual never diverges from the hit-tested rect
(see ``marquee_view``).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QMouseEvent

from sli_ui_toolkit.widgets import MarqueeState
from tabs.image_gallery.ui.marquee_view import (
    band_rects,
    band_widget,
    scroll_offset,
)
from tabs.image_gallery.ui.marquee_select import on_rect_finish, on_rect_update
from tabs.image_gallery.ui.marquee_select import paths_for_marquee_rect as paths_for_marquee_rect
from tabs.image_gallery.ui.marquee_select import paths_for_rect as paths_for_rect

def ensure_marquee_gesture(view) -> MarqueeState:  # type: ignore[no-untyped-def]
    """Lazily create the toolkit ``MarqueeState`` holder for *view*."""
    gesture = getattr(view, "_marquee_gesture", None)
    host = getattr(view, "items_host", None)
    if gesture is not None and not isinstance(gesture, MarqueeState):
        # Pre-unify holder (toolkit overlay gesture or gallery-local state):
        # drop it so the gallery path never mixes visuals.
        try:
            gesture.cancel()
        except Exception:
            pass
        gesture = None
    accent = getattr(view, "_selection_accent", None)
    if gesture is None:
        gesture = MarqueeState(
            host,
            parent=view,
            on_update=lambda r: on_rect_update(view, r),
            on_finish=lambda r: on_rect_finish(view, r),
            on_trace=lambda line: _mdbg(line),
        )
        try:
            view._marquee_gesture = gesture  # type: ignore[attr-defined]
        except Exception:
            pass
    else:
        try:
            viewport = view.scroll_area.viewport()
        except Exception:
            viewport = None
        try:
            gesture.set_clip_widget(viewport)
        except Exception:
            pass
    if accent is not None:
        # The holder keeps it for traces; the host paints the band.
        for target in (gesture, host):
            try:
                if target is not None and hasattr(target, "set_accent"):
                    target.set_accent(accent)
            except Exception:
                pass
    return gesture


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
    if event.button() != Qt.MouseButton.LeftButton:
        _mdbg("marquee press REFUSE button=%s (not Left)", event.button())
        return False
    host = getattr(view, "items_host", None)
    if host is None:
        _mdbg("marquee press REFUSE reason=no-host")
        return False
    try:
        press_pos = event.position().toPoint()
    except Exception:
        press_pos = None
    try:
        child = host.childAt(press_pos) if press_pos is not None else None
    except Exception:
        child = None
    if child is not None:
        _mdbg("marquee press REFUSE pos=%s child=%s (not empty host)", press_pos, type(child).__name__)
        return False
    try:
        view._marquee_additive = bool(_ctrl_held(event.modifiers()))  # type: ignore[attr-defined]
    except Exception:
        view._marquee_additive = False  # type: ignore[attr-defined]
    # Snapshot base selection.
    try:
        from pathlib import Path as _Path  # noqa: F401
        sel = None
        owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
        if owner is not None and hasattr(getattr(owner, "state", None), "selected_paths"):
            sel = getattr(owner.state, "selected_paths", None)
        if sel is None:
            sel = getattr(view, "_selection", None) or getattr(view, "_selection_paths", lambda: set())()
            if callable(sel):
                sel = sel()
        view._marquee_base = set(sel) if sel is not None else set()  # type: ignore[attr-defined]
    except Exception:
        view._marquee_base = set()  # type: ignore[attr-defined]
    # New gesture: drop the coalescing signature so the first update of
    # this drag always dispatches (its base may differ from the last drag).
    try:
        view._marquee_last_update_sig = None  # type: ignore[attr-defined]
    except Exception:
        pass
    gesture = ensure_marquee_gesture(view)
    try:
        if not gesture.start(event.position().toPoint()):
            _mdbg("marquee press IGNORED (gesture refused) pos=%s", event.position().toPoint())
            return False
    except Exception as exc:
        _mdbg("marquee press FAILED err=%r", exc)
        return False
    # Scroll basis for mid-drag compensation (see marquee_view) + band on.
    try:
        view._marquee_press_pos = event.position().toPoint()  # type: ignore[attr-defined]
        view._marquee_press_scroll = scroll_offset(view)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        band = band_widget(view)
        if band is not None:
            band.set_active(True)
    except Exception:
        pass
    _mdbg(  # fail-open: never raises, no wrapper needed
        "marquee press START pos=%s additive=%s base_n=%s gesture_active=%s",
        event.position().toPoint(),
        bool(getattr(view, "_marquee_additive", False)),
        len(getattr(view, "_marquee_base", set()) or set()),
        bool(getattr(gesture, "active", False)),
    )
    # Live preview clear for non-additive.
    cb = getattr(view, "_on_marquee_preview", None)
    if callable(cb):
        try:
            cb(set(), bool(getattr(view, "_marquee_additive", False)))
        except Exception:
            pass
    else:
        # Preview empty band immediately (non-additive clears).
        if not bool(getattr(view, "_marquee_additive", False)):
            try:
                view.apply_selection(set())
            except Exception:
                pass
    return True


def event_filter(view, watched: QObject, event: QEvent) -> bool:  # type: ignore[no-untyped-def]
    host = getattr(view, "items_host", None)
    if watched is host and event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
        return host_mouse_press(view, event)
    return False
