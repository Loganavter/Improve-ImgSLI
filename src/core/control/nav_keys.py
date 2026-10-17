"""Key delivery through the app's own keyboard navigation (write side).

A key the *user* presses reaches the window that holds OS focus and then travels
through the app's own filters, where ``NavigationManager``'s sections and each
surface's ``keyPressEvent`` decide what it means. ``press_keys`` does none of
that: it aims one event at one widget (right for a canvas, whose shortcuts are
not in the focus chain), so "the key reached the control" and "the key went
nowhere" look identical to a client.

This module is the write half: it delivers keys the way the running app receives
a real press and reports what happened, per key.

* the anchor is the widget a user's key would reach — the window's focus widget,
  or the element named by ``anchor`` (focused first, with the app's own
  focus-reason policy, so the keyboard ring behaves as it would for a human);
* the window is made OS-active first (``activated`` in the result): an inactive
  window receives no keys from a real keyboard at all, and the manager's filter
  is inert without that;
* every step reports the layer that took the key — ``section:<name>`` (a
  navigation section acted), ``focus`` (Qt moved focus, no section), ``surface``
  (the widget/surface's own handler took it without moving focus), ``unhandled``
  (the key was lost) — plus Qt's own ``accepted`` bit and the focus/owner change.

The model being measured is described in :mod:`core.control.nav_state`.
Live-only, GUI-thread only.
"""

from __future__ import annotations

import warnings
from typing import Any

from PySide6.QtCore import QEvent, QEventLoop, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from .discovery import MethodError, parse_key_sequence
from .elements.inventory import Element
from .elements.resolve import resolve_element
from .nav_state import element_map, focus_widget, nav_manager, owner_of, widget_row


def _activate_window(app: Any, window: Any) -> bool:
    """Make the app believe *window* holds OS focus — what a user's key implies.

    A real key can only reach the active window; the control channel drives an
    app that may be in the background, where Qt reports no focus widget and the
    navigation manager's filter goes inert (its KeyPress branch returns early on
    ``QApplication.focusWidget() is None``). ``QApplication.setActiveWindow`` is
    the only in-process seam that flips that (deprecated, still the documented
    one); when it is unavailable the honest ``activated: false`` stays in the
    result, because then a real keyboard could not reach the app either.
    """
    inst = app if app is not None else QApplication.instance()
    if not isinstance(window, QWidget) or inst is None:
        return False
    if hasattr(QApplication, "setActiveWindow"):
        try:
            with warnings.catch_warnings():
                # Deprecated in Qt, but the only in-process seam for this.
                warnings.simplefilter("ignore", DeprecationWarning)
                QApplication.setActiveWindow(window)
        except Exception:
            pass
    try:
        # Guard, never a bare kick: an xdg-activation on an already-active
        # window costs a frame of busy-cursor feedback (contract
        # tests/contracts/test_no_unconditional_activation.py).
        if not window.isActiveWindow():
            window.activateWindow()
    except Exception:
        pass
    try:
        inst.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    except Exception:
        pass
    try:
        return QApplication.focusWidget() is not None
    except Exception:
        return False


def _focus_anchor(
    *, registry: Any, app: Any, window: Any, element_id: str | None, manager
) -> tuple[QWidget | None, bool]:
    """Where a user's key would land; ``element_id`` focuses it first.

    Returns ``(widget, focused_by_us)``.
    """
    if element_id:
        element = resolve_element(registry, element_id)
        reason = Qt.FocusReason.OtherFocusReason
        try:
            if manager is not None:
                reason = manager.current_focus_reason()
        except Exception:
            pass
        try:
            element.widget.setFocus(reason)
        except Exception as exc:
            raise MethodError(
                f"could not focus {element_id!r}: {exc}",
                "the element may not accept keyboard focus (check its focus policy)",
            )
        if app is not None:
            try:
                app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            except Exception:
                pass
        return element.widget, True
    focused = focus_widget(window)
    if focused is not None:
        return focused, False
    try:
        if manager is not None:
            last = manager.last_keyboard_focus()
            if last is not None:
                return last, False
    except Exception:
        pass
    return (window if isinstance(window, QWidget) else None), False


def _snapshot(
    manager, elements: dict[int, Element], window: Any, *, accepted: bool = False
) -> dict[str, Any]:
    focus = focus_widget(window)
    last = None
    try:
        last = manager.last_keyboard_focus() if manager is not None else None
    except Exception:
        last = None
    return {
        "focus": focus,
        "focus_row": widget_row(focus, elements, manager),
        "last_keyboard_focus": last,
        "owner": owner_of(manager, focus),
        "accepted": bool(accepted),
    }


