from __future__ import annotations

import logging

import shiboken6 as sip
from PySide6.QtWidgets import QApplication, QDialog

from ui.context_menu.manager import get_context_menu_manager
from ui.host_debug import transient_close_debug
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


# --- process-global focus/close sweep guard --------------------------------
#
# ``QApplication.focusChanged`` is synchronous, and so is every ``hide()``
# that moves focus: a focus/close sweep can re-enter *itself* through routes a
# per-instance flag structurally cannot see:
#
# * a second ``UIManager`` instance — its own ``_in_focus_changed`` is free;
# * a manager resolved lazily *during* the sweep (one guard per tab);
# * a nested event pump — ``processEvents()`` / ``activateWindow()`` inside a
#   hide path delivers the deferred close timer (``QTimer.singleShot(0,
#   _run)``) while the first sweep is still on the stack, and every level then
#   emits the next ``focusChanged``.
#
# Live crash 2026-10-27 (RecursionError, ~1000 frames; the ``os.environ.get``
# in ``transient_close_debug`` is only where the stack ran out, not the
# cause): ``UIManager._on_app_focus_changed -> TransientUIManager.
# on_app_focus_changed -> PopupClosingController.on_app_focus_changed``
# repeated. The guard therefore has to be process-wide, with a hard depth of
# ONE sweep: "a focus/close sweep is already running in this process — bail
# out". It lives here (a leaf module both the slot and the controller can
# import) because ``ui_manager`` -> ``transient_ui_manager`` ->
# ``transient_ui_parts`` is the import direction; putting it in
# ``ui_manager`` would close that cycle.
#
# UI thread only: Qt delivers focus events and this timer on the GUI thread.
_MAX_SWEEP_DEPTH = 1
_sweep_depth = 0
_sweep_suppressed_logged = False


def begin_transient_sweep(origin: str) -> bool:
    """Claim the process-wide focus/close sweep slot.

    Returns False when a sweep is already running somewhere in this process —
    the caller must then return without touching transient UI (the running
    sweep is already doing it, and re-entering is what overflowed the stack).

    A True return MUST be paired with :func:`end_transient_sweep` in a
    ``finally``.

    The first suppression of a burst is logged once (``warning``, visible
    without ``--debug``); the remaining ~1000 re-entries of that same burst
    stay silent, so a recurrence leaves one line in ``log.txt`` instead of
    flooding it. The flag resets when the next outermost sweep starts.
    """
    global _sweep_depth, _sweep_suppressed_logged
    if _sweep_depth >= _MAX_SWEEP_DEPTH:
        if not _sweep_suppressed_logged:
            _sweep_suppressed_logged = True
            try:
                logger.warning(
                    "[transient-close] suppressed re-entrant focus/close sweep "
                    "(origin=%s, depth=%d)",
                    origin,
                    _sweep_depth,
                )
            except Exception:
                # Logging must never take the focus path down with it.
                pass
        return False
    _sweep_depth += 1
    _sweep_suppressed_logged = False
    return True


def end_transient_sweep() -> None:
    """Release the slot claimed by :func:`begin_transient_sweep`."""
    global _sweep_depth
    if _sweep_depth > 0:
        _sweep_depth -= 1


def transient_sweep_depth() -> int:
    """Current sweep nesting depth (diagnostics/tests; 0 when idle)."""
    return _sweep_depth


def _widget_under(widget, ancestor) -> bool:
    current = widget
    while current is not None:
        if current is ancestor:
            return True
        parent = getattr(current, "parentWidget", None)
        current = parent() if callable(parent) else None
    return False


def _safe_widget_label(widget):
    """Class name for focus-change diagnostics — never touches Qt.

    ``bool(widget)`` / ``repr(widget)`` on a half-deleted wrapper can run
    C++-side code; ``type(x).__name__`` is pure-Python and cannot recurse
    into logging or focus handling.
    """
    if widget is None:
        return None
    try:
        return type(widget).__name__
    except Exception:
        return "<undescribable>"


