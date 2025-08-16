from PyQt6.QtCore import Qt, QObject, QPoint, QTimer, QPropertyAnimation, QEasingCurve, QAbstractAnimation, QPointF, QRect
from PyQt6.QtWidgets import QMessageBox, QDialog, QApplication
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.help_dialog import HelpDialog
from ui.dialogs.export_dialog import ExportDialog
from ui.widgets.composite.unified_flyout import UnifiedFlyout, FlyoutMode
from core.constants import AppConstants
from resources.translations import tr
import gc
import sys
import logging
import time
from ui.widgets.composite.simple_options_flyout import SimpleOptionsFlyout
from core.font_manager import FontManager

logger = logging.getLogger("ImproveImgSLI")

class UIManager(QObject):
    def __init__(self, app_state, main_controller, ui, parent_widget):
        super().__init__(parent_widget)

        self.app_state = app_state
        self.main_controller = main_controller
        self.ui = ui
        self.parent_widget = parent_widget
        self.app_ref = parent_widget

        self.unified_flyout = UnifiedFlyout(self.parent_widget)
        self.font_settings_flyout = None
        self._is_modal_active = False

        try:
            self.unified_flyout.closing_animation_finished.connect(self._on_unified_flyout_closed)
        except Exception:
            pass

        self._help_dialog = None
        self._settings_dialog = None

        self._interp_flyout: SimpleOptionsFlyout | None = None
        self._interp_popup_open: bool = False
        self._interp_last_open_ts: float = 0.0

        self._font_popup_open: bool = False
        self._font_popup_last_open_ts: float = 0.0

        try:
            FontManager.get_instance().font_changed.connect(self._on_font_changed)
        except Exception:
            pass

    def set_modal_dialog_active(self, active: bool):
        self._is_modal_active = active

    def show_flyout(self, image_number: int):

        try:
            if (
                self.unified_flyout
                and self.unified_flyout.isVisible()
                and self.unified_flyout.mode == FlyoutMode.DOUBLE
            ):
                self.ui.combo_image1.setFlyoutOpen(False)
                self.ui.combo_image2.setFlyoutOpen(False)
                self.unified_flyout.start_closing_animation()
                return
        except Exception:
            pass

        try:
            if (
                self.unified_flyout
                and self.unified_flyout.isVisible()
                and self.unified_flyout.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_RIGHT)
                and self.unified_flyout.source_list_num == image_number
            ):
                button = self.ui.combo_image1 if image_number == 1 else self.ui.combo_image2
                button.setFlyoutOpen(False)
                self.unified_flyout.start_closing_animation()
                return
        except Exception:
            pass

        target_list = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2

        if len(target_list) == 0:
            return

        has_loaded_images = any(item[0] is not None for item in target_list)
        if not has_loaded_images:
            return

        button = self.ui.combo_image1 if image_number == 1 else self.ui.combo_image2
        other_button = self.ui.combo_image2 if image_number == 1 else self.ui.combo_image1

        other_button.setFlyoutOpen(False)
        button.setFlyoutOpen(True)

        self.unified_flyout.showAsSingle(image_number, button)

        try:

            def _sync_on_double():
                if self.unified_flyout.mode == FlyoutMode.DOUBLE:
                    self.ui.combo_image1.setFlyoutOpen(True)
                    self.ui.combo_image2.setFlyoutOpen(True)
            QTimer.singleShot(0, _sync_on_double)
        except Exception:
            pass

    def toggle_interpolation_flyout(self):
        try:
            if self._interp_popup_open:
                self._close_interpolation_flyout()
                return
        except Exception:
            pass
        self.show_interpolation_flyout()

    def show_interpolation_flyout(self):
        if not self._interp_flyout:
            self._interp_flyout = SimpleOptionsFlyout(self.parent_widget)
            try:

                self._interp_flyout.closed.connect(self._on_interpolation_flyout_closed_event)
            except Exception:
                pass

        from resources.translations import tr as _tr
        from core.constants import AppConstants as _AC
        lang = self.app_state.current_language
        labels: list[str] = []
        method_keys = list(_AC.INTERPOLATION_METHODS_MAP.keys())
        for key in method_keys:
            labels.append(_tr(_AC.INTERPOLATION_METHODS_MAP[key], lang))

        current_index = self.ui.combo_interpolation.currentIndex()
        if not (0 <= current_index < len(labels)):
            current_index = 0

        try:
            self._interp_flyout.item_chosen.disconnect()
        except Exception:
            pass

        try:
            item_height = self.ui.combo_interpolation.getItemHeight() if hasattr(self.ui.combo_interpolation, 'getItemHeight') else 34
        except Exception:
            item_height = 34
        try:
            item_font = self.ui.combo_interpolation.getItemFont() if hasattr(self.ui.combo_interpolation, 'getItemFont') else QApplication.font()
        except Exception:
            item_font = QApplication.font()
        try:
            self._interp_flyout.set_row_height(item_height)
            self._interp_flyout.set_row_font(item_font)
        except Exception:
            pass
        self._interp_flyout.populate(labels, current_index)
        self._interp_flyout.item_chosen.connect(self._apply_interpolation_choice)

        try:
            self.ui.combo_interpolation.setFlyoutOpen(True)
        except Exception:
            pass

        def _do_show():
            try:
                self._interp_flyout.show_below(self.ui.combo_interpolation)
                self._interp_popup_open = True
                self._interp_last_open_ts = time.monotonic()
            except Exception:
                logger.exception("UIManager.show_interpolation_flyout: failed to show (deferred)")
        QTimer.singleShot(0, _do_show)

    def _apply_interpolation_choice(self, idx: int):
        try:

            if 0 <= idx < self.ui.combo_interpolation.count():

                self.ui.combo_interpolation.setCurrentIndex(idx)

                self.main_controller.on_interpolation_changed(idx)
        finally:
            self._close_interpolation_flyout()

    def _close_interpolation_flyout(self):
        if self._interp_flyout:
            try:
                self._interp_flyout.hide()
            except Exception:
                logger.exception("UIManager._close_interpolation_flyout: exception while hiding flyout")
        try:
            self.ui.combo_interpolation.setFlyoutOpen(False)
        except Exception:
            pass
        self._interp_popup_open = False

    def _on_interpolation_flyout_closed_event(self):

        try:
            self.ui.combo_interpolation.setFlyoutOpen(False)
        except Exception:
            pass
        self._interp_popup_open = False

    def toggle_font_settings_flyout(self):
        if self._font_popup_open:
            self.hide_font_settings_flyout()
        else:
            self.show_font_settings_flyout()

    def show_font_settings_flyout(self):
        if not self.font_settings_flyout:
            return

        self.font_settings_flyout.set_values(
            self.app_state.font_size_percent,
            self.app_state.font_weight,
            self.app_state.file_name_color,
            self.app_state.file_name_bg_color,
            self.app_state.draw_text_background,
            self.app_state.text_placement_mode,
            getattr(self.app_state, 'text_alpha_percent', 100),
            self.app_state.current_language
        )
        self.font_settings_flyout.show_top_left_of(self.ui.btn_color_picker)
        self.ui.btn_color_picker.setFlyoutOpen(True)
        self._font_popup_open = True
        self._font_popup_last_open_ts = time.monotonic()

    def hide_font_settings_flyout(self):
        if self.font_settings_flyout:
            self.font_settings_flyout.hide()

    def repopulate_flyouts(self):
        if self.unified_flyout and self.unified_flyout.isVisible():
            self.unified_flyout.populate(1, self.app_state.image_list1)
            self.unified_flyout.populate(2, self.app_state.image_list2)
            if self.unified_flyout.mode == FlyoutMode.DOUBLE:
                QTimer.singleShot(0, self.unified_flyout.updateGeometryInDoubleMode)

    def _on_font_changed(self):
        try:
            self.repopulate_visible_flyouts()
            if hasattr(self.ui, 'reapply_button_styles'):
                self.ui.reapply_button_styles()
            if self.parent_widget:
                self.parent_widget.update()
        except Exception:
            pass

    def _on_flyout_item_chosen(self, index: int):
        pass

    def _on_flyout_closed(self, image_number: int):
        button = self.ui.combo_image1 if image_number == 1 else self.ui.combo_image2
        button.setFlyoutOpen(False)

    def _on_unified_flyout_closed(self):
        try:
            self.ui.combo_image1.setFlyoutOpen(False)
            self.ui.combo_image2.setFlyoutOpen(False)
        except Exception:
            pass

        try:
            self._on_flyout_closed(1)
            self._on_flyout_closed(2)
        except Exception:
            pass

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        if self._is_modal_active:
            return

        if self._font_popup_open and (time.monotonic() - self._font_popup_last_open_ts) > 0.12:

            flyout_global_rect = QRect(
                self.font_settings_flyout.mapToGlobal(QPoint(0, 0)),
                self.font_settings_flyout.size()
            )

            button_rect = self.ui.btn_color_picker.geometry()
            button_rect.moveTo(self.ui.btn_color_picker.mapToGlobal(QPoint(0,0)))

            if not flyout_global_rect.contains(global_pos.toPoint()) and not button_rect.contains(global_pos.toPoint()):
                self.hide_font_settings_flyout()

        if self._interp_popup_open and (time.monotonic() - self._interp_last_open_ts) < 0.12:
            return

        if not self.unified_flyout or not self.unified_flyout.isVisible():

            if self._interp_popup_open and self._interp_flyout:
                local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())

                try:
                    btn_rect = self.ui.combo_interpolation.rect()
                    btn_rect.moveTo(self.ui.combo_interpolation.mapTo(self.parent_widget, btn_rect.topLeft()))
                    if btn_rect.contains(local_pos):
                        return
                except Exception:
                    pass

                if not self._interp_flyout.geometry().contains(global_pos.toPoint()):
                    self._close_interpolation_flyout()
            return

        local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
        flyout_rect_local = self.unified_flyout.geometry()

        button_rects = []
        for btn in (self.ui.combo_image1, self.ui.combo_image2):
            rect = btn.rect()

            rect.moveTo(btn.mapTo(self.parent_widget, rect.topLeft()))
            button_rects.append(rect)

        is_click_on_any_button = any(r.contains(local_pos) for r in button_rects)
        is_click_inside_flyout = flyout_rect_local.contains(local_pos)

        if not is_click_on_any_button and not is_click_inside_flyout:
            self.unified_flyout.start_closing_animation()
            self.ui.combo_image1.setFlyoutOpen(False)
            self.ui.combo_image2.setFlyoutOpen(False)

        if self._interp_popup_open and self._interp_flyout:

            if not self._interp_flyout.geometry().contains(global_pos.toPoint()):
                self._close_interpolation_flyout()

    def show_help_dialog(self):

        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self.app_state.current_language, parent=self.parent_widget)

        if getattr(self._help_dialog, 'current_language', None) != self.app_state.current_language:
            try:
                if hasattr(self._help_dialog, 'update_language'):
                    self._help_dialog.update_language(self.app_state.current_language)
                else:

                    self._help_dialog.current_language = self.app_state.current_language
            except Exception:
                pass

        self._help_dialog.show()
        try:

            self._help_dialog.raise_()
            self._help_dialog.activateWindow()
        except Exception:
            pass

    def show_settings_dialog(self):

        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                current_language=self.app_state.current_language,
                current_theme=self.app_state.theme,
                current_max_length=self.app_state.max_name_length,
                min_limit=AppConstants.MIN_NAME_LENGTH_LIMIT,
                max_limit=AppConstants.MAX_NAME_LENGTH_LIMIT,
                debug_mode_enabled=self.app_state.debug_mode_enabled,
                system_notifications_enabled=getattr(self.app_state, 'system_notifications_enabled', True),
                current_resolution_limit=self.app_state.display_resolution_limit,
                parent=self.parent_widget,
                tr_func=tr,
                current_ui_font_mode=getattr(self.app_state, 'ui_font_mode', 'builtin'),
                current_ui_font_family=getattr(self.app_state, 'ui_font_family', ''),
            )

            self._settings_dialog.accepted.connect(lambda: self._apply_settings(self._settings_dialog.get_settings()))

            self._settings_dialog.destroyed.connect(lambda: setattr(self, "_settings_dialog", None))

        self._settings_dialog.show()
        try:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
        except Exception:
            pass

    def show_export_dialog(self, preview_image: object | None, suggested_filename: str = ""):
        dialog = ExportDialog(
            app_state=self.app_state,
            parent=None,
            tr_func=tr,
            preview_image=preview_image,
            suggested_filename=suggested_filename
        )
        return dialog.exec(), dialog.get_export_options()

    def _apply_settings(self, settings):
        new_lang, new_theme, new_max_length, new_debug, new_sys_notif, new_res_limit, new_ui_font_mode, new_ui_font_family = settings

        theme_changed = new_theme != self.app_state.theme
        if theme_changed:
            self.main_controller.app.apply_application_theme(new_theme)
        if new_res_limit != self.app_state.display_resolution_limit:
            self.app_state.display_resolution_limit = new_res_limit
        if new_max_length != self.app_state.max_name_length:
            self.app_state.max_name_length = new_max_length
        debug_changed = new_debug != self.app_state.debug_mode_enabled
        if debug_changed:
            self.app_state.debug_mode_enabled = new_debug
        if getattr(self.app_state, 'system_notifications_enabled', True) != new_sys_notif:
            self.app_state.system_notifications_enabled = new_sys_notif
        lang_changed = new_lang != self.app_state.current_language
        if lang_changed:
            self.main_controller.change_language(new_lang)

            if self._settings_dialog:
                self._settings_dialog.update_language(new_lang)

        font_mode_normalized = 'system_default' if new_ui_font_mode == 'system' else new_ui_font_mode
        font_mode_changed = font_mode_normalized != getattr(self.app_state, 'ui_font_mode', 'builtin')
        font_family_changed = (new_ui_font_family or "") != (getattr(self.app_state, 'ui_font_family', "") or "")
        if font_mode_changed or font_family_changed:
            self.app_state.ui_font_mode = font_mode_normalized
            self.app_state.ui_font_family = new_ui_font_family or ""
            FontManager.get_instance().apply_from_state(self.app_state)

            try:
                app = QApplication.instance()
                if app:
                    app.setStyleSheet(app.styleSheet())
            except Exception:
                pass
            try:
                self.main_controller.settings_manager._save_setting("ui_font_mode", self.app_state.ui_font_mode)
                self.main_controller.settings_manager._save_setting("ui_font_family", self.app_state.ui_font_family)
            except Exception:
                pass
        if debug_changed:
            QMessageBox.information(
                self.parent_widget,
                tr("Information", self.app_state.current_language),
                tr("Restart the application for the debug log setting to take full effect.", self.app_state.current_language),
            )

    def repopulate_visible_flyouts(self):
        if self.unified_flyout and self.unified_flyout.isVisible():
            self.repopulate_flyouts()
        else:
            pass
