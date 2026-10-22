"""The early-answer watchdog for handlers parked in a modal dialog.

The chord path is synchronous: ``press_keys ctrl+shift+o`` runs
``platform.open_project`` inline, which calls ``QFileDialog.getOpenFileName`` — a
modal ``exec()``. Every handler reply is written *after* the handler returns, so
the answer would sit inside the dialog until a human closed it and the client
would time out on a call that had already worked. Qt delivers timers inside that
nested loop, so the timer (not a thread) is what lets the channel answer.

The answer is a success frame carrying the answered-early flag because the request *is*
being carried out; reporting it as a failure would invite the retry that
double-applies the edit. A handler that fails *before* the budget is unaffected
by this: it returns (or raises) first and keeps its own full result / named error.

Split out of ``core/control/server.py`` (docs/dev/FILE_SIZE_POLICY.md): the
functions take the server as ``owner`` (the ``use_cases`` shape) and only reach
its ``_ack_budget_ms`` / ``_clear_inflight`` seams and writes through
``frames.send_frame`` (the one frame writer).
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QTimer

from .frames import send_frame

logger = logging.getLogger("ImproveImgSLI")

#: How long a handler may run before the channel answers on its own behalf
#: (milliseconds). A handler that opens one of the app's modal dialogs
#: (``QFileDialog.getOpenFileName`` behind ``platform.open_project``, reached by
#: ``ctrl+shift+o`` through ``press_keys``/``run_action``/``ui_click``) is parked
#: inside that dialog's nested event loop until a human closes it, so the reply
#: would otherwise be written minutes later and the client would report
#: "sent, no reply" for a call that had already worked (and retry it).
#:
#: Chosen well above the slowest honest verb (a big capture / layout dump) and
#: well below the MCP client's 5 s request timeout, with room for the
#: round trip. Qt *does* deliver timers inside a nested modal loop, which is
#: what makes the early answer possible without a second thread — the transport
#: stays GUI-thread-only on purpose (see the module docstring).
MODAL_ACK_BUDGET_MS = 2000



def active_modal_widget() -> Any:
    """The modal widget blocking the app right now, or ``None``.

    Measured, never assumed: it is only ever reported as a *hint* on an early
    answer, because a native file dialog (the desktop portal on Wayland/Flatpak)
    is not a ``QWidget`` at all — ``None`` there means "no Qt modal widget",
    not "nothing is open". Imported lazily: the transport needs QtCore only.
    """
    try:
        from PySide6.QtWidgets import QApplication

        return QApplication.activeModalWidget()
    except Exception:
        return None


def arm_early_answer(
    owner, socket, request_id: Any, method: str
) -> tuple[QTimer, dict[str, bool]]:
    """Arm the watchdog that answers a handler parked inside a nested loop.

    Returns the timer and the state the caller must consult: once
    ``state["answered"]`` is set, a frame is already on the wire and the late
    real result must be dropped (never a second frame for one id).
    """
    state = {"answered": False}

    def _overran() -> None:
        if state["answered"]:
            return
        state["answered"] = True
        modal = active_modal_widget()
        # ``send_frame``, not the handler's reply path: the in-flight note stays
        # until the handler returns, because the app is still busy with this
        # request and a crash in the dialog would otherwise leave no record of it.
        send_frame(
            owner,
            socket,
            {
                "id": request_id,
                "ok": True,
                "result": {
                    "accepted": True,
                    "answered_early": True,
                    "still_running": True,
                    "modal_open": modal is not None,
                    "method": method,
                    "budget_ms": owner._ack_budget_ms,
                },
            },
        )
        logger.info(
            "control channel: %s still running after %s ms (%s) — answered "
            "early; its real result will be dropped",
            method,
            owner._ack_budget_ms,
            "a Qt modal widget is open" if modal is not None else "no Qt modal widget",
        )

    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(owner._ack_budget_ms)
    timer.timeout.connect(_overran)
    timer.start()
    return timer, state


def report_late_failure(owner, method: str, exc: BaseException, note: int | None) -> None:
    """A handler that overran then failed: the client already has its frame.

    Nothing can be rewritten on the wire, so the failure goes to the log
    (``read_log`` serves it) instead of vanishing, and the in-flight note is
    cleared (only if this request still owns it) — the app is alive, it just
    cannot report this one.
    """
    logger.warning(
        "control channel: %s failed after it was answered early: %s: %s",
        method,
        type(exc).__name__,
        exc,
    )
    owner._clear_inflight(note)