def _modal_dialog_blocks_transient_hide(host, widget=None) -> bool:
    """Keep flyouts open while a modal prompt (rename / properties / …) owns focus."""
    if getattr(host, "_is_modal_active", False):
        return True
    app = QApplication.instance()
    if isinstance(app, QApplication) and app.activeModalWidget() is not None:
        return True
    if widget is not None:
        try:
            window = widget.window()
        except RuntimeError:
            return False
        if isinstance(window, QDialog) and window.isModal():
            return True
    return False


class PopupClosingController:
    def __init__(self, manager):
        self.manager = manager
        self._tab_extension = self._resolve_tab_extension()

    def _resolve_tab_extension(self):
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        return registry.create_startup_service("popup_close_extension", self.manager)

    def close_all_flyouts_if_needed(self, global_pos):
        host = self.manager.host
        if host._is_modal_active:
            return
        get_context_menu_manager().hide_active_menu_if_outside(global_pos)
        if self._tab_extension is not None:
            self._tab_extension.close_at_pointer(global_pos)
        # Font settings / interp / options are FlyoutManager-owned; the tab
        # extension only knows UnifiedFlyout. Keep them on the same outside-click
        # path as the dual list.
        #
        # Deliberately not FlyoutManager.close_if_outside(): that calls
        # close_all(), which (unlike the manager's own app-wide event filter)
        # does not exempt pinned=True HUDs (ZoomIndicator, InfoHUD — see
        # FLYOUT_SYSTEM.md "Pinned flyouts", which promises outside clicks
        # never close them). This call exists because the QRhi canvas can
        # swallow the mouse press before it reaches the manager's own
        # eventFilter, so it must apply the same pinned exemption by hand
        # (_dismiss_passive, the exact routine the manager's eventFilter uses
        # for outside clicks) instead of delegating to the blunter close_all.
        try:
            from PySide6.QtCore import QPoint
            from sli_ui_toolkit.managers import FlyoutManager

            point = (
                global_pos.toPoint()
                if hasattr(global_pos, "toPoint")
                else QPoint(int(global_pos.x()), int(global_pos.y()))
            )
            manager = FlyoutManager.get_instance()
            if not manager._contains_global(point):
                manager._dismiss_passive()
        except Exception:
            pass

    def hide_transient_same_window_ui(self, *, reason: str = "unspecified"):
        import traceback

        # DIAGNOSTIC: log reason + caller for duplicate hide spams (file.settings → dialog)
        _caller = "".join(traceback.format_stack()[-4:-2])
        transient_close_debug(
            "hide_transient_same_window_ui reason=%s scheduled=%s caller=%s old_active=%s",
            reason,
            getattr(self, "_hide_transient_scheduled", False),
            _caller.strip(),
            getattr(self.manager.host, "_active_session_type", None),
        )
        # Coalesce bursts from deactivate + focus_changed in one event-loop turn.
        if getattr(self, "_hide_transient_scheduled", False):
            transient_close_debug("hide suppressed — already scheduled reason=%s", reason)
            return
        self._hide_transient_scheduled = True

        def _run() -> None:
            self._hide_transient_scheduled = False
            transient_close_debug("hide_run reason=%s", reason)
            if self._hide_transient_same_window_ui_now():
                return
            # A focus/close sweep is already on the stack (a nested event pump
            # delivering this timer, or the focus slot that scheduled us). Queue
            # the hide *behind* it instead of nesting it — the close must not be
            # lost, and it must not re-enter the sweep synchronously.
            self.hide_transient_same_window_ui(reason=f"{reason}:deferred")

        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, _run)

    def _hide_transient_same_window_ui_now(self) -> bool:
        # The real sweep runs under the process-global guard: a nested event
        # pump (``processEvents`` / ``activateWindow`` reached from a hide
        # path) can deliver ``_run`` again while this sweep is still on the
        # stack, and every nesting level hides → emits ``focusChanged`` →
        # schedules the next one. That nesting is the 2026-10-27
        # RecursionError, so the second sweep is dropped, not nested; ``_run``
        # re-queues it instead of losing it. Returns True when the sweep ran.
        if not begin_transient_sweep("PopupClosingController.hide_now"):
            return False
        try:
            self._hide_transient_same_window_ui_now_unchecked()
            return True
        finally:
            end_transient_sweep()

    def _hide_transient_same_window_ui_now_unchecked(self):
        host = self.manager.host
        # Deferred hide can run inside AppTextInputDialog.exec()'s nested loop —
        # do not tear down the list flyout while that modal is up.
        if _modal_dialog_blocks_transient_hide(host):
            return
        get_context_menu_manager().hide_active_menu()
        if self._tab_extension is not None:
            try:
                self._tab_extension.hide_same_window()
            except Exception:
                pass
        try:
            if host._interp_popup_open and host._interp_flyout is not None:
                self.manager.interpolation.close()
        except Exception:
            pass
        try:
            if host._font_popup_open and host.font_settings_flyout is not None:
                self.manager.font_settings.hide()
        except Exception:
            pass
        try:
            overlay_layer = getattr(host.parent_widget, "overlay_layer", None)
            if overlay_layer is not None:
                overlay_layer.hide_all_popups()
        except Exception:
            pass
        try:
            from events.drag_drop_handler import DragAndDropService
            service = DragAndDropService.get_instance()
            if service.is_dragging():
                service.cancel_drag()
        except Exception:
            pass
        try:
            from events.image_carry import ImageCarryService

            carry = ImageCarryService.get_instance()
            if carry.is_active():
                carry.cancel()
        except Exception:
            pass

    def _focus_aware_owners(self):
        # Use cached services only — accessing self.manager.interpolation /
        # font_settings here would force a TabRegistry probe on every
        # focusChanged (which fires at high frequency due to the flyout
        # focus guard). Passive focus checks must not create services.
        return (
            self._tab_extension,
            self.manager._services.get("interpolation"),
            self.manager._services.get("font_settings"),
        )

    def on_app_focus_changed(self, old_widget, new_widget):
        host = self.manager.host
        try:
            window_active = host.parent_widget.isActiveWindow() if hasattr(host, "parent_widget") else None
        except RuntimeError:
            window_active = None
        transient_close_debug(
            "on_app_focus_changed old=%s new=%s window_active=%s",
            _safe_widget_label(old_widget),
            _safe_widget_label(new_widget),
            window_active,
        )
        if _modal_dialog_blocks_transient_hide(host, new_widget):
            transient_close_debug("focus change blocked by modal")
            return
        try:
            window_active = host.parent_widget.isActiveWindow()
        except RuntimeError:
            window_active = None

        # Window fully deactivated → sweep. Otherwise ignore null-focus flicker.
        if new_widget is None:
            if window_active:
                return
            self.hide_transient_same_window_ui(reason="focus_null_inactive_window")
            return

        menu_manager = get_context_menu_manager()
        if menu_manager.active_menu_has_focus_inside(new_widget):
            return

        for owner in self._focus_aware_owners():
            if owner is not None and owner.has_focus_inside(new_widget):
                return

        try:
            from sli_ui_toolkit.managers import FlyoutManager

            active = FlyoutManager.get_instance().get_active_flyout()
            if active is not None and _widget_under(new_widget, active):
                return
        except Exception:
            pass

        # Only sweep when focus *left* a still-relevant popup owner.
        # Routine canvas ↔ button focus must not touch transient UI (canvas jerk).
        for owner in self._focus_aware_owners():
            if owner is None:
                continue
            try:
                left_owner = owner.has_focus_inside(old_widget)
            except Exception:
                left_owner = False
            if left_owner:
                self.hide_transient_same_window_ui(
                    reason=f"focus_left_{type(owner).__name__}"
                )
                return
