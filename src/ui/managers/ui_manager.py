import logging
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from core.plugin_system.ui_integration import PluginUIRegistry
from ui.managers.dialog_manager import DialogManager
from ui.managers.message_manager import MessageManager
from ui.managers.transient_ui_manager import TransientUIManager
from ui.managers.ui_manager_parts import (
    initialize_ui_manager_post_transient,
    initialize_ui_manager_pre_transient,
)

logger = logging.getLogger("ImproveImgSLI")

class UIManager(QObject):
    def __init__(
        self,
        store,
        main_controller,
        ui,
        parent_widget,
        plugin_ui_registry: PluginUIRegistry | None = None,
    ):
        super().__init__(parent_widget)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.parent_widget = parent_widget
        self.app_ref = parent_widget
        self.plugin_ui_registry = plugin_ui_registry
        self.event_bus = main_controller.event_bus if main_controller else None
        self._settings_application_service = None
        self._unified_flyout_ref = None

        self._active_message_boxes = []
        initialize_ui_manager_pre_transient(self)
        self.transient = TransientUIManager(self)
        initialize_ui_manager_post_transient(self)
        self.dialogs = DialogManager(self)
        self.messages = MessageManager(self)

    def get_plugin_action(self, action_id: str) -> Callable[..., Any] | None:
        if self.plugin_ui_registry:
            return self.plugin_ui_registry.get_action(action_id)
        return None

    @property
    def unified_flyout(self):
        return self._unified_flyout_ref

    @unified_flyout.setter
    def unified_flyout(self, value):
        self._unified_flyout_ref = value

    def set_modal_dialog_active(self, active: bool):
        self._is_modal_active = active

    def show_flyout(self, image_number: int):
        self.transient.show_flyout(image_number)

    def _sync_flyout_combo_status(self):
        self.transient.sync_flyout_combo_status()

    def toggle_interpolation_flyout(self):
        self.transient.toggle_interpolation_flyout()

    def show_interpolation_flyout(self):
        self.transient.show_interpolation_flyout()

    def _apply_interpolation_choice(self, idx: int):
        self.transient.apply_interpolation_choice(idx)

    def _close_interpolation_flyout(self):
        self.transient.close_interpolation_flyout()

    def _on_interpolation_flyout_closed_event(self):
        self.transient.on_interpolation_flyout_closed_event()

    def toggle_font_settings_flyout(self, anchor_widget=None):
        self.transient.toggle_font_settings_flyout(anchor_widget)

    def show_font_settings_flyout(self, anchor_widget=None):
        self.transient.show_font_settings_flyout(anchor_widget)

    def hide_font_settings_flyout(self):
        self.transient.hide_font_settings_flyout()

    def repopulate_flyouts(self):
        self.transient.repopulate_flyouts()

    def _on_font_changed(self):
        self.transient.on_font_changed()

    def _on_flyout_item_chosen(self, index: int):
        pass

    def _on_flyout_closed(self, image_number: int):
        self.transient.on_flyout_closed(image_number)

    def _on_unified_flyout_closed(self):
        self.transient.on_unified_flyout_closed()

    def _update_magnifier_flyout_states(self):
        self.transient.magnifier.update_states()

    def _on_magnifier_toggle_with_hover(self, checked: bool):
        self.transient.magnifier.on_toggle_with_hover(checked)

    def _show_magnifier_visibility_flyout(self, reason: str = "hover"):
        self.transient.magnifier.show(reason)

    def _hide_magnifier_visibility_flyout(self):
        self.transient.magnifier.hide()

    def _show_magnifier_instances_popup(self):
        self.transient.magnifier_instances.show()

    def _hide_magnifier_instances_popup(self):
        self.transient.magnifier_instances.hide()

    def _on_magnifier_instances_count_changed(self):
        self.transient.magnifier_instances.on_count_changed()

    def eventFilter(self, watched, event):
        app = QApplication.instance()
        if (
            watched is self.parent_widget
            and event.type() == QEvent.Type.WindowDeactivate
        ):
            self._schedule_hide_transient_if_still_inactive()
        elif watched is self.parent_widget and event.type() in (
            QEvent.Type.Hide,
            QEvent.Type.Close,
        ):
            self.transient.hide_transient_same_window_ui(reason="window_hide_or_close")
        elif watched is app and event.type() == QEvent.Type.ApplicationDeactivate:
            self._schedule_hide_transient_if_still_inactive()
        if self.transient.event_filter(watched, event):
            return True
        return super().eventFilter(watched, event)

    def _schedule_hide_transient_if_still_inactive(self) -> None:
        """Wayland often flickers WindowDeactivate when in-window menus close.

        Defer the sweep and only run it if the app/window is still inactive.
        Modal rename/properties dialogs deactivate the main window while the
        app stays active — those must not dismiss the list flyout.
        """
        if getattr(self, "_deactivate_hide_scheduled", False):
            return
        self._deactivate_hide_scheduled = True

        def _maybe_hide() -> None:
            self._deactivate_hide_scheduled = False
            from ui.managers.transient_ui_parts.closing import (
                _modal_dialog_blocks_transient_hide,
            )

            if _modal_dialog_blocks_transient_hide(self):
                return
            gui = QGuiApplication.instance()
            app_active = (
                gui is not None
                and gui.applicationState() == Qt.ApplicationState.ApplicationActive
            )
            win_active = bool(self.parent_widget.isActiveWindow())
            if app_active and win_active:
                return
            self.transient.hide_transient_same_window_ui(
                reason="window_or_app_deactivate"
            )

        QTimer.singleShot(0, _maybe_hide)

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        self.transient.close_all_flyouts_if_needed(global_pos)

    def show_help_dialog(self, *, page: str | None = None, anchor: str | None = None):
        self.dialogs.show_help_dialog(page=page, anchor=anchor)

    def show_settings_dialog(self, *, section_id: str | None = None):
        self.dialogs.show_settings_dialog(section_id=section_id)

    def show_export_dialog(
        self,
        dialog_state,
        preview_image: object | None,
        suggested_filename: str = "",
        on_set_favorite_dir=None,
        native_size: tuple[int, int] | None = None,
    ):
        return self.dialogs.show_export_dialog(
            dialog_state, preview_image, suggested_filename, on_set_favorite_dir, native_size
        )

    def show_non_modal_message(self, kind, title: str, text: str):
        self.messages.show_non_modal_message(kind, title, text)

    def repopulate_visible_flyouts(self):
        import shiboken6 as sip

        flyout = self.unified_flyout
        if flyout is None or not sip.isValid(flyout):
            return
        try:
            visible = flyout.isVisible()
        except RuntimeError:
            return
        if visible:
            self.repopulate_flyouts()

    def hide_transient_same_window_ui(self):
        self.transient.hide_transient_same_window_ui()

    def _on_app_focus_changed(self, old_widget, new_widget):
        self.transient.on_app_focus_changed(old_widget, new_widget)
