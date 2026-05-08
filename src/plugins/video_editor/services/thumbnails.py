import logging
import math
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from plugins.video_editor.services.keyframing import KeyframedRecording
from shared.image_processing.pipeline import (
    RenderingPipeline,
    create_render_context_from_store,
)
from shared.image_processing.progressive_loader import load_preview_image
from shared_toolkit.workers.generic_worker import GenericWorker
from ui.canvas_presentation import (
    build_render_frame_presentation,
    build_snapshot_store_presentation,
)

logger = logging.getLogger("ImproveImgSLI")

DEFAULT_THUMBNAIL_RENDER_SCALE = 2.0

def _render_thumbnail_using_pipeline(
    snap,
    thumbnail_size: Tuple[int, int],
    auto_crop: bool = False,
    render_scale: float = DEFAULT_THUMBNAIL_RENDER_SCALE,
    image_loader: Optional[Callable[[str, bool], Optional[Image.Image]]] = None,
) -> Optional[Image.Image]:
    try:
        out_w, out_h = thumbnail_size
        render_scale = max(1.0, float(render_scale))
        target_w = max(1, int(round(out_w * render_scale)))
        target_h = max(1, int(round(out_h * render_scale)))

        loader = image_loader or load_preview_image
        img1 = loader(snap.image1_path, auto_crop)
        img2 = loader(snap.image2_path, auto_crop)

        if not img1:
            img1 = Image.new("RGBA", (target_w, target_h), (50, 50, 50, 255))
        if not img2:
            img2 = Image.new("RGBA", (target_w, target_h), (80, 80, 80, 255))

        presentation = build_snapshot_store_presentation(
            snap,
            img1,
            img2,
            fit_content=False,
        )
        presentation.store.settings.auto_crop_black_borders = auto_crop
        frame = build_render_frame_presentation(
            presentation,
            output_width=target_w,
            output_height=target_h,
        )

        ctx = create_render_context_from_store(
            store=frame.store,
            width=frame.render_width,
            height=frame.render_height,
            magnifier_drawing_coords=frame.magnifier_drawing_coords,
            image1_scaled=frame.scaled_image1,
            image2_scaled=frame.scaled_image2,
        )
        ctx.images.file_name1 = snap.name1 or ""
        ctx.images.file_name2 = snap.name2 or ""

        pipeline = RenderingPipeline(font_path=None)
        frame_pil, p_l, p_t, _, _, _ = pipeline.render_frame(ctx)

        if not frame_pil:
            return Image.new("RGBA", (frame.render_width, out_h), (0, 0, 0, 255))

        crop_rect = (
            max(0, p_l),
            max(0, p_t),
            min(frame_pil.width, p_l + frame.render_width),
            min(frame_pil.height, p_t + frame.render_height),
        )

        base_image_content = frame_pil.crop(crop_rect)

        final_w = max(1, int(round(base_image_content.width / render_scale)))
        final_frame = base_image_content.resize(
            (final_w, out_h), Image.Resampling.LANCZOS
        )

        return final_frame

    except Exception as e:
        logger.error(f"Error rendering thumbnail using pipeline: {e}", exc_info=True)
        return None

