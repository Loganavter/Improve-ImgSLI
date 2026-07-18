from __future__ import annotations

import shiboken6 as sip
from PySide6.QtWidgets import QApplication, QDialog

from ui.context_menu.manager import get_context_menu_manager


def _widget_under(widget, ancestor) -> bool:
    current = widget
    while current is not None:
        if current is ancestor:
            return True
        parent = getattr(current, "parentWidget", None)
        current = parent() if callable(parent) else None
    return False


def _modal_dialog_blocks_transient_hide(host, widget=None) -> bool:
    """Keep flyouts open while a modal prompt (rename / properties / …) owns focus."""
    if getattr(host, "_is_modal_active", False):
        return True
    app = QApplication.instance()
    if app is not None and app.activeModalWidget() is not None:
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
        try:
            from PySide6.QtCore import QPoint
            from sli_ui_toolkit.managers import FlyoutManager

            point = (
                global_pos.toPoint()
                if hasattr(global_pos, "toPoint")
                else QPoint(int(global_pos.x()), int(global_pos.y()))
            )
            FlyoutManager.get_instance().close_if_outside(point)
        except Exception:
            pass

    def hide_transient_same_window_ui(self, *, reason: str = "unspecified"):
        # Coalesce bursts from deactivate + focus_changed in one event-loop turn.
        if getattr(self, "_hide_transient_scheduled", False):
            return
        self._hide_transient_scheduled = True

        def _run() -> None:
            self._hide_transient_scheduled = False
            self._hide_transient_same_window_ui_now()

        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, _run)

    def _hide_transient_same_window_ui_now(self):
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
        return (self._tab_extension, self.manager.interpolation, self.manager.font_settings)

    def on_app_focus_changed(self, old_widget, new_widget):
        host = self.manager.host
        if _modal_dialog_blocks_transient_hide(host, new_widget):
            return
        window_active = host.parent_widget.isActiveWindow()

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
