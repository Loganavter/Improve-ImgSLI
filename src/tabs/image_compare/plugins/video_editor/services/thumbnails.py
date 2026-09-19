"""Video-editor thumbnail pipeline — queue, workers, convert, emit.

Audit-Meta: pattern=state-machine size=exempt reason="one thumbnail pipeline — queue/worker/convert/emit share one generation token + pending guard"
"""

import logging
import math
from typing import Callable, List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from tabs.image_compare.plugins.video_editor.services.keyframing import KeyframedRecording
from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
    ThumbnailDiskCache,
    thumbnail_cache_key_for_snap,
)
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
    # Trim fully-transparent margins (snapshot-plan letterbox pads survive
    # the same-size passthrough below and would read as gaps between strip
    # blocks once painted over the light strip background). Full-bleed
    # renders are unaffected (bbox == full size → no-op).
    bbox = rendered.getbbox()
    if bbox is None:
        return None
    if bbox != (0, 0, rendered.width, rendered.height):
        rendered = rendered.crop(bbox)
        if rendered.width <= 0 or rendered.height <= 0:
            return None
    if rendered.size == (out_w, out_h):
        return rendered
    if rendered.width <= 0 or rendered.height <= 0:
        return None
    # Cover: scale to fill out_w×out_h, center-crop (long-term uniform 72px strip, no letterbox)
    scale = max(out_w / float(rendered.width), out_h / float(rendered.height))
    new_w = max(1, int(round(rendered.width * scale)))
    new_h = max(1, int(round(rendered.height * scale)))
    scaled = rendered.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = max(0, (new_w - out_w) // 2)
    top = max(0, (new_h - out_h) // 2)
    return scaled.crop((left, top, left + out_w, top + out_h))


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
    # NOTE: thumbnailsGenerated is Signal(object), not Signal(dict): a
    # ``Signal(dict)`` emission converts the payload through QVariantMap,
    # which drops QPixmap values — receivers got ``{}`` (verified:
    # ``_pythonToCppCopy: Cannot copy-convert (dict)``). ``object``
    # delivers the dict intact. The presenter-side ``thumbnailsUpdated``
    # is still ``Signal(dict)`` (A-shell owns it) — see the coordinator.
    thumbnailsGenerated = Signal(object)
    thumbnailReady = Signal(int, QPixmap)
    generationFinished = Signal()

    def __init__(self):
        super().__init__()
        # Single cancellation token: bumped by every new wave and by
        # cancel(). Workers capture the value at queue time; completions
        # whose token mismatches the current one are stale and dropped on
        # arrival. Replaces the old `_is_generating` + `_generation_cancelled`
        # bool pair and the log-only `_current_task_id`.
        self._generation = 0
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
        # I4 generation-scoped feed: window snapshot captured per
        # generation at queue time (never the live window). Same-generation
        # completions outside their captured window drop on arrival;
        # stale-generation completions always drop via the token above.
        # Missing entry = unknown (additional-only wave before any initial
        # queue, or a pruned ancestor) → fail-open, apply everything.
        self._generation_windows: dict[int, frozenset] = {}
        # Bulk-revive accumulator: pixmaps of the live generation for the
        # atomic ``thumbnailsGenerated`` replace on wave completion.
        # Cleared on every new wave / retire / cancel / teardown.
        self._generation_pixmaps: dict[int, QPixmap] = {}
        # Frame-count owner is the editor service (``ceil(duration * fps) + 1``
        # off its ``get_duration``). When the coordinator injects it via
        # :meth:`set_frame_count_source`, :meth:`_get_frame_count` derives
        # through it and never owns a fourth formula; None = fall back to
        # the recording formula below (fail-open).
        self._frame_count_source = None
        # Z4 zoom-aware membership: coordinator-pushed snapshot of the
        # current visible window (+margin). Same-generation completions
        # outside it drop on arrival in _on_thumbnail_generated. None =
        # unknown → apply everything (fail-open, today's behavior). The
        # generation token stays the single cancel source — this is an
        # additional filter, never a replacement.
        self._visible_window = None
        self._thumbnail_size = (160, 90)
        self._thumbnail_render_scale = DEFAULT_THUMBNAIL_RENDER_SCALE
        self._render_snapshot: Optional[Callable[..., Optional[Image.Image]]] = None
        self._render_snapshot_async: Optional[Callable[..., None]] = None
        self._auto_crop = False
        self._active_workers = 0
        self._fps = 60
        # P2 persistent disk cache of finished thumbnails. Lazily built on
        # first use (construction touches the filesystem); a None set via
        # set_thumbnail_disk_cache() disables it for the service lifetime.
        self._thumbnail_disk_cache = None
        self._thumbnail_disk_cache_unavailable = False

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
            ic_video_debug("thumb_svc generate ENTRY gen=%s pending=%s generated=%s priority_len=%s target=%s fps=%s", self._generation, len(self._pending_indices), len(self._generated_indices), len(priority_indices) if priority_indices else 0, target_count, fps)
        except Exception:
            pass
        # Every new wave retires any in-flight one: bump the single
        # generation token so stale worker completions drop on arrival
        # (a resize-triggered refresh preempts the previous wave instead
        # of returning -1 forever). No poison flag, so no reset needed on
        # the additional path.
        self._generation += 1
        generation = self._generation
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_svc generate NEW gen=%s pending_clear %s->0", generation, len(self._pending_indices))
        except Exception:
            pass
        self._pending_indices.clear()

        self._recording = self._coerce_recording(recording)
        self._thumbnail_size = thumbnail_size
        self._auto_crop = auto_crop
        self._fps = max(1, int(fps))
        self._generated_indices.clear()
        self._generation_pixmaps.clear()

        count = self._get_frame_count()
        indices_to_generate = self._build_initial_indices(
            count=count,
            target_count=target_count,
            priority_indices=priority_indices,
        )
        # I4: capture this generation's window at queue time. The
        # completion filter reads this snapshot, never ``_visible_window``.
        self._generation_windows[generation] = frozenset(indices_to_generate)
        self._prune_generation_windows(keep=8)

        self._active_workers = len(indices_to_generate)
        try:
            from tabs.image_compare.debug import ic_video_debug, ic_perf_debug
            ic_video_debug("thumb_svc generate gen=%s count=%s target=%s fps=%s queue=%s indices=%s", generation, count, target_count, self._fps, len(indices_to_generate), indices_to_generate[:12])
            ic_perf_debug("thumbnails_generate gen=%s count=%s target=%s fps=%s queue=%s pool_max=%s", generation, count, target_count, self._fps, len(indices_to_generate), self._thread_pool.maxThreadCount())
        except Exception:
            pass
        _thlog.debug(
            "thumbnails_generate gen=%s count=%s target=%s fps=%s queue=%s",
            generation,
            count,
            target_count,
            self._fps,
            len(indices_to_generate),
        )
        if self._active_workers <= 0:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc generate EMPTY queue gen=%s", generation)
            except Exception:
                pass
            self.generationFinished.emit()
            return generation

        for idx in indices_to_generate:
            self._queue_thumbnail_worker(
                idx,
                priority=0,
                track_finish=True,
            )

        return generation

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
            ic_video_debug("thumb_svc additional ENTRY gen=%s pending=%s generated=%s req=%s fps_in=%s", self._generation, len(self._pending_indices), len(self._generated_indices), indices[:12] if indices else [], fps)
        except Exception:
            pass
        # No poison reset: the generation token makes stale arrivals drop
        # on their own, so additional waves queue under the live token.
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
        # I4: additional queues extend the live generation's captured
        # window (union) — they are part of the same generation's queueing,
        # so their completions must survive the membership filter.
        live_window = self._generation_windows.get(self._generation)
        if live_window is None:
            self._generation_windows[self._generation] = frozenset(
                needed_indices
            )
        else:
            self._generation_windows[self._generation] = (
                live_window | frozenset(needed_indices)
            )
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

    def _generate_single_thumbnail(
        self,
        index: int,
        thumbnail_size: Tuple[int, int],
        auto_crop: bool,
        render_scale: float,
        fps: int,
        progress_callback,
        recording=None,
        render_snapshot=None,
    ):
        """Генерирует одно превью и возвращает PIL Image.

        ``recording`` / ``fps`` / ``render_snapshot`` are the queue-time
        capture threaded through the worker payload by
        :meth:`_queue_thumbnail_worker` — this path never reads the live
        ``self._recording`` / ``self._fps``. A ``None`` capture (direct
        call outside the queue path) fails closed to a miss: no thumbnail
        is better than one rendered from the wrong generation's params.
        """
        try:
            if recording is None or render_snapshot is None:
                _thlog.debug(
                    "thumbnail_worker_drop index=%s reason=no-capture",
                    index,
                )
                return None
            _thlog.debug("thumbnail_worker_start index=%s fps=%s", index, fps)
            snap = recording.evaluate_at(float(index) / float(max(1, fps)))
            result = _render_thumbnail_using_renderer(
                snap,
                thumbnail_size,
                auto_crop,
                render_scale,
                render_snapshot,
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
        provider = getattr(self, "_frame_count_source", None)
        if callable(provider):
            try:
                provided = int(provider())
            except Exception:
                _thlog.debug("frame_count provider raised; failing open")
                provided = 0
            if provided > 0:
                return provided
            _thlog.debug(
                "frame_count provider non-positive; failing open to recording"
            )
        if not self._recording:
            _thlog.debug("frame_count with no recording reads as empty")
            return 0
        duration = self._recording.get_duration()
        if duration <= 0:
            return 1
        return max(1, int(math.ceil(duration * self._fps)) + 1)

    def set_frame_count_source(self, provider) -> None:
        """Inject the dialog's frame-count owner (the editor service).

        The editor service owns ``ceil(duration * fps) + 1`` off its
        ``get_duration``; this service only derives through the provider.
        A None/non-callable provider — or any provider doubt (raising,
        non-positive) — falls back to the recording formula in
        :meth:`_get_frame_count` (fail-open, today's behavior).
        """
        self._frame_count_source = provider if callable(provider) else None

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

    def set_thumbnail_disk_cache(self, cache) -> None:
        """Inject the persistent thumbnail disk cache (None disables it).

        Public API additions only — ``generate_thumbnails``,
        ``generate_additional_thumbnails``, ``cancel`` and the
        ``set_snapshot_renderer*`` signatures are unchanged; P3 drives the
        cache through those same methods.
        """
        self._thumbnail_disk_cache = cache
        self._thumbnail_disk_cache_unavailable = cache is None

    def _ensure_thumbnail_disk_cache(self):
        if self._thumbnail_disk_cache is not None:
            return self._thumbnail_disk_cache
        if self._thumbnail_disk_cache_unavailable:
            return None
        try:
            self._thumbnail_disk_cache = ThumbnailDiskCache()
        except Exception:
            logger.debug(
                "Thumbnail disk cache unavailable; continuing without it",
                exc_info=True,
            )
            self._thumbnail_disk_cache_unavailable = True
            return None
        return self._thumbnail_disk_cache

    def _thumbnail_cache_key_for_index(
        self,
        index: int,
        *,
        fps: int,
        recording,
        auto_crop: bool,
        thumbnail_size: Tuple[int, int],
        render_scale: float,
    ):
        """``(cache, key)`` for ``index`` — ``(None, None)`` on any doubt.

        Pure function of the queue-time capture (I5): every component —
        index, fps, recording, autocrop, target, render scale — is passed
        in, never read live. A mid-flight ``self._fps`` / ``self._recording``
        change cannot shift a queued worker's key under it.
        """
        try:
            cache = self._ensure_thumbnail_disk_cache()
            if cache is None or recording is None:
                return None, None
            snap = recording.evaluate_at(
                float(index) / float(max(1, int(fps)))
            )
            key = thumbnail_cache_key_for_snap(
                snap,
                index=index,
                fps=max(1, int(fps)),
                auto_crop=auto_crop,
                thumbnail_size=thumbnail_size,
                render_scale=render_scale,
            )
            if key is None:
                return None, None
            return cache, key
        except Exception:
            return None, None

    def _serve_thumbnail_from_disk_cache(
        self,
        index: int,
        generation: int,
        track_finish: bool,
        *,
        fps: int,
        recording,
        auto_crop: bool,
        thumbnail_size: Tuple[int, int],
        render_scale: float,
    ) -> bool:
        """Emit a cached thumbnail without starting a worker. True = served.

        Lookup uses the same queue-time capture as the worker payload, so
        a hit serves this generation's pixels, never a stale fps's.
        Hits skip the store (``store=False``) — rewriting identical bytes
        would only churn mtime.
        """
        try:
            cache, cache_key = self._thumbnail_cache_key_for_index(
                index,
                fps=fps,
                recording=recording,
                auto_crop=auto_crop,
                thumbnail_size=thumbnail_size,
                render_scale=render_scale,
            )
            if cache is None or cache_key is None:
                return False
            hit = cache.get(cache_key, expected_size=tuple(thumbnail_size))
        except Exception:
            return False
        if hit is None:
            return False
        _thlog.debug("thumbnail_cache_hit index=%s", index)
        self._on_thumbnail_generated(index, hit, generation, store=False)
        if track_finish:
            self._on_worker_finished(generation)
        return True

    def _store_thumbnail_in_disk_cache(
        self, index: int, pil_image, *, cache=None, cache_key=None
    ) -> None:
        """Store a live-generation completion under its captured key.

        Must only be called past the stale-generation guard in
        :meth:`_on_thumbnail_generated` — stale completions return there
        and never reach this store. A missing captured key fails closed
        (skip + debug log): storing under a rebuilt live key could poison
        the cache with another generation's pixels.
        """
        try:
            if cache is None or cache_key is None:
                _thlog.debug(
                    "thumbnail_cache_store_skip index=%s reason=no-capture",
                    index,
                )
                return
            if cache.put(cache_key, pil_image):
                _thlog.debug("thumbnail_cache_store index=%s", index)
        except Exception:
            pass

    def set_visible_window(self, indices) -> None:
        """Snapshot the coordinator's current visible window (+margin).

        Pushed by the coordinator on every visible refresh (initial wave
        and settled refreshes — never the idle-fill path), so
        :meth:`_on_thumbnail_generated` can drop same-generation
        completions that scrolled out of view. Empty/unknown input clears
        to None (fail-open: apply everything, today's behavior).
        """
        try:
            wanted = set(indices) if indices else None
        except Exception:
            wanted = None
        self._visible_window = wanted if wanted else None

    def _prune_generation_windows(self, keep: int = 8) -> None:
        """Bound the per-generation window snapshots (I4).

        The token already drops every ancestor's completions, so only
        recent entries matter; pruning keeps the dict from growing over a
        long dialog lifetime.
        """
        try:
            windows = self._generation_windows
            while len(windows) > max(1, int(keep)):
                oldest = min(windows)
                del windows[oldest]
        except Exception:
            pass

    def retire_in_flight_thumbnails(self) -> int:
        """Retire in-flight thumbnail workers without blocking.

        Bumps the single generation token so every worker queued before
        this call stale-drops its completion on arrival (both the pixmap
        in :meth:`_on_thumbnail_generated` and the counter in
        :meth:`_on_worker_finished`). Clears ``_pending_indices`` so the
        next refresh can re-queue overlapping indices immediately instead
        of waiting for the retired workers to drain, and resets
        ``_active_workers`` — no tracked (``track_finish=True``) wave is
        in flight after this call, and a retired wave must never emit
        ``generationFinished`` late.

        Unlike :meth:`cancel` this never blocks (no ``waitForDone``), so
        the viewport-change refresh path can call it on scroll settle.
        ``_generated_indices`` and the P2 disk cache are preserved: already
        finished thumbnails stay finished, and cache hits still emit
        instantly with no worker.

        Z4: this stays the ONLY token-bump path. The coordinator calls it
        on scroll/pan window changes and deliberately skips it on
        zoom-only refreshes (zoom reshuffles geometry, not content).
        """
        self._generation += 1
        self._pending_indices.clear()
        self._active_workers = 0
        # Retired pixels must never surface in a later bulk replace.
        self._generation_pixmaps.clear()
        self._prune_generation_windows(keep=8)
        return self._generation

    def _build_initial_indices(
        self,
        *,
        count: int,
        target_count: int,
        priority_indices: List[int] | None,
    ) -> List[int]:
        """P3 wave discipline: visible-window-exact initial wave.

        When the coordinator passes a non-empty visible window
        (``priority_indices``), the initial queue is exactly that window —
        no fallback spread is appended on top. The remainder of the strip
        follows at idle via ``generate_additional_thumbnails`` (queued by
        the coordinator on ``generationFinished``).

        The ``<= 12`` capped fallback below runs ONLY for the
        genuinely-unknown case: no view/timeline visible window (empty
        ``priority_indices``). It spreads a bounded probe over ``count``
        so the strip still paints something when the viewport is not
        known yet.
        """
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
        # Capture the live token: the wave bumped `self._generation` before
        # queueing, so every worker of this wave carries the same value and
        # any wave/cancel that bumps it afterwards retires this worker's
        # completion. (Signature unchanged — callers/tests patch this hook.)
        generation = self._generation
        if index in self._pending_indices:
            return
        # I5 queue-time capture: snapshot fps/recording/renderers NOW so
        # the worker payload, the disk-cache key, and the completion store
        # all use one coherent params set even if the dialog changes fps
        # or swaps the recording mid-flight. This snapshot is the capture;
        # nothing below this point reads the live values for this index.
        queued_fps = self._fps
        queued_recording = self._recording
        queued_size = self._thumbnail_size
        queued_crop = self._auto_crop
        queued_scale = self._thumbnail_render_scale
        queued_render = self._render_snapshot
        queued_render_async = self._render_snapshot_async
        # P2: finished-thumbnail disk lookup before queueing — a hit emits
        # via the normal _on_thumbnail_generated path with no worker started.
        try:
            if self._serve_thumbnail_from_disk_cache(
                index,
                generation,
                track_finish,
                fps=queued_fps,
                recording=queued_recording,
                auto_crop=queued_crop,
                thumbnail_size=queued_size,
                render_scale=queued_scale,
            ):
                return
        except Exception:
            pass
        self._pending_indices.add(index)
        # The (cache, key) this completion must store under — computed
        # from the same capture, so the store can never poison the cache
        # with another generation's pixels.
        queued_cache, queued_key = self._thumbnail_cache_key_for_index(
            index,
            fps=queued_fps,
            recording=queued_recording,
            auto_crop=queued_crop,
            thumbnail_size=queued_size,
            render_scale=queued_scale,
        )

        if queued_render_async is not None:
            # Async path: the worker submits the GPU render and returns
            # right away, freeing the (single) pool thread to start the
            # next thumbnail's CPU prep instead of sitting blocked on the
            # GPU round-trip. Completion bookkeeping (_on_thumbnail_generated
            # / _on_worker_finished) happens from the callback once the
            # render actually finishes, not when this worker returns.
            worker = GenericWorker(
                self._start_single_thumbnail_async,
                index,
                queued_size,
                queued_crop,
                queued_scale,
                queued_fps,
                track_finish,
                generation,
                queued_recording,
                queued_render_async,
                queued_cache,
                queued_key,
            )
            self._thread_pool.start(worker, priority=priority)
            return

        worker = GenericWorker(
            self._generate_single_thumbnail,
            index,
            queued_size,
            queued_crop,
            queued_scale,
            queued_fps,
            None,
            queued_recording,
            queued_render,
        )
        worker.signals.result.connect(
            lambda result, i=index, g=generation, c=queued_cache, k=queued_key: self._on_thumbnail_generated(
                i, result, g, cache=c, cache_key=k
            )
        )
        if track_finish:
            worker.signals.finished.connect(
                lambda g=generation: self._on_worker_finished(g)
            )
        self._thread_pool.start(worker, priority=priority)

    def _start_single_thumbnail_async(
        self,
        index: int,
        thumbnail_size: Tuple[int, int],
        auto_crop: bool,
        render_scale: float,
        fps: int,
        track_finish: bool,
        generation: int,
        recording=None,
        render_async=None,
        cache=None,
        cache_key=None,
    ) -> None:
        """Runs on the background pool thread; must not block on the GPU.

        ``recording`` / ``render_async`` / ``(cache, cache_key)`` are the
        queue-time capture — this path never reads the live
        ``self._recording`` / ``self._fps``. A missing capture fails closed
        through the error path (drop, never a wrong thumbnail).
        """
        try:
            _thlog.debug(
                "thumbnail_worker_start index=%s fps=%s async=True", index, fps
            )
            if recording is None or render_async is None:
                raise RuntimeError(
                    "Thumbnail capture (recording/renderer) is not configured"
                )
            snap = recording.evaluate_at(float(index) / float(max(1, fps)))
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
                self._on_thumbnail_generated(
                    index, result, generation, cache=cache, cache_key=cache_key
                )
                if track_finish:
                    self._on_worker_finished(generation)

            render_async(
                snap, target_w, target_h, _on_rendered, auto_crop=auto_crop
            )
        except Exception as e:
            logger.error(
                f"Error starting async thumbnail at index {index}: {e}", exc_info=True
            )
            self._on_thumbnail_generated(index, None, generation)
            if track_finish:
                self._on_worker_finished(generation)

    def _on_thumbnail_generated(
        self,
        index: int,
        pil_image,
        generation: int | None = None,
        *,
        cache=None,
        cache_key=None,
        store: bool = True,
    ):
        """Completion for ``(generation, index)`` — drop on mismatch.

        Stale-generation completions always drop. Same-generation
        completions drop when outside the CAPTURED window for that
        generation (the snapshot taken at queue time, never the live
        ``_visible_window`` — a zoom remap may move the live window while
        the wave stays valid per Z4). A missing captured entry (legacy
        direct call, additional-only wave, pruned ancestor) fails open and
        applies — fail-open for DELIVERY. Identity stays fail-closed: the
        store only ever uses the captured ``(cache, cache_key)``.
        """
        self._pending_indices.discard(index)
        if generation is not None and generation != self._generation:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc _on_generated DROP stale gen=%s live=%s idx=%s", generation, self._generation, index)
            except Exception:
                pass
            return
        # I4 membership filter on top of the generation token (never a
        # replacement): same-generation but outside the captured window —
        # e.g. a zoom-driven refresh kept the wave alive while the window
        # moved. Fail-open: unknown window or any doubt → apply (today's
        # behavior).
        if generation is not None:
            captured = self._generation_windows.get(generation)
            if captured is not None:
                try:
                    outside = index not in captured
                except Exception:
                    outside = False
                if outside:
                    try:
                        from tabs.image_compare.debug import ic_video_debug
                        ic_video_debug("thumb_svc _on_generated DROP outside-captured-window idx=%s gen=%s live=%s window=%s", index, generation, self._generation, len(captured))
                    except Exception:
                        pass
                    return
        else:
            window = getattr(self, "_visible_window", None)
            if window is not None:
                try:
                    outside = index not in window
                except Exception:
                    outside = False
                if outside:
                    try:
                        from tabs.image_compare.debug import ic_video_debug
                        ic_video_debug("thumb_svc _on_generated DROP outside-window idx=%s gen=%s live=%s window=%s", index, generation, self._generation, len(window))
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
                # P2: store the finished image under the captured key —
                # stale generations returned above and never store, and a
                # missing capture fails closed (skip, never a live rebuild).
                if store:
                    self._store_thumbnail_in_disk_cache(
                        index, pil_image, cache=cache, cache_key=cache_key
                    )
                data = pil_image.tobytes("raw", "RGBA")
                qimg = QImage(
                    data,
                    pil_image.width,
                    pil_image.height,
                    QImage.Format.Format_RGBA8888,
                )
                pixmap = QPixmap.fromImage(qimg.copy())

                self._generated_indices.add(index)
                # Bulk-revive accumulator: the wave completion below emits
                # the full dict as one atomic generation replace (I4).
                # Only the live generation accumulates — stale generations
                # returned above, so anything here belongs to it (or to a
                # legacy None-generation direct call, which also applies).
                if generation is None or generation == self._generation:
                    self._generation_pixmaps[index] = pixmap
                self.thumbnailReady.emit(index, pixmap)
            except Exception as e:
                logger.error(f"Error converting thumbnail {index}: {e}")

    def _on_worker_finished(self, generation: int | None = None):
        if generation is not None and generation != self._generation:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc _on_worker_finished DROP stale gen=%s live=%s", generation, self._generation)
            except Exception:
                pass
            return
        self._active_workers -= 1
        _thlog.debug("thumbnail_worker_finished active=%s", self._active_workers)
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_svc _on_worker_finished active=%s gen=%s", self._active_workers, self._generation)
        except Exception:
            pass

        if self._active_workers <= 0:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_svc generationFinished emit active=%s", self._active_workers)
            except Exception:
                pass
            self._active_workers = 0
            # I4 bulk revive: the tracked wave completed — emit the full
            # dict as one atomic generation replace (Signal(object): a
            # Signal(dict) would QVariantMap-convert the QPixmap values
            # away — receivers got ``{}``). The coordinator applies it via
            # ``timeline.set_thumbnails``. Empty payloads never emit: a
            # fully-dropped wave must not wipe the strip with ``{}``.
            # (Additional/idle-track completions keep their own
            # ``thumbnailReady`` upserts; they never re-emit this finish.)
            payload = dict(self._generation_pixmaps)
            self._generation_pixmaps.clear()
            if payload:
                try:
                    from tabs.image_compare.debug import ic_video_debug
                    ic_video_debug("thumb_svc thumbnailsGenerated emit count=%s", len(payload))
                except Exception:
                    pass
                _thlog.debug("thumbnails_generated_bulk count=%s", len(payload))
                self.thumbnailsGenerated.emit(payload)
            self.generationFinished.emit()

    def cancel(self):
        # Retire the live wave: bump the token so any worker that finishes
        # after this point drops its result on arrival.
        self._generation += 1
        self._pending_indices.clear()
        self._active_workers = 0
        self._generation_pixmaps.clear()
        self._prune_generation_windows(keep=8)
        self._thread_pool.waitForDone(500)

    def teardown(self) -> None:
        """Dialog-lifetime end: retire the live wave and release state.

        Bumps the single generation token (the same cancel source as
        :meth:`cancel` / :meth:`retire_in_flight_thumbnails` — never a
        second flag), clears the pending + finished sets so a later dialog
        starts clean, drops the visible-window filter, and releases the
        recording reference (``_recording`` lifetime is bound to the dialog
        lifetime). Blocks briefly for in-flight workers to drain, like
        :meth:`cancel`.
        """
        self._generation += 1
        self._pending_indices.clear()
        self._generated_indices.clear()
        self._generation_pixmaps.clear()
        self._generation_windows.clear()
        self._visible_window = None
        self._recording = None
        self._active_workers = 0
        try:
            self._thread_pool.waitForDone(500)
        except Exception:
            pass