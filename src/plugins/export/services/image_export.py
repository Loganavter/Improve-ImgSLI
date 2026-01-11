import logging
import os
import threading
from typing import Optional, Tuple, Any

import PIL.Image
from PIL import Image
from PyQt6.QtGui import QColor

from core.store import Store
from core.constants import AppConstants
from shared.image_processing.pipeline import RenderingPipeline, create_render_context_from_store
from shared.image_processing.resize import resize_images_processor
from utils.resource_loader import get_magnifier_drawing_coords
from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

try:
    import imagecodecs
    import numpy as np
    JXL_SUPPORTED = True
    logger.info("JXL export support: imagecodecs imported successfully")
except ImportError as e:
    JXL_SUPPORTED = False
    logger.warning(f"JXL export support: imagecodecs import failed - {e}")

class ExportService:

    def __init__(self, font_path_absolute: str):
        self.font_path_absolute = font_path_absolute

    def export_image(
        self,
        store: Store,
        original_image1: Image.Image,
        original_image2: Image.Image,
        export_options: dict,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Any] = None,
    ) -> str:
        """
        Экспортирует изображение сравнения в файл.
        """
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Export canceled by user")

        if not original_image1 or not original_image2:
            raise ValueError("Full resolution images are not available for saving.")
        if not export_options.get("output_dir") or not export_options.get("file_name"):
            raise ValueError("Output directory or file name not specified.")

        if progress_callback:
            progress_callback(10)

        image1_for_save, image2_for_save = resize_images_processor(
            original_image1, original_image2
        )
        if not image1_for_save or not image2_for_save:
            raise ValueError("Failed to unify images for saving.")

        store.viewport.image1 = image1_for_save
        store.viewport.image2 = image2_for_save

        save_width, save_height = image1_for_save.size

        magnifier_coords = None
        if store.viewport.use_magnifier:
            magnifier_coords = get_magnifier_drawing_coords(
                store=store,
                drawing_width=save_width,
                drawing_height=save_height,
                container_width=save_width,
                container_height=save_height,
            )

        if progress_callback:
            progress_callback(30)

        ctx = create_render_context_from_store(
            store=store,
            width=save_width,
            height=save_height,
            magnifier_drawing_coords=magnifier_coords,
            image1_scaled=image1_for_save,
            image2_scaled=image2_for_save
        )

        ctx.is_interactive_mode = False
        ctx.file_name1 = self._get_current_display_name(store, 1)
        ctx.file_name2 = self._get_current_display_name(store, 2)

        from toolkit.managers.font_manager import FontManager
        font_path = FontManager.get_instance().get_font_path_for_image_text(store)
        pipeline = RenderingPipeline(font_path)
        final_img, _, _, _, _, _ = pipeline.render_frame(ctx)

        if final_img is None:
            raise ValueError("Failed to create the base image for saving.")

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Export canceled by user")

        if progress_callback:
            progress_callback(50)

        img_to_save = final_img
        if export_options.get("fill_background", False):
            bg_color_tuple = export_options.get("background_color")
            if bg_color_tuple:
                bg = Image.new("RGBA", final_img.size, bg_color_tuple)
                bg.paste(
                    final_img,
                    mask=final_img.split()[3] if final_img.mode == "RGBA" else None,
                )
                img_to_save = bg

        target_format = export_options.get("format", "PNG").upper()
        pil_format = "JPEG" if target_format == "JPG" else target_format
        output_dir = export_options["output_dir"]
        base_name = export_options["file_name"]
        is_quick_save = export_options.get("is_quick_save", False)
        ext = f".{target_format.lower().replace('jpeg', 'jpg')}"

        if is_quick_save:
            full_path = self._generate_unique_filepath(output_dir, base_name, ext)
        else:
            full_path = os.path.join(output_dir, f"{base_name}{ext}")

        os.makedirs(output_dir, exist_ok=True)

        save_kwargs = {}
        formats_with_alpha = {"PNG", "TIFF", "WEBP", "JXL"}
        if pil_format not in formats_with_alpha and img_to_save.mode == "RGBA":
            bg_color_tuple = export_options.get("background_color") or (255, 255, 255, 255)
            bg_flat = Image.new("RGBA", img_to_save.size, bg_color_tuple)
            bg_flat.paste(img_to_save, mask=img_to_save.split()[3])
            img_to_save = bg_flat.convert("RGB")

        if pil_format == "JPEG":
            save_kwargs["quality"] = int(export_options.get("quality", 95))
            try:
                comment_text = (export_options.get("comment_text") or "").strip()
                if comment_text and bool(export_options.get("include_metadata", True)):
                    exif = img_to_save.getexif()
                    exif[0x9286] = comment_text
                    save_kwargs["exif"] = exif.tobytes()
            except Exception:
                pass
        elif pil_format == "PNG":
            save_kwargs["compress_level"] = int(
                export_options.get("png_compress_level", 9)
            )
            save_kwargs["optimize"] = bool(export_options.get("png_optimize", True))
            try:
                comment_text = (export_options.get("comment_text") or "").strip()
                if comment_text and bool(export_options.get("include_metadata", True)):
                    import PIL.PngImagePlugin as PngImagePlugin

                    meta = PngImagePlugin.PngInfo()
                    meta.add_text("Comment", comment_text)
                    save_kwargs["pnginfo"] = meta
            except Exception:
                pass

        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Export canceled by user")

        try:

            if pil_format == "JXL" and JXL_SUPPORTED:
                logger.info(f"Attempting to save JXL image: {full_path}")
                try:

                    img_array = np.array(img_to_save)
                    logger.debug(f"JXL array shape: {img_array.shape}")

                    quality = int(export_options.get("quality", 95))
                    logger.debug(f"JXL quality setting: {quality}")

                    if quality >= 100:

                        logger.debug("Saving JXL in lossless mode")
                        imagecodecs.imwrite(full_path, img_array, codec='jxl', lossless=True)
                    else:

                        distance = max(0.1, (100 - quality) / 10.0)
                        logger.debug(f"Saving JXL in lossy mode with distance: {distance}")
                        imagecodecs.imwrite(full_path, img_array, codec='jxl', distance=distance)

                    logger.info(f"JXL image saved successfully: {full_path}")
                except Exception as e:
                    logger.error(f"Failed to save JXL image: {e}", exc_info=True)
                    raise
            else:

                with open(full_path, "wb") as f:

                    class _CancelableStream:
                        def __init__(self, base, cancel_ev):
                            self._b = base
                            self._e = cancel_ev

                        def write(self, b):
                            if self._e and self._e.is_set():
                                raise RuntimeError("Save canceled by user")
                            return self._b.write(b)

                        def flush(self):
                            return self._b.flush()

                        def close(self):
                            return self._b.close()

                        def seek(self, *args, **kwargs):
                            return self._b.seek(*args, **kwargs)

                        def tell(self):
                            return self._b.tell()

                        def writable(self):
                            return True

                        def readable(self):
                            return False

                        def seekable(self):
                            return True

                        def fileno(self):
                            return self._b.fileno()

                    stream = _CancelableStream(f, cancel_event)
                    img_to_save.save(stream, format=pil_format, **save_kwargs)
        except Exception:

            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception:
                pass
            raise

        if progress_callback:
            progress_callback(100)

        return full_path

    def quick_export(
        self,
        store: Store,
        original_image1: Image.Image,
        original_image2: Image.Image,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Any] = None,
    ) -> str:
        """
        Быстрый экспорт с использованием сохранённых в store настроек.
        """

        bg_color_qcolor = getattr(
            store.settings, "export_background_color", QColor(255, 255, 255, 255)
        )
        bg_color_tuple = (
            bg_color_qcolor.red(),
            bg_color_qcolor.green(),
            bg_color_qcolor.blue(),
            bg_color_qcolor.alpha(),
        )

        export_options = {
            "output_dir": store.settings.export_default_dir,
            "file_name": self._generate_base_filename(store),
            "format": store.settings.export_last_format or "PNG",
            "quality": store.settings.export_quality or 95,
            "fill_background": getattr(store.settings, "export_fill_background", False),
            "background_color": bg_color_tuple,
            "png_compress_level": getattr(store.settings, "export_png_compress_level", 9),
            "png_optimize": True,
            "include_metadata": bool(
                getattr(store.settings, "export_comment_keep_default", False)
            ),
            "comment_text": (
                getattr(store.settings, "export_comment_text", "")
                if getattr(store.settings, "export_comment_keep_default", False)
                else ""
            ),
            "is_quick_save": True,
        }

        return self.export_image(
            store,
            original_image1,
            original_image2,
            export_options,
            cancel_event,
            progress_callback,
        )

    def _generate_base_filename(self, store: Store) -> str:
        import re

        name1 = (self._get_current_display_name(store, 1) or "image1").strip()
        name2 = (self._get_current_display_name(store, 2) or "image2").strip()

        def sanitize(s: str) -> str:
            s = re.sub(r'[\\/*?:"<>|]', "_", s)
            return s[:80]

        return f"{sanitize(name1)}_{sanitize(name2)}"

    def _get_current_display_name(self, store: Store, image_number: int) -> str:
        target_list, index = (
            (store.document.image_list1, store.document.current_index1)
            if image_number == 1
            else (store.document.image_list2, store.document.current_index2)
        )
        if 0 <= index < len(target_list):
            return target_list[index].display_name
        return ""

    def _generate_unique_filepath(
        self, directory: str, base_name: str, extension: str
    ) -> str:
        """
        Генерирует уникальный путь к файлу, добавляя номер, если файл уже существует.
        """
        full_path = os.path.join(directory, f"{base_name}{extension}")
        if not os.path.exists(full_path):
            return full_path

        counter = 1
        while True:
            new_name = f"{base_name} ({counter})"
            new_path = os.path.join(directory, f"{new_name}{extension}")
            if not os.path.exists(new_path):
                return new_path
            counter += 1

