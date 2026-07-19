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


def ensure_window_active_for_qrhi(widget: QWidget | None) -> bool:
    """Re-activate our window when Qt reports Inactive during canvas input.

    MC wheel zoom often runs under ``ApplicationInactive`` + ``focus=none``
    while the user is clearly interacting — Wayland then throttles the Vulkan
    subsurface until a transient restacks it.
    """
    if widget is None:
        return False
    app = QApplication.instance()
    win = widget.window()
    if app is None or win is None or not win.isVisible() or win.isMinimized():
        return False
    if app.applicationState() == Qt.ApplicationState.ApplicationActive:
        return False
    win.raise_()
    win.activateWindow()
    return True


def flush_qrhi_compositor(widget: QWidget | None, *, reason: str = "") -> None:
    """One-shot present + window update mirroring the first-flyout restack."""
    _ = reason
    if widget is None:
        return
    try:
        if not widget.isVisible():
            return
    except RuntimeError:
        return

    ensure_window_active_for_qrhi(widget)
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
