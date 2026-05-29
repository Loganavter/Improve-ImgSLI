import logging
import os
import threading
from typing import Any, Optional

from PIL import Image

from core.store import Store
from domain.types import Color
from plugins.video_editor.services.video_export_models import VideoRenderRequest
from plugins.video_editor.services.video_snapshot_rendering import SnapshotFrameRenderer
from shared.image_processing.resize import resize_images_processor
from shared.rendering import TargetSurfaceSpec
from shared.rendering.live_snapshot import build_live_frame_snapshot
from shared.rendering import get_effective_export_interpolation_method

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

    def __init__(self, font_path_absolute: str, gpu_export_service=None):
        self.font_path_absolute = font_path_absolute
        self.gpu_export_service = gpu_export_service

    @staticmethod
    def apply_background_fill(image: Image.Image, background_color):
        if not background_color:
            return image
        bg = Image.new("RGBA", image.size, background_color)
        bg.paste(image, mask=image.split()[3] if image.mode == "RGBA" else None)
        return bg

    def export_image(
        self,
        store: Store,
        original_image1: Image.Image,
        original_image2: Image.Image,
        export_options: dict,
        render_plan=None,
        render_store=None,
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

        renderer = SnapshotFrameRenderer(
            image_loader=lambda _path, _auto_crop=False: None,
            gpu_export_service=self.gpu_export_service,
        )
        current_render_plan = render_plan
        current_render_store = render_store
        canvas_fill_rgba = (
            tuple(export_options.get("background_color") or ())
            if export_options.get("fill_background", False)
            else None
        )

        override_w = export_options.get("width")
        override_h = export_options.get("height")
        try:
            override_w = int(override_w) if override_w else 0
            override_h = int(override_h) if override_h else 0
        except (TypeError, ValueError):
            override_w = override_h = 0

        plan_size = None
        if current_render_plan is not None:
            cw = int(getattr(current_render_plan, "canvas_w", 0) or 0)
            ch = int(getattr(current_render_plan, "canvas_h", 0) or 0)
            if cw > 0 and ch > 0:
                plan_size = (cw, ch)
        needs_rebuild = (
            current_render_plan is None
            or (override_w > 0 and override_h > 0 and plan_size is not None and plan_size != (override_w, override_h))
        )

        if needs_rebuild:
            live_snapshot = build_live_frame_snapshot(store)
            resize_method = get_effective_export_interpolation_method(
                live_snapshot.viewport_state
            )
            image1_for_save, image2_for_save = resize_images_processor(
                original_image1, original_image2, resize_method
            )
            if not image1_for_save or not image2_for_save:
                raise ValueError("Failed to unify images for export.")
            if override_w > 0 and override_h > 0 and plan_size is not None:
                native_canvas_w, native_canvas_h = plan_size
                scale_w = override_w / float(native_canvas_w)
                scale_h = override_h / float(native_canvas_h)
                target_w = max(1, int(round(image1_for_save.width * scale_w)))
                target_h = max(1, int(round(image1_for_save.height * scale_h)))
            else:
                target_w = override_w if override_w > 0 else image1_for_save.width
                target_h = override_h if override_h > 0 else image1_for_save.height
            prepared_frame = renderer.prepare_canvas_frame_from_images(
                live_snapshot,
                VideoRenderRequest(
                    target_surface=TargetSurfaceSpec(
                        width=target_w,
                        height=target_h,
                        fill_rgba=canvas_fill_rgba,
                    ),
                    font_path=None,
                    auto_crop=False,
                    fit_content=False,
                    global_bounds=None,
                ),
                image1_for_save,
                image2_for_save,
                allow_feature_layout_fallback=True,
            )
            current_render_plan = prepared_frame.plan
            current_render_store = prepared_frame.store

        if progress_callback:
            progress_callback(30)

        if self.gpu_export_service is None:
            raise RuntimeError("GPU export service is not configured")

        diff_image_for_render = None
        try:
            render_cache = getattr(
                getattr(current_render_store, "viewport", None),
                "session_data",
                None,
            )
            render_cache = getattr(render_cache, "render_cache", None)
            diff_image_for_render = getattr(render_cache, "cached_diff_image", None)
        except Exception:
            diff_image_for_render = None

        final_img, _gpu_debug = self.gpu_export_service.render_plan(
            current_render_plan,
            store=current_render_store or store,
            diff_image=diff_image_for_render,
        )
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
                img_to_save = self.apply_background_fill(final_img, bg_color_tuple)

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
            bg_color_tuple = export_options.get("background_color") or (
                255,
                255,
                255,
                255,
            )
            bg_flat = Image.new("RGBA", img_to_save.size, bg_color_tuple)
            bg_flat.paste(img_to_save, mask=img_to_save.split()[3])
            img_to_save = bg_flat.convert("RGB")

        comment_text = (export_options.get("comment_text") or "").strip()
        include_metadata = bool(export_options.get("include_metadata", True))

        if pil_format == "JPEG":
            save_kwargs["quality"] = int(export_options.get("quality", 95))
            if comment_text and include_metadata:
                self._attach_comment_metadata(img_to_save, save_kwargs, pil_format, comment_text)
        elif pil_format == "PNG":
            save_kwargs["compress_level"] = int(
                export_options.get("png_compress_level", 9)
            )
            save_kwargs["optimize"] = bool(export_options.get("png_optimize", True))
            if comment_text and include_metadata:
                self._attach_comment_metadata(img_to_save, save_kwargs, pil_format, comment_text)
        elif pil_format in {"TIFF", "WEBP"}:
            if comment_text and include_metadata:
                self._attach_comment_metadata(img_to_save, save_kwargs, pil_format, comment_text)
        elif pil_format == "JXL" and comment_text and include_metadata:
            logger.warning(
                "JXL export currently does not embed textual metadata; comment_text will not be saved."
            )

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
                        imagecodecs.imwrite(
                            full_path, img_array, codec="jxl", lossless=True
                        )
                    else:

                        distance = max(0.1, (100 - quality) / 10.0)
                        logger.debug(
                            f"Saving JXL in lossy mode with distance: {distance}"
                        )
                        imagecodecs.imwrite(
                            full_path, img_array, codec="jxl", distance=distance
                        )

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

    def _attach_comment_metadata(self, img_to_save, save_kwargs: dict, pil_format: str, comment_text: str) -> None:
        try:
            if pil_format == "PNG":
                import PIL.PngImagePlugin as PngImagePlugin

                meta = PngImagePlugin.PngInfo()
                meta.add_text("Comment", comment_text)
                save_kwargs["pnginfo"] = meta
                return

            exif = img_to_save.getexif()
            exif[0x9286] = comment_text
            save_kwargs["exif"] = exif.tobytes()
        except Exception:
            logger.debug(
                "Failed to attach export comment metadata for format=%s",
                pil_format,
                exc_info=True,
            )

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

        bg_color = getattr(
            store.settings, "export_background_color", Color(255, 255, 255, 255)
        )
        bg_color_tuple = (bg_color.r, bg_color.g, bg_color.b, bg_color.a)

        export_options = {
            "output_dir": store.settings.export_default_dir,
            "file_name": self._generate_base_filename(store),
            "format": store.settings.export_last_format or "PNG",
            "quality": store.settings.export_quality or 95,
            "fill_background": getattr(store.settings, "export_fill_background", False),
            "background_color": bg_color_tuple,
            "png_compress_level": getattr(
                store.settings, "export_png_compress_level", 9
            ),
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
            store=store,
            original_image1=original_image1,
            original_image2=original_image2,
            export_options=export_options,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
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
