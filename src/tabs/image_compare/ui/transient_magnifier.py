from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QApplication

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer
from tabs.image_compare.canvas.registry import registry
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _query_overlay(store, capability_id: str, default=None):
    command = registry().get_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result


#: Attribute holding ``{key: _TransientWiring}`` on the owning widget. Stored
#: on the widget rather than on a module dict so it dies with the widget and a
#: controller built for a *different* page never inherits it.
_WIRING_ATTR = "_magnifier_transient_wiring"

#: Closing latch. Set on the manager chain (``TransientUIManager`` /
#: ``UIManager``) by ``TransientUIManager.shutdown``; read by every controller
#: before it reacts. The host window's own ``_closing`` flag (set by the first
#: shutdown step) is the second input, so a controller built *after* the
#: shutdown started is born inert instead of re-arming its timers.
_SHUTDOWN_LATCH_ATTR = "_transient_shutdown_latched"


def _manager_chain(manager):
    """``(manager, host, window)`` — the three nodes that may carry the latch."""
    host = getattr(manager, "host", None)
    window = getattr(host, "parent_widget", None)
    if window is not None:
        window_of = getattr(window, "window", None)
        if callable(window_of):
            try:
                window = window_of()
            except (RuntimeError, TypeError):
                pass
    return (manager, host, window)


def transient_shutdown_latched(manager) -> bool:
    """True once the host window / transient UI is closing.

    Three inputs, cheapest first: Qt's own ``closingDown()`` (already past the
    loop), the latch the shutdown step puts on the manager chain, and the
    host window's ``_closing`` flag (``MarkShuttingDownStep``). All of them
    are plain bool reads — this runs on every focus event, which during the
    owner's storm is every ~11 ms, so no imports or registry probes here.
    """
    try:
        if QApplication.closingDown():
            return True
    except Exception:
        pass
    for node in _manager_chain(manager):
        if node is None:
            continue
        try:
            if getattr(node, _SHUTDOWN_LATCH_ATTR, False):
                return True
            if getattr(node, "_closing", False):
                return True
        except (AttributeError, RuntimeError):
            continue
    return False


def latch_transient_shutdown(manager) -> None:
    """Engage the latch on the manager chain (idempotent)."""
    for node in _manager_chain(manager)[:2]:
        if node is None:
            continue
        try:
            setattr(node, _SHUTDOWN_LATCH_ATTR, True)
        except (AttributeError, TypeError):
            pass


class _TransientWiring:
    """One owning installation of an event filter plus its signal hooks.

    The owner is recorded on the widget (see ``_WIRING_ATTR``) so a second
    controller for the same widget can *take over*: Qt only dedupes the very
    same filter object, so two distinct hosts (a page rebuilt under a fresh
    ``UIManager``/``TransientUIManager``, a controller resolved twice) each get
    their own delivery and one focus event is handled — and logged — twice
    (``[magnifier-visibility] btn_magnifier event=8`` pairs, 2026-10-26).
    """

    __slots__ = ("widget", "key", "host", "targets", "connections")

    def __init__(self, widget, key: str, host, targets=(), connections=()):
        self.widget = widget
        self.key = key
        self.host = host
        self.targets = tuple(target for target in targets if target is not None)
        self.connections = list(connections)

    def teardown(self, *, force: bool = False) -> None:
        registry = getattr(self.widget, _WIRING_ATTR, None)
        if not force and registry is not None and registry.get(self.key) is not self:
            # Superseded by a newer owner: its filters are not ours to remove
            # (with a shared host object, removing here would deafen it).
            return
        for target in self.targets:
            try:
                target.removeEventFilter(self.host)
            except (AttributeError, RuntimeError):
                # Widget's C++ side already gone (page teardown race).
                pass
        for signal, slot in self.connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        if registry is not None and registry.get(self.key) is self:
            registry.pop(self.key, None)


def _wiring_registry(widget) -> dict:
    registry = getattr(widget, _WIRING_ATTR, None)
    if registry is None:
        registry = {}
        try:
            setattr(widget, _WIRING_ATTR, registry)
        except (AttributeError, TypeError):
            pass
    return registry


