import logging
import math
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from plugins.video_editor.services.keyframing import KeyframedRecording
from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")
_thlog = logging.getLogger("ImproveImgSLI.video_thumbnails")

DEFAULT_THUMBNAIL_RENDER_SCALE = 2.0

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
        if rendered.height == out_h:
            return rendered
        if rendered.height <= 0:
            return None
        fit_scale = float(out_h) / float(rendered.height)
        final_w = max(1, int(round(rendered.width * fit_scale)))
        return rendered.resize((final_w, out_h), Image.Resampling.LANCZOS)
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
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._generated_indices = set()
        self._pending_indices = set()
        self._recording = None
        self._thumbnail_size = (160, 90)
        self._thumbnail_render_scale = DEFAULT_THUMBNAIL_RENDER_SCALE
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
        self._pending_indices.clear()
        self._generation_cancelled = False

        self._is_generating = True
        self._current_task_id += 1
        task_id = self._current_task_id

        count = self._get_frame_count()
        indices_to_generate = self._build_initial_indices(
            count=count,
            target_count=target_count,
            priority_indices=priority_indices,
        )

        self._active_workers = len(indices_to_generate)
        _thlog.debug(
            "thumbnails_generate task=%s count=%s target=%s fps=%s queue=%s",
            task_id,
            count,
            target_count,
            self._fps,
            len(indices_to_generate),
        )
        if self._active_workers <= 0:
            self._is_generating = False
            self.generationFinished.emit()
            return task_id

        for idx in indices_to_generate:
            self._queue_thumbnail_worker(
                idx,
                priority=0,
                track_finish=True,
            )

        return task_id

    def generate_additional_thumbnails(self, indices: List[int], fps: int | None = None):
        if not self._recording:
            return
        if fps is not None:
            self._fps = max(1, int(fps))

        needed_indices = [
            i
            for i in indices
            if (
                i not in self._generated_indices
                and i not in self._pending_indices
                and 0 <= i < self._get_frame_count()
            )
        ]

        if not needed_indices:
            return
        _thlog.debug(
            "thumbnails_generate_additional fps=%s queue=%s indices=%s",
            self._fps,
            len(needed_indices),
            needed_indices[:12],
        )

        for idx in needed_indices:
            self._queue_thumbnail_worker(
                idx,
                priority=1,
                track_finish=False,
            )

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
            _thlog.debug("thumbnail_worker_start index=%s fps=%s", index, fps)
            snap = self._recording.evaluate_at(float(index) / float(max(1, fps)))
            if self._render_snapshot is None:
                raise RuntimeError("Thumbnail GPU renderer is not configured")
            result = _render_thumbnail_using_renderer(
                snap,
                thumbnail_size,
                auto_crop,
                render_scale,
                self._render_snapshot,
            )
            _thlog.debug(
                "thumbnail_worker_end index=%s ok=%s size=%s",
                index,
                result is not None,
                getattr(result, "size", None),
            )
            return result
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

    def set_snapshot_renderer(
        self, renderer: Optional[Callable[..., Optional[Image.Image]]]
    ):
        self._render_snapshot = renderer

    def _build_initial_indices(
        self,
        *,
        count: int,
        target_count: int,
        priority_indices: List[int] | None,
    ) -> List[int]:
        valid_priority = []
        seen = set()
        for idx in priority_indices or []:
            if 0 <= idx < count and idx not in seen:
                seen.add(idx)
                valid_priority.append(idx)
        if valid_priority:
            return valid_priority

        if count <= 0:
            return []

        fallback_count = min(count, max(1, min(int(target_count or 1), 12)))
        if fallback_count >= count:
            return list(range(count))
        step = max(1, int(math.ceil(count / float(fallback_count))))
        return list(range(0, count, step))[:fallback_count]

    def _queue_thumbnail_worker(
        self,
        index: int,
        *,
        priority: int,
        track_finish: bool,
    ) -> None:
        if index in self._pending_indices:
            return
        self._pending_indices.add(index)
        worker = GenericWorker(
            self._generate_single_thumbnail,
            index,
            self._thumbnail_size,
            self._auto_crop,
            self._thumbnail_render_scale,
            self._fps,
            None,
        )
        worker.signals.result.connect(
            lambda result, i=index: self._on_thumbnail_generated(i, result)
        )
        if track_finish:
            worker.signals.finished.connect(self._on_worker_finished)
        self._thread_pool.start(worker, priority=priority)

    def _on_thumbnail_generated(self, index: int, pil_image):
        self._pending_indices.discard(index)
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
        _thlog.debug("thumbnail_worker_finished active=%s", self._active_workers)

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
        self._pending_indices.clear()
        self._thread_pool.waitForDone(500)

    def _on_generation_finished(self):
        self._is_generating = False
        self.generationFinished.emit()
