"""``SLI_FOCUS_DEBUG``-gated tracing of keyboard-focus ownership.

Answers "who took focus / who failed to take it" without touching the ~100
``setFocus``/``clearFocus`` call sites: hooks ``QApplication.focusChanged``
once and logs every transition with widget identity plus host-window state
(visible / minimized / active). That covers both classic hunts:

* focus lost and nobody reclaimed it (old widget in the log, now ``None``),
* focus requested after the window was minimized (``isMinimized=True`` on
  the gaining side's window at log time).

Same convention as ``ui/widgets/flyout_debug.py``: gate on an env var via
``shared.debug_flags.env_flag``, tag every line with a bracketed prefix,
near-zero overhead when disabled (one flag check per transition).

Caveat: ``focusChanged`` does not carry ``Qt.FocusReason`` — when the
*reason* matters (e.g. distinguishing ``PopupFocusReason`` grabs), log it
at the requesting call site with ``focus_debug()``.
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")

_FLAG = "SLI_FOCUS_DEBUG"

_installed_on: list[int] = []


def focus_debug_enabled() -> bool:
    return _env_flag(_FLAG)


def focus_debug(message: str, *args) -> None:
    if focus_debug_enabled():
        logger.debug("[focus-debug] " + message, *args)


def _describe(widget) -> str:
    if widget is None:
        return "None"
    try:
        cls = type(widget).__name__
        name = widget.objectName() or "<noname>"
        window = widget.window()
        if window is None:
            return f"{cls}#{name} (no-window)"
        try:
            minimized = window.isMinimized()
        except Exception:
            minimized = "?"
        try:
            visible = window.isVisible()
        except Exception:
            visible = "?"
        try:
            active = window.isActiveWindow()
        except Exception:
            active = "?"
        return (
            f"{cls}#{name} "
            f"(win={type(window).__name__} "
            f"minimized={minimized} visible={visible} active={active})"
        )
    except Exception:
        return f"<undescribable {type(widget).__name__}>"


def _on_focus_changed(old, now) -> None:
    try:
        focus_debug("focus %s -> %s", _describe(old), _describe(now))
    except Exception:
        pass


def install_focus_tracer(app=None) -> bool:
    """Connect ``focusChanged`` logging. Idempotent; no-op when flag is off.

    When the flag is on, also drops the ``ImproveImgSLI`` logger level to
    DEBUG if something else set it higher — otherwise the tracer's own
    ``logger.debug`` lines never reach any handler and the flag looks dead.
    Returns True when the tracer is (or already was) connected.
    Never raises — focus handling must keep working with or without tracing.
    """
    try:
        if not focus_debug_enabled():
            return False
        if app is None:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
        if app is None:
            return False
        if logger.getEffectiveLevel() > logging.DEBUG:
            logger.setLevel(logging.DEBUG)
        if id(app) in _installed_on:
            return True
        app.focusChanged.connect(_on_focus_changed)
        _installed_on.append(id(app))
        focus_debug("tracer installed")
        return True
    except Exception:
        return False
