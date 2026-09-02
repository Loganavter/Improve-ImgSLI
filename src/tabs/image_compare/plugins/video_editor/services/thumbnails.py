import logging
import math
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from tabs.image_compare.plugins.video_editor.services.keyframing import KeyframedRecording
from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")
_thlog = logging.getLogger("ImproveImgSLI.video_thumbnails")

DEFAULT_THUMBNAIL_RENDER_SCALE = 1.0

def _thumbnail_render_target_size(
    thumbnail_size: Tuple[int, int], render_scale: float
) -> Tuple[int, int]:
    out_w, out_h = thumbnail_size
    render_scale = max(1.0, float(render_scale))
    return (
        max(1, int(round(out_w * render_scale))),
        max(1, int(round(out_h * render_scale))),
    )


def _finish_thumbnail_image(
    rendered: Optional[Image.Image], thumbnail_size: Tuple[int, int]
) -> Optional[Image.Image]:
    if rendered is None:
        return None
    out_w, out_h = thumbnail_size
    rendered = rendered.convert("RGBA")
    if rendered.height == out_h:
        return rendered
    if rendered.height <= 0:
        return None
    fit_scale = float(out_h) / float(rendered.height)
    final_w = max(1, int(round(rendered.width * fit_scale)))
    return rendered.resize((final_w, out_h), Image.Resampling.LANCZOS)


def _render_thumbnail_using_renderer(
    snap,
    thumbnail_size: Tuple[int, int],
    auto_crop: bool,
    render_scale: float,
    render_snapshot: Callable[..., Optional[Image.Image]],
) -> Optional[Image.Image]:
    try:
        target_w, target_h = _thumbnail_render_target_size(thumbnail_size, render_scale)
        rendered = render_snapshot(
            snap,
            target_w,
            target_h,
            auto_crop=auto_crop,
        )
        return _finish_thumbnail_image(rendered, thumbnail_size)
    except Exception as e:
        logger.error(f"Error rendering thumbnail using shared renderer: {e}", exc_info=True)
        return None

