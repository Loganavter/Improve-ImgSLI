from services.event_handler import EventHandler
import os
import importlib
import traceback
import time
from typing import Tuple
import PIL.Image
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QSizePolicy,
    QMessageBox,
    QDialog,
    QApplication,
    QColorDialog,
)
from PyQt6.QtGui import (
    QPixmap,
    QColor,
    QImage,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QIcon,
)
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPoint,
    QEvent,
    QSize,
    QEventLoop,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
    QRect,
)

from services.state_manager import AppState, AppConstants
from services.settings_manager import SettingsManager
from services.ui_logic import UILogic
from services.main_controller import MainController
from services.image_processing_worker import ImageRenderingWorker
import services.logging_service as logging_service
from processing_services.image_io import save_result_processor
from processing_services.image_resize import (
    resize_images_processor,
    get_pil_resampling_method,
)
from services.utils import get_scaled_pixmap_dimensions, get_magnifier_drawing_coords
import logging

try:
    from settings_dialog import SettingsDialog

    _SETTINGS_DIALOG_AVAILABLE = True
except ImportError:
    logging.getLogger("ImproveImgSLI").warning("settings_dialog.py not found. Settings button will be disabled.")
    _SETTINGS_DIALOG_AVAILABLE = False

translations_mod = importlib.import_module("translations")
tr = getattr(
    translations_mod,
    "tr",
    lambda text,
    lang="en",
    *args,
    **kwargs: text)

clickable_label_mod = importlib.import_module("clickable_label")
ClickableLabel = getattr(clickable_label_mod, "ClickableLabel", QLabel)

logger = logging.getLogger("ImproveImgSLI")