def _render_thumbnail_using_renderer(
    snap,
    thumbnail_size: Tuple[int, int],
    auto_crop: bool,
    render_scale: float,
    render_snapshot: Callable[..., Optional[Image.Image]],
) -> Optional[Image.Image]:
    try:
        out_w, out_h = thumbnail_size
        render_scale = max(1.0, float(render_scale))
        target_w = max(1, int(round(out_w * render_scale)))
        target_h = max(1, int(round(out_h * render_scale)))
        rendered = render_snapshot(
            snap,
            target_w,
            target_h,
            auto_crop=auto_crop,
        )
        if rendered is None:
            return None
        rendered = rendered.convert("RGBA")
        if rendered.size == (out_w, out_h):
            return rendered
        return rendered.resize((out_w, out_h), Image.Resampling.LANCZOS)
    except Exception as e:
        logger.error(f"Error rendering thumbnail using shared renderer: {e}", exc_info=True)
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
        self._recording = None
        self._thumbnail_size = (160, 90)
        self._thumbnail_render_scale = DEFAULT_THUMBNAIL_RENDER_SCALE
        self._image_loader: Optional[Callable[[str, bool], Optional[Image.Image]]] = None
        self._render_snapshot: Optional[Callable[..., Optional[Image.Image]]] = None
        self._auto_crop = False
        self._active_workers = 0
        self._generation_cancelled = False
        self._fps = 60

    def generate_thumbnails(
        self,
        recording,
        target_count: int = 50,
        thumbnail_size: Tuple[int, int] = (160, 90),
        auto_crop: bool = False,
        priority_indices: List[int] = None,
        fps: int = 60,
    ) -> int:
        """
        Генерирует превью для snapshot'ов ПАРАЛЛЕЛЬНО.

        Args:
            snapshots: Список snapshot'ов для рендеринга
            target_count: Целевое количество превью для первой волны
            thumbnail_size: Размер превью
            auto_crop: Обрезать ли черные рамки
            priority_indices: Индексы, которые нужно сгенерировать в первую очередь (видимые кадры)
        """
        if self._is_generating or not recording:
            return -1

        self._recording = self._coerce_recording(recording)
        self._thumbnail_size = thumbnail_size
        self._auto_crop = auto_crop
        self._fps = max(1, int(fps))
        self._generated_indices.clear()
        self._generation_cancelled = False

        self._is_generating = True
        self._current_task_id += 1
        task_id = self._current_task_id

        count = self._get_frame_count()
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
                idx,
                thumbnail_size,
                auto_crop,
                self._thumbnail_render_scale,
                self._fps,
                None,
            )

            worker.signals.result.connect(
                lambda result, i=idx: self._on_thumbnail_generated(i, result)
            )
            worker.signals.finished.connect(self._on_worker_finished)

            self._thread_pool.start(worker)

        return task_id

    def generate_additional_thumbnails(self, indices: List[int], fps: int | None = None):
        if not self._recording:
            return
        if fps is not None:
            self._fps = max(1, int(fps))

        needed_indices = [
            i
            for i in indices
            if i not in self._generated_indices and 0 <= i < self._get_frame_count()
        ]

        if not needed_indices:
            return

        for idx in needed_indices:
            worker = GenericWorker(
                self._generate_single_thumbnail,
                idx,
                self._thumbnail_size,
                self._auto_crop,
                self._thumbnail_render_scale,
                self._fps,
                None,
            )

            worker.signals.result.connect(
                lambda result, i=idx: self._on_thumbnail_generated(i, result)
            )

            self._thread_pool.start(worker, priority=1)

    def request_priority_thumbnails(self, indices: List[int]):
        self.generate_additional_thumbnails(indices)

    def _generate_single_thumbnail(
        self,
        index: int,
        thumbnail_size: Tuple[int, int],
        auto_crop: bool,
        render_scale: float,
        fps: int,
        progress_callback,
    ):
        """Генерирует одно превью и возвращает PIL Image."""
        try:
            snap = self._recording.evaluate_at(float(index) / float(max(1, fps)))
            if self._render_snapshot is not None:
                composed_pil = _render_thumbnail_using_renderer(
                    snap,
                    thumbnail_size,
                    auto_crop,
                    render_scale,
                    self._render_snapshot,
                )
            else:
                composed_pil = _render_thumbnail_using_pipeline(
                    snap,
                    thumbnail_size,
                    auto_crop,
                    render_scale,
                    self._image_loader,
                )
            return composed_pil
        except Exception as e:
            logger.error(
                f"Error generating thumbnail at index {index}: {e}", exc_info=True
            )
            return None

    def _coerce_recording(self, recording):
        if isinstance(recording, KeyframedRecording):
            return recording
        if hasattr(recording, "evaluate_at") and hasattr(recording, "get_duration"):
            return recording
        extra_adapters = tuple(getattr(recording, "extra_adapters", ()))
        return KeyframedRecording.from_snapshots(
            list(recording or []),
            extra_adapters=extra_adapters,
        )

    def _get_frame_count(self) -> int:
        if not self._recording:
            return 0
        duration = self._recording.get_duration()
        if duration <= 0:
            return 1
        return max(1, int(math.ceil(duration * self._fps)) + 1)

    def set_thumbnail_render_scale(self, scale: float):
        self._thumbnail_render_scale = max(1.0, float(scale))

    def set_image_loader(
        self, loader: Optional[Callable[[str, bool], Optional[Image.Image]]]
    ):
        self._image_loader = loader

    def set_snapshot_renderer(
        self, renderer: Optional[Callable[..., Optional[Image.Image]]]
    ):
        self._render_snapshot = renderer

    def _on_thumbnail_generated(self, index: int, pil_image):
        if self._generation_cancelled:
            return

        if pil_image:
            try:
                pil_image = pil_image.convert("RGBA")
                data = pil_image.tobytes("raw", "RGBA")
                qimg = QImage(
                    data,
                    pil_image.width,
                    pil_image.height,
                    QImage.Format.Format_RGBA8888,
                )
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

    def cancel(self):
        self._generation_cancelled = True
        self._is_generating = False
        self._thread_pool.waitForDone(500)

    def _on_generation_finished(self):
        self._is_generating = False
        self.generationFinished.emit()