class ThumbnailService(QObject):
    thumbnailsGenerated = Signal(dict)
    thumbnailReady = Signal(int, QPixmap)
    generationFinished = Signal()

    def __init__(self):
        super().__init__()
        self._is_generating = False
        self._current_task_id = 0
        self._thread_pool = QThreadPool(self)
        try:
            ideal = QThreadPool.globalInstance().maxThreadCount()
        except Exception:
            ideal = 4
        adaptive = max(2, min(4, int(ideal) if ideal else 4))
        self._thread_pool.setMaxThreadCount(adaptive)
        self._generated_indices = set()
        self._pending_indices = set()
        self._recording = None
        self._thumbnail_size = (160, 90)
        self._thumbnail_render_scale = DEFAULT_THUMBNAIL_RENDER_SCALE
        self._render_snapshot: Optional[Callable[..., Optional[Image.Image]]] = None
        self._render_snapshot_async: Optional[Callable[..., None]] = None
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
        priority_indices: List[int] | None = None,
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
        if not recording:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc generate ABORT no recording")
            except Exception:
                pass
            return -1
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_svc generate ENTRY is_gen=%s cancelled=%s pending=%s gen=%s priority_len=%s target=%s fps=%s", self._is_generating, self._generation_cancelled, len(self._pending_indices), len(self._generated_indices), len(priority_indices) if priority_indices else 0, target_count, fps)
        except Exception:
            pass
        # If a previous generation is still in flight, retire it so a
        # resize-triggered refresh doesn't return -1 forever (the old
        # `_is_generating` guard caused the strip to die after any resize
        # that happened before the first wave finished).
        if self._is_generating:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc generate PREEMPT is_gen=%s cancelled->True pending_clear %s->0 active %s->0", self._is_generating, len(self._pending_indices), self._active_workers)
            except Exception:
                pass
            self._generation_cancelled = True
            self._pending_indices.clear()
            self._is_generating = False
            self._active_workers = 0

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
        try:
            from tabs.image_compare.debug import ic_video_debug, ic_perf_debug
            ic_video_debug("thumb_svc generate task=%s count=%s target=%s fps=%s queue=%s indices=%s", task_id, count, target_count, self._fps, len(indices_to_generate), indices_to_generate[:12])
            ic_perf_debug("thumbnails_generate task=%s count=%s target=%s fps=%s queue=%s pool_max=%s", task_id, count, target_count, self._fps, len(indices_to_generate), self._thread_pool.maxThreadCount())
        except Exception:
            pass
        _thlog.debug(
            "thumbnails_generate task=%s count=%s target=%s fps=%s queue=%s",
            task_id,
            count,
            target_count,
            self._fps,
            len(indices_to_generate),
        )
        if self._active_workers <= 0:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc generate EMPTY queue task=%s", task_id)
            except Exception:
                pass
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
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc additional ABORT no recording indices=%s", indices[:12] if indices else [])
            except Exception:
                pass
            return
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_svc additional ENTRY cancelled=%s pending=%s gen=%s req=%s fps_in=%s", self._generation_cancelled, len(self._pending_indices), len(self._generated_indices), indices[:12] if indices else [], fps)
        except Exception:
            pass
        # Stale `cancel()` poisoned `_generation_cancelled=True` — without
        # reset every arrival is dropped in `_on_thumbnail_generated`.
        if self._generation_cancelled:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc additional RESET poison cancelled->False pending_clear %s->0", len(self._pending_indices))
            except Exception:
                pass
            self._generation_cancelled = False
            self._pending_indices.clear()
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
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc additional SKIP nothing needed req=%s pending=%s gen=%s", indices[:12] if indices else [], len(self._pending_indices), len(self._generated_indices))
            except Exception:
                pass
            return
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_svc additional QUEUE fps=%s queue=%s indices=%s", self._fps, len(needed_indices), needed_indices[:12])
        except Exception:
            pass
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

    def set_async_snapshot_renderer(self, renderer: Optional[Callable[..., None]]):
        """Preferred over :meth:`set_snapshot_renderer` when available.

        ``renderer(snap, out_w, out_h, callback, auto_crop=...)`` must call
        ``callback(pil_image_or_None)`` later instead of returning — lets the
        worker thread submit the GPU render and move on to the next
        thumbnail's CPU prep instead of blocking on the round-trip.
        """
        self._render_snapshot_async = renderer

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

        if self._render_snapshot_async is not None:
            # Async path: the worker submits the GPU render and returns
            # right away, freeing the (single) pool thread to start the
            # next thumbnail's CPU prep instead of sitting blocked on the
            # GPU round-trip. Completion bookkeeping (_on_thumbnail_generated
            # / _on_worker_finished) happens from the callback once the
            # render actually finishes, not when this worker returns.
            worker = GenericWorker(
                self._start_single_thumbnail_async,
                index,
                self._thumbnail_size,
                self._auto_crop,
                self._thumbnail_render_scale,
                self._fps,
                track_finish,
            )
            self._thread_pool.start(worker, priority=priority)
            return

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

    def _start_single_thumbnail_async(
        self,
        index: int,
        thumbnail_size: Tuple[int, int],
        auto_crop: bool,
        render_scale: float,
        fps: int,
        track_finish: bool,
    ) -> None:
        """Runs on the background pool thread; must not block on the GPU."""
        try:
            _thlog.debug(
                "thumbnail_worker_start index=%s fps=%s async=True", index, fps
            )
            snap = self._recording.evaluate_at(float(index) / float(max(1, fps)))
            if self._render_snapshot_async is None:
                raise RuntimeError("Async thumbnail GPU renderer is not configured")
            target_w, target_h = _thumbnail_render_target_size(
                thumbnail_size, render_scale
            )

            def _on_rendered(rendered_pil: Optional[Image.Image]) -> None:
                result = _finish_thumbnail_image(rendered_pil, thumbnail_size)
                _thlog.debug(
                    "thumbnail_worker_end index=%s ok=%s size=%s async=True",
                    index,
                    result is not None,
                    getattr(result, "size", None),
                )
                self._on_thumbnail_generated(index, result)
                if track_finish:
                    self._on_worker_finished()

            self._render_snapshot_async(
                snap, target_w, target_h, _on_rendered, auto_crop=auto_crop
            )
        except Exception as e:
            logger.error(
                f"Error starting async thumbnail at index {index}: {e}", exc_info=True
            )
            self._on_thumbnail_generated(index, None)
            if track_finish:
                self._on_worker_finished()

    def _on_thumbnail_generated(self, index: int, pil_image):
        self._pending_indices.discard(index)
        if self._generation_cancelled:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc _on_generated DROP cancelled idx=%s ok=%s pending=%s gen=%s", index, pil_image is not None, len(self._pending_indices), len(self._generated_indices))
            except Exception:
                pass
            return
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_svc _on_generated idx=%s ok=%s pending=%s gen=%s has_pixmap=%s", index, pil_image is not None, len(self._pending_indices), len(self._generated_indices), bool(pil_image))
        except Exception:
            pass

        if pil_image:
            try:
                # Debug dump first thumbnail to verify not black/null — gated
                try:
                    import os
                    if os.getenv("IMGSLI_THUMBNAIL_DEBUG") == "1" or os.getenv("IMGSLI_VIDEO_EDITOR_DEBUG") == "1":
                        from tabs.image_compare.debug import ic_thumbnail_debug
                        ext = pil_image.getextrema() if hasattr(pil_image, "getextrema") else None
                        is_trans = False
                        try:
                            if pil_image.mode == "RGBA" and ext and len(ext) > 3:
                                is_trans = ext[3][1] == 0
                        except Exception:
                            pass
                        ic_thumbnail_debug("thumb_svc pil idx=%s size=%s mode=%s extrema=%s transparent=%s", index, pil_image.size, pil_image.mode, ext, is_trans)
                        if index == 0 and not hasattr(self, "_thumb_dump_done"):
                            self._thumb_dump_done = True
                            pil_image.save("/tmp/thumb_debug_0.png")
                            ic_thumbnail_debug("thumb_debug saved /tmp/thumb_debug_0.png size=%s", pil_image.size)
                            if is_trans:
                                ic_thumbnail_debug("thumb_debug WARNING transparent — offscreen render empty")
                except Exception:
                    pass
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
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_svc _on_worker_finished active=%s is_gen=%s", self._active_workers, self._is_generating)
        except Exception:
            pass

        if self._active_workers <= 0:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc generationFinished emit active=%s", self._active_workers)
            except Exception:
                pass
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