def _verdict(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Which layer took the key — derived, never guessed.

    ``section:<name>`` — a navigation section acted (the owner changed, or the
    keyboard-granted widget moved through a section's own ``navigate()``);
    ``focus`` — Qt moved focus without a section (Qt's own traversal);
    ``surface`` — the receiving widget/surface accepted the key without a focus
    change (its own ``keyPressEvent`` ran: an overlay walking its series, a
    button activating on Enter); ``unhandled`` — the key was ignored and nothing
    changed, i.e. a real key here would be lost.
    """
    if after["owner"] != before["owner"]:
        return f"section:{after['owner'] or before['owner'] or 'none'}"
    moved = after["last_keyboard_focus"] is not before["last_keyboard_focus"]
    if moved and after["owner"]:
        return f"section:{after['owner']}"
    if after["focus"] is not before["focus"] or moved:
        return "focus"  # Qt moved focus, yet no section owns either end
    if after.get("accepted"):
        return "surface"
    return "unhandled"


def deliver_nav_keys(
    *,
    registry: Any,
    app: Any,
    window: Any,
    keys: str | None,
    element_id: str | None = None,
) -> dict[str, Any]:
    """Send *keys* the way the running app receives a real key press.

    The event goes to the widget that holds what a user's key would reach — the
    window's focus widget (or the element named by ``element_id``, which is
    focused first) — and travels through the app's own event filters, so
    ``NavigationManager``'s sections and each surface's ``keyPressEvent`` take
    part in the decision exactly as they do for a human. Nothing is aimed at a
    single widget behind the routing (that is ``press_keys target=``).
    """
    sequence = parse_key_sequence(keys)
    manager = nav_manager()
    elements = element_map(registry)
    activated = _activate_window(app, window)
    anchor, focused_by_us = _focus_anchor(
        registry=registry,
        app=app,
        window=window,
        element_id=element_id,
        manager=manager,
    )
    if anchor is None:
        raise MethodError(
            "no live widget to receive keys",
            "focus a window first (e.g. open a tab), then retry",
        )
    steps: list[dict[str, Any]] = []
    for key, modifiers, label in sequence:
        before = _snapshot(manager, elements, window)
        press = QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
        try:
            QApplication.sendEvent(anchor, press)
            QApplication.sendEvent(anchor, QKeyEvent(QEvent.Type.KeyRelease, key, modifiers))
        except Exception as exc:
            raise MethodError(
                f"could not deliver {label!r}: {exc}",
                "the live window may be shutting down",
            )
        if app is not None:
            try:
                app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            except Exception:
                pass
        # ``isAccepted`` is Qt's own "a handler took this key" bit — the only
        # way to see a surface's own keyPressEvent act without moving focus
        # (an overlay walking its series, a button activating on Enter).
        accepted = bool(press.isAccepted())
        after = _snapshot(manager, elements, window, accepted=accepted)
        steps.append(
            {
                "key": label,
                "delivered_to": widget_row(anchor, elements, manager),
                "handled": _verdict(before, after),
                "accepted": after["accepted"],
                "focus_before": before["focus_row"],
                "focus_after": after["focus_row"],
                "owner_before": before["owner"],
                "owner_after": after["owner"],
            }
        )
    return {
        "source": "live",
        "keys": [label for _key, _mods, label in sequence],
        "count": len(sequence),
        "anchor": widget_row(anchor, elements, manager),
        "activated": activated,
        "focus_is_ours": focused_by_us,
        "focus_after": widget_row(focus_widget(window), elements, manager),
        "steps": steps,
    }


class NavMethodsMixin:
    """``ui_nav_state`` / ``nav_key``, mixed into ``ControlHandlers``."""

    def ui_nav_state(self, params: dict[str, Any]) -> dict[str, Any]:
        from .nav_state import nav_state_payload

        return nav_state_payload(
            registry=self._registry(),  # type: ignore[attr-defined]
            app=getattr(self, "_app", None),
            window=getattr(self, "_window", None),
        )

    def nav_key(self, params: dict[str, Any]) -> dict[str, Any]:
        return deliver_nav_keys(
            registry=self._registry(),  # type: ignore[attr-defined]
            app=getattr(self, "_app", None),
            window=getattr(self, "_window", None),
            keys=params.get("keys"),
            element_id=params.get("anchor") or params.get("from") or params.get("element_id"),
        )


__all__ = ["NavMethodsMixin", "deliver_nav_keys"]
