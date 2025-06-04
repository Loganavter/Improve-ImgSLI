import os
import traceback
import time
from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtCore import QPoint, QPointF
from typing import Tuple
from processing_services.image_drawing import create_base_split_image_pil, draw_all_overlays_on_base_image_pil

def save_result_processor(app_instance_for_ui_dialogs, image1_processed: Image.Image, image2_processed: Image.Image, split_position_target: float, is_horizontal: bool, use_magnifier: bool, show_capture_area_on_main_image: bool, capture_position_relative: QPointF, original_image1: Image.Image, original_image2: Image.Image, magnifier_drawing_coords: Tuple[QPoint, QPoint, int, int, QPoint, int, int] | Tuple[None, ...], include_file_names: bool, font_path_absolute: str, font_size_percent: int, max_name_length: int, file_name1_text: str, file_name2_text: str, file_name_color_rgb: tuple, jpeg_quality: int, interpolation_method: str):
    _DEBUG_TIMER_START = time.perf_counter()
    file_name = None
    try:
        if not image1_processed or not image2_processed:
            QMessageBox.warning(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Warning', app_instance_for_ui_dialogs.app_state.current_language), app_instance_for_ui_dialogs.tr('Resized images not available. Cannot save result. Please reload or select images.', app_instance_for_ui_dialogs.app_state.current_language))
            return
        if image1_processed.size != image2_processed.size:
            QMessageBox.warning(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Error', app_instance_for_ui_dialogs.app_state.current_language), app_instance_for_ui_dialogs.tr('Resized images not available or sizes mismatch. Cannot save result. Please reload or select images.', app_instance_for_ui_dialogs.app_state.current_language))
            return
        create_base_start = time.perf_counter()
        base_image_for_save = create_base_split_image_pil(image1_processed, image2_processed, split_position_target, is_horizontal)
        print(f'_DEBUG_TIMER_: save_result: create_base_split_image_pil took {(time.perf_counter() - create_base_start) * 1000:.2f} ms')
        if base_image_for_save is None:
            QMessageBox.critical(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Error', app_instance_for_ui_dialogs.app_state.current_language), app_instance_for_ui_dialogs.tr('Failed to create the base image for saving.', app_instance_for_ui_dialogs.app_state.current_language))
            return
        draw_overlays_start = time.perf_counter()
        image_to_save = draw_all_overlays_on_base_image_pil(base_image=base_image_for_save, app_state=app_instance_for_ui_dialogs.app_state, split_position_visual=split_position_target, is_horizontal=is_horizontal, use_magnifier=use_magnifier, show_capture_area_on_main_image=show_capture_area_on_main_image, capture_position_relative=capture_position_relative, original_image1=original_image1, original_image2=original_image2, magnifier_drawing_coords=magnifier_drawing_coords, include_file_names=include_file_names, font_path_absolute=font_path_absolute, font_size_percent=font_size_percent, max_name_length=max_name_length, file_name1_text=file_name1_text, file_name2_text=file_name2_text, file_name_color_rgb=file_name_color_rgb, interpolation_method=interpolation_method)
        print(f'_DEBUG_TIMER_: save_result: draw_all_overlays_on_base_image_pil took {(time.perf_counter() - draw_overlays_start) * 1000:.2f} ms')
        if image_to_save is None:
            QMessageBox.critical(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Error', app_instance_for_ui_dialogs.app_state.current_language), app_instance_for_ui_dialogs.tr('Failed to create the base image for saving.', app_instance_for_ui_dialogs.app_state.current_language))
            return
        dialog_open_start = time.perf_counter()
        file_name, selected_filter = QFileDialog.getSaveFileName(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Save Image', app_instance_for_ui_dialogs.app_state.current_language), '', app_instance_for_ui_dialogs.tr('PNG Files', app_instance_for_ui_dialogs.app_state.current_language) + ' (*.png);;' + app_instance_for_ui_dialogs.tr('JPEG Files', app_instance_for_ui_dialogs.app_state.current_language) + ' (*.jpg *.jpeg);;' + app_instance_for_ui_dialogs.tr('All Files', app_instance_for_ui_dialogs.app_state.current_language) + ' (*)')
        print(f'_DEBUG_TIMER_: save_result: QFileDialog took {(time.perf_counter() - dialog_open_start) * 1000:.2f} ms')
        if not file_name:
            return
        _, ext = os.path.splitext(file_name)
        if not ext:
            if 'PNG' in selected_filter:
                ext = '.png'
            elif 'JPEG' in selected_filter:
                ext = '.jpg'
            else:
                ext = '.png'
            file_name = file_name + ext
        save_file_start = time.perf_counter()
        if ext.lower() in ['.jpg', '.jpeg']:
            rgb_image = Image.new('RGB', image_to_save.size, (0, 0, 0))
            rgb_image.paste(image_to_save, mask=image_to_save.split()[3])
            try:
                rgb_image.save(file_name, quality=jpeg_quality)
            except Exception as e_save:
                print(f'Error saving JPEG: {e_save}')
                QMessageBox.critical(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Error', app_instance_for_ui_dialogs.app_state.current_language), app_instance_for_ui_dialogs.tr('Failed to save image: {}', app_instance_for_ui_dialogs.app_state.current_language).format(str(e_save)))
        else:
            try:
                image_to_save.save(file_name)
            except Exception as e_save:
                print(f'Error saving image: {e_save}')
                QMessageBox.critical(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Error', app_instance_for_ui_dialogs.app_state.current_language), app_instance_for_ui_dialogs.tr('Failed to save image: {}', app_instance_for_ui_dialogs.app_state.current_language).format(str(e_save)))
        print(f'_DEBUG_TIMER_: File save operation took {(time.perf_counter() - save_file_start) * 1000:.2f} ms')
    except Exception as e:
        print(f'Error in save_result_processor: {e}')
        traceback.print_exc()
        if file_name:
            try:
                if os.path.exists(file_name):
                    os.remove(file_name)
            except:
                pass
        QMessageBox.critical(app_instance_for_ui_dialogs, app_instance_for_ui_dialogs.tr('Error', app_instance_for_ui_dialogs.app_state.current_language), app_instance_for_ui_dialogs.tr('An unexpected error occurred during the save process:', app_instance_for_ui_dialogs.app_state.current_language) + f'\n{str(e)}')
    print(f'_DEBUG_TIMER_: save_result_processor total took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')