"""Quick look card resize — resize-cursor apply + ql-resize debug tracing.

Bodies moved verbatim from ``ui/quick_look/resize.py`` (plan-gallery-split-
2026-10-17, Part C2). Plain functions taking the overlay as their first
argument (``CODE_PATTERNS.md`` "thin owner + use_cases module"); function
names and signatures are unchanged.
"""

from __future__ import annotations

from .zones import QL_RESIZABLE


def _resize_dbg():
    """Debug helper pair (IMGSLI_GALLERY_DEBUG=1): [gallery-debug] ql-resize
    traces for edge press/drag/hover diagnosis. Returns (enabled, dbg)."""
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.debug import gallery_debug_enabled as _enabled

        if _enabled():
            return True, _dbg
    except Exception:
        pass
    return False, None


def _resize_trace_on() -> bool:
    """Full firehose (IMGSLI_QL_RESIZE_TRACE=1): log EVERY observed move with
    receiver + effective cursor + app override cursor + window-filter state,
    no change-gating. For when the filtered ql-resize logs hide the picture
    (steady states and child-swallowed events are silent there by design).

    The ``override=`` column is the decisive one for "wrong cursor"
    reports: ``QApplication.overrideCursor()`` beats every widget cursor,
    so a line reading ``cursor=SizeHorCursor override=WaitCursor`` means
    the screen shows waiting while the card logic holds a resize arrow.
    ``winfilter=`` mirrors the main-window toolkit ``_ResizeFilter``
    (manual edges / native resize / override pushed) — the only other
    override-cursor owner besides project busy."""
    try:
        from shared.debug_flags import env_flag as _env_flag

        return bool(_env_flag("IMGSLI_QL_RESIZE_TRACE"))
    except Exception:
        return False


def _override_cursor_name() -> str:
    """App-wide override cursor shape (``none`` when the stack is empty).

    Deliberately NOT reusing ``_cursor_name``'s ``None → arrow`` mapping:
    an empty stack and a pushed ArrowCursor look identical on screen but
    mean different things (the latter still shadows widget cursors while
    pushed, and a leak would show here first).
    """
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return "no-app"
        cur = app.overrideCursor()
        if cur is None:
            return "none"
        try:
            shape = cur.shape() if hasattr(cur, "shape") else cur
            return str(shape).split(".")[-1]
        except Exception:
            return "?"
    except Exception:
        return "?"


def _winfilter_state(overlay) -> str:
    """Compact main-window ``_ResizeFilter`` state for the trace line."""
    try:
        win = overlay.window() if hasattr(overlay, "window") else None
        if win is None:
            return "no-win"
        try:
            from sli_ui_toolkit.ui.windows.frameless.resize_filter import (
                _ResizeFilter,
            )

            f = win.findChild(_ResizeFilter)
        except Exception:
            return "no-filter"
        if f is None:
            return "no-filter"
        return (
            f"manual={f._manual_edges} native={f._native_resizing} "
            f"pushed={f._override_pushed} armed={f._cursor_armed}"
        )
    except Exception:
        return "?"


def _effective_cursor_name(widget) -> str:
    """Effective (inherited) cursor shape name for a widget."""
    try:
        if widget is None:
            return "none"
        cur = widget.cursor()
        shape = cur.shape() if hasattr(cur, "shape") else cur
        return str(shape).split(".")[-1]
    except Exception:
        return "?"


def trace_move(overlay, where: str, pos, receiver=None) -> None:
    """One firehose line per observed mouse move (trace mode only)."""
    try:
        if not _resize_trace_on():
            return
        from tabs.image_gallery.debug import gallery_debug as _dbg

        try:
            recv_name = (
                f"{type(receiver).__name__}:{receiver.objectName()}"
                if receiver is not None
                else "veil"
            )
        except Exception:
            recv_name = "?"
        try:
            eff = _effective_cursor_name(receiver if receiver is not None else overlay)
        except Exception:
            eff = "?"
        try:
            drag = getattr(overlay, "_border_drag", None)
            drag_s = drag[0] if drag is not None else "-"
        except Exception:
            drag_s = "?"
        try:
            ovr = _override_cursor_name()
        except Exception:
            ovr = "?"
        try:
            wfs = _winfilter_state(overlay)
        except Exception:
            wfs = "?"
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                cg = content.geometry()
                geos = f"card=({cg.x()},{cg.y()},{cg.width()}x{cg.height()})"
            else:
                geos = "card=?"
        except Exception:
            geos = "card=?"
        _dbg(
            "ql-resize trace %s pos=(%d,%d) receiver=%s cursor=%s drag=%s override=%s winfilter=(%s) %s",
            where,
            pos.x(),
            pos.y(),
            recv_name,
            eff,
            drag_s,
            ovr,
            wfs,
            geos,
        )
    except Exception:
        pass


def _cursor_name(cursor) -> str:
    """Human-readable cursor shape (ArrowCursor for None)."""
    if cursor is None:
        return "arrow"
    try:
        shape = cursor.shape() if hasattr(cursor, "shape") else cursor
        return str(shape).split(".")[-1]
    except Exception:
        return "?"


def apply_resize_cursor(overlay, target, slot: str, cursor) -> None:
    """Set/unset a resize cursor, logging the ACTUAL change (ql-resize).

    ``slot`` is ``plate`` (``_content``) or ``overlay``. Logs only on change
    (per slot), so plain hovers don't spam — you see exactly when the visible
    cursor flips and on which widget. No-op overhead when the debug flag is
    unset (one env check).

    When ``QL_RESIZABLE`` is False the card is fixed-size: any resize cursor
    is forced to None (clear), so hovers always restore the arrow while
    stale-cursor clearing (D1/D5) keeps working.
    """
    if not QL_RESIZABLE:
        cursor = None
    _dbg_on, _dbg = _resize_dbg()
    try:
        if not _dbg_on:
            if cursor is None:
                try:
                    target.unsetCursor()
                except Exception:
                    pass
            else:
                try:
                    target.setCursor(cursor)
                except Exception:
                    pass
            return
        want = _cursor_name(cursor)
        try:
            state = getattr(overlay, "_dbg_cursor_state", None)
            if not isinstance(state, dict):
                state = {}
                overlay._dbg_cursor_state = state
            prev = state.get(slot)
        except Exception:
            state, prev = None, None
        try:
            if cursor is None:
                target.unsetCursor()
            else:
                target.setCursor(cursor)
        except Exception:
            pass
        if want != prev:
            try:
                if isinstance(state, dict):
                    state[slot] = want
            except Exception:
                pass
            try:
                _dbg("ql-resize cursor %s -> %s", slot, want)
            except Exception:
                pass
    except Exception:
        pass
