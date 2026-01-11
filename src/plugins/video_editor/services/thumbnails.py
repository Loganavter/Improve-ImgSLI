import logging
from typing import Dict, List, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool
from PyQt6.QtGui import QImage, QPixmap
from PIL import Image
from shared_toolkit.workers.generic_worker import GenericWorker
from shared.image_processing.progressive_loader import load_preview_image
from copy import deepcopy
from core.store import Store
from utils.resource_loader import get_magnifier_drawing_coords
from shared.image_processing.pipeline import create_render_context_from_store, RenderingPipeline

logger = logging.getLogger("ImproveImgSLI")

def _render_thumbnail_using_pipeline(snap, thumbnail_size: Tuple[int, int], auto_crop: bool = True) -> Optional[Image.Image]:
    try:
        out_w, out_h = thumbnail_size

        img1 = load_preview_image(snap.image1_path, auto_crop=auto_crop)
        img2 = load_preview_image(snap.image2_path, auto_crop=auto_crop)

        if not img1: img1 = Image.new("RGBA", (out_w, out_h), (50, 50, 50, 255))
        if not img2: img2 = Image.new("RGBA", (out_w, out_h), (80, 80, 80, 255))

        base_w, base_h = img1.size

        temp_store = Store()

        temp_store.viewport = snap.viewport_state.clone()
        temp_store.settings = snap.settings_state.freeze_for_export()

        temp_store.settings.auto_crop_black_borders = auto_crop

        temp_store.viewport.image1 = img1
        temp_store.viewport.image2 = img2
        temp_store.document.full_res_image1 = img1
        temp_store.document.full_res_image2 = img2

        scale = max(out_w / base_w, out_h / base_h)
        render_w = int(base_w * scale)
        render_h = int(base_h * scale)
        render_w = max(1, render_w)
        render_h = max(1, render_h)

        temp_store.viewport.pixmap_width = render_w
        temp_store.viewport.pixmap_height = render_h

        mag_coords = get_magnifier_drawing_coords(
            store=temp_store,
            drawing_width=render_w,
            drawing_height=render_h,
            container_width=render_w,
            container_height=render_h
        ) if temp_store.viewport.use_magnifier else None

        img1_s = img1.resize((render_w, render_h), Image.Resampling.BILINEAR)
        img2_s = img2.resize((render_w, render_h), Image.Resampling.BILINEAR)

        ctx = create_render_context_from_store(
            store=temp_store,
            width=render_w,
            height=render_h,
            magnifier_drawing_coords=mag_coords,
            image1_scaled=img1_s,
            image2_scaled=img2_s
        )
        ctx.file_name1 = snap.name1
        ctx.file_name2 = snap.name2

        pipeline = RenderingPipeline(font_path=None)
        frame_pil, p_l, p_t, _, _, _ = pipeline.render_frame(ctx)

        if not frame_pil:
            return Image.new("RGBA", thumbnail_size, (0, 0, 0, 255))

        crop_rect = (
            max(0, p_l), max(0, p_t),
            min(frame_pil.width, p_l + render_w), min(frame_pil.height, p_t + render_h)
        )

        base_image_content = frame_pil.crop(crop_rect)

        if base_image_content.size != (render_w, render_h):
            base_image_content = base_image_content.resize((render_w, render_h), Image.Resampling.BILINEAR)

        crop_x = max(0, (render_w - out_w) // 2)
        crop_y = max(0, (render_h - out_h) // 2)

        final_frame = base_image_content.crop((
            crop_x, crop_y,
            min(render_w, crop_x + out_w),
            min(render_h, crop_y + out_h)
        ))

        if final_frame.size != thumbnail_size:
            final_frame = final_frame.resize(thumbnail_size, Image.Resampling.BILINEAR)

        return final_frame

    except Exception as e:
        logger.error(f"Error rendering thumbnail using pipeline: {e}", exc_info=True)
        return None

class ThumbnailService(QObject):
    thumbnailsGenerated = pyqtSignal(dict)
    thumbnailReady = pyqtSignal(int, QPixmap)
    generationFinished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._is_generating = False
        self._current_task_id = 0
        self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.setMaxThreadCount(4)
        self._generated_indices = set()
        self._snapshots = None
        self._thumbnail_size = (160, 90)
        self._auto_crop = True
        self._active_workers = 0
        self._generation_cancelled = False

    def generate_thumbnails(self, snapshots: List, target_count: int = 50,
                          thumbnail_size: Tuple[int, int] = (160, 90),
                          auto_crop: bool = True, priority_indices: List[int] = None) -> int:
        """
        Генерирует превью для snapshot'ов ПАРАЛЛЕЛЬНО.

        Args:
            snapshots: Список snapshot'ов для рендеринга
            target_count: Целевое количество превью для первой волны
            thumbnail_size: Размер превью
            auto_crop: Обрезать ли черные рамки
            priority_indices: Индексы, которые нужно сгенерировать в первую очередь (видимые кадры)
        """
        if self._is_generating or not snapshots:
            return -1

        self._snapshots = snapshots
        self._thumbnail_size = thumbnail_size
        self._auto_crop = auto_crop
        self._generated_indices.clear()
        self._generation_cancelled = False

        self._is_generating = True
        self._current_task_id += 1
        task_id = self._current_task_id

        count = len(snapshots)
        step = max(1, count // target_count)

        indices_to_generate = []

        if priority_indices:
            indices_to_generate.extend(priority_indices)

        for i in range(0, count, step):
            if i not in indices_to_generate:
                indices_to_generate.append(i)

        self._active_workers = len(indices_to_generate)

        for idx in indices_to_generate:
            if idx >= count:
                continue

            worker = GenericWorker(
                self._generate_single_thumbnail,
                snapshots[idx], idx, thumbnail_size, auto_crop, None
            )

            worker.signals.result.connect(lambda result, i=idx: self._on_thumbnail_generated(i, result))
            worker.signals.finished.connect(self._on_worker_finished)

            self._thread_pool.start(worker)

        return task_id

    def generate_additional_thumbnails(self, indices: List[int]):
        if not self._snapshots:
            return

        needed_indices = [i for i in indices if i not in self._generated_indices and 0 <= i < len(self._snapshots)]

        if not needed_indices:
            return

        logger.debug(f"[ThumbnailService] Loading {len(needed_indices)} additional thumbnails")

        for idx in needed_indices:
            worker = GenericWorker(
                self._generate_single_thumbnail,
                self._snapshots[idx], idx, self._thumbnail_size, self._auto_crop, None
            )

            worker.signals.result.connect(lambda result, i=idx: self._on_thumbnail_generated(i, result))

            self._thread_pool.start(worker, priority=1)

    def request_priority_thumbnails(self, indices: List[int]):
        self.generate_additional_thumbnails(indices)

    def _generate_single_thumbnail(self, snap, index: int, thumbnail_size: Tuple[int, int],
                                   auto_crop: bool, progress_callback):
        """Генерирует одно превью и возвращает PIL Image."""
        try:

            composed_pil = _render_thumbnail_using_pipeline(snap, thumbnail_size, auto_crop)
            return composed_pil
        except Exception as e:
            logger.error(f"Error generating thumbnail at index {index}: {e}", exc_info=True)
            return None

    def _on_thumbnail_generated(self, index: int, pil_image):
        if self._generation_cancelled:
            return

        if pil_image:
            try:
                pil_image = pil_image.convert("RGBA")
                data = pil_image.tobytes("raw", "RGBA")
                qimg = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
                pixmap = QPixmap.fromImage(qimg.copy())

                self._generated_indices.add(index)
                self.thumbnailReady.emit(index, pixmap)
            except Exception as e:
                logger.error(f"Error converting thumbnail {index}: {e}")

    def _on_worker_finished(self):
        self._active_workers -= 1

        if self._active_workers <= 0:
            self._is_generating = False
            self.generationFinished.emit()

    def _on_single_thumbnail_ready(self, result: Tuple[int, QPixmap]):
        index, pixmap = result
        self._generated_indices.add(index)
        self.thumbnailReady.emit(index, pixmap)

    def _on_thumbnails_ready(self, result: Dict):
        if result:
            self.thumbnailsGenerated.emit(result)

    def _on_generation_finished(self):
        self._is_generating = False
        self.generationFinished.emit()
