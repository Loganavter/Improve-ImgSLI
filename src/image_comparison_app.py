import os
import importlib
import traceback
import time
from typing import Tuple
import PIL.Image
from PyQt6.QtWidgets import QWidget, QLabel, QSizePolicy, QMessageBox, QDialog, QApplication, QColorDialog
from PyQt6.QtGui import QPixmap, QColor, QImage, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtCore import Qt, QTimer, QPointF, QEvent, QSize, QEventLoop, QThreadPool, pyqtSignal, pyqtSlot
from services.state_manager import AppState, AppConstants
from services.settings_manager import SettingsManager
from services.ui_logic import UILogic
from services.main_controller import MainController
from services.image_processing_worker import ImageRenderingWorker
from processing_services.image_io import save_result_processor
from processing_services.image_resize import resize_images_processor
from services.utils import get_scaled_pixmap_dimensions, get_magnifier_drawing_coords
translations_mod = importlib.import_module('translations')
clickable_label_mod = importlib.import_module('clickable_label')
try:
    from settings_dialog import SettingsDialog
    _SETTINGS_DIALOG_AVAILABLE = True
except ImportError:
    print('Warning: settings_dialog.py not found. Settings button will be disabled.')
    _SETTINGS_DIALOG_AVAILABLE = False
tr = getattr(translations_mod, 'tr', lambda text, lang='en', *args, **kwargs: text)
ClickableLabel = getattr(clickable_label_mod, 'ClickableLabel', QLabel)
from services.event_handler import EventHandler

