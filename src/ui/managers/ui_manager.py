import logging
from typing import Any, Callable

from PyQt6.QtCore import QEvent, QObject, QPointF
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.plugin_system.ui_integration import PluginUIRegistry
from ui.managers.dialog_manager import DialogManager
from ui.managers.message_manager import MessageManager
from ui.managers.transient_ui_manager import TransientUIManager
from ui.managers.ui_manager_parts import initialize_ui_manager

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
        initialize_ui_manager(self)
        self.dialogs = DialogManager(self)
        self.messages = MessageManager(self)
        self.transient = TransientUIManager(self)

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
        self.transient.update_magnifier_flyout_states()

    def _on_magnifier_toggle_with_hover(self, checked: bool):
        self.transient.on_magnifier_toggle_with_hover(checked)

    def _show_magnifier_visibility_flyout(self, reason: str = "hover"):
        self.transient.show_magnifier_visibility_flyout(reason)

    def _hide_magnifier_visibility_flyout(self):
        self.transient.hide_magnifier_visibility_flyout()

    def eventFilter(self, watched, event):
        app = QApplication.instance()
        if (
            watched is self.parent_widget
            and event.type()
            in (QEvent.Type.WindowDeactivate, QEvent.Type.Hide, QEvent.Type.Close)
        ):
            self.hide_transient_same_window_ui()
        elif watched is app and event.type() == QEvent.Type.ApplicationDeactivate:
            self.hide_transient_same_window_ui()
        if self.transient.event_filter(watched, event):
            return True
        return super().eventFilter(watched, event)

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        self.transient.close_all_flyouts_if_needed(global_pos)

    def show_help_dialog(self):
        self.dialogs.show_help_dialog()

    def show_settings_dialog(self):
        self.dialogs.show_settings_dialog()

    def show_export_dialog(
        self,
        dialog_state,
        preview_image: object | None,
        suggested_filename: str = "",
        on_set_favorite_dir=None,
    ):
        return self.dialogs.show_export_dialog(
            dialog_state, preview_image, suggested_filename, on_set_favorite_dir
        )

    def show_non_modal_message(self, icon, title: str, text: str):
        self.messages.show_non_modal_message(icon, title, text)

    def repopulate_visible_flyouts(self):
        if self.unified_flyout and self.unified_flyout.isVisible():
            self.repopulate_flyouts()

    def hide_transient_same_window_ui(self):
        self.transient.hide_transient_same_window_ui()

    def _on_app_focus_changed(self, old_widget, new_widget):
        self.transient.on_app_focus_changed(old_widget, new_widget)
