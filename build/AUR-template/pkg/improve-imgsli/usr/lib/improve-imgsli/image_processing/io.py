import logging
import os
import traceback

from PIL import Image
from PyQt6.QtWidgets import QMessageBox

from image_processing.composer import ImageComposer

logger = logging.getLogger("ImproveImgSLI")

def save_result_processor(
    app_instance_for_ui_dialogs,
    app_state,
    image1_processed,
    image2_processed,
    original_image1,
    original_image2,
    magnifier_drawing_coords,
    font_path_absolute: str | None,
    file_name1_text,
    file_name2_text,
    jpeg_quality,
):
    tr = app_instance_for_ui_dialogs.tr

    if not image1_processed or not image2_processed:
        QMessageBox.warning(
            app_instance_for_ui_dialogs,
            tr("Warning", app_state.current_language),
            tr(
                "Resized images not available. Cannot save result. Please reload or select images.",
                app_state.current_language,
            ),
        )
        return
    if image1_processed.size != image2_processed.size:
        QMessageBox.warning(
            app_instance_for_ui_dialogs,
            tr("Error", app_state.current_language),
            tr(
                "Resized images not available or sizes mismatch. Cannot save result. Please reload or select images.",
                app_state.current_language,
            ),
        )
        return
    app_state.is_interactive_mode = False

    composer = ImageComposer(font_path_absolute)
    image_to_save, *_ = composer.generate_comparison_image(
        app_state=app_state,
        image1_scaled=image1_processed,
        image2_scaled=image2_processed,
        original_image1=original_image1,
        original_image2=original_image2,
        magnifier_drawing_coords=magnifier_drawing_coords,
        font_path_absolute=font_path_absolute,
        file_name1_text=file_name1_text,
        file_name2_text=file_name2_text,
    )

    if image_to_save is None:
        QMessageBox.critical(
            app_instance_for_ui_dialogs,
            tr("Error", app_state.current_language),
            tr(
                "Failed to create the base image for saving.",
                app_state.current_language,
            ),
        )
        return

    target_dir = getattr(app_state, "export_default_dir", None)
    target_name = getattr(app_state, "export_last_filename", None)
    target_fmt = (getattr(app_state, "export_last_format", "PNG") or "PNG").upper()
    file_name = None
    if target_dir and target_name:
        try:
            os.makedirs(target_dir, exist_ok=True)
            ext = ".png" if target_fmt == "PNG" else ".jpg" if target_fmt in ("JPG", "JPEG") else f".{target_fmt.lower()}"
            file_name = os.path.join(target_dir, f"{target_name}{ext}")
        except Exception:
            file_name = None
    if not file_name:

        return

    try:
        if ext.lower() in [".jpg", ".jpeg"]:
            rgb_image = Image.new("RGB", image_to_save.size, (0, 0, 0))
            if image_to_save.mode == "RGBA":
                rgb_image.paste(image_to_save, mask=image_to_save.split()[3])
            else:
                rgb_image.paste(image_to_save)
            rgb_image.save(file_name, quality=jpeg_quality)
        else:
            image_to_save.save(file_name)

    except Exception as e:
        traceback.print_exc()
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
            except Exception:
                pass
        QMessageBox.critical(
            app_instance_for_ui_dialogs,
            tr("Error", app_state.current_language),
            f"{
                tr(
                    'An unexpected error occurred during the save process:',
                    app_state.current_language,
                )
            }\n{str(e)}",
        )
