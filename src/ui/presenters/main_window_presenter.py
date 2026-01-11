import logging
import os
import re
import threading

import PIL.Image
from PyQt6.QtCore import QObject, QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QWidget,
)

from core.store import Store
from core.constants import AppConstants
from core.events import CoreUpdateRequestedEvent
from core.main_controller import MainController
from shared.image_processing.resize import resize_images_processor
from resources.translations import tr
from ui.icon_manager import AppIcon, get_app_icon
from ui.main_window_ui import Ui_ImageComparisonApp
from core.plugin_system.ui_integration import PluginUIRegistry
from ui.managers.ui_manager import UIManager
from ui.presenters.ui_update_batcher import UIUpdateBatcher
from ui.presenters.image_canvas_presenter import ImageCanvasPresenter
from ui.presenters.toolbar_presenter import ToolbarPresenter
from plugins.export.presenter import ExportPresenter
from plugins.settings.presenter import SettingsPresenter
from utils.resource_loader import get_magnifier_drawing_coords
from shared_toolkit.workers import GenericWorker
logger = logging.getLogger("ImproveImgSLI")

class MainWindowPresenter(QObject):
    def __init__(
        self,
        main_window_app: QWidget,
        ui: Ui_ImageComparisonApp,
        store: Store,
        main_controller: MainController,
        plugin_ui_registry: PluginUIRegistry | None = None,
    ):
        super().__init__(main_window_app)
        self.main_window_app = main_window_app
        self.ui = ui
        self.store = store
        self.main_controller = main_controller
        self.plugin_ui_registry = plugin_ui_registry
        self.event_bus = main_controller.event_bus if main_controller else None

        self.ui_manager = UIManager(
            store,
            main_controller,
            ui,
            main_window_app,
            plugin_ui_registry=plugin_ui_registry,
        )
        self.ui_batcher = UIUpdateBatcher(self)

        self.image_canvas_presenter = ImageCanvasPresenter(store, main_controller, ui, main_window_app)
        self.toolbar_presenter = ToolbarPresenter(store, main_controller, ui, main_window_app, ui_manager=self.ui_manager)
        self.export_presenter = ExportPresenter(
            store, main_controller, self.ui_manager, main_window_app, main_window_app.font_path_absolute
        )
        self.settings_presenter = SettingsPresenter(store, main_controller, self.ui_manager, main_window_app)

        from toolkit.widgets.composite.text_settings_flyout import FontSettingsFlyout
        self.font_settings_flyout = FontSettingsFlyout(main_window_app)
        self.font_settings_flyout.hide()
        self.ui_manager.font_settings_flyout = self.font_settings_flyout

        self._orientation_popup = None
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.timeout.connect(self._hide_orientation_popup)

        self._file_dialog = None
        self._first_dialog_load_pending = True

        self._connect_signals()

        try:
            self._apply_initial_settings_to_ui()
            self.ui.update_translations(self.store.settings.current_language)
            self.update_slider_tooltips()
            self.ui.reapply_button_styles()
            self.repopulate_flyouts()

            if self.main_controller is not None and self.main_controller.plugin_coordinator is not None:
                layout_plugin = self.main_controller.plugin_coordinator.get_plugin("layout")
                if layout_plugin is not None:
                    layout_plugin.setup_ui_reference(self.ui)
        except Exception as e:
            logger.exception("MainWindowPresenter.__init__: error during initialization")

    def _connect_signals(self):

        self.font_settings_flyout.closed.connect(self._on_font_flyout_closed)
        self.store.state_changed.connect(self._on_store_state_changed)
        from core.events import SettingsApplyFontSettingsEvent
        if self.event_bus:
            self.font_settings_flyout.settings_changed.connect(
                lambda size, weight, color, bg_color, draw_bg, placement, alpha:
                self.event_bus.emit(SettingsApplyFontSettingsEvent(size, weight, color, bg_color, draw_bg, placement, alpha))
            )
        else:
            self.font_settings_flyout.settings_changed.connect(self.main_controller.apply_font_settings)

        self.main_controller.error_occurred.connect(self._on_error_occurred)
        self.main_controller.update_requested.connect(self._on_update_requested)
        self.main_controller.ui_update_requested.connect(self._on_ui_update_requested)
        self.main_controller.start_interactive_movement.connect(self.start_interactive_movement)
        self.main_controller.stop_interactive_movement.connect(self.stop_interactive_movement)

        self.main_controller.start_interactive_movement.connect(self.image_canvas_presenter.start_interactive_movement)
        self.main_controller.stop_interactive_movement.connect(self.image_canvas_presenter.stop_interactive_movement)

        def handle_load_button(image_number):
            self._open_image_dialog(image_number)
        self.ui.btn_image1.clicked.connect(lambda: handle_load_button(1))
        self.ui.btn_image2.clicked.connect(lambda: handle_load_button(2))

        self.ui.btn_color_picker.clicked.connect(lambda: self.ui_manager.toggle_font_settings_flyout(anchor_widget=self.ui.btn_color_picker))

        self._connect_button_action(
            self.ui.btn_quick_save,
            "quick_save",
            self.export_presenter.quick_save,
        )
        self.ui.btn_save.clicked.connect(self.export_presenter.save_result)

        if hasattr(self.ui.btn_magnifier_color_settings, 'set_store'):
            self.ui.btn_magnifier_color_settings.set_store(self.store)

        self.ui.btn_magnifier_color_settings.smartColorSetRequested.connect(
            self.settings_presenter.apply_smart_magnifier_colors
        )
        self.ui.btn_magnifier_color_settings.colorOptionClicked.connect(
            self._on_color_option_clicked
        )

        self.ui.btn_magnifier_color_settings.elementHovered.connect(
            self._on_magnifier_element_hovered
        )
        self.ui.btn_magnifier_color_settings.elementHoverEnded.connect(
            self._on_magnifier_element_hover_ended
        )

        if hasattr(self.ui, 'btn_magnifier_color_settings_beginner'):
            if hasattr(self.ui.btn_magnifier_color_settings_beginner, 'set_store'):
                self.ui.btn_magnifier_color_settings_beginner.set_store(self.store)

            self.ui.btn_magnifier_color_settings_beginner.smartColorSetRequested.connect(
                self.settings_presenter.apply_smart_magnifier_colors
            )
            self.ui.btn_magnifier_color_settings_beginner.colorOptionClicked.connect(
                self._on_color_option_clicked
            )

            self.ui.btn_magnifier_color_settings_beginner.elementHovered.connect(
                self._on_magnifier_element_hovered
            )
            self.ui.btn_magnifier_color_settings_beginner.elementHoverEnded.connect(
                self._on_magnifier_element_hover_ended
            )
        self.ui.btn_magnifier_guides.toggled.connect(self._on_magnifier_guides_toggled)
        self.ui.btn_magnifier_guides.valueChanged.connect(self._on_magnifier_guides_thickness_changed)

        if hasattr(self.ui, 'btn_magnifier_guides_simple'):
            self.ui.btn_magnifier_guides_simple.toggled.connect(self._on_magnifier_guides_toggled)
        if hasattr(self.ui, 'btn_magnifier_guides_width'):
            self.ui.btn_magnifier_guides_width.valueChanged.connect(self._on_magnifier_guides_thickness_changed)

        self.toolbar_presenter.connect_signals()

    def _connect_button_action(self, button, action_id, fallback):
        handler = None
        if self.plugin_ui_registry:
            handler = self.plugin_ui_registry.get_action(action_id)
        if handler:
            button.clicked.connect(handler)
        else:
            button.clicked.connect(fallback)

    def connect_event_handler_signals(self, event_handler):
        self.image_canvas_presenter.connect_event_handler_signals(event_handler)

        if hasattr(self.ui, 'image_label'):
            self.ui.image_label.mousePressed.connect(event_handler.mouse_press_event_on_image_label_signal.emit)
            self.ui.image_label.mouseMoved.connect(event_handler.mouse_move_event_on_image_label_signal.emit)
            self.ui.image_label.mouseReleased.connect(event_handler.mouse_release_event_on_image_label_signal.emit)
            self.ui.image_label.keyPressed.connect(event_handler.keyboard_press_event_signal.emit)
            self.ui.image_label.keyReleased.connect(event_handler.keyboard_release_event_signal.emit)
            self.ui.image_label.wheelScrolled.connect(event_handler.mouse_wheel_event_on_image_label_signal.emit)

        event_handler.mouse_press_event_signal.connect(self._handle_global_mouse_press)

        self.main_controller.start_interactive_movement.connect(event_handler.start_interactive_movement)
        self.main_controller.stop_interactive_movement.connect(event_handler.stop_interactive_movement)

    def _on_interpolation_combo_clicked(self):
        self.ui_manager.toggle_interpolation_flyout()

    def repopulate_flyouts(self):
        if self.ui_manager:
            self.ui_manager.repopulate_flyouts()

    def _handle_global_mouse_press(self, event):
        global_pos = event.globalPosition()
        def _close_popups():
            self.ui_manager.close_all_flyouts_if_needed(global_pos)
        QTimer.singleShot(0, _close_popups)

    def _on_font_flyout_closed(self):
        self.ui_manager._font_popup_open = False
        self.ui.btn_color_picker.setFlyoutOpen(False)

    def _apply_initial_settings_to_ui(self):

        self.ui.slider_size.setValue(int(self.store.viewport.magnifier_size_relative * 100))
        self.ui.slider_capture.setValue(int(self.store.viewport.capture_size_relative * 100))
        self.ui.slider_speed.setValue(int(self.store.viewport.movement_speed_per_sec * 10))

        divider_thickness = 0 if not self.store.viewport.divider_line_visible else self.store.viewport.divider_line_thickness
        magnifier_thickness = 0 if not self.store.viewport.magnifier_divider_visible else self.store.viewport.magnifier_divider_thickness

        self.ui.btn_orientation.set_value(divider_thickness)
        self.ui.btn_magnifier_orientation.set_value(magnifier_thickness)

        self.ui.btn_orientation.setChecked(self.store.viewport.is_horizontal, emit_signal=False)
        self.ui.btn_magnifier_orientation.setChecked(self.store.viewport.magnifier_is_horizontal, emit_signal=False)

        if hasattr(self.ui, 'btn_orientation_simple'):
            self.ui.btn_orientation_simple.setChecked(self.store.viewport.is_horizontal, emit_signal=False)
        if hasattr(self.ui, 'btn_divider_visible'):

            self.ui.btn_divider_visible.setChecked(not self.store.viewport.divider_line_visible, emit_signal=False)
        if hasattr(self.ui, 'btn_divider_width'):
            self.ui.btn_divider_width.set_value(divider_thickness)

        if hasattr(self.ui, 'btn_divider_color') and hasattr(self.ui.btn_divider_color, 'set_color'):
            self.ui.btn_divider_color.set_color(self.store.viewport.divider_line_color)
        if hasattr(self.ui, 'btn_magnifier_orientation_simple'):
            self.ui.btn_magnifier_orientation_simple.setChecked(self.store.viewport.magnifier_is_horizontal, emit_signal=False)
        if hasattr(self.ui, 'btn_magnifier_divider_visible'):

            self.ui.btn_magnifier_divider_visible.setChecked(not self.store.viewport.magnifier_divider_visible, emit_signal=False)
        if hasattr(self.ui, 'btn_magnifier_divider_width'):
            self.ui.btn_magnifier_divider_width.set_value(magnifier_thickness)

        if hasattr(self.ui, 'btn_magnifier_guides_simple'):
            self.ui.btn_magnifier_guides_simple.setChecked(self.store.viewport.show_magnifier_guides, emit_signal=False)
        if hasattr(self.ui, 'btn_magnifier_guides_width'):
            self.ui.btn_magnifier_guides_width.set_value(self.store.viewport.magnifier_guides_thickness)

        self.ui.btn_magnifier.setChecked(self.store.viewport.use_magnifier, emit_signal=False)
        self.ui.btn_freeze.setChecked(self.store.viewport.freeze_magnifier, emit_signal=False)
        self.ui.btn_magnifier_guides.setChecked(self.store.viewport.show_magnifier_guides, emit_signal=False)
        self.ui.btn_magnifier_guides.set_value(self.store.viewport.magnifier_guides_thickness)
        self.ui.btn_file_names.setChecked(self.store.viewport.include_file_names_in_saved, emit_signal=False)

        current_mode = getattr(self.store.settings, "ui_mode", "beginner")
        if hasattr(self.ui.btn_orientation, 'set_show_underline'):
            if current_mode == "advanced":
                self.ui.btn_orientation.set_show_underline(False)
            else:
                self.ui.btn_orientation.set_show_underline(True)
        if hasattr(self.ui.btn_orientation, 'set_color'):
            self.ui.btn_orientation.set_color(self.store.viewport.divider_line_color)
        if hasattr(self.ui.btn_magnifier_orientation, 'set_color'):
            self.ui.btn_magnifier_orientation.set_color(self.store.viewport.magnifier_divider_color)

        if hasattr(self.ui, 'btn_divider_color') and hasattr(self.ui.btn_divider_color, 'set_color'):
            self.ui.btn_divider_color.set_color(self.store.viewport.divider_line_color)

        if hasattr(self.ui, 'btn_magnifier_color_settings_beginner') and hasattr(self.ui.btn_magnifier_color_settings_beginner, 'button'):
            if hasattr(self.ui.btn_magnifier_color_settings_beginner.button, 'set_color'):
                self.ui.btn_magnifier_color_settings_beginner.button.set_color(self.store.viewport.magnifier_divider_color)

        self.ui.toggle_edit_layout_visibility(self.store.viewport.include_file_names_in_saved)
        self.ui.toggle_magnifier_panel_visibility(self.store.viewport.use_magnifier)

        self.ui.btn_file_names.setChecked(self.store.viewport.include_file_names_in_saved, emit_signal=False)

        if self.font_settings_flyout:
            self.font_settings_flyout.set_values(
                self.store.viewport.font_size_percent,
                self.store.viewport.font_weight,
                self.store.viewport.file_name_color,
                self.store.viewport.file_name_bg_color,
                self.store.viewport.draw_text_background,
                self.store.viewport.text_placement_mode,
                self.store.viewport.text_alpha_percent,
                self.store.settings.current_language
            )

        self.settings_presenter.update_interpolation_combo_box_ui()
        self.settings_presenter.setup_view_buttons()

        self.update_file_names_display()
        self.on_language_changed()

    def _on_store_state_changed(self, domain: str):
        if domain in ("viewport", "document", "settings"):

            if domain == "settings":
                current_mode = getattr(self.store.settings, "ui_mode", "beginner")
                if hasattr(self.ui.btn_orientation, 'set_show_underline'):
                    if current_mode == "advanced":
                        self.ui.btn_orientation.set_show_underline(False)
                    else:
                        self.ui.btn_orientation.set_show_underline(True)

            self.ui.toggle_magnifier_panel_visibility(self.store.viewport.use_magnifier)

            if self.ui.btn_orientation.isChecked() != self.store.viewport.is_horizontal:
                self.ui.btn_orientation.setChecked(self.store.viewport.is_horizontal, emit_signal=False)
            if self.ui.btn_magnifier_orientation.isChecked() != self.store.viewport.magnifier_is_horizontal:
                self.ui.btn_magnifier_orientation.setChecked(self.store.viewport.magnifier_is_horizontal, emit_signal=False)

            divider_thickness = 0 if not self.store.viewport.divider_line_visible else self.store.viewport.divider_line_thickness
            magnifier_thickness = 0 if not self.store.viewport.magnifier_divider_visible else self.store.viewport.magnifier_divider_thickness

            if self.ui.btn_orientation.get_value() != divider_thickness:
                self.ui.btn_orientation.set_value(divider_thickness)
            if self.ui.btn_magnifier_orientation.get_value() != magnifier_thickness:
                self.ui.btn_magnifier_orientation.set_value(magnifier_thickness)

            if self.ui.btn_magnifier_guides.isChecked() != self.store.viewport.show_magnifier_guides:
                self.ui.btn_magnifier_guides.setChecked(self.store.viewport.show_magnifier_guides, emit_signal=False)
            if self.ui.btn_magnifier_guides.get_value() != self.store.viewport.magnifier_guides_thickness:
                self.ui.btn_magnifier_guides.set_value(self.store.viewport.magnifier_guides_thickness)

            current_mode = getattr(self.store.settings, "ui_mode", "beginner")
            if hasattr(self.ui.btn_orientation, 'set_color'):
                if current_mode == "advanced":
                    if hasattr(self.ui.btn_orientation, 'set_show_underline'):
                        self.ui.btn_orientation.set_show_underline(False)
                else:
                    if hasattr(self.ui.btn_orientation, 'set_show_underline'):
                        self.ui.btn_orientation.set_show_underline(True)
                self.ui.btn_orientation.set_color(self.store.viewport.divider_line_color)
            if hasattr(self.ui.btn_magnifier_orientation, 'set_color'):
                self.ui.btn_magnifier_orientation.set_color(self.store.viewport.magnifier_divider_color)

            if hasattr(self.ui, 'btn_divider_color') and hasattr(self.ui.btn_divider_color, 'set_color'):
                self.ui.btn_divider_color.set_color(self.store.viewport.divider_line_color)

            if hasattr(self.ui, 'btn_magnifier_color_settings_beginner') and hasattr(self.ui.btn_magnifier_color_settings_beginner, 'button'):
                if hasattr(self.ui.btn_magnifier_color_settings_beginner.button, 'set_color'):

                    self.ui.btn_magnifier_color_settings_beginner.button.set_color(self.store.viewport.magnifier_divider_color)

            if hasattr(self.ui, 'btn_divider_visible'):

                should_be_checked = not self.store.viewport.divider_line_visible
                if self.ui.btn_divider_visible.isChecked() != should_be_checked:
                    self.ui.btn_divider_visible.setChecked(should_be_checked, emit_signal=False)

            if hasattr(self.ui, 'btn_magnifier_divider_visible'):

                should_be_checked = not self.store.viewport.magnifier_divider_visible
                if self.ui.btn_magnifier_divider_visible.isChecked() != should_be_checked:
                    self.ui.btn_magnifier_divider_visible.setChecked(should_be_checked, emit_signal=False)

            if hasattr(self.ui, 'btn_magnifier_guides_simple'):
                if self.ui.btn_magnifier_guides_simple.isChecked() != self.store.viewport.show_magnifier_guides:
                    self.ui.btn_magnifier_guides_simple.setChecked(self.store.viewport.show_magnifier_guides, emit_signal=False)
            if hasattr(self.ui, 'btn_magnifier_guides_width'):
                if self.ui.btn_magnifier_guides_width.get_value() != self.store.viewport.magnifier_guides_thickness:
                    self.ui.btn_magnifier_guides_width.set_value(self.store.viewport.magnifier_guides_thickness)

            self.ui.toggle_edit_layout_visibility(self.store.viewport.include_file_names_in_saved)

            self.ui_batcher.schedule_batch_update(['file_names', 'resolution', 'combobox', 'slider_tooltips', 'ratings', 'window_schedule'])

    def _open_image_dialog(self, image_number: int):

        start_dir = self.store.settings.export_default_dir or os.path.expanduser("~")

        lang = self.store.settings.current_language
        filters = f"{tr('common.file_type.image_files', lang)} (*.png *.bmp *.gif *.webp *.tif *.tiff *.jxl *.jpg *.jpeg);;{tr('common.file_type.all_files', lang)} (*)"

        paths, _ = QFileDialog.getOpenFileNames(
            self.main_window_app,
            tr("button.select_images", lang),
            start_dir,
            filters
        )

        if paths:

            delay = 100 if getattr(self, "_first_dialog_load_pending", True) else 0
            QTimer.singleShot(
                delay,
                lambda: self.main_controller.session_ctrl.load_images_from_paths(paths, image_number)
                if self.main_controller is not None and self.main_controller.session_ctrl is not None else None
            )
            self._first_dialog_load_pending = False

    def update_resolution_labels(self):
        self.ui_batcher.schedule_update('resolution')

    def _do_update_resolution_labels(self):
        res1_text = "--x--"
        if dim := self._get_image_dimensions(1):
            res1_text = f"{dim[0]}x{dim[1]}"
        res2_text = "--x--"
        if dim := self._get_image_dimensions(2):
            res2_text = f"{dim[0]}x{dim[1]}"
        self.ui.update_resolution_labels(res1_text, res1_text, res2_text, res2_text)

        psnr_visible = self.store.viewport.auto_calculate_psnr
        self.ui.psnr_label.setVisible(psnr_visible)
        if psnr_visible:
            psnr = self.store.viewport.psnr_value
            if psnr is not None:
                self.ui.psnr_label.setText(f"{tr('ui.psnr', self.store.settings.current_language)}: {psnr:.2f} dB")
            else:
                self.ui.psnr_label.setText(f"{tr('ui.psnr', self.store.settings.current_language)}: --")

        ssim_visible = self.store.viewport.auto_calculate_ssim or self.store.viewport.diff_mode == 'ssim'
        self.ui.ssim_label.setVisible(ssim_visible)
        if ssim_visible:
            ssim = self.store.viewport.ssim_value
            if ssim is not None:
                self.ui.ssim_label.setText(f"{tr('ui.ssim', self.store.settings.current_language)}: {ssim:.4f}")
            else:
                self.ui.ssim_label.setText(f"{tr('ui.ssim', self.store.settings.current_language)}: --")

    def update_file_names_display(self):
        self.ui_batcher.schedule_update('file_names')

    def _do_update_file_names_display(self):

        name1 = self.store.document.get_current_display_name(1) or "-----"
        name2 = self.store.document.get_current_display_name(2) or "-----"

        lang = self.store.settings.current_language

        show_labels = bool(name1 != "-----" or name2 != "-----")

        self.ui.update_file_names_display(
            name1_text=name1,
            name2_text=name2,
            is_horizontal=self.store.viewport.is_horizontal,
            current_language=lang,
            show_labels=show_labels,
        )

        if hasattr(self.ui, 'edit_name1') and not self.ui.edit_name1.hasFocus():
            self.ui.edit_name1.blockSignals(True)
            display_name1 = self.store.document.get_current_display_name(1)
            if display_name1:
                self.ui.edit_name1.setText(display_name1)
            else:
                self.ui.edit_name1.setText("")
            self.ui.edit_name1.setCursorPosition(0)
            self.ui.edit_name1.blockSignals(False)

        if hasattr(self.ui, 'edit_name2') and not self.ui.edit_name2.hasFocus():
            self.ui.edit_name2.blockSignals(True)
            display_name2 = self.store.document.get_current_display_name(2)
            if display_name2:
                self.ui.edit_name2.setText(display_name2)
            else:
                self.ui.edit_name2.setText("")
            self.ui.edit_name2.setCursorPosition(0)
            self.ui.edit_name2.blockSignals(False)

        self.check_name_lengths()

    def check_name_lengths(self):
        self.toolbar_presenter.check_name_lengths()

    def update_combobox_displays(self):
        self.ui_batcher.schedule_update('combobox')

    def _do_update_combobox_displays(self):
        count1 = len(self.store.document.image_list1)
        idx1 = self.store.document.current_index1
        text1 = self._get_current_display_name(1) if 0 <= idx1 < count1 else tr("misc.select_an_image", self.store.settings.current_language)
        self.ui.update_combobox_display(1, count1, idx1, text1, "")

        count2 = len(self.store.document.image_list2)
        idx2 = self.store.document.current_index2
        text2 = self._get_current_display_name(2) if 0 <= idx2 < count2 else tr("misc.select_an_image", self.store.settings.current_language)
        self.ui.update_combobox_display(2, count2, idx2, text2, "")

        if self.ui_manager and self.ui_manager.unified_flyout.isVisible():

            self.ui_manager.repopulate_flyouts()

            QTimer.singleShot(10, self.ui_manager.unified_flyout.refreshGeometry)

    def update_slider_tooltips(self):
        self.ui_batcher.schedule_update('slider_tooltips')

    def _do_update_slider_tooltips(self):
        self.ui.update_slider_tooltips(self.store.viewport.movement_speed_per_sec, self.store.viewport.magnifier_size_relative, self.store.viewport.capture_size_relative, self.store.settings.current_language)

    def update_rating_displays(self):
        self.ui_batcher.schedule_update('ratings')

    def _do_update_rating_displays(self):
        self.ui.update_rating_display(1, self._get_current_score(1), self.store.settings.current_language)
        self.ui.update_rating_display(2, self._get_current_score(2), self.store.settings.current_language)

        if self.ui_manager and self.ui_manager.unified_flyout.isVisible():

            current_idx1 = self.store.document.current_index1
            current_idx2 = self.store.document.current_index2
            if current_idx1 >= 0:
                self.ui_manager.unified_flyout.update_rating_for_item(1, current_idx1)
            if current_idx2 >= 0:
                self.ui_manager.unified_flyout.update_rating_for_item(2, current_idx2)

            QTimer.singleShot(0, self.ui_manager.unified_flyout.refreshGeometry)

    def on_language_changed(self):
        self.ui.update_translations(self.store.settings.current_language)
        self.settings_presenter.on_language_changed()
        if hasattr(self.main_window_app, 'tray_manager') and self.main_window_app.tray_manager:
            self.main_window_app.tray_manager.update_language(self.store.settings.current_language)
        self._do_update_combobox_displays()
        self.ui.reapply_button_styles()

    def _hide_orientation_popup(self):
        if self._orientation_popup:
            self._orientation_popup.hide()

    def get_current_label_dimensions(self) -> tuple[int, int]:
        return self.image_canvas_presenter.get_current_label_dimensions()

    def update_minimum_window_size(self):
        self.image_canvas_presenter.update_minimum_window_size()

    def _finish_resize_delay(self):
        self.image_canvas_presenter._finish_resize_delay()

    def update_magnifier_orientation_button_state(self):
        self.toolbar_presenter.update_magnifier_orientation_button_state()

    def _update_interpolation_combo_box_ui(self):
        self.settings_presenter.update_interpolation_combo_box_ui()

    def _get_current_display_name(self, image_number: int) -> str:

        return self.store.document.get_current_display_name(image_number)

    def _get_current_score(self, image_number: int) -> int | None:
        target_list, index = (
            (self.store.document.image_list1, self.store.document.current_index1)
            if image_number == 1
            else (self.store.document.image_list2, self.store.document.current_index2)
        )
        if 0 <= index < len(target_list):

            return target_list[index].rating
        return None

    def _get_image_dimensions(self, image_number: int) -> tuple[int, int] | None:
        img = None
        if image_number == 1:
            img = self.store.document.full_res_image1 or self.store.document.preview_image1
        else:
            img = self.store.document.full_res_image2 or self.store.document.preview_image2
        if img and hasattr(img, "size"):
            return img.size
        return None

    def _on_error_occurred(self, error_message: str):
        QMessageBox.warning(
            self.main_window_app,
            tr("common.error", self.store.settings.current_language),
            error_message,
        )

    def _on_update_requested(self):
        self.main_window_app.schedule_update()

    def _on_ui_update_requested(self, components: list):
        self.ui_batcher.schedule_batch_update(components)

    def update_image_name(self, image_number: int, name: str):
        if image_number == 1:
            self.ui.edit_name1.blockSignals(True)
            self.ui.edit_name1.setText(name)
            self.ui.edit_name1.setCursorPosition(0)
            self.ui.edit_name1.blockSignals(False)
        elif image_number == 2:
            self.ui.edit_name2.blockSignals(True)
            self.ui.edit_name2.setText(name)
            self.ui.edit_name2.setCursorPosition(0)
            self.ui.edit_name2.blockSignals(False)

    def start_interactive_movement(self):
        if hasattr(self, 'image_canvas_presenter'):
            self.image_canvas_presenter.start_interactive_movement()

    def stop_interactive_movement(self):
        if hasattr(self, 'image_canvas_presenter'):
            self.image_canvas_presenter.stop_interactive_movement()

    def _on_magnifier_guides_toggled(self, checked: bool):
        self.main_controller.toggle_magnifier_guides(checked)

    def _on_magnifier_guides_thickness_changed(self, thickness: int):
        self.main_controller.set_magnifier_guides_thickness(thickness)

    def _on_magnifier_element_hovered(self, element_name: str):
        if self.store:
            self.store.viewport.highlighted_magnifier_element = element_name
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.main_controller.update_requested.emit()

    def _on_magnifier_element_hover_ended(self):
        if self.store:
            self.store.viewport.highlighted_magnifier_element = None
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.main_controller.update_requested.emit()

    def _on_color_option_clicked(self, option: str):
        if option == "divider":
            self.settings_presenter.show_magnifier_divider_color_picker()

        elif option == "capture":
            self.settings_presenter.show_capture_ring_color_picker()
        elif option == "border":
            self.settings_presenter.show_magnifier_border_color_picker()
        elif option == "laser":
            self.settings_presenter.show_laser_color_picker()