class ImageComparisonApp(QWidget):
    font_file_name = "SourceSans3-Regular.ttf"

    _worker_finished_signal = pyqtSignal(dict, dict, int)
    _worker_error_signal = pyqtSignal(str)

    def __init__(self, parent=None, debug_mode: bool = False):
        super().__init__(parent)
        self.settings_dialog_available = _SETTINGS_DIALOG_AVAILABLE
        self.app_state = AppState()

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(script_dir, "icons", "icon.png")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
            else:
                logger.warning(f"Window icon not found at: {icon_path}")
        except Exception as e:
            logger.error(f"Failed to set window icon: {e}")
        
        if debug_mode:
            self.app_state.debug_mode_enabled = True

        self.settings_manager = SettingsManager(
            "MyCompany", "ImageComparisonApp")
        self.settings_manager.load_all_settings(self.app_state)
        
        logging_service.setup_logging(self.app_state.debug_mode_enabled)

        self.main_controller = MainController(self.app_state, self)
        self.ui_logic = UILogic(self, self.app_state)
        self.event_handler = EventHandler(self, self.app_state, self.ui_logic)
        self._determine_font_path()
        self.combobox_update_timer = QTimer(self)
        self.combobox_update_timer.setSingleShot(True)
        self.combobox_update_timer.setInterval(150)
        self.combobox_update_timer.timeout.connect(self._perform_combobox_update)
        self.last_combo_to_update = 0
        self.ui_logic.build_all()
        
        self._update_scheduler_timer = QTimer(self)
        self._update_scheduler_timer.setSingleShot(True)
        self._update_scheduler_timer.setInterval(10)
        self._update_scheduler_timer.timeout.connect(self.update_comparison_if_needed)

        self.app_state.stateChanged.connect(self.schedule_update)

        if hasattr(self, "image_label"):
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.image_label.setMinimumSize(1, 1)
            self.image_label.installEventFilter(self.event_handler)

        self.current_displayed_pixmap: QPixmap | None = None

        self.installEventFilter(self.event_handler)
        app_instance_qt = QApplication.instance()
        if app_instance_qt:
            app_instance_qt.installEventFilter(self.event_handler)

        self.thread_pool = QThreadPool()

        self._worker_finished_signal.connect(self._on_worker_finished)
        self._worker_error_signal.connect(self._on_worker_error)
        
        self.render_start_times = {}

        self.scaled_image1_for_display: PIL.Image.Image | None = None
        self.scaled_image2_for_display: PIL.Image.Image | None = None
        
        self.current_rendering_task_id = 0

        self._connect_signals()
        self._restore_geometry()
        QTimer.singleShot(0, self.main_controller.initialize_app_display)
        self._apply_initial_settings_to_ui()

    def schedule_update(self):
        if not self._update_scheduler_timer.isActive():
            self._update_scheduler_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.event_handler.handle_resize_event(event)

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        self.event_handler.handle_change_event(event)

    def closeEvent(self, event):
        self.thread_pool.waitForDone()
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

    def _determine_font_path(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.font_path_absolute = None

        flatpak_font_path = f"/app/share/fonts/truetype/{self.font_file_name}"
        expected_font_path = os.path.join(
            self.script_dir, "font", self.font_file_name)

        paths_to_check = [
            (flatpak_font_path, "Flatpak"),
            (expected_font_path, "Relative to script"),
        ]

        found_path = None
        for path_candidate, description in paths_to_check:
            try:
                if os.path.exists(path_candidate):
                    found_path = path_candidate
                    break
            except Exception:
                pass

        self.font_path_absolute = found_path
        if self.font_path_absolute is None:
            logger.critical(
                "No valid custom font path found. Relying on system fonts.")

    def _apply_panel_visibility(self):
        if hasattr(self, "magnifier_settings_panel"):
            self.magnifier_settings_panel.setVisible(
                self.app_state.use_magnifier)
        if hasattr(self, "freeze_button"):
            self.freeze_button.setEnabled(self.app_state.use_magnifier)
        if hasattr(self, "edit_layout_widget"):
            self.edit_layout_widget.setVisible(
                self.app_state.include_file_names_in_saved
            )

    def _apply_initial_settings_to_ui(self):
        if hasattr(self, "slider_size"):
            self.slider_size.setValue(
                int(self.app_state.magnifier_size_relative * 100))
        if hasattr(self, "slider_capture"):
            self.slider_capture.setValue(
                int(self.app_state.capture_size_relative * 100)
            )
        if hasattr(self, "slider_speed"):
            self.slider_speed.setValue(
                int(self.app_state.movement_speed_per_sec * 10))
        if hasattr(self, "checkbox_horizontal"):
            self.checkbox_horizontal.setChecked(self.app_state.is_horizontal)
        if hasattr(self, "checkbox_magnifier"):
            self.checkbox_magnifier.setChecked(self.app_state.use_magnifier)
        if hasattr(self, "freeze_button"):
            self.freeze_button.setChecked(self.app_state.freeze_magnifier)
            self.freeze_button.setEnabled(self.app_state.use_magnifier)
        if hasattr(self, "font_size_slider"):
            self.font_size_slider.setValue(self.app_state.font_size_percent)
        if hasattr(self, "checkbox_file_names"):
            self.checkbox_file_names.setChecked(
                self.app_state.include_file_names_in_saved
            )
        if hasattr(self, "btn_color_picker"):
            self._update_color_button_tooltip()

        if hasattr(self, "combo_interpolation"):
            target_method_key = self.app_state.interpolation_method
            found_index_for_initial_setting = -1
            method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())

            try:
                target_user_data_value = method_keys.index(target_method_key)
                for i in range(self.combo_interpolation.count()):
                    item_data = self.combo_interpolation.itemData(i)
                    if (
                        isinstance(item_data, int)
                        and item_data == target_user_data_value
                    ):
                        found_index_for_initial_setting = i
                        break
            except ValueError:
                pass

            if found_index_for_initial_setting != -1:
                if (
                    self.combo_interpolation.currentIndex()
                    != found_index_for_initial_setting
                ):
                    self.combo_interpolation.blockSignals(True)
                    self.combo_interpolation.setCurrentIndex(
                        found_index_for_initial_setting
                    )
                    self.combo_interpolation.blockSignals(False)
            else:
                if self.combo_interpolation.count() > 0:
                    first_item_user_data = self.combo_interpolation.itemData(0)
                    if isinstance(
                        first_item_user_data, int
                    ) and 0 <= first_item_user_data < len(method_keys):
                        self.app_state.interpolation_method = method_keys[
                            first_item_user_data
                        ]
        self.ui_logic.update_translations()

    def _connect_signals(self):
        self.btn_image1.clicked.connect(
            lambda: self.main_controller.load_images_from_dialog(1)
        )
        self.btn_image2.clicked.connect(
            lambda: self.main_controller.load_images_from_dialog(2)
        )

        self.btn_swap.shortClicked.connect(
            self.main_controller.swap_current_images)
        self.btn_swap.longPressed.connect(
            self.main_controller.swap_entire_lists)

        self.btn_clear_list1.shortClicked.connect(
            lambda: self.main_controller.remove_current_image_from_list(1)
        )
        self.btn_clear_list1.longPressed.connect(
            lambda: self.main_controller.clear_image_list(1)
        )
        self.btn_clear_list2.shortClicked.connect(
            lambda: self.main_controller.remove_current_image_from_list(2)
        )
        self.btn_clear_list2.longPressed.connect(
            lambda: self.main_controller.clear_image_list(2)
        )

        self.slider_size.sliderPressed.connect(
            lambda: self.main_controller.on_slider_pressed("magnifier_size")
        )
        self.slider_capture.sliderPressed.connect(
            lambda: self.main_controller.on_slider_pressed("capture_size")
        )
        self.slider_speed.sliderPressed.connect(
            lambda: self.main_controller.on_slider_pressed("movement_speed")
        )
        self.font_size_slider.sliderPressed.connect(
            lambda: self.main_controller.on_slider_pressed("font_size")
        )

        self.combo_image1.currentIndexChanged.connect(
            lambda: self._schedule_combobox_update(1)
        )
        self.combo_image2.currentIndexChanged.connect(
            lambda: self._schedule_combobox_update(2)
        )

        self.edit_name1.editingFinished.connect(
            lambda: self.main_controller.on_edit_name_changed(self.edit_name1)
        )
        self.edit_name1.textChanged.connect(
            self.main_controller.trigger_live_name_or_font_update
        )
        self.edit_name2.editingFinished.connect(
            lambda: self.main_controller.on_edit_name_changed(self.edit_name2)
        )
        self.edit_name2.textChanged.connect(
            self.main_controller.trigger_live_name_or_font_update
        )

        self.checkbox_horizontal.stateChanged.connect(
            lambda state: self.main_controller.toggle_orientation(
                state == Qt.CheckState.Checked.value
            )
        )
        self.checkbox_magnifier.stateChanged.connect(
            lambda state: self.main_controller.toggle_magnifier(
                state == Qt.CheckState.Checked.value
            )
        )
        self.freeze_button.stateChanged.connect(
            lambda state: self.main_controller.toggle_freeze_magnifier(
                state == Qt.CheckState.Checked.value
            )
        )
        self.checkbox_file_names.toggled.connect(
            lambda checked: self.main_controller.toggle_include_filenames_in_saved(
                checked
            )
        )

        self.slider_size.valueChanged.connect(
            self.main_controller.update_magnifier_size_relative
        )
        self.slider_size.sliderReleased.connect(
            lambda: self.main_controller.on_slider_released(
                'magnifier_size_relative', self.app_state.magnifier_size_relative
            )
        )

        self.slider_capture.valueChanged.connect(
            self.main_controller.update_capture_size_relative
        )
        self.slider_capture.sliderReleased.connect(
            lambda: self.main_controller.on_slider_released(
                'capture_size_relative', self.app_state.capture_size_relative
            )
        )

        self.slider_speed.valueChanged.connect(
            self.main_controller.update_movement_speed
        )
        self.slider_speed.sliderReleased.connect(
            lambda: self.main_controller.on_slider_released(
                'movement_speed_per_sec', self.app_state.movement_speed_per_sec
            )
        )

        self.combo_interpolation.currentIndexChanged.connect(
            self.main_controller.on_interpolation_changed
        )

        self.font_size_slider.valueChanged.connect(
            self.main_controller.apply_font_size_change
        )
        self.font_size_slider.sliderReleased.connect(
            lambda: self.main_controller.on_slider_released(
                'font_size_percent', self.app_state.font_size_percent
            )
        )
        self.btn_color_picker.clicked.connect(self._open_color_dialog)

        self.btn_save.clicked.connect(self._save_result_with_error_handling)
        self.help_button.clicked.connect(self._show_help_dialog)
        self.btn_settings.clicked.connect(self._open_settings_dialog)

        if hasattr(self, "image_label") and self.image_label is not None:
            self.image_label.mousePressed.connect(
                self.event_handler.handle_mouse_press)
            self.image_label.mouseMoved.connect(
                self.event_handler.handle_mouse_move)
            self.image_label.mouseReleased.connect(
                self.event_handler.handle_mouse_release
            )

    def _restore_geometry(self):
        self.settings_manager.restore_geometry(self, self.app_state)
        QTimer.singleShot(0, self._ensure_minimum_size_after_restore)
        
    def _ensure_minimum_size_after_restore(self):
        self.update_minimum_window_size()
        min_size = self.minimumSize()
        current_size = self.size()

        new_width = max(current_size.width(), min_size.width())
        new_height = max(current_size.height(), min_size.height())

        if new_width != current_size.width() or new_height != current_size.height():
            self.resize(new_width, new_height)

    def _update_resolution_labels(self):
        res1_text = "--x--"
        tooltip1 = tr("No image loaded", self.app_state.current_language)
        if self.app_state.original_image1 and hasattr(
            self.app_state.original_image1, "size"
        ):
            try:
                w, h = self.app_state.original_image1.size
                res1_text = f"{w}x{h}"
                tooltip1 = res1_text
            except Exception:
                res1_text = tr("Error", self.app_state.current_language)

        res2_text = "--x--"
        tooltip2 = tr("No image loaded", self.app_state.current_language)
        if self.app_state.original_image2 and hasattr(
            self.app_state.original_image2, "size"
        ):
            try:
                w, h = self.app_state.original_image2.size
                res2_text = f"{w}x{h}"
                tooltip2 = res2_text
            except Exception:
                res2_text = tr("Error", self.app_state.current_language)

        if hasattr(self, "resolution_label1"):
            self.resolution_label1.setText(res1_text)
            self.resolution_label1.setToolTip(tooltip1)
        if hasattr(self, "resolution_label2"):
            self.resolution_label2.setText(res2_text)
            self.resolution_label2.setToolTip(tooltip2)

    def _display_single_image_on_label(
        self, pil_image_to_display: PIL.Image.Image | None
    ):
        if not hasattr(self, "image_label"):
            return

        try:
            if (
                pil_image_to_display is None
                or pil_image_to_display.width <= 0
                or pil_image_to_display.height <= 0
            ):
                if self.image_label.pixmap() is not None:
                    self.image_label.clear()
                self.current_displayed_pixmap = None
                self.app_state.pixmap_width, self.app_state.pixmap_height = (
                    0, 0)
                return

            label_width, label_height = self.get_current_label_dimensions()

            pil_img_rgba = (
                pil_image_to_display.convert("RGBA")
                if pil_image_to_display.mode != "RGBA"
                else pil_image_to_display
            )
            data = pil_img_rgba.tobytes("raw", "RGBA")
            bytes_per_line = pil_img_rgba.width * 4
            qimage = QImage(
                data,
                pil_img_rgba.width,
                pil_img_rgba.height,
                bytes_per_line,
                QImage.Format.Format_RGBA8888,
            )
            if qimage.isNull():
                raise ValueError("QImage conversion null.")

            original_pixmap_for_scaling = QPixmap.fromImage(qimage)
            if original_pixmap_for_scaling.isNull():
                raise ValueError("QPixmap conversion null.")

            scaled_pixmap = original_pixmap_for_scaling.scaled(
                label_width,
                label_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if scaled_pixmap.isNull():
                raise ValueError("Scaled QPixmap for single image is null.")

            self.image_label.setPixmap(scaled_pixmap)
            self.current_displayed_pixmap = scaled_pixmap.copy()

            self.app_state.pixmap_width = scaled_pixmap.width()
            self.app_state.pixmap_height = scaled_pixmap.height()

        except Exception as e:
            logger.error(
                f"Error converting PIL to QPixmap for single image: {e}")
            traceback.print_exc()
            if self.image_label.pixmap() is not None:
                self.image_label.clear()
            self.current_displayed_pixmap = None
            self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
        finally:
            if (
                hasattr(self, "image_label")
                and self.image_label is not None
                and (not self.image_label.updatesEnabled())
            ):
                self.image_label.setUpdatesEnabled(True)
                self.image_label.update()

    def _update_combobox(self, image_number: int):
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        target_list = (
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )
        current_internal_index = (
            self.app_state.current_index1
            if image_number == 1
            else self.app_state.current_index2
        )

        combobox.blockSignals(True)
        combobox.clear()

        for i, item_data in enumerate(target_list):
            display_name = tr("Invalid Data", self.app_state.current_language)
            full_name_for_tooltip = ""

            if isinstance(item_data, tuple) and len(item_data) >= 3:
                display_name = item_data[2] or tr(
                    "Unnamed", self.app_state.current_language
                )
                full_name_for_tooltip = display_name
            elif isinstance(item_data, tuple) and len(item_data) >= 2 and item_data[1]:
                display_name = os.path.splitext(
                    os.path.basename(item_data[1]))[0]
                full_name_for_tooltip = item_data[1]

            max_cb_len = 60
            cb_name = (
                display_name[: max_cb_len - 3] + "..."
                if len(display_name) > max_cb_len
                else display_name
            )

            combobox.addItem(cb_name)
            path = (
                item_data[1]
                if isinstance(item_data, tuple) and len(item_data) > 1
                else None
            )

            combobox.setItemData(
                i,
                {
                    "full_name": full_name_for_tooltip,
                    "list_index": i,
                    "path": path,
                    "display_name_truncated": cb_name,
                },
            )

        new_index_to_select = -1
        if 0 <= current_internal_index < len(target_list):
            new_index_to_select = current_internal_index
        elif len(target_list) > 0:
            new_index_to_select = 0

        if new_index_to_select != -1:
            combobox.setCurrentIndex(new_index_to_select)
            self.ui_logic.update_combobox_tooltip_on_selection(
                combobox, new_index_to_select
            )
        else:
            combobox.setToolTip("")

        combobox.blockSignals(False)

    def _update_single_combobox_item_text(
            self, combobox, item_index, new_display_name):
        if 0 <= item_index < combobox.count():
            max_cb_len = 60
            cb_name = (
                new_display_name[: max_cb_len - 3] + "..."
                if len(new_display_name) > max_cb_len
                else new_display_name
            )
            combobox.setItemText(item_index, cb_name)

            current_data = combobox.itemData(item_index)
            if isinstance(current_data, dict):
                current_data["full_name"] = new_display_name
                current_data["display_name_truncated"] = cb_name
                combobox.setItemData(item_index, current_data)
            else:
                combobox.setItemData(
                    item_index,
                    {
                        "full_name": new_display_name,
                        "list_index": item_index,
                        "path": current_data if isinstance(current_data, str) else None,
                        "display_name_truncated": cb_name,
                    },
                )

            if combobox.currentIndex() == item_index:
                self.ui_logic.update_combobox_tooltip_on_selection(
                    combobox, item_index)

    def _on_combobox_changed(self, image_number: int, index: int):
        self.main_controller.on_combobox_changed(image_number, index)
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        self.ui_logic.update_combobox_tooltip_on_selection(combobox, index)

    def _stabilize_ui_layout(self):
        max_attempts = 3
        for attempt in range(max_attempts):
            old_content_rect = self.image_label.contentsRect()
            old_content_width = old_content_rect.width()
            old_content_height = old_content_rect.height()

            if self.layout():
                self.layout().invalidate()
                self.layout().activate()

            QApplication.processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )

            new_content_rect = self.image_label.contentsRect()
            new_content_width = new_content_rect.width()
            new_content_height = new_content_rect.height()

            if (
                abs(old_content_width - new_content_width) < 2
                and abs(old_content_height - new_content_height) < 2
                and new_content_width > 0
                and new_content_height > 0
            ):
                break

    def get_current_label_dimensions(self) -> Tuple[int, int]:
        if (
            self.app_state.fixed_label_width is not None
            and self.app_state.fixed_label_height is not None
        ):
            width = self.app_state.fixed_label_width
            height = self.app_state.fixed_label_height
            return (max(1, width), max(1, height))
        else:
            content_rect = self.image_label.contentsRect()
            width = content_rect.width()
            height = content_rect.height()
            return (max(1, width), max(1, height))

    def update_comparison_if_needed(self) -> bool:
        if self.app_state.resize_in_progress:
            return False

        if self.app_state.showing_single_image_mode != 0:
            self._display_single_image_on_label(
                self.app_state.image1 if self.app_state.showing_single_image_mode == 1 else self.app_state.image2
            )
            return False

        if not self.app_state.original_image1 or not self.app_state.original_image2:
            if hasattr(self, "image_label") and self.image_label is not None:
                self.image_label.clear()
            self.current_displayed_pixmap = None
            self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
            return False
            
        logger.debug(
            f"Update requested. State: H_Split={self.app_state.is_horizontal}, "
            f"Mag={self.app_state.use_magnifier}, Freeze={self.app_state.freeze_magnifier}, "
            f"Interactive={self.app_state.is_interactive_mode}"
        )

        if (
            not self.app_state.image1
            or not self.app_state.image2
            or self.app_state.image1.size != self.app_state.image2.size
        ):
            full_res_img1, full_res_img2 = resize_images_processor(
                self.app_state.original_image1,
                self.app_state.original_image2,
            )
            self.app_state.image1 = full_res_img1.copy() if full_res_img1 else None
            self.app_state.image2 = full_res_img2.copy() if full_res_img2 else None

            self.scaled_image1_for_display = None
            self.scaled_image2_for_display = None

        if not self.app_state.image1 or not self.app_state.image2:
            return False

        label_width, label_height = self.get_current_label_dimensions()
        scaled_img_w, scaled_img_h = get_scaled_pixmap_dimensions(
            self.app_state.image1, label_width, label_height
        )

        if (
            self.scaled_image1_for_display is None
            or self.scaled_image1_for_display.size != (scaled_img_w, scaled_img_h)
        ):
            resampling_method_for_display = get_pil_resampling_method(
                'LANCZOS', True
            )
            self.scaled_image1_for_display = self.app_state.image1.resize(
                (scaled_img_w, scaled_img_h), resampling_method_for_display
            )
            self.scaled_image2_for_display = self.app_state.image2.resize(
                (scaled_img_w, scaled_img_h), resampling_method_for_display
            )
            self.app_state.clear_all_caches()

        self.app_state.pixmap_width, self.app_state.pixmap_height = (
            scaled_img_w,
            scaled_img_h,
        )
        img_x_in_label = (label_width - scaled_img_w) // 2
        img_y_in_label = (label_height - scaled_img_h) // 2

        self.app_state.image_display_rect_on_label = QRect(
            img_x_in_label, img_y_in_label, scaled_img_w, scaled_img_h
        )

        app_state_copy = self.app_state.copy_for_worker()

        magnifier_coords = None
        if self.app_state.use_magnifier:
            magnifier_coords = get_magnifier_drawing_coords(
                app_state=self.app_state,
                drawing_width=scaled_img_w,
                drawing_height=scaled_img_h,
                container_width=label_width,
                container_height=label_height,
            )

        current_name1_text = (
            self.edit_name1.text()
            if hasattr(self, "edit_name1") and self.edit_name1.text()
            else self.app_state.get_current_display_name(1)
        )
        current_name2_text = (
            self.edit_name2.text()
            if hasattr(self, "edit_name2") and self.edit_name2.text()
            else self.app_state.get_current_display_name(2)
        )

        self.current_rendering_task_id += 1
        
        self.render_start_times[self.current_rendering_task_id] = time.perf_counter()
        logger.debug(f"Starting render task ID {self.current_rendering_task_id} (Interactive: {self.app_state.is_interactive_mode})")


        render_params = {
            "app_state_copy": app_state_copy,
            "image1_scaled_for_display": self.scaled_image1_for_display,
            "image2_scaled_for_display": self.scaled_image2_for_display,
            "original_image1_pil_copy": self.app_state.original_image1.copy(),
            "original_image2_pil_copy": self.app_state.original_image2.copy(),
            "magnifier_coords": magnifier_coords,
            "font_path_absolute": self.font_path_absolute,
            "file_name1_text": current_name1_text,
            "file_name2_text": current_name2_text,
            "finished_signal": self._worker_finished_signal,
            "error_signal": self._worker_error_signal,
            "task_id": self.current_rendering_task_id,
            "label_dims": (label_width, label_height),
        }

        worker = ImageRenderingWorker(render_params)
        priority = 1 if not self.app_state.is_interactive_mode else 0
        self.thread_pool.start(worker, priority=priority)

        return True

    @pyqtSlot(dict, dict, int)
    def _on_worker_finished(
        self, result_payload: dict, params: dict, finished_task_id: int
    ):
        start_time = self.render_start_times.pop(finished_task_id, None)
        total_duration_ms = (time.perf_counter() - start_time) * 1000 if start_time else -1

        task_was_interactive = params["app_state_copy"].is_interactive_mode
        is_stale = False

        if self.app_state.is_interactive_mode and not task_was_interactive:
            is_stale = True
        elif not self.app_state.is_interactive_mode and task_was_interactive:
            is_stale = True
        elif (
            not self.app_state.is_interactive_mode
            and finished_task_id < self.current_rendering_task_id
        ):
            is_stale = True
            
        logger.debug(
            f"Render task {finished_task_id} finished. Total duration: {total_duration_ms:.2f}ms. "
            f"Stale: {is_stale}. Current task ID: {self.current_rendering_task_id}."
        )

        if is_stale:
            if (
                (
                    self.image_label.pixmap() is None
                    or self.image_label.pixmap().isNull()
                )
                and self.current_displayed_pixmap
                and not self.current_displayed_pixmap.isNull()
            ):
                self.image_label.setPixmap(self.current_displayed_pixmap)
                self.image_label.update()
            return

        final_canvas_pil = result_payload.get("final_canvas")
        padding_left = result_payload.get("padding_left", 0)
        padding_top = result_payload.get("padding_top", 0)

        if not final_canvas_pil:
            return

        self.app_state.result_image = final_canvas_pil

        try:
            paint_start_time = time.perf_counter()
            
            pil_img_rgba = (
                final_canvas_pil.convert("RGBA")
                if final_canvas_pil.mode != "RGBA"
                else final_canvas_pil
            )
            data = pil_img_rgba.tobytes("raw", "RGBA")
            qimage = QImage(
                data,
                pil_img_rgba.width,
                pil_img_rgba.height,
                QImage.Format.Format_RGBA8888,
            )
            if qimage.isNull():
                raise ValueError("QImage null after conversion from PIL.")
            canvas_pixmap = QPixmap.fromImage(qimage)
            if canvas_pixmap.isNull():
                raise ValueError("QPixmap for canvas is null.")

            label_width, label_height = params.get(
                "label_dims", (self.image_label.width(), self.image_label.height()))
            final_pixmap_for_label = QPixmap(label_width, label_height)
            final_pixmap_for_label.fill(Qt.GlobalColor.transparent)

            painter = QPainter(final_pixmap_for_label)

            target_image_rect_in_label = self.app_state.image_display_rect_on_label

            draw_x = target_image_rect_in_label.x() - padding_left
            draw_y = target_image_rect_in_label.y() - padding_top

            painter.drawPixmap(QPoint(draw_x, draw_y), canvas_pixmap)
            painter.end()
            
            paint_duration_ms = (time.perf_counter() - paint_start_time) * 1000
            logger.debug(f"PIL to QPixmap and painting took: {paint_duration_ms:.2f}ms")

            self.image_label.setPixmap(final_pixmap_for_label)
            self.current_displayed_pixmap = final_pixmap_for_label.copy()

            self.app_state.pixmap_width = target_image_rect_in_label.width()
            self.app_state.pixmap_height = target_image_rect_in_label.height()

        except Exception as e:
            logger.error(
                f"Error converting or displaying final image in _on_worker_finished: {e}")
            traceback.print_exc()
            if (
                self.current_displayed_pixmap
                and not self.current_displayed_pixmap.isNull()
            ):
                self.image_label.setPixmap(self.current_displayed_pixmap)
            else:
                self.image_label.clear()
            self.image_label.update()
            return

        if not self.app_state.is_interactive_mode:
            self._stabilize_ui_layout()

    @pyqtSlot(str)
    def _on_worker_error(self, error_message: str):
        QMessageBox.critical(
            self, tr("Error", self.app_state.current_language), error_message
        )
        if (
            hasattr(self, "image_label")
            and self.image_label is not None
            and (not self.image_label.updatesEnabled())
        ):
            self.image_label.setUpdatesEnabled(True)
            self.image_label.update()
    
    def _save_result_with_error_handling(self):
        try:
            if self.app_state.showing_single_image_mode != 0:
                QMessageBox.warning(
                    self,
                    tr("Warning", self.app_state.current_language),
                    tr(
                        "Cannot save while previewing single image.",
                        self.app_state.current_language,
                    ),
                )
                return
            if not self.app_state.original_image1 or not self.app_state.original_image2:
                QMessageBox.warning(
                    self,
                    tr("Warning", self.app_state.current_language),
                    tr(
                        "Please load and select images in both slots first.",
                        self.app_state.current_language,
                    ),
                )
                return

            full_res_img1, full_res_img2 = (
                self.app_state.image1,
                self.app_state.image2,
            )
            if (
                not full_res_img1
                or not full_res_img2
                or full_res_img1.size != full_res_img2.size
            ):
                full_res_img1, full_res_img2 = resize_images_processor(
                    self.app_state.original_image1,
                    self.app_state.original_image2,
                )

            if (
                not full_res_img1
                or not full_res_img2
                or full_res_img1.size != full_res_img2.size
            ):
                QMessageBox.warning(
                    self,
                    tr("Warning", self.app_state.current_language),
                    tr(
                        "Resized images not available or sizes mismatch. Cannot save result. Please reload or select images.",
                        self.app_state.current_language,
                    ),
                )
                return

            img_w_full, img_h_full = full_res_img1.size

            magnifier_coords = None
            if self.app_state.use_magnifier:
                temp_state_for_save = self.app_state.copy_for_worker()
                if not temp_state_for_save.image1: temp_state_for_save.image1 = full_res_img1
                if not temp_state_for_save.image2: temp_state_for_save.image2 = full_res_img2

                magnifier_coords = get_magnifier_drawing_coords(
                    app_state=temp_state_for_save,
                    drawing_width=img_w_full,
                    drawing_height=img_h_full,
                    container_width=img_w_full,
                    container_height=img_h_full
                )

                if self.app_state.freeze_magnifier and self.app_state.frozen_magnifier_absolute_pos:
                    if self.app_state.pixmap_width > 0 and self.app_state.pixmap_height > 0:
                        scale_x = img_w_full / self.app_state.pixmap_width
                        scale_y = img_h_full / self.app_state.pixmap_height
                        
                        frozen_pos_on_screen = self.app_state.frozen_magnifier_absolute_pos
                        
                        new_x = int(round(frozen_pos_on_screen.x() * scale_x))
                        new_y = int(round(frozen_pos_on_screen.y() * scale_y))
                        
                        (crop_box1, crop_box2, 
                         _old_magn_mid, magn_size_pix, magn_spacing_pix, _old_bbox) = magnifier_coords
                        
                        magn_midpoint_full_res = QPoint(new_x, new_y)

                        radius = magn_size_pix / 2.0
                        if magn_spacing_pix < 1.0:
                            new_bbox = QRect(int(new_x - radius), int(new_y - radius), magn_size_pix, magn_size_pix)
                        else:
                            total_width = magn_size_pix * 2 + magn_spacing_pix
                            left_edge = int(new_x - total_width / 2.0)
                            top_edge = int(new_y - radius)
                            new_bbox = QRect(left_edge, top_edge, int(total_width), magn_size_pix)

                        magnifier_coords = (crop_box1, crop_box2,
                                            magn_midpoint_full_res, magn_size_pix, magn_spacing_pix, new_bbox)

            name1_from_state = self.app_state.get_current_display_name(1)
            name2_from_state = self.app_state.get_current_display_name(2)
            current_name1_text = (
                self.edit_name1.text()
                if hasattr(self, "edit_name1") and self.edit_name1.text()
                else name1_from_state or ""
            )
            current_name2_text = (
                self.edit_name2.text()
                if hasattr(self, "edit_name2") and self.edit_name2.text()
                else name2_from_state or ""
            )

            save_result_processor(
                app_instance_for_ui_dialogs=self,
                app_state=self.app_state,
                image1_processed=full_res_img1,
                image2_processed=full_res_img2,
                original_image1=self.app_state.original_image1,
                original_image2=self.app_state.original_image2,
                magnifier_drawing_coords=magnifier_coords,
                font_path_absolute=self.font_path_absolute,
                file_name1_text=current_name1_text,
                file_name2_text=current_name2_text,
                jpeg_quality=self.app_state.jpeg_quality,
            )
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self,
                                 tr("Error",
                                     self.app_state.current_language),
                                 f"{tr('An unexpected error occurred during the save process:',
                                       self.app_state.current_language)}\n{str(e)}",
                                 )

    def _update_color_button_tooltip(self):
        if hasattr(self, "btn_color_picker"):
            self.btn_color_picker.setToolTip(
                f"{
                    tr(
                        'Change Filename Color',
                        self.app_state.current_language)}\n{
                    tr(
                        'Current:',
                        self.app_state.current_language)} {
                    self.app_state.file_name_color.name(
                        QColor.NameFormat.HexArgb)}")

    def _open_color_dialog(self):
        options = QColorDialog.ColorDialogOption.ShowAlphaChannel
        initial_color = self.app_state.file_name_color
        color = QColorDialog.getColor(
            initial_color,
            self,
            tr("Select Filename Color", self.app_state.current_language),
            options=options,
        )
        if color.isValid():
            self.main_controller.apply_filename_color_change(color)

    def _show_help_dialog(self):
        lang = self.app_state.current_language
        html = f"""
        <html><body>
        <h2 style='margin:0 0 8px 0'>{tr('Improve ImgSLI Help', lang)}</h2>
        <h3 style='margin:8px 0 4px 0'>{tr('Loading Images:', lang)}</h3>
        <ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'>
            <li style='margin-bottom:2px'>{tr('Use Add buttons or Drag-n-Drop images onto the left/right side.', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Use dropdown menus to select from loaded images.', lang)} (<b>{tr("Hint:", lang)}</b> {tr("You can scroll through the list with the mouse wheel.", lang)})</li>
            <li style='margin-bottom:2px'>{tr('Use the ⇄ button to swap image lists.', lang)} (<b>{tr('Click: Swap current images', lang)}</b>, <b>{tr('Hold: Swap entire lists', lang)}</b>)</li>
            <li style='margin-bottom:2px'>{tr('Use the Trash buttons (🗑️) to clear the corresponding image list.', lang)} (<b>{tr('Click: Remove current image', lang)}</b>, <b>{tr('Hold: Clear entire list', lang)}</b>)</li>
        </ul>
        <h3 style='margin:8px 0 4px 0'>{tr('Comparison View:', lang)}</h3>
        <ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'>
            <li style='margin-bottom:2px'>{tr('Click and drag the split line (when Magnifier is off).', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Check [Horizontal Split] to change the split orientation.', lang)}</li>
        </ul>
        <h3 style='margin:8px 0 4px 0'>{tr('Magnifier Tool (when checked):', lang)}</h3>
        <ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'>
            <li style='margin-bottom:2px'>{tr('Magnifier: Click/drag sets capture point (red circle).', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Magnifier: Use WASD keys to move magnifier offset relative to capture point.', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Magnifier: Use QE keys to change spacing between magnifier halves (when separated).', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Sliders adjust Magnifier Size (zoom level), Capture Size (area sampled), and Move Speed.', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Select interpolation method for magnifier zoom', lang)}</li>
        </ul>
        <h3 style='margin:8px 0 4px 0'>{tr('Output:', lang)}</h3>
        <ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'>
            <li style='margin-bottom:2px'>{tr('Include file names saves names onto the output image.', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Edit names, adjust font size, and pick text color in the bottom panel (visible when names are included).', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Click [Save Result] to save the current view (including split, magnifier, names if enabled) as a PNG or JPG file.', lang)}</li>
        </ul>
        <h3 style='margin:8px 0 4px 0'>{tr('Settings', lang)}:</h3>
        <ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'>
            <li style='margin-bottom:2px'>{tr('Click the settings button (...) to change the application language, the maximum displayed name length, and JPEG quality.', lang)}</li>
            <li style='margin-bottom:2px'>{tr('Enable debug logging', lang)}: {tr('Shows detailed logs for developers. Requires restart.', lang)}</li>
        </ul>
        <h3 style='margin:8px 0 4px 0'>{tr('Quick Preview:', lang)}</h3>
        <ul style='margin:0 0 6px 0; padding-left:10px; list-style-position:inside;'>
            <li style='margin-bottom:2px'>{tr('Hold Space and use mouse buttons to quickly preview', lang)}</li>
        </ul>
        </body></html>
        """
        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setWindowTitle(tr("Help", lang))
        dlg.setTextFormat(Qt.TextFormat.RichText)
        dlg.setText(html)
        dlg.exec()

    def _reapply_button_styles(self):
        icon_size_clear = QSize(22, 22)
        icon_size_others = QSize(24, 24)

        if hasattr(self, "btn_swap"):
            self.btn_swap.setIconSize(icon_size_others)
            self.btn_swap.setStyleSheet(
                """
                TransparentPushButton {
                    padding: 6px;
                    qproperty-iconSize: 24px;
                }
            """
            )
        if hasattr(self, "btn_clear_list1"):
            self.btn_clear_list1.setIconSize(icon_size_clear)
            self.btn_clear_list1.setStyleSheet(
                """
                TransparentPushButton {
                    padding: 7px;
                    qproperty-iconSize: 22px;
                }
            """
            )
        if hasattr(self, "btn_clear_list2"):
            self.btn_clear_list2.setIconSize(icon_size_clear)
            self.btn_clear_list2.setStyleSheet(
                """
                TransparentPushButton {
                    padding: 7px;
                    qproperty-iconSize: 22px;
                }
            """
            )
        if hasattr(self, "btn_settings"):
            self.btn_settings.setIconSize(icon_size_others)
            self.btn_settings.setStyleSheet(
                """
                TransparentPushButton {
                    padding: 6px;
                    qproperty-iconSize: 24px;
                }
            """
            )
        if hasattr(self, "help_button"):
            self.help_button.setIconSize(icon_size_others)
            self.help_button.setStyleSheet(
                """
                TransparentPushButton {
                    padding: 6px;
                    qproperty-iconSize: 24px;
                }
            """
            )

        if hasattr(self, "btn_color_picker"):
            self.btn_color_picker.setIconSize(icon_size_others)
            self.btn_color_picker.setStyleSheet(
                """
                PushButton {
                    padding: 6px;
                    qproperty-iconSize: 24px;
                }
            """
            )

    def _open_settings_dialog(self):
        if not self.settings_dialog_available:
            QMessageBox.critical(
                self,
                tr("Error", self.app_state.current_language),
                tr(
                    "Settings dialog module not found.", self.app_state.current_language
                ),
            )
            return

        try:
            settings_dialog = SettingsDialog(
                current_language=self.app_state.current_language,
                current_max_length=self.app_state.max_name_length,
                min_limit=AppConstants.MIN_NAME_LENGTH_LIMIT,
                max_limit=AppConstants.MAX_NAME_LENGTH_LIMIT,
                current_jpeg_quality=self.app_state.jpeg_quality,
                debug_mode_enabled=self.app_state.debug_mode_enabled,
                parent=self,
                tr_func=tr,
            )
            dialog_result = settings_dialog.exec()

            if dialog_result == QDialog.DialogCode.Accepted:
                try:
                    new_lang, new_max_length, new_jpeg_quality, new_debug_enabled = (
                        settings_dialog.get_settings()
                    )

                    if new_max_length != self.app_state.max_name_length:
                        self.app_state.max_name_length = max(
                            AppConstants.MIN_NAME_LENGTH_LIMIT, min(
                                AppConstants.MAX_NAME_LENGTH_LIMIT, new_max_length), )
                        self.settings_manager._save_setting(
                            "max_name_length", self.app_state.max_name_length
                        )

                    if new_jpeg_quality != self.app_state.jpeg_quality:
                        self.app_state.jpeg_quality = max(
                            1, min(100, new_jpeg_quality))
                        self.settings_manager._save_setting(
                            "jpeg_quality", self.app_state.jpeg_quality
                        )
                    
                    debug_mode_changed = new_debug_enabled != self.app_state.debug_mode_enabled
                    if debug_mode_changed:
                        self.app_state.debug_mode_enabled = new_debug_enabled
                        logging_service.setup_logging(new_debug_enabled)
                        self.settings_manager._save_setting(
                            "debug_mode_enabled", new_debug_enabled
                        )
                        QMessageBox.information(
                            self,
                            tr("Information", self.app_state.current_language),
                            tr("Restart the application for the debug log setting to take full effect.", self.app_state.current_language)
                        )
                        
                    if new_lang != self.app_state.current_language:
                        self.main_controller.change_language(new_lang)

                except Exception as e:
                    QMessageBox.warning(
                        self,
                        tr("Error", self.app_state.current_language),
                        tr(
                            "Failed to apply settings: {}",
                            self.app_state.current_language,
                        ).format(str(e)),
                    )

            QTimer.singleShot(0, self._reapply_button_styles)

        except Exception as e:
            QMessageBox.warning(
                self,
                tr("Error", self.app_state.current_language),
                tr(
                    "Failed to open settings dialog: {}",
                    self.app_state.current_language,
                ).format(str(e)),
            )
            QTimer.singleShot(0, self._reapply_button_styles)

    def update_minimum_window_size(self):
        layout = self.layout()
        if not layout or not hasattr(self, "image_label"):
            return

        original_policy = self.image_label.sizePolicy()
        temp_policy = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        temp_policy.setHeightForWidth(original_policy.hasHeightForWidth())
        temp_policy.setWidthForHeight(original_policy.hasWidthForHeight())
        temp_policy.setVerticalPolicy(
            QSizePolicy.Policy.Preferred
            if original_policy.verticalPolicy() != QSizePolicy.Policy.Ignored
            else QSizePolicy.Policy.Ignored
        )
        temp_policy.setHorizontalPolicy(
            QSizePolicy.Policy.Preferred
            if original_policy.horizontalPolicy() != QSizePolicy.Policy.Ignored
            else QSizePolicy.Policy.Ignored
        )

        try:
            self.image_label.setSizePolicy(temp_policy)
            self.image_label.updateGeometry()

            if layout:
                layout.invalidate()
                layout.activate()

            layout_hint_size = layout.sizeHint() if layout else QSize(250, 300)

            base_min_w, base_min_h = (250, 300)

            new_min_w, new_min_h = (
                max(base_min_w, layout_hint_size.width()),
                max(base_min_h, layout_hint_size.height()),
            )

            padding = 10
            new_min_w += padding
            new_min_h += padding

            current_min = self.minimumSize()
            if current_min.width() != new_min_w or current_min.height() != new_min_h:
                self.setMinimumSize(new_min_w, new_min_h)
        except Exception:
            pass
        finally:
            if (
                hasattr(self, "image_label")
                and self.image_label.sizePolicy() != original_policy
            ):
                self.image_label.setSizePolicy(original_policy)
                self.image_label.updateGeometry()
                if layout:
                    layout.invalidate()
                    layout.activate()
    def _schedule_combobox_update(self, combo_number: int):
        self.last_combo_to_update = combo_number
        self.combobox_update_timer.start()

    def _perform_combobox_update(self):
        if self.last_combo_to_update == 0:
            return

        combo_number = self.last_combo_to_update
        combobox = self.combo_image1 if combo_number == 1 else self.combo_image2
        current_index = combobox.currentIndex()

        self._on_combobox_changed(combo_number, current_index)
        
        self.last_combo_to_update = 0