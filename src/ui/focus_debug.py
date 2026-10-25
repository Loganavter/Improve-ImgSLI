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
at the requesting call site with ``focus_debug()``. Reason stays
call-site-only by design: the tracer reports ownership + window state,
never why focus moved.
"""

from __future__ import annotations

import logging
import time

from shared.debug_flags import env_flag as _env_flag
from core.log_names import APP_LOGGER_NAME

try:  # Qt is optional at import time; install degrades gracefully without it.
    from PySide6.QtCore import QEvent, QObject, Qt
except Exception:  # pragma: no cover - headless import guard
    QEvent = QObject = Qt = None  # type: ignore[assignment]

logger = logging.getLogger(APP_LOGGER_NAME)

_FLAG = "SLI_FOCUS_DEBUG"

_installed_on: list[int] = []
_state_filters: dict[int, object] = {}


def focus_debug_enabled() -> bool:
    return _env_flag(_FLAG)


def focus_debug(message: str, *args) -> None:
    if focus_debug_enabled():
        logger.debug("[focus-debug] " + message, *args)


def _short_label(widget) -> str:
    """``Class#name`` (or ``None``) — never raises."""
    if widget is None:
        return "None"
    try:
        return f"{type(widget).__name__}#{widget.objectName() or '<noname>'}"
    except Exception:
        try:
            return f"<undescribable {type(widget).__name__}>"
        except Exception:
            return "<undescribable>"


def _app_snapshot() -> str:
    """App-wide focus ownership: activeWindow / activeModalWidget / focusWidget."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return "app_active=None app_modal=None app_focus=None"
        return (
            f"app_active={_short_label(app.activeWindow())} "
            f"app_modal={_short_label(app.activeModalWidget())} "
            f"app_focus={_short_label(app.focusWidget())}"
        )
    except Exception:
        return "app_active=? app_modal=? app_focus=?"


def _state_value(state) -> str:
    """Hex of a Qt state flag. PySide6 flag enums reject plain int()."""
    try:
        return f"0x{int(state):x}"
    except Exception:
        pass
    try:
        return f"0x{int(state.value):x}"
    except Exception:
        return "?"


def _state_bits(window) -> str:
    """Compact ``windowState`` bits; supplements the lagging ``isMinimized`` poll."""
    if Qt is None:
        return "state=?"
    try:
        state = window.windowState()
        bits: list[str] = []
        try:
            if state & Qt.WindowState.WindowMinimized:
                bits.append("minimized")
        except Exception:
            pass
        try:
            if state & Qt.WindowState.WindowMaximized:
                bits.append("maximized")
        except Exception:
            pass
        try:
            if state & Qt.WindowState.WindowFullScreen:
                bits.append("fullscreen")
        except Exception:
            pass
        try:
            if state & Qt.WindowState.WindowActive:
                bits.append("active")
        except Exception:
            pass
        return f"state={_state_value(state)}[{'+'.join(bits) if bits else 'normal'}]"
    except Exception:
        pass
    try:  # QWindow and friends expose visibility() instead of windowState().
        vis = window.visibility()
        name = vis.name if hasattr(vis, "name") else vis
        return f"vis={name}"
    except Exception:
        return "state=?"


def _describe(widget) -> str:
    if widget is None:
        return f"None {_app_snapshot()} t={time.monotonic():.3f}"
    try:
        cls = type(widget).__name__
        name = widget.objectName() or "<noname>"
        wid = f"0x{id(widget):x}"
        stamp = f"{time.monotonic():.3f}"
        window = None
        try:
            window = widget.window()
        except Exception:
            window = None
        if window is None and hasattr(widget, "isVisible"):
            window = widget  # top-level QWindow and friends have no .window().
        if window is None:
            return f"{cls}#{name} id={wid} (no-window) {_app_snapshot()} t={stamp}"
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
            f"{cls}#{name} id={wid} "
            f"(win={type(window).__name__} "
            f"minimized={minimized} visible={visible} active={active} "
            f"{_state_bits(window)} t={stamp} {_app_snapshot()})"
        )
    except Exception:
        return f"<undescribable {type(widget).__name__}>"


def _on_focus_changed(old, now) -> None:
    try:
        focus_debug("focus %s -> %s", _describe(old), _describe(now))
    except Exception:
        pass


if QObject is not None and QEvent is not None:

    class _WindowStateFilter(QObject):  # type: ignore[no-redef]
        """App-level ``WindowStateChange`` hook: synchronous minimized-now log.

        ``isMinimized()`` polled inside ``focusChanged`` can lag the actual
        minimize on some platforms; this filter logs the state change at
        event time so "focus requested after minimize" is visible even when
        the poll has not caught up yet. Pure observer — never consumes.
        """

        def eventFilter(self, watched, event):  # noqa: N802 - Qt API
            try:
                if event.type() == QEvent.Type.WindowStateChange:
                    try:
                        old_txt = _state_value(event.oldState())
                    except Exception:
                        old_txt = "?"
                    focus_debug(
                        "window-state %s old=%s now=%s",
                        _describe(watched),
                        old_txt,
                        _state_bits(watched),
                    )
            except Exception:
                pass
            return False

else:  # pragma: no cover - Qt unavailable

    _WindowStateFilter = None  # type: ignore[assignment]


def install_focus_tracer(app=None) -> bool:
    """Connect ``focusChanged`` logging. Idempotent; no-op when flag is off.

    When the flag is on, also drops the ``BlinkTable`` logger level to
    DEBUG if something else set it higher — otherwise the tracer's own
    ``logger.debug`` lines never reach any handler and the flag looks dead.
    Installs an app-level ``WindowStateChange`` event filter alongside the
    ``focusChanged`` connection so minimize transitions are logged
    synchronously (the ``isMinimized()`` poll in ``_describe`` can lag).
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
        try:
            if _WindowStateFilter is not None and id(app) not in _state_filters:
                filt = _WindowStateFilter(app)
                app.installEventFilter(filt)
                _state_filters[id(app)] = filt
        except Exception:
            pass
        focus_debug("tracer installed")
        return True
    except Exception:
        return False
