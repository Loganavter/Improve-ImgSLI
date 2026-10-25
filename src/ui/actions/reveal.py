"""Reveal an ActionTarget — pulse chrome, or open a title-bar menu row."""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from core.actions.types import ActionTarget
from ui.actions import widget_pulse
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

# After ``ensure_visible`` opens Settings / a flyout for the first time,
# activation / deferred geometry still emit Hide/Deactivate events that
# collapse toolkit ComboBox overlays. Wait longer than a single event-loop
# tick before resolve + pulse. Flyout + edit-row reveal needs a bit more.
_ENSURE_SETTLE_MS = 280


def _is_alive(widget: object) -> bool:
    """Best-effort Qt liveness check (fail-open without shiboken)."""
    try:
        from shiboken6 import isValid

        return bool(isValid(widget))
    except ImportError:
        return widget is not None
    except Exception:
        return False


def reveal_action_target(target: ActionTarget | None, *, delay_ms: int = 80) -> None:
    """Highlight ``target`` after Find Action closes.

    Plain targets pulse the widget. Menu targets (``menu_action_id`` set) force-open
    the title-bar dropdown owned by ``widget`` and pulse that row instead.
    Lazy targets may ``ensure_visible`` first, then ``resolve_widget``.
    """
    if target is None:
        return

    ensured = False
    ensure = getattr(target, "ensure_visible", None)
    if callable(ensure):
        try:
            ensure()
        except Exception:
            logger.debug("reveal ensure_visible failed", exc_info=True)
            return
        ensured = True

    def _pulse_now() -> None:
        # Timer slot: the target may have died while waiting (dialog closed,
        # tab switched). Validity-check before touching Qt, and never let a
        # dead target raise out of the slot.
        try:
            widget = target.resolve_widget_instance()
        except Exception:
            logger.debug("reveal resolve failed", exc_info=True)
            return
        if widget is None or not _is_alive(widget):
            return
        try:
            menu_action_id = getattr(target, "menu_action_id", None)
            if menu_action_id and isinstance(widget, QWidget):
                strip = widget.parentWidget()
                reveal = getattr(strip, "reveal_menu_action", None)
                if callable(reveal):
                    row = reveal(widget, menu_action_id)
                    if row is not None:
                        if _is_alive(row):
                            widget_pulse.pulse_widget(row)
                        return
                widget_pulse.pulse_widget(widget)
                return
            widget_pulse.pulse_widget(widget)
        except Exception:
            logger.debug("reveal pulse failed", exc_info=True)

    delay = max(0, int(delay_ms))
    if ensured:
        # Cards / pages / first Settings show need settle time before resolve.
        delay = max(delay, _ENSURE_SETTLE_MS)
    if delay == 0:
        _pulse_now()
    else:
        QTimer.singleShot(delay, _pulse_now)