def release_wiring(widget, key: str) -> None:
    """Tear down a previous owner's installation for ``key`` on ``widget``.

    Called from every controller's wiring step *before* it installs its own:
    one widget, one live installation, regardless of how many controllers were
    constructed for it. Must run before the new filter is installed — with the
    same host object (a re-wire through the same manager) tearing down after
    would remove the filter just installed.
    """
    previous = _wiring_registry(widget).pop(key, None)
    if previous is not None:
        previous.teardown(force=True)


def bind_wiring(widget, key: str, host, targets=(), connections=()) -> _TransientWiring:
    """Record this installation as the widget's owner for ``key``."""
    wiring = _TransientWiring(widget, key, host, targets, connections)
    _wiring_registry(widget)[key] = wiring
    return wiring


class MagnifierVisibilityController:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget
        self._hover_timer = DelayedActionTimer(
            lambda: self.show(reason="hover"), parent=manager.host
        )
        self._last_flyout_hide_ts = 0.0
        self._wiring = None
        self._shutdown_done = False
        self._wire_button()

    def _is_latched(self) -> bool:
        return getattr(self, "_shutdown_done", False) or transient_shutdown_latched(
            self.manager
        )

    def _wire_button(self) -> None:
        host = self.manager.host
        btn = getattr(self.widget, "btn_magnifier", None)
        flyout = getattr(self.widget, "magnifier_visibility_flyout", None)
        if btn is None or flyout is None:
            return
        if self._is_latched():
            # Shutdown already started: install nothing, arm nothing.
            return
        btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        # Drop a previous owner's installation before installing ours: a
        # second construction for the same widget replaces it instead of
        # stacking a second filter (one focus event, one handler).
        release_wiring(self.widget, "visibility")
        targets = (
            btn,
            flyout,
            getattr(flyout, "btn_left", None),
            getattr(flyout, "btn_center", None),
            getattr(flyout, "btn_right", None),
        )
        for target in targets:
            if target is not None:
                target.installEventFilter(host)
        btn.toggled.connect(self.on_toggle_with_hover)
        self._wiring = bind_wiring(
            self.widget,
            "visibility",
            host,
            targets,
            [(btn.toggled, self.on_toggle_with_hover)],
        )
        # Один вызов вместо трёх проволочек — side декларирован на классе,
        # но оставляем императивный для надёжности (фасад оркестрирует nav+hover).
        try:
            from sli_ui_toolkit.managers import bind_flyout

            bind_flyout(btn, flyout, side="above")
        except Exception:
            pass

    def teardown(self) -> None:
        """Detach from the widget: filters, ``toggled``, pending hover timer.

        Used when a controller is replaced for the same widget and by tests;
        without it the host filter outlives the controller that dispatched to
        it (``TransientUIManager.event_filter`` keeps calling the cached
        service, so a stale filter is a duplicate-delivery source).
        """
        try:
            self._hover_timer.stop()
        except Exception:
            pass
        wiring, self._wiring = self._wiring, None
        if wiring is not None:
            wiring.teardown()

    def shutdown(self) -> None:
        """The host window is closing: stop reacting, for good.

        Called from the window close path (``MarkShuttingDownStep`` ->
        ``UIManager.shutdown`` -> ``TransientUIManager.shutdown``) *before*
        the steps that hide/close windows. Those steps still produce one last
        burst of focus events; while this controller stayed live, each
        FocusOut ran ``hide()`` (focus back to the button) and each FocusIn
        re-armed the hover timer that re-opens the flyout — the owner's
        post-close ``[magnifier-visibility] btn_magnifier event=9`` loop
        (2026-10-26). Latched, armed-off and un-wired, the burst is inert.
        """
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        latch_transient_shutdown(self.manager)
        try:
            self._hover_timer.stop()
        except Exception:
            pass
        flyout = getattr(self.widget, "magnifier_visibility_flyout", None)
        if flyout is not None:
            try:
                flyout.cancel_auto_hide()
            except Exception:
                pass
        self.teardown()

    def update_states(self):
        if self._is_latched():
            return
        host = self.manager.host
        try:
            model = _query_overlay(host.store, "overlay.active_state")
            show_center = getattr(host.store.viewport.view_state, "diff_mode", "off") != "off"
            left_on = bool(model.get("visible_left", True)) if model is not None else True
            center_on = bool(model.get("visible_center", True)) if model is not None else True
            right_on = bool(model.get("visible_right", True)) if model is not None else True
            self.widget.magnifier_visibility_flyout.set_mode_and_states(
                show_center, left_on, center_on, right_on
            )
        except Exception:
            pass

    def on_toggle_with_hover(self, checked: bool):
        if self._is_latched():
            return
        btn = getattr(self.widget, "btn_magnifier", None)
        if btn is None:
            return
        if not checked:
            try:
                self._hover_timer.stop()
            except Exception:
                pass
            self.hide(reason="main_toggle_disabled")
            return
        # Toggling the button with Enter/Space while it holds keyboard focus
        # (no mouse involved) never sets underMouse() -- mirror the hover
        # path for that case too, the same way on_count_changed does for the
        # instances counter, or a keyboard-driven "turn magnifier on" never
        # shows the flyout that mouse users get automatically.
        keyboard_driven = (
            bool(getattr(btn, "_keyboard_focus", False)) and btn.hasFocus()
        )
        if btn.underMouse() or keyboard_driven:
            QTimer.singleShot(0, lambda kd=keyboard_driven: self.show(reason="keyboard" if kd else "hover"))

    def show(self, reason: str = "hover"):
        if self._is_latched():
            return
        host = self.manager.host
        use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
        logger.debug("[magnifier-visibility] show() reason=%s use_magnifier=%s", reason, use_magnifier)
        if not use_magnifier:
            return
        # Hover now opens preview for both mouse and keyboard (user request:
        # "сделай чтобы открывались" on hover). No early return.
        if reason == "hover":
            pass
        try:
            self.manager.panel_instances.hide()
        except Exception:
            pass
        self.update_states()
        btn = getattr(self.widget, "btn_magnifier", None)
        if btn is None:
            return
        # Preview — keep focus on the anchor button (btn_magnifier) with its
        # ring; opening the flyout must not steal focus. register_nav_section
        # is False for BOTH hover and keyboard openings, deliberately: this
        # panel is transient and non-modal, so it stays outside the section
        # graph (the canonical preview shape, grab_focus=False plus
        # register_nav_section=False). Down/Up from the anchor must keep
        # walking the parent toolbar rows instead of entering a panel that
        # disappears on hover-out — the parent list keeps ownership of the
        # arrows. Enter is the explicit act that admits keyboard navigation
        # into the panel (see the FocusIn branch below and
        # PanelVisibilityFlyout.focus_first_child), which is also why
        # _keyboard_navigation_active stays tied to input modality (showEvent
        # sets it from last_input_was_keyboard) instead of being forced
        # False: a keyboard peek must allow Left/Right inside the toggle
        # immediately, while a hover open stays preview-only (mirrors the
        # bottom panel's zone logic).
        self.widget.magnifier_visibility_flyout.show_for_button(
            btn,
            host.parent_widget,
            hover_delay_ms=0,
            grab_focus=False,
            register_nav_section=False,
            animation="none",
        )
        host._magn_popup_open = True
        host._magn_popup_last_open_ts = time.monotonic()
        if reason == "wheel":
            self.widget.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_WHEEL_AUTO_HIDE_DELAY_MS
            )
        else:
            self.widget.magnifier_visibility_flyout.cancel_auto_hide()

    def hide(self, reason: str = "explicit"):
        if self._is_latched():
            return
        host = self.manager.host
        try:
            self._hover_timer.stop()
        except Exception:
            pass
        self.widget.magnifier_visibility_flyout.hide()
        host._magn_popup_open = False

    def event_filter(self, watched, event):
        if self._is_latched():
            return False
        host = self.manager.host
        btn = getattr(self.widget, "btn_magnifier", None)
        if btn is None:
            return False
        if watched is btn:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                logger.debug(
                    "[magnifier-visibility] btn_magnifier event=%s reason=%s",
                    event.type(),
                    getattr(event, "reason", lambda: None)(),
                )
            return self._handle_button_event(event)
        if watched is self.widget.magnifier_visibility_flyout:
            return self._handle_flyout_event(event)
        flyout = self.widget.magnifier_visibility_flyout
        if watched in (
            getattr(flyout, "btn_left", None),
            getattr(flyout, "btn_center", None),
            getattr(flyout, "btn_right", None),
        ):
            return self._handle_child_event(event)
        return False

    def _handle_button_event(self, event):
        host = self.manager.host
        btn = getattr(self.widget, "btn_magnifier", None)
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
            if use_magnifier:
                self.show(reason="hover")
            return False
        if et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            # Schedule hide on leave, but keep open if cursor moves to flyout itself
            # (handled by _handle_flyout_event). Use auto-hide delay.
            self.widget.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS
            )
            return False
        if et == QEvent.Type.FocusIn:
            reason = getattr(event, "reason", lambda: None)()
            is_keyboard = reason not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            )
            use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
            if is_keyboard and use_magnifier:
                # Keyboard focus alone shows the panel flyout as a preview
                # (no focus steal) — actual keyboard navigation inside the
                # flyout still requires explicit Enter (see
                # PanelVisibilityFlyout._keyboard_navigation_active).
                self._hover_timer.stop()
                # Use hover delay to avoid flicker on rapid Tab
                self._hover_timer.start(AppConstants.TRANSIENT_HOVER_OPEN_DELAY_MS)
            return False
        if et == QEvent.Type.FocusOut:
            # Mirror bottom MagnifierSettingsHoverController: stay open while
            # focus is inside btn+flyout, hide when it leaves (keyboard-driven).
            # Without this, Up→enter keeps flyout alive but Up→previous-row
            # would never close it; the hover-leave timer alone is too slow for
            # keyboard.
            from PySide6.QtWidgets import QApplication as _QApp

            _new = _QApp.focusWidget()
            _flyout = self.widget.magnifier_visibility_flyout
            _still = _new is not None and (
                _new is btn or (_flyout is not None and _flyout.isAncestorOf(_new))
            )
            if not _still:
                # Keep open only if focus ring still alive on btn/flyout and
                # last input was keyboard — same guard as bottom panel.
                try:
                    from sli_ui_toolkit.ui.managers.navigation_manager import (
                        NavigationManager as _NM,
                    )

                    _has_ring = bool(getattr(btn, "_keyboard_focus", False) and btn.hasFocus())
                    if not _has_ring:
                        # Check flyout children rings as well
                        for _b in (
                            getattr(_flyout, "btn_left", None),
                            getattr(_flyout, "btn_center", None),
                            getattr(_flyout, "btn_right", None),
                        ):
                            if _b is not None and getattr(_b, "_keyboard_focus", False) and _b.hasFocus():
                                _has_ring = True
                                break
                    if not _has_ring or not _NM.get_instance().last_input_was_keyboard():
                        self.hide(reason="focus_out")
                        return False
                except Exception:
                    pass
                # Still hide when focus truly left the unit
                self.widget.magnifier_visibility_flyout.schedule_auto_hide(0)
            return False
        if et == QEvent.Type.Wheel:
            use_magnifier = bool(_query_overlay(host.store, "overlay.enabled", False))
            if not use_magnifier:
                return True
            self.show(reason="wheel")
            return True
        return False

    def _handle_flyout_event(self, event):
        host = self.manager.host
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            self.widget.magnifier_visibility_flyout.cancel_auto_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            self.widget.magnifier_visibility_flyout.schedule_auto_hide(
                AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS
            )
        elif et == QEvent.Type.Hide:
            self._last_flyout_hide_ts = time.monotonic()
        return False

    def _handle_child_event(self, event):
        flyout = self.widget.magnifier_visibility_flyout
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            flyout.cancel_auto_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            flyout.schedule_auto_hide(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)
        return False
