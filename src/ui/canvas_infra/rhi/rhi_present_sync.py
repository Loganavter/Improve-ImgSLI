"""Coax Wayland to show the latest QRhi buffer after interactive view changes.

Multi Compare (Vulkan + Wayland) can leave the *displayed* frame behind the
store zoom/pan: the percent chip already shows the final value, but the
canvas still looks like the previous notch. Opening any transient (RMB menu,
scroll-value cloud) once restacks the subsurface and the image “catches up”
in the zoom direction — with no store delta. Later flyouts are clean.

``setUpdatesEnabled(False)`` still showed that catch-up with no app present,
so this is compositor stacking, not a wrong redraw. Keyboard-focus parking
did not restore ``ApplicationActive`` and did not remove the bug.

Call :func:`schedule_compositor_sync` after zoom/pan/reset so the catch-up
happens on gesture settle instead of on the next flyout.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget

_DEBOUNCE_MS = 100
_TIMER_ATTR = "_qrhi_compositor_sync_timer"
_REASON_ATTR = "_qrhi_compositor_sync_reason"

# Minimum gap between real window raise/activate kicks (ms, monotonic).
# Wheel-zoom ticks arrive far faster than this while Qt still reports
# ApplicationInactive (the common Wayland scroll state), and every kick is
# an xdg-activation request — a per-tick storm of them is what the
# compositor answers with busy/loading cursor feedback (MC zoom showed it,
# IC zoom never calls this helper and stays quiet). The QRhi present fix
# only needs an occasional kick, not one per tick, so repeats inside the
# window are skipped. Tests reset ``_LAST_ACTIVE_KICK_MS`` directly.
_ACTIVE_KICK_COOLDOWN_MS = 500.0
_LAST_ACTIVE_KICK_MS: float | None = None


def _active_kick_now_ms() -> float:
    import time

    return time.monotonic() * 1000.0


def ensure_window_active_for_qrhi(widget: QWidget | None) -> bool:
    """Re-activate our window when Qt reports Inactive during canvas input.

    MC wheel zoom often runs under ``ApplicationInactive`` + ``focus=none``
    while the user is clearly interacting — Wayland then throttles the Vulkan
    subsurface until a transient restacks it.
    """
    if widget is None:
        return False
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = None
    win = widget.window()
    if app is None or win is None or not win.isVisible() or win.isMinimized():
        return False
    if app.applicationState() == Qt.ApplicationState.ApplicationActive:
        return False
    global _LAST_ACTIVE_KICK_MS
    now_ms = _active_kick_now_ms()
    if (
        _LAST_ACTIVE_KICK_MS is not None
        and now_ms - _LAST_ACTIVE_KICK_MS < _ACTIVE_KICK_COOLDOWN_MS
    ):
        # A kick landed very recently (e.g. the previous wheel tick of the
        # same gesture) — the window is already as active as one kick can
        # make it; another raise/activate would only feed the compositor's
        # busy feedback without making presents any more visible.
        return False
    win.raise_()
    win.activateWindow()
    _LAST_ACTIVE_KICK_MS = now_ms
    return True


def flush_qrhi_compositor(widget: QWidget | None, *, reason: str = "") -> None:
    """One-shot present + window update mirroring the first-flyout restack."""
    _ = reason
    try:
        is_vis = getattr(widget, "isVisible", None)
        if is_vis is None or not is_vis():
            return
    except (RuntimeError, AttributeError):
        return

    ensure_window_active_for_qrhi(widget)
    if widget is None:
        return
    win = widget.window()
    if win is not None:
        handle = win.windowHandle()
        if handle is not None:
            handle.requestUpdate()
        win.update()
    widget.update()
    parent = widget.parentWidget()
    if parent is not None:
        parent.update()

    try:
        from ui.overlay_layer import get_overlay_layer

        overlay = get_overlay_layer(widget)
        host = getattr(overlay, "host", None) if overlay is not None else None
        if host is not None:
            host.update()
    except Exception:
        pass


def schedule_compositor_sync(widget: QWidget | None, *, reason: str = "") -> None:
    """Debounce :func:`flush_qrhi_compositor` until the zoom/pan gesture settles."""
    if widget is None:
        return
    try:
        setattr(widget, _REASON_ATTR, reason)
    except Exception:
        return

    timer: QTimer | None = getattr(widget, _TIMER_ATTR, None)
    if timer is None:
        from PySide6.QtCore import QObject

        parent = widget if isinstance(widget, QObject) else None
        try:
            timer = QTimer(parent)
        except TypeError:
            timer = QTimer()
        timer.setSingleShot(True)

        def _fire(w: QWidget = widget) -> None:
            flush_qrhi_compositor(
                w, reason=str(getattr(w, _REASON_ATTR, "") or "")
            )

        timer.timeout.connect(_fire)
        try:
            setattr(widget, _TIMER_ATTR, timer)
        except Exception:
            pass
    timer.start(_DEBOUNCE_MS)