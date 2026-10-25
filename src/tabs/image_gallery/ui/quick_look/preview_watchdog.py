"""Quick-look canvas watchdog — generation-guarded no-frame fallback.

Split from ``preview_canvas.py`` (500-line contract gate): the canvas
widget stays a thin owner, all timer bookkeeping lives here as plain
functions taking the widget. Fail-open everywhere — a watchdog miss must
never break the preview (worst case is a late QLabel fallback).

Race fixed (2026-09-28): ``set_source`` used to reset ``_frame_ok`` while
the previous source's ``QTimer.singleShot`` was still pending
(``_arm_watchdog`` no-op'd on ``_watchdog_armed``), so a late
first-source timer saw the fresh ``_frame_ok == False`` and killed a
healthy new canvas ~26ms after populate. Every arm now mints a
generation; a fire older than the live generation is ignored.
"""

from __future__ import annotations

import logging

from engine.frame.present import PresentDebt, begin_source, should_fire
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

# Tab policy: the Quick Look cover drops on the 2nd settled present (MC
# parity). Passed explicitly to note_presented — never rely on the engine
# default (FIRST_PRESENT_SETTLE_COUNT = 10).
QL_SETTLE_COUNT = 2


def _qlc_log(msg: str, *args) -> None:
    try:
        from tabs.image_gallery.debug import ql_cover, ql_cover_enabled

        if ql_cover_enabled():
            ql_cover(msg, *args)
    except Exception:
        pass


def next_gen(canvas) -> int:
    """Mint the next watchdog generation for *canvas* (never raises).

    Renews ``canvas._present_debt`` via ``begin_source`` (new generation)
    and returns ``debt.generation``; the ``_watchdog_gen`` attribute is
    kept as a truthful mirror. Never synthesizes presents — the debt
    count only grows through ``note_presented`` on real frames.
    """
    try:
        old = getattr(canvas, "_present_debt", None)
        debt: PresentDebt = begin_source(old)
    except Exception:
        return _mirror_gen(canvas)
    try:
        canvas._present_debt = debt
    except Exception:
        pass
    try:
        canvas._watchdog_gen = int(debt.generation)
    except Exception:
        pass
    return int(debt.generation)


def _mirror_gen(canvas) -> int:
    """Legacy int-mirror fallback when the debt ledger is unreachable."""
    try:
        gen = int(getattr(canvas, "_watchdog_gen", 0) or 0) + 1
    except Exception:
        gen = 1
    try:
        canvas._watchdog_gen = gen
    except Exception:
        pass
    return gen


def invalidate(canvas) -> None:
    """Retire pending timers (clear/hide paths); their fires go stale."""
    try:
        next_gen(canvas)
    except Exception:
        pass
    try:
        canvas._watchdog_armed = False
    except Exception:
        pass


_REPUMP_MS = 250


def ensure_repump(canvas) -> None:
    """GUI-thread delayed re-request: heal a lost pump (never raises).

    Must be called on the GUI thread (the reveal paths are): a
    ``QTimer.singleShot`` created here lives on the GUI loop. If the
    settle pump's update was coalesced/eaten (walk pattern: exactly one
    render, then silence), this re-requests a frame once the loop is
    idle. No-op when the frame already settled or was never pumped.
    """
    try:
        from PySide6.QtCore import QTimer

        def _check() -> None:
            try:
                if bool(getattr(canvas, "_frame_ok", False)):
                    return
                if not bool(getattr(canvas, "_settle_pumped", False)):
                    return
                try:
                    import shiboken6

                    if not shiboken6.isValid(canvas):
                        return
                except Exception:
                    pass
                canvas.update()
            except Exception:
                pass

        QTimer.singleShot(_REPUMP_MS, _check)
    except Exception:
        pass


def arm_watchdog(canvas, gen=None) -> None:
    """Arm a no-frame timer bound to generation *gen* (never raises)."""
    try:
        g = int(gen) if gen is not None else next_gen(canvas)
    except Exception:
        return
    try:
        canvas._watchdog_gen = g
        canvas._watchdog_armed = True
    except Exception:
        return
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(
            _timeout_ms(),
            lambda _g=g: fire_watchdog(canvas, _g),
        )
    except Exception:
        try:
            canvas._watchdog_armed = False
        except Exception:
            pass


def _timeout_ms() -> int:
    try:
        from tabs.image_gallery.ui.quick_look.preview_canvas import _NO_FRAME_TIMEOUT_MS

        return int(_NO_FRAME_TIMEOUT_MS)
    except Exception:
        return 1500


def fire_watchdog(canvas, expected_gen=None) -> None:
    """Fire a pending timer; stale generations are ignored (never raises)."""
    try:
        live = int(getattr(canvas, "_watchdog_gen", 0) or 0)
    except Exception:
        live = 0
    if expected_gen is not None:
        try:
            if int(expected_gen) != live:
                logger.debug(
                    "QuickLook preview: stale watchdog gen=%s (live=%s) ignored",
                    expected_gen,
                    live,
                )
                _qlc_log("watchdog stale gen=%s live=%s ignored", expected_gen, live)
                return
        except Exception:
            pass
        try:
            debt = getattr(canvas, "_present_debt", None)
            if debt is not None and not should_fire(expected_gen, debt):
                logger.debug(
                    "QuickLook preview: stale watchdog gen=%s (live=%s) ignored",
                    expected_gen,
                    live,
                )
                _qlc_log(
                    "watchdog stale gen=%s live=%s debt=%s ignored",
                    expected_gen,
                    live,
                    getattr(debt, "generation", None),
                )
                return
        except Exception:
            pass
    try:
        canvas._watchdog_armed = False
    except Exception:
        pass
    try:
        if bool(getattr(canvas, "_frame_ok", False)):
            return
    except Exception:
        return
    try:
        import shiboken6

        if not shiboken6.isValid(canvas):
            return
    except Exception:
        pass
    try:
        _shell_ready = bool(getattr(canvas, "_shell_ready", False))
        _has_comp = bool(getattr(canvas, "_active_composition", None))
        _cw, _ch = int(canvas.width()), int(canvas.height())
    except Exception:
        _shell_ready, _has_comp, _cw, _ch = False, False, -1, -1
    try:
        _updates = bool(canvas.updatesEnabled())
    except Exception:
        _updates = None
    try:
        _vis_to = bool(canvas.isVisibleTo(canvas.window())) if callable(getattr(canvas, "isVisibleTo", None)) else None
    except Exception:
        _vis_to = None
    try:
        _wh = canvas.windowHandle() if callable(getattr(canvas, "windowHandle", None)) else None
        _exposed = bool(_wh.isExposed()) if _wh is not None else None
    except Exception:
        _exposed = None
    _qlc_log(
        "watchdog firing: no frame shell_ready=%s has_composition=%s canvas=%sx%s updates=%s vis_to_win=%s exposed=%s",
        _shell_ready,
        _has_comp,
        _cw,
        _ch,
        _updates,
        _vis_to,
        _exposed,
    )
    try:
        canvas.previewFailed.emit()
    except Exception:
        pass