class ImageComparisonApp(QWidget):
    font_file_name = 'SourceSans3-Regular.ttf'
    _worker_finished_signal = pyqtSignal(PIL.Image.Image, tuple, tuple, str, str, int, bool)
    _worker_error_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_dialog_available = _SETTINGS_DIALOG_AVAILABLE
        self.app_state = AppState()
        self.settings_manager = SettingsManager('MyCompany', 'ImageComparisonApp')
        self.settings_manager.load_all_settings(self.app_state)
        self.main_controller = MainController(self.app_state, self)
        self.ui_logic = UILogic(self, self.app_state)
        self.event_handler = EventHandler(self, self.app_state, self.ui_logic)
        self._determine_font_path()
        self.ui_logic.build_all()
        self.current_displayed_pixmap: QPixmap | None = None
        self.installEventFilter(self.event_handler)
        app_instance_qt = QApplication.instance()
        if app_instance_qt:
            app_instance_qt.installEventFilter(self.event_handler)
        self.thread_pool = QThreadPool()
        print(f'DEBUG: QThreadPool initialized with max thread count: {self.thread_pool.maxThreadCount()}')
        self._worker_finished_signal.connect(self._on_worker_finished)
        self._worker_error_signal.connect(self._on_worker_error)
        self._ui_settle_render_timer = QTimer(self)
        self._ui_settle_render_timer.setSingleShot(True)
        self._ui_settle_render_timer.setInterval(30)
        self._ui_settle_render_timer.timeout.connect(self._perform_settled_ui_render)
        self._needs_settled_ui_render = False
        self.current_rendering_task_id = 0
        self.current_rendering_is_interactive_worker_flag = False
        self._connect_signals()
        self._restore_geometry()
        QTimer.singleShot(0, lambda: self._load_initial_images_from_settings())
        self._apply_initial_settings_to_ui()
        if hasattr(self, 'image_label'):
            self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.image_label.setMinimumSize(1, 1)

    def _request_settled_ui_render(self):
        if self.app_state.showing_single_image_mode != 0:
            print('DEBUG: _request_settled_ui_render skipped, in single image mode.')
            return
        print('DEBUG: ImageComparisonApp._request_settled_ui_render called.')
        self._needs_settled_ui_render = True
        self._ui_settle_render_timer.start()

    def _perform_settled_ui_render(self):
        if not self._needs_settled_ui_render:
            return
        self._needs_settled_ui_render = False
        self.event_handler._exit_interactive_mode_if_settled(force_redraw=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.event_handler.handle_resize_event(event)

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        self.event_handler.handle_change_event(event)

    def closeEvent(self, event):
        print('DEBUG: Application closing. Waiting for rendering tasks to finish...')
        self.thread_pool.waitForDone()
        print('DEBUG: All rendering tasks finished. Proceeding with close.')
        self.event_handler.handle_close_event(event)
        super().closeEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.event_handler.handle_focus_in(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.event_handler.handle_drag_enter(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        self.event_handler.handle_drag_move(event)

    def dragLeaveEvent(self, event: QEvent):
        self.event_handler.handle_drag_leave(event)

    def dropEvent(self, event: QDropEvent):
        self.event_handler.handle_drop(event)

    def _load_initial_images_from_settings(self):
        QTimer.singleShot(0, self.main_controller.initialize_app_display)

    def _determine_font_path(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.font_path_absolute = None
        flatpak_font_path = f'/app/share/fonts/truetype/{self.font_file_name}'
        expected_font_path = os.path.join(self.script_dir, 'font', self.font_file_name)
        paths_to_check = [(flatpak_font_path, 'Flatpak'), (expected_font_path, 'Relative to script')]
        found_path = None
        for path_candidate, description in paths_to_check:
            try:
                if os.path.exists(path_candidate):
                    found_path = path_candidate
                    break
            except Exception as e:
                print(f"Warning: Error checking font path '{path_candidate}': {e}")
        self.font_path_absolute = found_path
        if self.font_path_absolute is None:
            print(f'CRITICAL FONT INFO: No valid custom font path found. Relying on system fonts.')

    def _apply_panel_visibility(self):
        if hasattr(self, 'magnifier_settings_panel'):
            self.magnifier_settings_panel.setVisible(self.app_state.use_magnifier)
            print(f'DEBUG (_apply_panel_visibility): Magnifier panel visibility set to {self.app_state.use_magnifier}')
        if hasattr(self, 'freeze_button'):
            self.freeze_button.setEnabled(self.app_state.use_magnifier)
        if hasattr(self, 'edit_layout_widget'):
            self.edit_layout_widget.setVisible(self.app_state.include_file_names_in_saved)
            print(f'DEBUG (_apply_panel_visibility): Edit layout visibility set to {self.app_state.include_file_names_in_saved}')

    def _apply_initial_settings_to_ui(self):
        if hasattr(self, 'slider_size'):
            self.slider_size.setValue(int(self.app_state.magnifier_size_relative * 100))
        if hasattr(self, 'slider_capture'):
            self.slider_capture.setValue(int(self.app_state.capture_size_relative * 100))
        if hasattr(self, 'slider_speed'):
            self.slider_speed.setValue(int(self.app_state.movement_speed_per_sec * 10))
        if hasattr(self, 'checkbox_horizontal'):
            self.checkbox_horizontal.setChecked(self.app_state.is_horizontal)
        if hasattr(self, 'checkbox_magnifier'):
            self.checkbox_magnifier.setChecked(self.app_state.use_magnifier)
            print(f'DEBUG: Initial UI setup: checkbox_magnifier is checked={self.app_state.use_magnifier}')
        if hasattr(self, 'freeze_button'):
            self.freeze_button.setChecked(self.app_state.freeze_magnifier)
            self.freeze_button.setEnabled(self.app_state.use_magnifier)
        if hasattr(self, 'font_size_slider'):
            self.font_size_slider.setValue(self.app_state.font_size_percent)
        if hasattr(self, 'checkbox_file_names'):
            self.checkbox_file_names.setChecked(self.app_state.include_file_names_in_saved)
        if hasattr(self, 'btn_color_picker'):
            self._update_color_button_tooltip()
        if hasattr(self, 'combo_interpolation'):
            target_method_key = self.app_state.interpolation_method
            found_index_for_initial_setting = -1
            method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
            target_user_data_value = -1
            try:
                target_user_data_value = method_keys.index(target_method_key)
                for i in range(self.combo_interpolation.count()):
                    item_data = self.combo_interpolation.itemData(i)
                    if isinstance(item_data, int) and item_data == target_user_data_value:
                        found_index_for_initial_setting = i
                        break
            except ValueError:
                print(f"WARNING: Initial interpolation method key '{target_method_key}' not found in AppConstants.INTERPOLATION_METHODS_MAP keys.")
            if found_index_for_initial_setting != -1:
                if self.combo_interpolation.currentIndex() != found_index_for_initial_setting:
                    print(f"DEBUG _apply_initial_settings_to_ui: Setting combo_interpolation index to {found_index_for_initial_setting} for method '{target_method_key}'")
                    self.combo_interpolation.blockSignals(True)
                    self.combo_interpolation.setCurrentIndex(found_index_for_initial_setting)
                    self.combo_interpolation.blockSignals(False)
                else:
                    pass
            else:
                print(f"WARNING: Could not find combobox item for initial interpolation method key '{target_method_key}' (expected userData: {target_user_data_value}). Defaulting to current index (usually 0).")
                if self.combo_interpolation.count() > 0:
                    first_item_user_data = self.combo_interpolation.itemData(0)
                    if isinstance(first_item_user_data, int) and 0 <= first_item_user_data < len(method_keys):
                        self.app_state.interpolation_method = method_keys[first_item_user_data]
                        print(f"DEBUG: Setting app_state.interpolation_method to default '{self.app_state.interpolation_method}' based on first combobox item's userData.")
        self.ui_logic.update_translations()

    def _connect_signals(self):
        self.btn_image1.clicked.connect(lambda: self.main_controller.load_images_from_dialog(1))
        self.btn_image2.clicked.connect(lambda: self.main_controller.load_images_from_dialog(2))
        self.btn_swap.clicked.connect(self.main_controller.swap_images)
        self.btn_clear_list1.clicked.connect(lambda: self.main_controller.clear_image_list(1))
        self.btn_clear_list2.clicked.connect(lambda: self.main_controller.clear_image_list(2))
        self.slider_size.sliderPressed.connect(lambda: self.main_controller.on_slider_pressed('magnifier_size'))
        self.slider_capture.sliderPressed.connect(lambda: self.main_controller.on_slider_pressed('capture_size'))
        self.slider_speed.sliderPressed.connect(lambda: self.main_controller.on_slider_pressed('movement_speed'))
        self.font_size_slider.sliderPressed.connect(lambda: self.main_controller.on_slider_pressed('font_size'))
        self.combo_image1.currentIndexChanged.connect(lambda index: self._on_combobox_changed(1, index))
        self.combo_image2.currentIndexChanged.connect(lambda index: self._on_combobox_changed(2, index))
        self.edit_name1.editingFinished.connect(lambda: self.main_controller.on_edit_name_changed(self.edit_name1))
        self.edit_name1.textChanged.connect(self.main_controller.trigger_live_name_or_font_update)
        self.edit_name2.editingFinished.connect(lambda: self.main_controller.on_edit_name_changed(self.edit_name2))
        self.edit_name2.textChanged.connect(self.main_controller.trigger_live_name_or_font_update)
        self.checkbox_horizontal.stateChanged.connect(lambda state: self.main_controller.toggle_orientation(state == Qt.CheckState.Checked.value))
        self.checkbox_magnifier.stateChanged.connect(lambda state: self.main_controller.toggle_magnifier(state == Qt.CheckState.Checked.value))
        self.freeze_button.stateChanged.connect(lambda state: self.main_controller.toggle_freeze_magnifier(state == Qt.CheckState.Checked.value))
        self.slider_size.valueChanged.connect(self.main_controller.update_magnifier_size_relative)
        self.slider_size.sliderReleased.connect(self.main_controller.on_slider_magnifier_size_released)
        self.slider_capture.valueChanged.connect(self.main_controller.update_capture_size_relative)
        self.slider_capture.sliderReleased.connect(self.main_controller.on_slider_capture_size_released)
        self.slider_speed.valueChanged.connect(self.main_controller.update_movement_speed)
        self.slider_speed.sliderReleased.connect(self.main_controller.on_slider_movement_speed_released)
        self.combo_interpolation.currentIndexChanged.connect(self.main_controller.on_interpolation_changed)
        self.checkbox_file_names.toggled.connect(lambda checked: self.main_controller.toggle_include_filenames_in_saved(checked))
        self.font_size_slider.valueChanged.connect(self.main_controller.apply_font_size_change)
        self.font_size_slider.sliderReleased.connect(self.main_controller.on_slider_font_size_released)
        self.btn_color_picker.clicked.connect(self._open_color_dialog)
        self.btn_save.clicked.connect(self._save_result_with_error_handling)
        self.help_button.clicked.connect(self._show_help_dialog)
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        if hasattr(self, 'image_label') and self.image_label is not None:
            self.image_label.mousePressed.connect(self.event_handler.handle_mouse_press)
            self.image_label.mouseMoved.connect(self.event_handler.handle_mouse_move)
            self.image_label.mouseReleased.connect(self.event_handler.handle_mouse_release)

    def _restore_geometry(self):
        self.settings_manager.restore_geometry(self, self.app_state)
        QTimer.singleShot(0, self._ensure_minimum_size_after_restore)
        QTimer.singleShot(10, self.update_comparison_if_needed)

    def _ensure_minimum_size_after_restore(self):
        self.update_minimum_window_size()
        min_size = self.minimumSize()
        current_size = self.size()
        new_width = max(current_size.width(), min_size.width())
        new_height = max(current_size.height(), min_size.height())
        if new_width != current_size.width() or new_height != current_size.height():
            print(f'DEBUG: Resizing window to ensure minimum size. From {current_size.width()}x{current_size.height()} to {new_width}x{new_height}')
            self.resize(new_width, new_height)

    def _update_resolution_labels(self):
        res1_text = '--x--'
        tooltip1 = tr('No image loaded', self.app_state.current_language)
        if self.app_state.original_image1 and hasattr(self.app_state.original_image1, 'size'):
            try:
                w, h = self.app_state.original_image1.size
                res1_text = f'{w}x{h}'
                tooltip1 = res1_text
            except Exception:
                res1_text = tr('Error', self.app_state.current_language)
        res2_text = '--x--'
        tooltip2 = tr('No image loaded', self.app_state.current_language)
        if self.app_state.original_image2 and hasattr(self.app_state.original_image2, 'size'):
            try:
                w, h = self.app_state.original_image2.size
                res2_text = f'{w}x{h}'
                tooltip2 = res2_text
            except Exception:
                res2_text = tr('Error', self.app_state.current_language)
        if hasattr(self, 'resolution_label1'):
            self.resolution_label1.setText(res1_text)
            self.resolution_label1.setToolTip(tooltip1)
        if hasattr(self, 'resolution_label2'):
            self.resolution_label2.setText(res2_text)
            self.resolution_label2.setToolTip(tooltip2)

    def _activate_single_image_mode_internal(self, image_number):
        original_img_to_check = self.app_state.original_image1 if image_number == 1 else self.app_state.original_image2
        pil_to_display = self.app_state.image1 if image_number == 1 else self.app_state.image2
        if original_img_to_check is None:
            if self.app_state.showing_single_image_mode != 0:
                self._deactivate_single_image_mode_internal()
            return
        if pil_to_display is None:
            print(f'DEBUG: Single image mode {image_number}: processed image is None, re-processing.')
            if image_number == 1:
                processed_single, _ = resize_images_processor(self.app_state.original_image1, None, self.app_state.interpolation_method)
                self.app_state.image1 = processed_single
                pil_to_display = self.app_state.image1
            else:
                _, processed_single = resize_images_processor(None, self.app_state.original_image2, self.app_state.interpolation_method)
                self.app_state.image2 = processed_single
                pil_to_display = self.app_state.image2
        if pil_to_display is None:
            if self.app_state.showing_single_image_mode != 0:
                self._deactivate_single_image_mode_internal()
            return
        self.app_state.showing_single_image_mode = image_number
        print(f'DEBUG: Activating single image mode for image {image_number}.')
        if self.event_handler.movement_timer.isActive():
            self.event_handler.movement_timer.stop()
        if self.event_handler.interactive_update_timer.isActive():
            self.event_handler.interactive_update_timer.stop()
        self.event_handler.pending_interactive_update = False
        self.app_state.pressed_keys.clear()
        current_label_size = self.image_label.contentsRect().size()
        self.app_state.fixed_label_width = current_label_size.width()
        self.app_state.fixed_label_height = current_label_size.height()
        if hasattr(self, 'image_label') and self.image_label is not None:
            if self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                current_label_pixmap = self.image_label.pixmap()
                if current_label_pixmap is None or current_label_pixmap.isNull() or current_label_pixmap.cacheKey() != self.current_displayed_pixmap.cacheKey():
                    print('DEBUG: _activate_single_image_mode_internal: Restoring last displayed pixmap before disabling updates.')
                    self.image_label.setPixmap(self.current_displayed_pixmap)
                    QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents | QEventLoop.ProcessEventsFlag.WaitForMoreEvents, 10)
            elif self.image_label.pixmap() and (not self.image_label.pixmap().isNull()):
                print('DEBUG: _activate_single_image_mode_internal: Updating current_displayed_pixmap from label before disabling updates.')
                self.current_displayed_pixmap = self.image_label.pixmap().copy()
            if self.image_label.updatesEnabled():
                self.image_label.setUpdatesEnabled(False)
                print('DEBUG: _activate_single_image_mode_internal: image_label.setUpdatesEnabled(False)')
        self._stabilize_ui_layout()
        self._display_single_image_on_label(pil_to_display)

    def _deactivate_single_image_mode_internal(self):
        if self.app_state.showing_single_image_mode == 0:
            return
        print('DEBUG: Deactivating single image mode.')
        self.app_state.showing_single_image_mode = 0
        self.app_state.fixed_label_width = None
        self.app_state.fixed_label_height = None
        print('DEBUG: Fixed label sizes reset in app_state for _deactivate_single_image_mode_internal.')
        if hasattr(self, 'image_label') and self.image_label is not None:
            if self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                current_label_pixmap = self.image_label.pixmap()
                if current_label_pixmap is None or current_label_pixmap.isNull() or current_label_pixmap.cacheKey() != self.current_displayed_pixmap.cacheKey():
                    print('DEBUG: _deactivate_single_image_mode_internal: Restoring last displayed pixmap before disabling updates.')
                    self.image_label.setPixmap(self.current_displayed_pixmap)
                    QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents | QEventLoop.ProcessEventsFlag.WaitForMoreEvents, 10)
            elif self.image_label.pixmap() and (not self.image_label.pixmap().isNull()):
                print('DEBUG: _deactivate_single_image_mode_internal: Updating current_displayed_pixmap from label before disabling updates.')
                self.current_displayed_pixmap = self.image_label.pixmap().copy()
            if self.image_label.updatesEnabled():
                self.image_label.setUpdatesEnabled(False)
                print('DEBUG: _deactivate_single_image_mode_internal: image_label.setUpdatesEnabled(False)')
        self._stabilize_ui_layout()
        self.update_comparison_if_needed()

    def _display_single_image_on_label(self, pil_image_to_display: PIL.Image.Image | None):
        _DEBUG_TIMER_START = time.perf_counter()
        if not hasattr(self, 'image_label'):
            return
        try:
            if pil_image_to_display is None or pil_image_to_display.width <= 0 or pil_image_to_display.height <= 0:
                print(f'_DEBUG_LOG_: _display_single_image_on_label: pil_image_to_display is None or invalid. Clearing label.')
                if self.image_label.pixmap() is not None:
                    self.image_label.clear()
                self.current_displayed_pixmap = None
                self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
                return
            label_width, label_height = (0, 0)
            if self.app_state.fixed_label_width is not None and self.app_state.fixed_label_height is not None:
                label_width = self.app_state.fixed_label_width
                label_height = self.app_state.fixed_label_height
            else:
                label_width = self.image_label.contentsRect().width()
                label_height = self.image_label.contentsRect().height()
            label_width = max(1, label_width)
            label_height = max(1, label_height)
            pil_convert_start = time.perf_counter()
            pil_img_rgba = pil_image_to_display.convert('RGBA') if pil_image_to_display.mode != 'RGBA' else pil_image_to_display
            data = pil_img_rgba.tobytes('raw', 'RGBA')
            bytes_per_line = pil_img_rgba.width * 4
            qimage = QImage(data, pil_img_rgba.width, pil_img_rgba.height, bytes_per_line, QImage.Format.Format_RGBA8888)
            if qimage.isNull():
                raise ValueError('QImage conversion null.')
            pixmap_from_qimage_start = time.perf_counter()
            original_pixmap_for_scaling = QPixmap.fromImage(qimage)
            if original_pixmap_for_scaling.isNull():
                raise ValueError('QPixmap conversion null.')
            scale_pixmap_start = time.perf_counter()
            scaled_pixmap = original_pixmap_for_scaling.scaled(label_width, label_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if scaled_pixmap.isNull():
                raise ValueError('Scaled QPixmap for single image is null.')
            set_pixmap_start = time.perf_counter()
            self.image_label.setPixmap(scaled_pixmap)
            self.current_displayed_pixmap = scaled_pixmap.copy()
            self.app_state.pixmap_width = scaled_pixmap.width()
            self.app_state.pixmap_height = scaled_pixmap.height()
        except Exception as e:
            print(f'ERROR: Error converting PIL to QPixmap for single image: {e}')
            traceback.print_exc()
            if self.image_label.pixmap() is not None:
                self.image_label.clear()
            self.current_displayed_pixmap = None
            self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
        finally:
            if hasattr(self, 'image_label') and self.image_label is not None and (not self.image_label.updatesEnabled()):
                self.image_label.setUpdatesEnabled(True)
                self.image_label.update()
                print('DEBUG: _display_single_image_on_label: image_label updates re-enabled in finally block.')

    def _update_combobox(self, image_number: int):
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        target_list = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        current_internal_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2
        combobox.blockSignals(True)
        combobox.clear()
        for i, item_data in enumerate(target_list):
            display_name = tr('Invalid Data', self.app_state.current_language)
            full_name_for_tooltip = ''
            if isinstance(item_data, tuple) and len(item_data) >= 3:
                display_name = item_data[2] or tr('Unnamed', self.app_state.current_language)
                full_name_for_tooltip = display_name
            elif isinstance(item_data, tuple) and len(item_data) >= 2 and item_data[1]:
                display_name = os.path.splitext(os.path.basename(item_data[1]))[0]
                full_name_for_tooltip = item_data[1]
            max_cb_len = 60
            cb_name = display_name[:max_cb_len - 3] + '...' if len(display_name) > max_cb_len else display_name
            combobox.addItem(cb_name)
            path = item_data[1] if isinstance(item_data, tuple) and len(item_data) > 1 else None
            combobox.setItemData(i, {'full_name': full_name_for_tooltip, 'list_index': i, 'path': path, 'display_name_truncated': cb_name})
        new_index_to_select = -1
        if 0 <= current_internal_index < len(target_list):
            new_index_to_select = current_internal_index
        elif len(target_list) > 0:
            new_index_to_select = 0
        if new_index_to_select != -1:
            combobox.setCurrentIndex(new_index_to_select)
            self.ui_logic.update_combobox_tooltip_on_selection(combobox, new_index_to_select)
        else:
            combobox.setToolTip('')
        combobox.blockSignals(False)

    def _update_single_combobox_item_text(self, combobox, item_index, new_display_name):
        if 0 <= item_index < combobox.count():
            max_cb_len = 60
            cb_name = new_display_name[:max_cb_len - 3] + '...' if len(new_display_name) > max_cb_len else new_display_name
            combobox.setItemText(item_index, cb_name)
            current_data = combobox.itemData(item_index)
            if isinstance(current_data, dict):
                current_data['full_name'] = new_display_name
                current_data['display_name_truncated'] = cb_name
                combobox.setItemData(item_index, current_data)
            else:
                combobox.setItemData(item_index, {'full_name': new_display_name, 'list_index': item_index, 'path': current_data if isinstance(current_data, str) else None, 'display_name_truncated': cb_name})
            if combobox.currentIndex() == item_index:
                self.ui_logic.update_combobox_tooltip_on_selection(combobox, item_index)

    def _on_combobox_changed(self, image_number: int, index: int):
        self.main_controller.on_combobox_changed(image_number, index)
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        self.ui_logic.update_combobox_tooltip_on_selection(combobox, index)

    def _stabilize_ui_layout(self):
        _DEBUG_TIMER_START = time.perf_counter()
        print('DEBUG: Stabilizing UI layout...')
        max_attempts = 3
        for attempt in range(max_attempts):
            old_content_rect = self.image_label.contentsRect()
            old_content_width = old_content_rect.width()
            old_content_height = old_content_rect.height()
            if self.layout():
                self.layout().invalidate()
                self.layout().activate()
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            new_content_rect = self.image_label.contentsRect()
            new_content_width = new_content_rect.width()
            new_content_height = new_content_rect.height()
            print(f'_DEBUG_LOG_: Stabilization attempt {attempt + 1}: contentsRect {old_content_width}x{old_content_height} -> {new_content_width}x{new_content_height}')
            if abs(old_content_width - new_content_width) < 2 and abs(old_content_height - new_content_height) < 2 and (new_content_width > 0) and (new_content_height > 0):
                print(f'DEBUG: UI stabilized (contentsRect) after {attempt + 1} attempts. Final contentsRect: {new_content_width}x{new_content_height}')
                break
            if attempt == max_attempts - 1:
                print(f'WARNING: UI not fully stabilized (contentsRect) after {max_attempts} attempts. Final contentsRect: {new_content_width}x{new_content_height}')
        print(f'_DEBUG_TIMER_: _stabilize_ui_layout took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')

    def get_current_label_dimensions(self) -> Tuple[int, int]:
        if self.app_state.fixed_label_width is not None and self.app_state.fixed_label_height is not None:
            width = self.app_state.fixed_label_width
            height = self.app_state.fixed_label_height
            return (max(1, width), max(1, height))
        else:
            content_rect = self.image_label.contentsRect()
            width = content_rect.width()
            height = content_rect.height()
            return (max(1, width), max(1, height))

    def update_comparison_if_needed(self) -> bool:
        _DEBUG_TIMER_START_FULL = time.perf_counter()
        print('\n--- update_comparison_if_needed START (MAIN THREAD) ---')
        label_width, label_height = self.get_current_label_dimensions()
        print(f'_DEBUG_LOG_: app_state.pixmap_width (previous displayed): {self.app_state.pixmap_width}, app_state.pixmap_height (previous displayed): {self.app_state.pixmap_height}')
        print(f'_DEBUG_LOG_: Current label dimensions: {label_width}x{label_height}')
        if self.app_state.resize_in_progress:
            print('DEBUG: update_comparison_if_needed skipped due to resize_in_progress.')
            print(f'_DEBUG_TIMER_: update_comparison_if_needed total took {(time.perf_counter() - _DEBUG_TIMER_START_FULL) * 1000:.2f} ms (skipped)')
            return False
        if self.app_state.showing_single_image_mode != 0:
            print(f'DEBUG: update_comparison_if_needed: Activating single image mode {self.app_state.showing_single_image_mode} as per app_state.')
            self._activate_single_image_mode_internal(self.app_state.showing_single_image_mode)
            print(f'_DEBUG_TIMER_: update_comparison_if_needed total took {(time.perf_counter() - _DEBUG_TIMER_START_FULL) * 1000:.2f} ms (single image mode activated)')
            return False
        if not self.app_state.original_image1 and (not self.app_state.original_image2):
            print('DEBUG: Both original image slots empty. Clearing display.')
            if hasattr(self, 'image_label') and self.image_label is not None:
                if not self.image_label.updatesEnabled():
                    self.image_label.setUpdatesEnabled(True)
                self.image_label.clear()
                self.image_label.update()
            self.current_displayed_pixmap = None
            self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
            self.app_state.result_image = None
            self._update_resolution_labels()
            print(f'_DEBUG_TIMER_: update_comparison_if_needed total took {(time.perf_counter() - _DEBUG_TIMER_START_FULL) * 1000:.2f} ms (no images loaded)')
            return False
        if not self.app_state.original_image1 or not self.app_state.original_image2:
            print('CRITICAL_WARNING: update_comparison_if_needed reached comparison logic BUT not all images are loaded and not in single_mode. This indicates a logic flaw. Preserving display.')
            if hasattr(self, 'image_label') and self.image_label is not None:
                if not self.image_label.updatesEnabled():
                    self.image_label.setUpdatesEnabled(True)
                if self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                    self.image_label.setPixmap(self.current_displayed_pixmap)
                self.image_label.update()
            print(f'_DEBUG_TIMER_: update_comparison_if_needed total took {(time.perf_counter() - _DEBUG_TIMER_START_FULL) * 1000:.2f} ms (images missing, comparison skipped)')
            return False
        if not self.app_state.image1 or not self.app_state.image2 or self.app_state.image1.size != self.app_state.image2.size or (self.app_state.image1.mode != 'RGBA') or (self.app_state.image2.mode != 'RGBA'):
            print('DEBUG: Processed images missing, sizes mismatch, or modes not RGBA. Re-processing full res images for worker input.')
            resize_processor_start = time.perf_counter()
            full_res_img1, full_res_img2 = resize_images_processor(self.app_state.original_image1, self.app_state.original_image2, self.app_state.interpolation_method)
            self.app_state.image1 = full_res_img1.copy() if full_res_img1 else None
            self.app_state.image2 = full_res_img2.copy() if full_res_img2 else None
        if not self.app_state.image1 or not self.app_state.image2:
            print('ERROR: After re-processing, images still not available for worker. Clearing display.')
            if hasattr(self, 'image_label') and self.image_label is not None:
                if not self.image_label.updatesEnabled():
                    self.image_label.setUpdatesEnabled(True)
                self.image_label.clear()
                self.image_label.update()
            self.current_displayed_pixmap = None
            self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
            self.app_state.result_image = None
            print(f'_DEBUG_TIMER_: update_comparison_if_needed total took {(time.perf_counter() - _DEBUG_TIMER_START_FULL) * 1000:.2f} ms (re-processing failed)')
            return False
        app_state_copy_for_worker = AppState()
        app_state_copy_for_worker.split_position = self.app_state.split_position
        app_state_copy_for_worker.split_position_visual = self.app_state.split_position_visual
        app_state_copy_for_worker.is_horizontal = self.app_state.is_horizontal
        app_state_copy_for_worker.use_magnifier = self.app_state.use_magnifier
        app_state_copy_for_worker.capture_position_relative = QPointF(self.app_state.capture_position_relative)
        app_state_copy_for_worker.show_capture_area_on_main_image = self.app_state.show_capture_area_on_main_image
        app_state_copy_for_worker.magnifier_offset_relative = QPointF(self.app_state.magnifier_offset_relative)
        app_state_copy_for_worker.magnifier_offset_relative_visual = QPointF(self.app_state.magnifier_offset_relative_visual)
        app_state_copy_for_worker.magnifier_spacing_relative = self.app_state.magnifier_spacing_relative
        app_state_copy_for_worker.magnifier_spacing_relative_visual = self.app_state.magnifier_spacing_relative_visual
        app_state_copy_for_worker.magnifier_size_relative = self.app_state.magnifier_size_relative
        app_state_copy_for_worker.capture_size_relative = self.app_state.capture_size_relative
        app_state_copy_for_worker.freeze_magnifier = self.app_state.freeze_magnifier
        if self.app_state.frozen_magnifier_position_relative:
            app_state_copy_for_worker.frozen_magnifier_position_relative = QPointF(self.app_state.frozen_magnifier_position_relative)
        app_state_copy_for_worker.include_file_names_in_saved = self.app_state.include_file_names_in_saved
        app_state_copy_for_worker.font_size_percent = self.app_state.font_size_percent
        app_state_copy_for_worker.max_name_length = self.app_state.max_name_length
        app_state_copy_for_worker.file_name_color = QColor(self.app_state.file_name_color)
        app_state_copy_for_worker.interpolation_method = self.app_state.interpolation_method
        app_state_copy_for_worker.is_interactive_mode = self.app_state.is_interactive_mode
        app_state_copy_for_worker.original_image1 = self.app_state.original_image1
        app_state_copy_for_worker.original_image2 = self.app_state.original_image2
        app_state_copy_for_worker._magnifier_cache = self.app_state._magnifier_cache
        app_state_copy_for_worker._cached_split_base_image = self.app_state._cached_split_base_image
        app_state_copy_for_worker._last_split_cached_params = self.app_state._last_split_cached_params
        image1_pil_copy = self.app_state.image1.copy()
        image2_pil_copy = self.app_state.image2.copy()
        original_image1_pil_copy = self.app_state.original_image1.copy() if self.app_state.original_image1 else None
        original_image2_pil_copy = self.app_state.original_image2.copy() if self.app_state.original_image2 else None
        magnifier_coords = None
        name1_for_render = ''
        if hasattr(self, 'edit_name1'):
            name1_for_render = self.edit_name1.text()
        if not self.app_state.original_image1:
            name1_for_render = tr('Image 1', self.app_state.current_language)
        name2_for_render = ''
        if hasattr(self, 'edit_name2'):
            name2_for_render = self.edit_name2.text()
        if not self.app_state.original_image2:
            name2_for_render = tr('Image 2', self.app_state.current_language)
        current_name1_text = name1_for_render
        current_name2_text = name2_for_render
        if app_state_copy_for_worker.use_magnifier:
            magnifier_coords = get_magnifier_drawing_coords(app_state_copy_for_worker, drawing_width=image1_pil_copy.width, drawing_height=image1_pil_copy.height, display_width=label_width, display_height=label_height)

        def _get_base_name_without_ext(path):
            return os.path.splitext(os.path.basename(path))[0] if path else ''
        if self.app_state.original_image1:
            current_name1_text = self.edit_name1.text() if hasattr(self, 'edit_name1') else self.app_state.get_current_display_name(1)
        else:
            current_name1_text = tr('Image 1', self.app_state.current_language)
        if self.app_state.original_image2:
            current_name2_text = self.edit_name2.text() if hasattr(self, 'edit_name2') else self.app_state.get_current_display_name(2)
        else:
            current_name2_text = tr('Image 2', self.app_state.current_language)
        self.current_rendering_task_id += 1
        current_task_id = self.current_rendering_task_id
        self.current_rendering_is_interactive_worker_flag = app_state_copy_for_worker.is_interactive_mode
        render_params = {'app_state_copy': app_state_copy_for_worker, 'image1_pil_copy': image1_pil_copy, 'image2_pil_copy': image2_pil_copy, 'original_image1_pil_copy': original_image1_pil_copy, 'original_image2_pil_copy': original_image2_pil_copy, 'current_label_dims': (label_width, label_height), 'magnifier_coords': magnifier_coords, 'font_path_absolute': self.font_path_absolute, 'file_name1_text': current_name1_text, 'file_name2_text': current_name2_text, 'finished_signal': self._worker_finished_signal, 'error_signal': self._worker_error_signal, 'task_id': current_task_id, 'file_name2_text': current_name2_text, 'file_name1_text': current_name1_text}
        worker = ImageRenderingWorker(render_params)
        priority = 1 if not app_state_copy_for_worker.is_interactive_mode else 0
        print(f'DEBUG: Queueing rendering task (ID: {current_task_id}) with priority {priority}. Interactive state for worker: {app_state_copy_for_worker.is_interactive_mode}. Active threads: {self.thread_pool.activeThreadCount()}. Queued: {self.thread_pool.waitForDone(0)}')
        self.thread_pool.start(worker, priority=priority)
        print(f'--- update_comparison_if_needed END (MAIN THREAD - Render queued) Total time: {(time.perf_counter() - _DEBUG_TIMER_START_FULL) * 1000:.2f} ms ---\n')
        return True

    @pyqtSlot(PIL.Image.Image, tuple, tuple, str, str, int, bool)
    def _on_worker_finished(self, result_pil_image: PIL.Image.Image, current_label_dims: Tuple[int, int], processed_original_sizes: Tuple[Tuple[int, int], Tuple[int, int]], name1_text: str, name2_text: str, finished_task_id: int, task_was_interactive: bool):
        _DEBUG_TIMER_START_FINISH_SLOT = time.perf_counter()
        print(f'\n--- _on_worker_finished START (MAIN THREAD - Received render result for Task ID: {finished_task_id}) ---')
        print(f'DEBUG: _on_worker_finished: Task ID {finished_task_id}, Task was interactive: {task_was_interactive}, App currently interactive: {self.app_state.is_interactive_mode}, Master Task ID: {self.current_rendering_task_id}')
        if hasattr(self, 'image_label') and self.image_label is not None:
            if not self.image_label.updatesEnabled():
                self.image_label.setUpdatesEnabled(True)
                print('DEBUG: _on_worker_finished: image_label updates re-enabled (early in slot for safety).')
        if self.app_state.is_interactive_mode:
            if not task_was_interactive:
                print(f'DEBUG: Discarding late FINAL task {finished_task_id} because app is in INTERACTIVE mode.')
                if (self.image_label.pixmap() is None or self.image_label.pixmap().isNull()) and self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                    print('DEBUG: Discarding task, restoring last displayed pixmap as current is null.')
                    self.image_label.setPixmap(self.current_displayed_pixmap)
                self.image_label.update()
                return
            print(f'DEBUG: Processing INTERACTIVE task {finished_task_id} during interactive app state.')
        else:
            if task_was_interactive:
                print(f'DEBUG: Discarding late INTERACTIVE task {finished_task_id} because app expects a FINAL render.')
                if (self.image_label.pixmap() is None or self.image_label.pixmap().isNull()) and self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                    print('DEBUG: Discarding task, restoring last displayed pixmap as current is null.')
                    self.image_label.setPixmap(self.current_displayed_pixmap)
                self.image_label.update()
                return
            if finished_task_id < self.current_rendering_task_id:
                print(f'DEBUG: Discarding stale FINAL task {finished_task_id} (current master task ID is {self.current_rendering_task_id}).')
                if (self.image_label.pixmap() is None or self.image_label.pixmap().isNull()) and self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                    print('DEBUG: Discarding task, restoring last displayed pixmap as current is null.')
                    self.image_label.setPixmap(self.current_displayed_pixmap)
                self.image_label.update()
                return
            print(f'DEBUG: Processing FINAL task {finished_task_id}.')
        self.app_state.result_image = result_pil_image.copy() if result_pil_image else None
        if self.app_state.result_image:
            try:
                pil_to_qimage_start = time.perf_counter()
                pil_img_rgba = self.app_state.result_image.convert('RGBA') if self.app_state.result_image.mode != 'RGBA' else self.app_state.result_image
                data = pil_img_rgba.tobytes('raw', 'RGBA')
                bytes_per_line = pil_img_rgba.width * 4
                qimage = QImage(data, pil_img_rgba.width, pil_img_rgba.height, bytes_per_line, QImage.Format.Format_RGBA8888)
                if qimage.isNull():
                    raise ValueError('QImage null after conversion from PIL.')
                qimage_to_pixmap_start = time.perf_counter()
                original_pixmap_for_scaling = QPixmap.fromImage(qimage)
                if original_pixmap_for_scaling.isNull():
                    raise ValueError('Original QPixmap for scaling is null.')
                label_width_at_task_creation, label_height_at_task_creation = current_label_dims
                print(f'_DEBUG_LOG_: Label dimensions at task creation for scaling: {label_width_at_task_creation}x{label_height_at_task_creation}')
                scaled_target_width, scaled_target_height = get_scaled_pixmap_dimensions(self.app_state.result_image, label_width_at_task_creation, label_height_at_task_creation)
                scaled_target_width = max(1, scaled_target_width)
                scaled_target_height = max(1, scaled_target_height)
                qt_scale_mode = Qt.TransformationMode.SmoothTransformation
                scale_pixmap_start = time.perf_counter()
                scaled_pixmap = original_pixmap_for_scaling.scaled(scaled_target_width, scaled_target_height, Qt.AspectRatioMode.KeepAspectRatio, qt_scale_mode)
                if scaled_pixmap.isNull():
                    raise ValueError('Scaled QPixmap is null.')
                self.image_label.setPixmap(scaled_pixmap)
                self.current_displayed_pixmap = scaled_pixmap.copy()
                self.app_state.pixmap_width = scaled_pixmap.width()
                self.app_state.pixmap_height = scaled_pixmap.height()
                print(f'_DEBUG_LOG_: Pixmap set. Displayed size: {self.app_state.pixmap_width}x{self.app_state.pixmap_height}')
            except Exception as e_conv:
                print(f'ERROR: Error converting final PIL to QPixmap or displaying in _on_worker_finished: {e_conv}')
                traceback.print_exc()
                print('DEBUG: Conversion to QPixmap failed. Attempting to restore previous pixmap on label.')
                if self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                    self.image_label.setPixmap(self.current_displayed_pixmap)
                else:
                    if self.image_label.pixmap() is not None:
                        self.image_label.clear()
                    self.current_displayed_pixmap = None
                self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
        else:
            print('DEBUG: Worker returned None image. Attempting to restore previous pixmap on label.')
            if self.current_displayed_pixmap and (not self.current_displayed_pixmap.isNull()):
                self.image_label.setPixmap(self.current_displayed_pixmap)
            else:
                if self.image_label.pixmap() is not None:
                    self.image_label.clear()
                self.current_displayed_pixmap = None
            self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
        self.image_label.update()
        if not self.app_state.is_interactive_mode:
            print('DEBUG: Performing final stabilization after non-interactive render.')
            self._stabilize_ui_layout()
            final_check_width, final_check_height = self.get_current_label_dimensions()
            if abs(final_check_width - label_width_at_task_creation) > 2 or abs(final_check_height - label_height_at_task_creation) > 2:
                print(f'WARNING: Label dimensions shifted after final pixmap set and stabilization. Initial: {label_width_at_task_creation}x{label_height_at_task_creation}, Final: {final_check_width}x{final_check_height}')
        else:
            print('DEBUG: Skipping final stabilization as app is in interactive mode.')
        print(f'--- _on_worker_finished END (Total time in slot: {(time.perf_counter() - _DEBUG_TIMER_START_FINISH_SLOT) * 1000:.2f} ms) ---\n')

    @pyqtSlot(str)
    def _on_worker_error(self, error_message: str):
        print(f'ERROR: Worker reported an error: {error_message}')
        QMessageBox.critical(self, tr('Error', self.app_state.current_language), error_message)
        if hasattr(self, 'image_label') and self.image_label is not None and (not self.image_label.updatesEnabled()):
            self.image_label.setUpdatesEnabled(True)
            self.image_label.update()

    def _save_result_with_error_handling(self):
        try:
            if self.app_state.showing_single_image_mode != 0:
                QMessageBox.warning(self, tr('Warning', self.app_state.current_language), tr('Cannot save while previewing single image.', self.app_state.current_language))
                return
            if not self.app_state.original_image1 or not self.app_state.original_image2:
                QMessageBox.warning(self, tr('Warning', self.app_state.current_language), tr('Please load and select images in both slots first.', self.app_state.current_language))
                return
            full_res_img1, full_res_img2 = (self.app_state.image1, self.app_state.image2)
            if not full_res_img1 or not full_res_img2 or full_res_img1.size != full_res_img2.size:
                full_res_img1, full_res_img2 = resize_images_processor(self.app_state.original_image1, self.app_state.original_image2, self.app_state.interpolation_method)
            if not full_res_img1 or not full_res_img2 or full_res_img1.size != full_res_img2.size:
                QMessageBox.warning(self, tr('Warning', self.app_state.current_language), tr('Resized images not available or sizes mismatch. Cannot save result. Please reload or select images.', self.app_state.current_language))
                return
            drawing_width, drawing_height = full_res_img1.size
            label_width, label_height = self.get_current_label_dimensions()
            magnifier_coords = None
            if self.app_state.use_magnifier:
                magnifier_coords = get_magnifier_drawing_coords(self.app_state, drawing_width=drawing_width, drawing_height=drawing_height, display_width=label_width, display_height=label_height)

            def _get_base_name_without_ext(path):
                return os.path.splitext(os.path.basename(path))[0] if path else ''
            name1_from_state = self.app_state.get_current_display_name(1)
            name2_from_state = self.app_state.get_current_display_name(2)
            current_name1_text = self.edit_name1.text() if hasattr(self, 'edit_name1') and self.edit_name1.text() else name1_from_state or (_get_base_name_without_ext(self.app_state.image1_path) if self.app_state.image1_path else tr('Image 1', self.app_state.current_language))
            current_name2_text = self.edit_name2.text() if hasattr(self, 'edit_name2') and self.edit_name2.text() else name2_from_state or (_get_base_name_without_ext(self.app_state.image2_path) if self.app_state.image2_path else tr('Image 2', self.app_state.current_language))
            save_result_processor(app_instance_for_ui_dialogs=self, image1_processed=full_res_img1, image2_processed=full_res_img2, split_position_target=self.app_state.split_position, is_horizontal=self.app_state.is_horizontal, use_magnifier=self.app_state.use_magnifier, show_capture_area_on_main_image=self.app_state.show_capture_area_on_main_image, capture_position_relative=self.app_state.capture_position_relative, original_image1=self.app_state.original_image1, original_image2=self.app_state.original_image2, magnifier_drawing_coords=magnifier_coords, include_file_names=self.app_state.include_file_names_in_saved, font_path_absolute=self.font_path_absolute, font_size_percent=self.font_size_slider.value(), max_name_length=self.app_state.max_name_length, file_name1_text=current_name1_text, file_name2_text=current_name2_text, file_name_color_rgb=self.app_state.file_name_color.getRgb(), jpeg_quality=self.app_state.jpeg_quality, interpolation_method=self.app_state.interpolation_method)
        except Exception as e:
            print(f'Error in _save_result: {e}')
            traceback.print_exc()
            QMessageBox.critical(self, tr('Error', self.app_state.current_language), f"{tr('An unexpected error occurred during the save process:', self.app_state.current_language)}\n{str(e)}")

    def _update_color_button_tooltip(self):
        if hasattr(self, 'btn_color_picker'):
            self.btn_color_picker.setToolTip(f"{tr('Change Filename Color', self.app_state.current_language)}\n{tr('Current:', self.app_state.current_language)} {self.app_state.file_name_color.name(QColor.NameFormat.HexArgb)}")

    def _open_color_dialog(self):
        options = QColorDialog.ColorDialogOption.ShowAlphaChannel
        initial_color = self.app_state.file_name_color
        color = QColorDialog.getColor(initial_color, self, tr('Select Filename Color', self.app_state.current_language), options=options)
        if color.isValid():
            self.main_controller.apply_filename_color_change(color)

    def _show_help_dialog(self):
        lang = self.app_state.current_language
        html = f"<html><body><h2 style='margin:0 0 8px 0'>{tr('Improve ImgSLI Help', lang)}</h2><h3 style='margin:8px 0 4px 0'>{tr('Loading Images:', lang)}</h3><ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'><li style='margin-bottom:2px'>{tr('Use Add buttons or Drag-n-Drop images onto the left/right side.', lang)}</li><li style='margin-bottom:2px'>{tr('Use dropdown menus to select from loaded images.', lang)}</li><li style='margin-bottom:2px'>{tr('Use the ⇄ button to swap the entire left and right image lists.', lang)}</li><li style='margin-bottom:2px'>{tr('Use the Trash buttons (🗑️) to clear respective image lists.', lang)}</li></ul><h3 style='margin:8px 0 4px 0'>{tr('Comparison View:', lang)}</h3><ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'><li style='margin-bottom:2px'>{tr('Click and drag the split line (when Magnifier is off).', lang)}</li><li style='margin-bottom:2px'>{tr('Check [Horizontal Split] to change the split orientation.', lang)}</li></ul><h3 style='margin:8px 0 4px 0'>{tr('Magnifier Tool (when checked):', lang)}</h3><ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'><li style='margin-bottom:2px'>{tr('Magnifier: Click/drag sets capture point (red circle).', lang)}</li><li style='margin-bottom:2px'>{tr('Magnifier: Use WASD keys to move magnifier offset relative to capture point.', lang)}</li><li style='margin-bottom:2px'>{tr('Magnifier: Use QE keys to change spacing between magnifier halves (when separated).', lang)}</li><li style='margin-bottom:2px'>{tr('Sliders adjust Magnifier Size (zoom level), Capture Size (area sampled), and Move Speed.', lang)}</li><li style='margin-bottom:2px'>{tr('Select interpolation method for magnifier zoom', lang)}</li></ul><h3 style='margin:8px 0 4px 0'>{tr('Output:', lang)}</h3><ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'><li style='margin-bottom:2px'>{tr('Include file names saves names onto the output image.', lang)}</li><li style='margin-bottom:2px'>{tr('Edit names, adjust font size, and pick text color in the bottom panel (visible when names are included).', lang)}</li><li style='margin-bottom:2px'>{tr('Click [Save Result] to save the current view (including split, magnifier, names if enabled) as a PNG or JPG file.', lang)}</li></ul><h3 style='margin:8px 0 4px 0'>{tr('Settings', lang)}:</h3><ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'><li style='margin-bottom:2px'>{tr('Click the settings button (…) to change the application language, the maximum displayed name length, and JPEG quality.', lang)}</li></ul><h3 style='margin:8px 0 4px 0'>{tr('Quick Preview:', lang)}</h3><ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'><li style='margin-bottom:2px'>{tr('Hold Space and use mouse buttons to quickly preview', lang)}</li></ul></body></html>"
        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setWindowTitle(tr('Help', lang))
        dlg.setTextFormat(Qt.TextFormat.RichText)
        dlg.setText(html)
        dlg.exec()

    def _reapply_button_styles(self):
        icon_size_clear = QSize(22, 22)
        icon_size_others = QSize(24, 24)
        if hasattr(self, 'btn_swap'):
            self.btn_swap.setIconSize(icon_size_others)
            self.btn_swap.setStyleSheet('\n                TransparentPushButton {\n                    padding: 6px;\n                    qproperty-iconSize: 24px;\n                }\n            ')
        if hasattr(self, 'btn_clear_list1'):
            self.btn_clear_list1.setIconSize(icon_size_clear)
            self.btn_clear_list1.setStyleSheet('\n                TransparentPushButton {\n                    padding: 7px;\n                    qproperty-iconSize: 22px;\n                }\n            ')
        if hasattr(self, 'btn_clear_list2'):
            self.btn_clear_list2.setIconSize(icon_size_clear)
            self.btn_clear_list2.setStyleSheet('\n                TransparentPushButton {\n                    padding: 7px;\n                    qproperty-iconSize: 22px;\n                }\n            ')
        if hasattr(self, 'btn_settings'):
            self.btn_settings.setIconSize(icon_size_others)
            self.btn_settings.setStyleSheet('\n                TransparentPushButton {\n                    padding: 6px;\n                    qproperty-iconSize: 24px;\n                }\n            ')
        if hasattr(self, 'help_button'):
            self.help_button.setIconSize(icon_size_others)
            self.help_button.setStyleSheet('\n                TransparentPushButton {\n                    padding: 6px;\n                    qproperty-iconSize: 24px;\n                }\n            ')
        if hasattr(self, 'btn_color_picker'):
            self.btn_color_picker.setIconSize(icon_size_others)
            self.btn_color_picker.setStyleSheet('\n                PushButton {\n                    padding: 6px;\n                    qproperty-iconSize: 24px;\n                }\n            ')

    def _open_settings_dialog(self):
        if not self.settings_dialog_available:
            QMessageBox.critical(self, tr('Error', self.app_state.current_language), tr('Settings dialog module not found.', self.app_state.current_language))
            return
        try:
            settings_dialog = SettingsDialog(current_language=self.app_state.current_language, current_max_length=self.app_state.max_name_length, min_limit=AppConstants.MIN_NAME_LENGTH_LIMIT, max_limit=AppConstants.MAX_NAME_LENGTH_LIMIT, current_jpeg_quality=self.app_state.jpeg_quality, parent=self, tr_func=tr)
            dialog_result = settings_dialog.exec()
            if dialog_result == QDialog.DialogCode.Accepted:
                try:
                    new_lang, new_max_length, new_jpeg_quality = settings_dialog.get_settings()
                    length_changed = False
                    if new_max_length != self.app_state.max_name_length:
                        self.app_state.max_name_length = max(AppConstants.MIN_NAME_LENGTH_LIMIT, min(AppConstants.MAX_NAME_LENGTH_LIMIT, new_max_length))
                        self.settings_manager._save_setting('max_name_length', self.app_state.max_name_length)
                        length_changed = True
                        self.ui_logic.update_file_names()
                    if new_jpeg_quality != self.app_state.jpeg_quality:
                        self.app_state.jpeg_quality = max(1, min(100, new_jpeg_quality))
                        self.settings_manager._save_setting('jpeg_quality', self.app_state.jpeg_quality)
                    language_actually_changed = new_lang != self.app_state.current_language
                    if language_actually_changed:
                        self.main_controller.change_language(new_lang)
                    if length_changed and (not language_actually_changed):
                        self.ui_logic.check_name_lengths()
                        if self.app_state.include_file_names_in_saved and self.app_state.showing_single_image_mode == 0:
                            self.update_comparison_if_needed()
                except Exception as e:
                    QMessageBox.warning(self, tr('Error', self.app_state.current_language), tr('Failed to apply settings: {}', self.app_state.current_language).format(str(e)))
            QTimer.singleShot(0, self._reapply_button_styles)
        except Exception as e:
            QMessageBox.warning(self, tr('Error', self.app_state.current_language), tr('Failed to open settings dialog: {}', self.app_state.current_language).format(str(e)))
            QTimer.singleShot(0, self._reapply_button_styles)

    def update_minimum_window_size(self):
        layout = self.layout()
        if not layout or not hasattr(self, 'image_label'):
            return
        original_policy = self.image_label.sizePolicy()
        temp_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        temp_policy.setHeightForWidth(original_policy.hasHeightForWidth())
        temp_policy.setWidthForHeight(original_policy.hasWidthForHeight())
        temp_policy.setVerticalPolicy(QSizePolicy.Policy.Preferred if original_policy.verticalPolicy() != QSizePolicy.Policy.Ignored else QSizePolicy.Policy.Ignored)
        temp_policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred if original_policy.horizontalPolicy() != QSizePolicy.Policy.Ignored else QSizePolicy.Policy.Ignored)
        try:
            self.image_label.setSizePolicy(temp_policy)
            self.image_label.updateGeometry()
            if layout:
                layout.invalidate()
                layout.activate()
            layout_hint_size = layout.sizeHint() if layout else QSize(250, 300)
            base_min_w, base_min_h = (250, 300)
            new_min_w, new_min_h = (max(base_min_w, layout_hint_size.width()), max(base_min_h, layout_hint_size.height()))
            padding = 10
            new_min_w += padding
            new_min_h += padding
            current_min = self.minimumSize()
            if current_min.width() != new_min_w or current_min.height() != new_min_h:
                self.setMinimumSize(new_min_w, new_min_h)
        except Exception:
            pass
        finally:
            if hasattr(self, 'image_label') and self.image_label.sizePolicy() != original_policy:
                self.image_label.setSizePolicy(original_policy)
                self.image_label.updateGeometry()
                if layout:
                    layout.invalidate()
                    layout.activate()