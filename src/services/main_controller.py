import os
import traceback
from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtCore import QPointF, QTimer, QPoint
from PyQt6.QtGui import QColor
from services.state_manager import AppState, AppConstants
from processing_services.image_resize import resize_images_processor
from services.utils import get_magnifier_drawing_coords
from translations import tr
import logging

logger = logging.getLogger("ImproveImgSLI")

class MainController:

    def __init__(self, app_state: AppState, app_instance_ref):
        self.app_state = app_state
        self.app = app_instance_ref

    def initialize_app_display(self):
        logger.debug('Initializing app display from settings...')
        if self.app_state.loaded_image1_paths:
            self.load_images_from_paths(self.app_state.loaded_image1_paths, 1)
        if self.app_state.loaded_image2_paths:
            self.load_images_from_paths(self.app_state.loaded_image2_paths, 2)
        
        if self.app_state.loaded_current_index1 != -1 and 0 <= self.app_state.loaded_current_index1 < len(self.app_state.image_list1):
            self.app_state.current_index1 = self.app_state.loaded_current_index1
        elif self.app_state.image_list1:
            self.app_state.current_index1 = 0

        if self.app_state.loaded_current_index2 != -1 and 0 <= self.app_state.loaded_current_index2 < len(self.app_state.image_list2):
            self.app_state.current_index2 = self.app_state.loaded_current_index2
        elif self.app_state.image_list2:
            self.app_state.current_index2 = 0
            
        self.app._update_combobox(1)
        self.app._update_combobox(2)
        self.set_current_image(1) 
        self.set_current_image(2)
        
        self.app.ui_logic.update_file_names()
        self.app._update_resolution_labels()
        self.app.update_minimum_window_size()
        
        logger.debug('Initial app display setup complete. State will trigger update.')
        self.app_state.stateChanged.emit()

    def load_images_from_paths(self, file_paths: list[str], image_number: int):
        logger.debug(f'Attempting to load {len(file_paths)} images for slot {image_number}. Files: {file_paths}')
        target_list_ref = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        loaded_count, newly_added_indices, load_errors = (0, [], [])
        current_paths_in_list = {entry[1] for entry in target_list_ref if len(entry) > 1 and entry[1]}
        
        for file_path in file_paths:
            if not isinstance(file_path, str) or not file_path:
                load_errors.append(f"{str(file_path)}: {tr('Invalid item type or empty path', self.app_state.current_language)}")
                continue
            try:
                normalized_path = os.path.normpath(file_path)
                original_path_for_display = os.path.basename(normalized_path) or tr('Unnamed File', self.app_state.current_language)
            except Exception as e_norm:
                load_errors.append(f'{file_path}: Error normalizing path - {e_norm}')
                continue
            if normalized_path in current_paths_in_list:
                logger.debug(f"Skipping already loaded file: {normalized_path}")
                continue

            try:
                with Image.open(normalized_path) as img:
                    temp_image = img.copy()
                    temp_image.load()
                base_filename = os.path.basename(normalized_path)
                display_name = os.path.splitext(base_filename)[0]
                target_list_ref.append((temp_image, normalized_path, display_name))
                current_paths_in_list.add(normalized_path)
                newly_added_indices.append(len(target_list_ref) - 1)
                loaded_count += 1
            except Exception as e:
                logger.error(f"Failed to load image '{original_path_for_display}': {e}")
                load_errors.append(f'{original_path_for_display}: {type(e).__name__}: {str(e)[:100]}')

        if loaded_count > 0:
            new_index = newly_added_indices[-1]
            logger.debug(f"Loaded {loaded_count} new images for slot {image_number}. Setting index to {new_index}.")
            if image_number == 1:
                self.app_state.current_index1 = new_index
            else:
                self.app_state.current_index2 = new_index
            
            self.app._update_combobox(image_number)
            self.set_current_image(image_number)

        if load_errors:
            QMessageBox.warning(self.app, tr('Error Loading Images', self.app_state.current_language), tr(
                'Some images could not be loaded:', self.app_state.current_language) + '\n\n - ' + '\n - '.join(load_errors))

    def set_current_image(self, image_number: int):
        logger.debug(f'set_current_image called for slot {image_number}.')
        target_list = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        current_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2
        edit_name_widget = self.app.edit_name1 if image_number == 1 else self.app.edit_name2

        new_pil_img, new_path, new_display_name = None, None, None
        if 0 <= current_index < len(target_list):
            new_pil_img, new_path, new_display_name = target_list[current_index]
            logger.debug(f"Image for slot {image_number} is set to index {current_index}, path: {new_path}")
        else:
            logger.debug(f"Clearing image for slot {image_number} as index is invalid ({current_index}).")

        self.app_state.set_current_image_data(image_number, new_pil_img, new_path, new_display_name)
        
        if edit_name_widget:
            edit_name_widget.blockSignals(True)
            edit_name_widget.setText(new_display_name or '')
            edit_name_widget.blockSignals(False)
        
        self.app.ui_logic.update_file_names()
        self.app._update_resolution_labels()
        
    def on_combobox_changed(self, image_number: int, combobox_index: int):
        logger.debug(f'on_combobox_changed called for slot {image_number}, index {combobox_index}.')
        current_internal_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2

        if combobox_index != current_internal_index:
            if image_number == 1:
                self.app_state.current_index1 = combobox_index
            else:
                self.app_state.current_index2 = combobox_index
            self.set_current_image(image_number)

    def swap_current_images(self):
        logger.debug('Swapping current images.')
        idx1, idx2 = self.app_state.current_index1, self.app_state.current_index2
        list1, list2 = self.app_state.image_list1, self.app_state.image_list2

        if not (0 <= idx1 < len(list1) and 0 <= idx2 < len(list2)):
            return

        list1[idx1], list2[idx2] = list2[idx2], list1[idx1]
        
        self.app._update_combobox(1)
        self.app._update_combobox(2)
        self.set_current_image(1)
        self.set_current_image(2)
        
    def swap_entire_lists(self):
        logger.debug('Swapping entire image lists.')
        self.app_state.swap_all_image_data()
        
        self.app._update_combobox(1)
        self.app._update_combobox(2)
        self.app.ui_logic.update_file_names()
        self.app._update_resolution_labels()

    def remove_current_image_from_list(self, image_number: int):
        logger.debug(f'Removing current image from list {image_number}.')
        target_list, current_index = ((self.app_state.image_list1, self.app_state.current_index1) if image_number == 1 else (self.app_state.image_list2, self.app_state.current_index2))

        if not (0 <= current_index < len(target_list)):
            return

        target_list.pop(current_index)
        new_list_len = len(target_list)
        new_index = min(current_index, new_list_len - 1) if new_list_len > 0 else -1

        if image_number == 1:
            self.app_state.current_index1 = new_index
        else:
            self.app_state.current_index2 = new_index
        
        self.app._update_combobox(image_number)
        self.set_current_image(image_number)

    def clear_image_list(self, image_number: int):
        logger.debug(f'Clearing image list for slot {image_number}.')
        self.app_state.clear_image_slot_data(image_number)
        self.app._update_combobox(image_number)
        self.app.ui_logic.update_file_names()
        self.app._update_resolution_labels()

    def toggle_orientation(self, is_horizontal_checked: bool):
        if is_horizontal_checked != self.app_state.is_horizontal:
            self.app_state.is_horizontal = is_horizontal_checked

    def toggle_magnifier(self, use_magnifier_checked: bool):
        if use_magnifier_checked != self.app_state.use_magnifier:
            self.app_state.use_magnifier = use_magnifier_checked
            self.app._apply_panel_visibility()

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        if freeze_checked == self.app_state.freeze_magnifier:
            return

        if freeze_checked:
            if not self.app_state.use_magnifier or not self.app_state.image1:
                logger.warning("Cannot freeze: Magnifier not in use or no image loaded.")
                self.app.freeze_button.setChecked(False) 
                return

            drawing_width, drawing_height = self.app_state.pixmap_width, self.app_state.pixmap_height
            label_width, label_height = self.app.get_current_label_dimensions()
            
            magnifier_coords = get_magnifier_drawing_coords(
                self.app_state, 
                drawing_width, 
                drawing_height,
                label_width,
                label_height
            )
            
            if magnifier_coords and magnifier_coords[4]:
                current_pixel_pos = magnifier_coords[4]
                self.app_state.frozen_magnifier_absolute_pos = current_pixel_pos
                self.app_state.freeze_magnifier = True
                logger.debug(f"Magnifier frozen at absolute position: {current_pixel_pos}")
            else:
                logger.error("Could not determine magnifier position to freeze.")
                self.app.freeze_button.setChecked(False)
        else:
            logger.debug("Unfreezing magnifier: resetting state.")
            
            if self.app_state.frozen_magnifier_absolute_pos:
                drawing_width, drawing_height = self.app_state.pixmap_width, self.app_state.pixmap_height
                target_max_dim = float(max(drawing_width, drawing_height))

                frozen_pos_pixels = self.app_state.frozen_magnifier_absolute_pos

                capture_rel_pos = self.app_state.capture_position_relative
                capture_pixel_pos = QPoint(
                    int(round(capture_rel_pos.x() * drawing_width)),
                    int(round(capture_rel_pos.y() * drawing_height))
                )

                new_offset_pixels = QPointF(frozen_pos_pixels) - QPointF(capture_pixel_pos)

                new_offset_rel = QPointF(
                    new_offset_pixels.x() / target_max_dim if target_max_dim > 0 else 0,
                    new_offset_pixels.y() / target_max_dim if target_max_dim > 0 else 0
                )

                self.app_state.magnifier_offset_relative = new_offset_rel
                self.app_state.magnifier_offset_relative_visual = new_offset_rel
                
                logger.debug(f"Magnifier unfrozen. New offset calculated: {new_offset_rel}")

            self.app_state.freeze_magnifier = False
            self.app_state.frozen_magnifier_absolute_pos = None

        self.app_state.stateChanged.emit()

    def on_slider_pressed(self, slider_name: str):
        self.app_state.is_dragging_any_slider = True
        self.app.event_handler._enter_interactive_mode()

    def update_magnifier_size_relative(self, value: int):
        self.app_state.magnifier_size_relative = max(0.05, min(1.0, value / 100.0))

    def update_capture_size_relative(self, value: int):
        self.app_state.capture_size_relative = max(0.01, min(1.0, value / 100.0))

    def update_movement_speed(self, value: int):
        self.app_state.movement_speed_per_sec = max(0.1, min(5.0, value / 10.0))
        
    def on_slider_released(self, setting_name: str, value_to_save):
        self.app_state.is_dragging_any_slider = False
        self.app.settings_manager._save_setting(setting_name, value_to_save)
        self.app.event_handler._exit_interactive_mode()

    def on_interpolation_changed(self, index: int):
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        user_data = self.app.combo_interpolation.itemData(index)
        if isinstance(user_data, int) and 0 <= user_data < len(method_keys):
            self.app_state.interpolation_method = method_keys[user_data]

    def on_edit_name_changed(self, line_edit):
        new_name = line_edit.text().strip()
        image_number = 1 if line_edit == self.app.edit_name1 else 2
        
        target_list = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        current_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2
        
        if 0 <= current_index < len(target_list):
            img, path, old_name = target_list[current_index]
            if new_name != old_name:
                target_list[current_index] = (img, path, new_name)
                self.app._update_single_combobox_item_text(self.app.combo_image1 if image_number == 1 else self.app.combo_image2, current_index, new_name)
                self.app.ui_logic.update_file_names()
                if self.app_state.include_file_names_in_saved:
                    self.app_state.stateChanged.emit()

    def trigger_live_name_or_font_update(self):
        if self.app_state.include_file_names_in_saved:
            self.app_state.stateChanged.emit()
        self.app.ui_logic.update_file_names()
        self.app.ui_logic.check_name_lengths()

    def activate_single_image_mode(self, image_number: int):
        if self.app_state.original_image1 if image_number == 1 else self.app_state.original_image2:
            self.app_state.showing_single_image_mode = image_number
        else:
            self.app_state.showing_single_image_mode = 0

    def deactivate_single_image_mode(self):
        self.app_state.showing_single_image_mode = 0

    def change_language(self, lang_code: str):
        self.app_state.current_language = lang_code
        self.app.ui_logic.update_translations()
        self.app.settings_manager._save_setting('language', lang_code)

    def apply_font_size_change(self, value: int):
        self.app_state.font_size_percent = value

    def apply_filename_color_change(self, color: QColor):
        if color.isValid():
            self.app_state.file_name_color = color
            self.app.settings_manager._save_setting('filename_color', color.name(QColor.NameFormat.HexArgb))
    
    def toggle_include_filenames_in_saved(self, checked: bool):
        self.app_state.include_file_names_in_saved = checked
        self.app._apply_panel_visibility()