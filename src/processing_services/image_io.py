import os
import traceback
from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QMessageBox
import logging
from processing_services.image_drawing import generate_comparison_image_with_canvas

logger = logging.getLogger("ImproveImgSLI")

def save_result_processor(
    app_instance_for_ui_dialogs,
    app_state,
    image1_processed,
    image2_processed,
    original_image1,
    original_image2,
    magnifier_drawing_coords,
    font_path_absolute,
    file_name1_text,
    file_name2_text,
    jpeg_quality
):
    tr = app_instance_for_ui_dialogs.tr

    if not image1_processed or not image2_processed:
        QMessageBox.warning(app_instance_for_ui_dialogs, tr('Warning', app_state.current_language), tr(
            'Resized images not available. Cannot save result. Please reload or select images.', app_state.current_language))
        return
    if image1_processed.size != image2_processed.size:
        QMessageBox.warning(app_instance_for_ui_dialogs, tr('Error', app_state.current_language), tr(
            'Resized images not available or sizes mismatch. Cannot save result. Please reload or select images.', app_state.current_language))
        return
    app_state.is_interactive_mode = False

    image_to_save, _, _ = generate_comparison_image_with_canvas(
        app_state=app_state,
        image1_scaled=image1_processed,
        image2_scaled=image2_processed,
        original_image1=original_image1,
        original_image2=original_image2,
        magnifier_drawing_coords=magnifier_drawing_coords,
        font_path_absolute=font_path_absolute,
        file_name1_text=file_name1_text,
        file_name2_text=file_name2_text
    )

    if image_to_save is None:
        QMessageBox.critical(
            app_instance_for_ui_dialogs, tr(
                'Error', app_state.current_language), tr(
                'Failed to create the base image for saving.', app_state.current_language))
        return

    file_name, selected_filter = QFileDialog.getSaveFileName(
        app_instance_for_ui_dialogs, tr(
            'Save Image', app_state.current_language), '', f"{
            tr(
                'PNG Files', app_state.current_language)} (*.png);;{
                    tr(
                        'JPEG Files', app_state.current_language)} (*.jpg *.jpeg);;{
                            tr(
                                'All Files', app_state.current_language)} (*)")

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
        file_name += ext

    try:
        if ext.lower() in ['.jpg', '.jpeg']:
            rgb_image = Image.new('RGB', image_to_save.size, (0, 0, 0))
            if image_to_save.mode == 'RGBA':
                rgb_image.paste(image_to_save, mask=image_to_save.split()[3])
            else:
                rgb_image.paste(image_to_save)
            rgb_image.save(file_name, quality=jpeg_quality)
        else:
            image_to_save.save(file_name)

    except Exception as e:
        logger.error(f'Error in save_result_processor: {e}')
        traceback.print_exc()
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
            except Exception:
                pass
        QMessageBox.critical(app_instance_for_ui_dialogs,
                             tr('Error',
                                app_state.current_language),
                             f"{tr('An unexpected error occurred during the save process:',
                                   app_state.current_language)}\n{str(e)}")