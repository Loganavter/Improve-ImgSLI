import os
import traceback
from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtGui import QColor
from services.state_manager import AppState, AppConstants
from processing_services.image_resize import resize_images_processor
from services.utils import get_magnifier_drawing_coords
from translations import tr

class MainController:

    def __init__(self, app_state: AppState, app_instance_ref):
        self.app_state = app_state
        self.app = app_instance_ref

    def initialize_app_display(self):
        print('DEBUG: Initializing app display from settings...')
        if self.app_state.loaded_image1_paths:
            print('DEBUG: Loading image1 paths from settings.')
            self.load_images_from_paths(self.app_state.loaded_image1_paths, 1, trigger_update=False)
        if self.app_state.loaded_image2_paths:
            print('DEBUG: Loading image2 paths from settings.')
            self.load_images_from_paths(self.app_state.loaded_image2_paths, 2, trigger_update=False)
        if self.app_state.loaded_current_index1 != -1 and 0 <= self.app_state.loaded_current_index1 < len(self.app_state.image_list1):
            self.app_state.current_index1 = self.app_state.loaded_current_index1
            print(f'DEBUG: Setting current image 1 to loaded index {self.app_state.current_index1}.')
            self.set_current_image(1, trigger_update=False)
        elif self.app_state.image_list1:
            self.app_state.current_index1 = 0
            print('DEBUG: Setting current image 1 to default index 0.')
            self.set_current_image(1, trigger_update=False)
        if self.app_state.loaded_current_index2 != -1 and 0 <= self.app_state.loaded_current_index2 < len(self.app_state.image_list2):
            self.app_state.current_index2 = self.app_state.loaded_current_index2
            print(f'DEBUG: Setting current image 2 to loaded index {self.app_state.loaded_current_index2}.')
            self.set_current_image(2, trigger_update=False)
        elif self.app_state.image_list2:
            self.app_state.current_index2 = 0
            print('DEBUG: Setting current image 2 to default index 0.')
            self.set_current_image(2, trigger_update=False)
        self.app.ui_logic.update_file_names()
        self.app._update_resolution_labels()
        self.app.update_minimum_window_size()
        print('DEBUG: Initial app display setup complete. Triggering first comparison update.')
        self.app.event_handler._exit_interactive_mode_if_settled(force_redraw=True)

    def load_images_from_dialog(self, image_number: int):
        dialog_title = tr(f'Select Image(s) {image_number}', self.app_state.current_language)
        file_filter = f"{tr('Image Files', self.app_state.current_language)} (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;{tr('All Files', self.app_state.current_language)} (*)"
        file_names, _ = QFileDialog.getOpenFileNames(self.app, dialog_title, '', file_filter)
        if file_names:
            print(f'DEBUG: Loading images from dialog for slot {image_number}: {file_names}')
            QTimer.singleShot(0, lambda: self.load_images_from_paths(file_names, image_number))
        else:
            print(f'DEBUG: Image loading dialog for slot {image_number} cancelled.')

    def load_images_from_paths(self, file_paths: list[str], image_number: int, trigger_update: bool=True):
        print(f'DEBUG: Attempting to load {len(file_paths)} images for slot {image_number} (trigger_update={trigger_update}).')
        target_list_ref = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        loaded_count, newly_added_indices, load_errors = (0, [], [])
        current_paths_in_list = {entry[1] for entry in target_list_ref if len(entry) > 1 and entry[1]}
        target_selection_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2
        if not 0 <= target_selection_index < len(target_list_ref):
            target_selection_index = -1
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
                found_index = next((idx for idx, item_data in enumerate(target_list_ref) if isinstance(item_data, tuple) and len(item_data) > 1 and (item_data[1] == normalized_path)), -1)
                if found_index != -1:
                    target_selection_index = found_index
                continue
            try:
                if not os.path.isfile(normalized_path):
                    raise FileNotFoundError(f'File not found: {normalized_path}')
                with Image.open(normalized_path) as img:
                    if not (hasattr(img, 'copy') and hasattr(img, 'mode') and hasattr(img, 'size')):
                        raise TypeError(f'Unexpected type for image file: {type(img)}')
                    temp_image = img.copy()
                    temp_image.load()
                base_filename = os.path.basename(normalized_path)
                display_name = os.path.splitext(base_filename)[0]
                list_to_append_to = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
                list_to_append_to.append((temp_image, normalized_path, display_name))
                current_paths_in_list.add(normalized_path)
                newly_added_indices.append(len(list_to_append_to) - 1)
                loaded_count += 1
                target_selection_index = newly_added_indices[-1]
            except FileNotFoundError:
                load_errors.append(f"{original_path_for_display}: {tr('File not found or inaccessible.', self.app_state.current_language)}")
            except Image.UnidentifiedImageError:
                load_errors.append(f"{original_path_for_display}: {tr('Cannot identify image file (unsupported format?).', self.app_state.current_language)}")
            except (OSError, IOError, MemoryError, TypeError, ValueError) as e:
                load_errors.append(f'{original_path_for_display}: {type(e).__name__}: {str(e)[:100]}')
            except Exception as e:
                load_errors.append(f'{original_path_for_display}: Unexpected {type(e).__name__}: {str(e)[:100]}')
        target_list_ref_after_load = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        if loaded_count > 0 or (target_selection_index != (self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2) and target_selection_index != -1):
            final_index_to_set = -1
            current_target_list_len = len(target_list_ref_after_load)
            if 0 <= target_selection_index < current_target_list_len:
                final_index_to_set = target_selection_index
            elif newly_added_indices:
                final_index_to_set = newly_added_indices[-1]
            elif current_target_list_len > 0:
                final_index_to_set = 0
            if final_index_to_set != -1:
                if image_number == 1:
                    self.app_state.current_index1 = final_index_to_set
                else:
                    self.app_state.current_index2 = final_index_to_set
            elif image_number == 1:
                self.app_state.current_index1 = -1
            else:
                self.app_state.current_index2 = -1
            self.app._update_combobox(image_number)
            self.set_current_image(image_number, trigger_update=trigger_update)
        elif not target_list_ref_after_load:
            if image_number == 1:
                self.app_state.current_index1 = -1
            else:
                self.app_state.current_index2 = -1
            self.set_current_image(image_number, trigger_update=trigger_update)
        if load_errors:
            QMessageBox.warning(self.app, tr('Error Loading Images', self.app_state.current_language), tr('Some images could not be loaded:', self.app_state.current_language) + '\n\n - ' + '\n - '.join(load_errors))

    def set_current_image(self, image_number: int, trigger_update: bool=True):
        print(f'DEBUG: set_current_image called for slot {image_number} (trigger_update={trigger_update}).')
        target_list = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        current_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2
        edit_name_widget = self.app.edit_name1 if image_number == 1 else self.app.edit_name2
        new_pil_img, new_path, new_display_name_from_list = (None, None, None)
        if 0 <= current_index < len(target_list):
            try:
                img_data = target_list[current_index]
                if isinstance(img_data, tuple) and len(img_data) >= 3:
                    new_pil_img, new_path, new_display_name_from_list = img_data[:3]
                print(f'DEBUG: Setting image {image_number} from list index {current_index}. Path: {new_path}, Name (from list): "{new_display_name_from_list}"')
            except Exception as e:
                print(f'Error accessing image data for slot {image_number} at index {current_index}: {e}')
        else:
            print(f'DEBUG: No valid image selected for slot {image_number} (index {current_index}). Clearing.')
        self.app_state.set_current_image_data(image_number, new_pil_img, new_path, new_display_name_from_list)
        temp_image1_to_process, temp_image2_to_process = (self.app_state.original_image1, self.app_state.original_image2)
        if temp_image1_to_process or temp_image2_to_process:
            print('DEBUG: Resizing original images for display (main content) for app_state.imageX.')
            processed1, processed2 = resize_images_processor(temp_image1_to_process, temp_image2_to_process, self.app_state.interpolation_method)
            self.app_state.image1 = processed1.copy() if processed1 else None
            self.app_state.image2 = processed2.copy() if processed2 else None
            print(f"DEBUG: Processed main images sizes (app_state.imageX): Image1: {(processed1.size if processed1 else 'None')}, Image2: {(processed2.size if processed2 else 'None')}")
        else:
            self.app_state.image1, self.app_state.image2 = (None, None)
        if self.app_state.original_image1 and self.app_state.original_image2:
            if self.app_state.showing_single_image_mode != 0:
                self.app_state.showing_single_image_mode = 0
                print('DEBUG (set_current_image): Both images now loaded, switching from single image mode to comparison mode.')
        elif self.app_state.original_image1:
            if self.app_state.showing_single_image_mode != 1:
                self.app_state.showing_single_image_mode = 1
                print('DEBUG (set_current_image): Only image 1 loaded, switching to single image mode 1.')
        elif self.app_state.original_image2:
            if self.app_state.showing_single_image_mode != 2:
                self.app_state.showing_single_image_mode = 2
                print('DEBUG (set_current_image): Only image 2 loaded, switching to single image mode 2.')
        elif self.app_state.showing_single_image_mode != 0:
            self.app_state.showing_single_image_mode = 0
            print('DEBUG (set_current_image): No images loaded, ensuring single image mode is 0.')
        if edit_name_widget:
            edit_name_widget.blockSignals(True)
            edit_name_widget.setText(new_display_name_from_list if new_display_name_from_list is not None else '')
            edit_name_widget.blockSignals(False)
        self.app.ui_logic.update_file_names()
        self.app._update_resolution_labels()
        if trigger_update:
            self.app_state.resize_in_progress = False
            print(f'DEBUG: Requesting settled UI render from set_current_image for slot {image_number}. Current single_mode: {self.app_state.showing_single_image_mode}')
            self.app._request_settled_ui_render()

    def on_combobox_changed(self, image_number: int, combobox_index: int):
        print(f'DEBUG: on_combobox_changed called for slot {image_number}, index {combobox_index}.')
        target_list = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2
        current_internal_appstate_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2
        if 0 <= combobox_index < len(target_list):
            if combobox_index != current_internal_appstate_index:
                print(f'DEBUG: Combobox selection changed for slot {image_number} from {current_internal_appstate_index} to {combobox_index}.')
                if image_number == 1:
                    self.app_state.current_index1 = combobox_index
                else:
                    self.app_state.current_index2 = combobox_index
                self.set_current_image(image_number, trigger_update=True)
            else:
                print(f'DEBUG: Combobox selection for slot {image_number} unchanged (index {combobox_index}).')
        elif combobox_index == -1 and current_internal_appstate_index != -1:
            print(f'DEBUG: Combobox selection cleared for slot {image_number}. Previous index was {current_internal_appstate_index}.')
            if image_number == 1:
                self.app_state.current_index1 = -1
            else:
                self.app_state.current_index2 = -1
            self.set_current_image(image_number, trigger_update=True)
        else:
            print(f'DEBUG: Combobox change for slot {image_number} resulted in no action (index {combobox_index}, internal {current_internal_appstate_index}).')

    def swap_images(self):
        print('DEBUG: Swapping images.')
        self.app_state.swap_all_image_data()
        self.app._update_combobox(1)
        self.app._update_combobox(2)
        if hasattr(self.app, 'edit_name1') and hasattr(self.app, 'edit_name2'):
            name1_text = self.app_state.get_current_display_name(1)
            self.app.edit_name1.blockSignals(True)
            self.app.edit_name1.setText(name1_text)
            self.app.edit_name1.blockSignals(False)
            name2_text = self.app_state.get_current_display_name(2)
            self.app.edit_name2.blockSignals(True)
            self.app.edit_name2.setText(name2_text)
            self.app.edit_name2.blockSignals(False)
        self.app.ui_logic.update_file_names()
        self.app._update_resolution_labels()
        print('DEBUG: Requesting settled UI render after swap.')
        self.app._request_settled_ui_render()

    def clear_image_list(self, image_number: int):
        print(f'DEBUG: Clearing image list for slot {image_number}.')
        self.app_state.clear_image_slot_data(image_number)
        combobox_to_clear = self.app.combo_image1 if image_number == 1 else self.app.combo_image2
        edit_name_to_clear = self.app.edit_name1 if image_number == 1 else self.app.edit_name2
        if combobox_to_clear:
            combobox_to_clear.blockSignals(True)
            combobox_to_clear.clear()
            combobox_to_clear.blockSignals(False)
        if edit_name_to_clear:
            edit_name_to_clear.blockSignals(True)
            edit_name_to_clear.clear()
            edit_name_to_clear.blockSignals(False)
        if image_number == 1 and self.app_state.original_image2:
            self.app_state.showing_single_image_mode = 2
        elif image_number == 2 and self.app_state.original_image1:
            self.app_state.showing_single_image_mode = 1
        else:
            self.app_state.showing_single_image_mode = 0
        print(f'DEBUG (clear_image_list): Set showing_single_image_mode to {self.app_state.showing_single_image_mode}')
        print(f'DEBUG: Requesting settled UI render after clearing list {image_number}.')
        self.app._request_settled_ui_render()
        self.app.ui_logic.update_file_names()
        self.app.ui_logic.check_name_lengths()
        self.app._update_resolution_labels()

    def toggle_orientation(self, is_horizontal_checked: bool):
        print(f'DEBUG: toggle_orientation called. is_horizontal_checked={is_horizontal_checked}. Current app_state.is_horizontal={self.app_state.is_horizontal}')
        if is_horizontal_checked != self.app_state.is_horizontal:
            self.app_state.is_horizontal = is_horizontal_checked
            self.app_state.clear_split_cache()
            self.app_state.clear_magnifier_cache()
            print('DEBUG: Orientation changed. Clearing split and magnifier caches.')
            self.app.ui_logic.update_file_names()
            if self.app_state.showing_single_image_mode == 0:
                self.app._request_settled_ui_render()
        else:
            print('DEBUG: Orientation unchanged.')

    def toggle_magnifier(self, use_magnifier_checked: bool):
        if use_magnifier_checked == self.app_state.use_magnifier:
            return
        self.app_state.use_magnifier = use_magnifier_checked
        if not self.app_state.use_magnifier:
            self.app_state.pressed_keys.clear()
            if self.app_state.freeze_magnifier:
                if hasattr(self.app, 'freeze_button'):
                    self.app.freeze_button.blockSignals(True)
                    self.app.freeze_button.setChecked(False)
                    self.app.freeze_button.blockSignals(False)
        else:
            self.app_state.magnifier_offset_relative_visual = QPointF(self.app_state.magnifier_offset_relative)
            self.app_state.magnifier_spacing_relative_visual = self.app_state.magnifier_spacing_relative
        self.app_state.clear_magnifier_cache()
        if self.app_state.showing_single_image_mode == 0:
            self.app._request_settled_ui_render()

    def update_split_or_capture_position_only_state(self, cursor_pos_f: QPointF):
        label_width, label_height = self.app.get_current_label_dimensions()
        if self.app_state.pixmap_width <= 0 or self.app_state.pixmap_height <= 0:
            return
        label_rect = self.app.image_label.contentsRect()
        x_offset = max(0, (label_rect.width() - self.app_state.pixmap_width) // 2)
        y_offset = max(0, (label_rect.height() - self.app_state.pixmap_height) // 2)
        pixmap_x_f, pixmap_y_f = (cursor_pos_f.x() - label_rect.x() - x_offset, cursor_pos_f.y() - label_rect.y() - y_offset)
        pixmap_x_clamped = max(0.0, min(float(self.app_state.pixmap_width), pixmap_x_f))
        pixmap_y_clamped = max(0.0, min(float(self.app_state.pixmap_height), pixmap_y_f))
        rel_x = pixmap_x_clamped / float(self.app_state.pixmap_width) if self.app_state.pixmap_width > 0 else 0.5
        rel_y = pixmap_y_clamped / float(self.app_state.pixmap_height) if self.app_state.pixmap_height > 0 else 0.5
        rel_x, rel_y = (max(0.0, min(1.0, rel_x)), max(0.0, min(1.0, rel_y)))
        epsilon = 1e-06
        if not self.app_state.use_magnifier:
            new_split_pos = rel_x if not self.app_state.is_horizontal else rel_y
            if abs(self.app_state.split_position - new_split_pos) > epsilon:
                self.app_state.split_position = new_split_pos
                self.app_state.split_is_actively_lerping = True
        else:
            new_capture_pos, current_capture_pos = (QPointF(rel_x, rel_y), self.app_state.capture_position_relative)
            if abs(current_capture_pos.x() - new_capture_pos.x()) > epsilon or abs(current_capture_pos.y() - new_capture_pos.y()) > epsilon:
                self.app_state.capture_position_relative = new_capture_pos
                self.app_state.clear_magnifier_cache()

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        print(f'DEBUG: toggle_freeze_magnifier called with freeze_checked={freeze_checked}. Current app_state.freeze_magnifier={self.app_state.freeze_magnifier}')
        if not self.app_state.use_magnifier:
            if freeze_checked and hasattr(self.app, 'freeze_button'):
                self.app.freeze_button.blockSignals(True)
                self.app.freeze_button.setChecked(False)
                self.app.freeze_button.blockSignals(False)
            return
        if freeze_checked == self.app_state.freeze_magnifier:
            return
        if freeze_checked:
            print('DEBUG: Attempting to freeze magnifier.')
            if not self.app_state.image1 or self.app_state.image1.width == 0 or self.app_state.image1.height == 0:
                if hasattr(self.app, 'freeze_button'):
                    self.app.freeze_button.blockSignals(True)
                    self.app.freeze_button.setChecked(False)
                    self.app.freeze_button.blockSignals(False)
                return
            can_freeze = self.app_state.use_magnifier and self.app_state.original_image1 and self.app_state.original_image2 and self.app_state.image1 and (self.app_state.image1.width > 0) and (self.app_state.image1.height > 0) and (self.app_state.pixmap_width > 0) and (self.app_state.pixmap_height > 0)
            if can_freeze:
                try:
                    drawing_width, drawing_height = (self.app_state.image1.width, self.app_state.image1.height)
                    display_width, display_height = self.app.get_current_label_dimensions()
                    print(f'DEBUG: Freezing: Drawing dimensions: {drawing_width}x{drawing_height}, Display dimensions for context: {display_width}x{display_height}')
                    magnifier_coords = get_magnifier_drawing_coords(self.app_state, drawing_width, drawing_height, display_width, display_height)
                    if magnifier_coords and magnifier_coords[4] is not None:
                        magnifier_midpoint_drawing = magnifier_coords[4]
                        rel_x = max(0.0, min(1.0, float(magnifier_midpoint_drawing.x()) / float(drawing_width)))
                        rel_y = max(0.0, min(1.0, float(magnifier_midpoint_drawing.y()) / float(drawing_height)))
                        self.app_state.frozen_magnifier_position_relative = QPointF(rel_x, rel_y)
                        self.app_state.freeze_magnifier = True
                        self.app_state.magnifier_offset_relative_visual.setX(self.app_state.magnifier_offset_relative.x())
                        self.app_state.magnifier_offset_relative_visual.setY(self.app_state.magnifier_offset_relative.y())
                        self.app_state.magnifier_spacing_relative_visual = self.app_state.magnifier_spacing_relative
                        print(f'DEBUG: Magnifier frozen at relative position: {rel_x:.4f},{rel_y:.4f}')
                        if self.app.event_handler.movement_timer.isActive():
                            self.app.event_handler.movement_timer.stop()
                            print('DEBUG: Movement timer stopped after freezing.')
                    else:
                        self.app_state.freeze_magnifier = False
                except Exception as e:
                    print(f'[DEBUG] Error during freeze: {e}')
                    self.app_state.freeze_magnifier = False
                    traceback.print_exc()
            else:
                self.app_state.freeze_magnifier = False
            if not self.app_state.freeze_magnifier and hasattr(self.app, 'freeze_button') and self.app.freeze_button.isChecked():
                self.app.freeze_button.blockSignals(True)
                self.app.freeze_button.setChecked(False)
                self.app.freeze_button.blockSignals(False)
                print('DEBUG: Freeze failed, unchecking freeze button.')
        else:
            print('DEBUG: Unfreezing magnifier.')
            self.unfreeze_magnifier_logic()
        self.app_state.clear_magnifier_cache()
        print('DEBUG: Magnifier cache cleared after freeze/unfreeze toggle.')
        if self.app_state.showing_single_image_mode == 0:
            print('DEBUG: Requesting settled UI render after freeze/unfreeze toggle.')
            self.app._request_settled_ui_render()

    def unfreeze_magnifier_logic(self):
        print('DEBUG: unfreeze_magnifier_logic called.')
        if not self.app_state.freeze_magnifier:
            return
        frozen_pos_rel = self.app_state.frozen_magnifier_position_relative
        self.app_state.freeze_magnifier = False
        self.app_state.frozen_magnifier_position_relative = None
        print('DEBUG: Magnifier state set to unfrozen, frozen position cleared.')
        new_target_offset_rel = QPointF(AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
        if self.app_state.image1 is None:
            print('WARNING: Cannot unfreeze magnifier, app_state.image1 is not available. Using default offset.')
        else:
            drawing_width, drawing_height = self.app_state.image1.size
            if frozen_pos_rel and drawing_width > 0 and (drawing_height > 0):
                try:
                    effective_magnifier_drawing_size = max(1.0, AppConstants.DEFAULT_MAGNIFIER_SIZE_RELATIVE * min(drawing_width, drawing_height))
                    frozen_x_drawing_pix = frozen_pos_rel.x() * drawing_width
                    frozen_y_drawing_pix = frozen_pos_rel.y() * drawing_height
                    cap_center_drawing_pix_x = self.app_state.capture_position_relative.x() * drawing_width
                    cap_center_drawing_pix_y = self.app_state.capture_position_relative.y() * drawing_height
                    required_offset_drawing_pixels_x = frozen_x_drawing_pix - cap_center_drawing_pix_x
                    required_offset_drawing_pixels_y = frozen_y_drawing_pix - cap_center_drawing_pix_y
                    if effective_magnifier_drawing_size > 0:
                        required_offset_rel_x = required_offset_drawing_pixels_x / effective_magnifier_drawing_size
                        required_offset_rel_y = required_offset_drawing_pixels_y / effective_magnifier_drawing_size
                        new_target_offset_rel = QPointF(required_offset_rel_x, required_offset_rel_y)
                        print(f'DEBUG: Calculated new target offset relative: {new_target_offset_rel.x():.4f},{new_target_offset_rel.y():.4f}')
                    else:
                        print('WARNING: Effective magnifier drawing size is zero, defaulting offset on unfreeze.')
                        new_target_offset_rel = QPointF(AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
                except Exception as e:
                    print(f'[DEBUG] Error calculating offset on unfreeze: {e}')
                    new_target_offset_rel = QPointF(AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
                    traceback.print_exc()
            else:
                print('DEBUG: No valid frozen position or image dimensions to unfreeze magnifier to, defaulting offset.')
                new_target_offset_rel = QPointF(AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
        self.app_state.magnifier_offset_relative = new_target_offset_rel
        self.app_state.magnifier_offset_relative_visual.setX(self.app_state.magnifier_offset_relative.x())
        self.app_state.magnifier_offset_relative_visual.setY(self.app_state.magnifier_offset_relative.y())
        self.app_state.magnifier_spacing_relative_visual = self.app_state.magnifier_spacing_relative
        print(f'DEBUG: Magnifier offset/spacing visuals reset to target values for lerping.')
        self.app.event_handler._handle_interactive_movement_and_lerp()

    def on_slider_pressed(self, slider_name: str):
        print(f"DEBUG: Slider '{slider_name}' pressed.")
        self.app_state.is_dragging_any_slider = True
        if not self.app_state.is_interactive_mode:
            self.app.event_handler._enter_interactive_mode()

    def update_magnifier_size_relative(self, value_percent: int):
        new_relative_size = max(0.05, min(1.0, value_percent / 100.0))
        if abs(new_relative_size - self.app_state.magnifier_size_relative) > 1e-06:
            self.app_state.magnifier_size_relative = new_relative_size
            if hasattr(self.app, 'slider_size'):
                self.app.slider_size.setToolTip(f'{int(self.app_state.magnifier_size_relative * 100):.0f}%')
            self.app_state.clear_magnifier_cache()
            if self.app_state.is_interactive_mode:
                self.app.event_handler._request_interactive_update()
        else:
            pass

    def update_capture_size_relative(self, value_percent: int):
        new_relative_size = max(0.01, min(0.5, value_percent / 100.0))
        if abs(new_relative_size - self.app_state.capture_size_relative) > 1e-06:
            self.app_state.capture_size_relative = new_relative_size
            if hasattr(self.app, 'slider_capture'):
                self.app.slider_capture.setToolTip(f'{int(self.app_state.capture_size_relative * 100):.0f}%')
            self.app_state.clear_magnifier_cache()
            if self.app_state.is_interactive_mode:
                self.app.event_handler._request_interactive_update()
        else:
            pass

    def update_movement_speed(self, value_slider: int):
        new_speed = max(0.1, min(5.0, value_slider / 10.0))
        if abs(new_speed - self.app_state.movement_speed_per_sec) > 1e-06:
            self.app_state.movement_speed_per_sec = new_speed
            if hasattr(self.app, 'slider_speed'):
                self.app.slider_speed.setToolTip(f"{self.app_state.movement_speed_per_sec:.1f} {tr('rel. units/sec', self.app_state.current_language)}")
        else:
            pass

    def on_interpolation_changed(self, combobox_index: int):
        print(f'DEBUG: on_interpolation_changed received index {combobox_index}. Deferring processing.')
        QTimer.singleShot(0, lambda: self._handle_interpolation_change_deferred(combobox_index))

    def _handle_interpolation_change_deferred(self, combobox_index: int):
        try:
            print(f'DEBUG: _handle_interpolation_change_deferred ENTER. Index: {combobox_index}')
            if not hasattr(self.app, 'combo_interpolation') or combobox_index < 0 or combobox_index >= self.app.combo_interpolation.count():
                print(f'DEBUG: _handle_interpolation_change_deferred: Index {combobox_index} out of bounds or combo_interpolation not found. Returning.')
                return
            user_data_index = self.app.combo_interpolation.itemData(combobox_index)
            new_method_internal_key = AppConstants.DEFAULT_INTERPOLATION_METHOD
            selected_display_text_key_for_log = 'Unknown Display Key'
            method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
            if isinstance(user_data_index, int) and 0 <= user_data_index < len(method_keys):
                new_method_internal_key = method_keys[user_data_index]
                selected_display_text_key_for_log = AppConstants.INTERPOLATION_METHODS_MAP.get(new_method_internal_key, 'Unknown Key')
            else:
                print(f'ERROR: userData for combobox_index {combobox_index} is not a valid int index: {user_data_index}. Defaulting to {new_method_internal_key}.')
                current_text = self.app.combo_interpolation.itemText(combobox_index)
                for k, v in AppConstants.INTERPOLATION_METHODS_MAP.items():
                    if tr(v, self.app_state.current_language) == current_text:
                        new_method_internal_key = k
                        selected_display_text_key_for_log = v
                        break
            print(f"DEBUG: Interpolation method selected (via userData index {user_data_index}): DisplayKey='{selected_display_text_key_for_log}', InternalKey='{new_method_internal_key}'")
            if new_method_internal_key == self.app_state.interpolation_method:
                return
            self.app_state.interpolation_method = new_method_internal_key
            if self.app_state.original_image1 or self.app_state.original_image2:
                print(f'DEBUG: Re-processing main images with new interpolation method: {self.app_state.interpolation_method}')
                full_res_processed1, full_res_processed2 = resize_images_processor(self.app_state.original_image1, self.app_state.original_image2, self.app_state.interpolation_method)
                self.app_state.image1, self.app_state.image2 = (full_res_processed1, full_res_processed2)
            self.app_state.clear_split_cache()
            self.app_state.clear_magnifier_cache()
            print('DEBUG: Caches cleared after interpolation method change. Requesting settled UI render.')
            self.app._request_settled_ui_render()
        except Exception as e_outer:
            print(f'CRITICAL ERROR in _handle_interpolation_change_deferred (outer catch block): {e_outer}')
            print(traceback.format_exc())

    def on_edit_name_changed(self, sender_line_edit):
        print(f"DEBUG: on_edit_name_changed (editingFinished) by {(sender_line_edit.objectName() if hasattr(sender_line_edit, 'objectName') else 'unknown')}.")
        image_number, target_list_ref, current_index, combobox = (0, None, -1, None)
        if sender_line_edit == self.app.edit_name1:
            image_number, target_list_ref, current_index, combobox = (1, self.app_state.image_list1, self.app_state.current_index1, self.app.combo_image1)
        elif sender_line_edit == self.app.edit_name2:
            image_number, target_list_ref, current_index, combobox = (2, self.app_state.image_list2, self.app_state.current_index2, self.app.combo_image2)
        else:
            return
        if 0 <= current_index < len(target_list_ref):
            new_name_for_state = sender_line_edit.text().strip()
            try:
                old_img, old_path, old_name_in_state = target_list_ref[current_index]
                if new_name_for_state != old_name_in_state:
                    target_list_ref[current_index] = (old_img, old_path, new_name_for_state)
                    if combobox:
                        self.app._update_single_combobox_item_text(combobox, current_index, new_name_for_state)
                    if sender_line_edit.text() != new_name_for_state:
                        sender_line_edit.blockSignals(True)
                        sender_line_edit.setText(new_name_for_state)
                        sender_line_edit.blockSignals(False)
                    self.app.ui_logic.update_file_names()
                    if self.app_state.include_file_names_in_saved and self.app_state.showing_single_image_mode == 0:
                        print('DEBUG: on_edit_name_changed (editingFinished): Requesting settled UI render.')
                        self.app._request_settled_ui_render()
            except Exception as e:
                print(f'[DEBUG] Error updating name in on_edit_name_changed: {e}')
                traceback.print_exc()
        else:
            print('DEBUG: on_edit_name_changed: No valid image selected, nothing to update name for.')

    def trigger_live_name_or_font_update(self):
        print(f"DEBUG: trigger_live_name_or_font_update called. Include_filenames: {hasattr(self.app, 'checkbox_file_names') and self.app.checkbox_file_names.isChecked()}")
        if hasattr(self.app, 'checkbox_file_names') and self.app.checkbox_file_names.isChecked():
            if self.app_state.original_image1 and self.app_state.original_image2 and (self.app_state.showing_single_image_mode == 0):
                if not self.app_state.is_interactive_mode:
                    print('DEBUG: Entering interactive mode from trigger_live_name_or_font_update for filename update.')
                    self.app.event_handler._enter_interactive_mode()
                self.app.event_handler._request_interactive_update()
        else:
            pass
        self.app.ui_logic.update_file_names()

    def activate_single_image_mode(self, image_number: int):
        print(f'DEBUG: activate_single_image_mode called for image {image_number}.')
        original_img_to_check = self.app_state.original_image1 if image_number == 1 else self.app_state.original_image2
        pil_to_display = self.app_state.image1 if image_number == 1 else self.app_state.image2
        if original_img_to_check is None:
            if self.app_state.showing_single_image_mode != 0:
                self.deactivate_single_image_mode()
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
                self.deactivate_single_image_mode()
            return
        self.app_state.showing_single_image_mode = image_number
        print(f'DEBUG: Single image mode set to {image_number}.')
        if self.app.event_handler.movement_timer.isActive():
            self.app.event_handler.movement_timer.stop()
        if self.app.event_handler.interactive_update_timer.isActive():
            self.app.event_handler.interactive_update_timer.stop()
        self.app.event_handler.pending_interactive_update = False
        self.app_state.is_interactive_mode = False
        self.app_state.pressed_keys.clear()
        self.app._display_single_image_on_label(pil_to_display)

    def deactivate_single_image_mode(self):
        print('DEBUG: deactivate_single_image_mode called.')
        if self.app_state.showing_single_image_mode == 0:
            return
        self.app_state.showing_single_image_mode = 0
        print('DEBUG: Requesting settled UI render to restore comparison view.')
        self.app._request_settled_ui_render()

    def change_language(self, language_code: str):
        print(f'DEBUG: change_language called. New language: {language_code}. Current: {self.app_state.current_language}')
        valid_languages = ['en', 'ru', 'zh', 'pt_BR']
        if language_code not in valid_languages:
            language_code = 'en'
            print('DEBUG: Invalid language code. Falling back to English.')
        if language_code == self.app_state.current_language:
            return
        self.app_state.current_language = language_code
        self.app.ui_logic.update_translations()
        self.app.ui_logic.update_file_names()
        self.app.settings_manager._save_setting('language', language_code)
        print(f'DEBUG: Language changed to {language_code}. UI translations and file names updated.')
        if hasattr(self.app, 'length_warning_label'):
            self.app.ui_logic.check_name_lengths()
        if hasattr(self.app, 'help_button'):
            self.app.help_button.setToolTip(tr('Show Help', self.app_state.current_language))
        if hasattr(self.app, 'slider_speed'):
            self.app.slider_speed.setToolTip(f"{self.app_state.movement_speed_per_sec:.1f} {tr('rel. units/sec', self.app_state.current_language)}")
        if hasattr(self.app, 'btn_settings'):
            self.app.btn_settings.setToolTip(tr('Settings dialog module not found.', self.app_state.current_language) if not self.app.settings_dialog_available else tr('Open Application Settings', self.app_state.current_language))
        self.app._update_color_button_tooltip()
        if self.app_state.include_file_names_in_saved and self.app_state.showing_single_image_mode == 0:
            print('DEBUG: File names included, requesting settled UI render after language change.')
            self.app._request_settled_ui_render()

    def apply_font_size_change(self, font_size_percent: int):
        if self.app_state.font_size_percent != font_size_percent:
            self.app_state.font_size_percent = font_size_percent
            self.trigger_live_name_or_font_update()
        else:
            pass

    def apply_filename_color_change(self, color: QColor):
        print(f'DEBUG: Filename color change to {color.name(QColor.NameFormat.HexArgb)}. Current: {self.app_state.file_name_color.name(QColor.NameFormat.HexArgb)}')
        if color.isValid() and color != self.app_state.file_name_color:
            self.app_state.file_name_color = color
            self.app._update_color_button_tooltip()
            self.app.settings_manager._save_setting('filename_color', self.app_state.file_name_color.name(QColor.NameFormat.HexArgb))
            if self.app_state.include_file_names_in_saved and self.app_state.showing_single_image_mode == 0:
                print('DEBUG: File names included, requesting settled UI render after color change.')
                self.app._request_settled_ui_render()
        else:
            print('DEBUG: Filename color not changed (invalid or same color).')

    def toggle_include_filenames_in_saved(self, include_checked: bool):
        if self.app_state.include_file_names_in_saved != include_checked:
            self.app_state.include_file_names_in_saved = include_checked
            self.app.ui_logic.check_name_lengths()
            if self.app_state.showing_single_image_mode == 0:
                self.app._apply_panel_visibility()
                self.app.event_handler._enter_interactive_mode()
            else:
                self.app._apply_panel_visibility()
        else:
            pass

    def on_slider_magnifier_size_released(self):
        print('DEBUG: Magnifier size slider released. Saving setting.')
        self.app.settings_manager._save_setting('magnifier_size_relative', self.app_state.magnifier_size_relative)
        self.app_state.is_dragging_any_slider = False
        self.app.event_handler._exit_interactive_mode_if_settled(force_redraw=True)

    def on_slider_capture_size_released(self):
        print('DEBUG: Capture size slider released. Saving setting.')
        self.app.settings_manager._save_setting('capture_size_relative', self.app_state.capture_size_relative)
        self.app_state.is_dragging_any_slider = False
        self.app.event_handler._exit_interactive_mode_if_settled(force_redraw=True)

    def on_slider_movement_speed_released(self):
        print('DEBUG: Movement speed slider released. Saving setting.')
        self.app.settings_manager._save_setting('movement_speed_per_sec', self.app_state.movement_speed_per_sec)
        self.app_state.is_dragging_any_slider = False
        self.app.event_handler._exit_interactive_mode_if_settled(force_redraw=False)

    def on_slider_font_size_released(self):
        print('DEBUG: Font size slider released. Saving setting.')
        self.app.settings_manager._save_setting('font_size_percent', self.app_state.font_size_percent)
        self.app_state.is_dragging_any_slider = False
        if hasattr(self.app, 'checkbox_file_names') and self.app.checkbox_file_names.isChecked():
            self.app.event_handler._exit_interactive_mode_if_settled(force_redraw=True)
        else:
            self.app.event_handler._exit_interactive_mode_if_settled(force_redraw=False)