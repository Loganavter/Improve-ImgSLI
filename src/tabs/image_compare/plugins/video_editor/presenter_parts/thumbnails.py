import logging
from typing import Callable, Dict, List

from PySide6.QtGui import QPixmap
from sli_ui_toolkit.managers import SettleGate

from .common import VIDEO_EDITOR_AUTO_CROP

logger = logging.getLogger("ImproveImgSLI")


class ThumbnailCoordinator:
    def __init__(
        self,
        view,
        editor_service,
        playback_engine,
        thumbnail_service,
        emit_thumbnails_updated: Callable[[Dict[int, QPixmap]], None],
        timer_parent=None,
    ):
        self.view = view
        self.editor_service = editor_service
        self.playback_engine = playback_engine
        self.thumbnail_service = thumbnail_service
        self.emit_thumbnails_updated = emit_thumbnails_updated

        # Coalesce resize + scrollbar-range churn while the window is dragged.
        # Deliberately settles later than PreviewCoordinator's gate (120ms):
        # both do a blocking main-thread GPU render on settle, and if they
        # land on the same tick the second one queues up behind the first,
        # showing up as one long stall instead of two short ones.
        self._visible_refresh = SettleGate(
            on_settle=self._refresh_visible_thumbnails,
            interval_ms=SettleGate.DEFAULT_INTERVAL_MS * 2,
            parent=timer_parent,
        )
        # P3 wave discipline: last visible window handed to the service.
        # The settled refresh compares against it and retires in-flight
        # workers only when the wanted set actually changed — same window
        # re-settling (e.g. repeated resizes without scrolling) must not
        # bump the generation token. None = no baseline yet (no retire).
        self._last_visible_indices: List[int] | None = None
        # Z4 zoom-aware refresh: last timeline zoom scalar seen. A refresh
        # where the zoom changed is zoom-driven (geometry reshuffled, content
        # identical) and must NOT retire the in-flight wave — completions are
        # index-addressed (P3), so they stay valid. Scroll/pan (window moved,
        # zoom unchanged) retires as before. None = no baseline yet.
        self._last_zoom_level: float | None = None

    def detach_view(self):
        self._visible_refresh.cancel()
        self.view = None

    def calculate_optimal_thumbnail_count(self) -> int:
        if self.view is None or not hasattr(self.view, "timeline"):
            return 50

        timeline = self.view.timeline
        content_height = timeline.height() - timeline.RULER_HEIGHT
        if content_height <= 0:
            return 50

        aspect_ratio = 16.0 / 9.0
        tile_width = content_height * aspect_ratio

        if not timeline.has_snapshots():
            return 50

        total_duration = timeline.get_total_duration()
        px_per_sec = timeline.get_pixels_per_second()
        logical_width = total_duration * px_per_sec
        if logical_width <= 0 or tile_width <= 0:
            return 50

        visible_count = int(logical_width / tile_width) + 2
        return max(20, min(visible_count, 200))

    def generate_thumbnails(self):
        self._visible_refresh.cancel()
        try:
            from tabs.image_compare.debug import ic_video_debug
            tl = getattr(self.view, "timeline", None) if self.view is not None else None
            ic_video_debug("thumb_coord generate_thumbnails view=%s timeline=%s h=%s has_snapshots=%s total_frames=%s", bool(self.view), bool(tl), getattr(tl, "height", lambda: -1)() if tl else -1, bool(getattr(tl, "has_snapshots", lambda: False)() if tl else False), self.editor_service.get_frame_count() if self.editor_service else -1)
        except Exception:
            pass
        if self.view is not None and hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "clear_thumbnails"
        ):
            self.view.timeline.clear_thumbnails()

        recording = self.editor_service.get_current_recording()
        if not recording:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_coord generate_thumbnails ABORT no recording")
            except Exception:
                pass
            return

        vis = self.get_visible_frame_indices()
        cnt = self.calculate_optimal_thumbnail_count()
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_coord generate_thumbnails target=%s vis_len=%s vis=%s fps=%s", cnt, len(vis), vis[:12], self.editor_service.get_fps())
        except Exception:
            pass
        self.thumbnail_service.generate_thumbnails(
            recording,
            target_count=cnt,
            auto_crop=True,
            priority_indices=vis,
            fps=self.editor_service.get_fps(),
        )
        self._last_visible_indices = list(vis)
        self._last_zoom_level = self._read_zoom_level()
        push_window = getattr(
            self.thumbnail_service, "set_visible_window", None
        )
        if callable(push_window):
            push_window(vis)

    def on_single_thumbnail_ready(self, index: int, pixmap: QPixmap):
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_coord on_single_ready idx=%s has_view=%s", index, bool(self.view))
        except Exception:
            pass
        if self.view is not None and hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "add_thumbnail"
        ):
            self.view.timeline.add_thumbnail(index, pixmap)

    def on_thumbnails_generated(self, thumbnails: Dict[int, QPixmap]):
        self.emit_thumbnails_updated(thumbnails)

    def on_thumbnails_generation_finished(self):
        # P3 idle fill: the initial wave covered the visible window only
        # (visible-window-exact queue). Queue every still-unseen index at
        # background priority — generate_additional runs them at lower pool
        # priority and consults the P2 disk cache first, so a warm
        # remainder costs ~zero. track_finish=False there means this fill
        # never re-emits generationFinished: no loop, no second scheduler.
        try:
            if self.editor_service is None:
                return None
            total_frames = self.editor_service.get_frame_count()
            generated = set(
                getattr(self.thumbnail_service, "_generated_indices", None)
                or ()
            )
            pending = set(
                getattr(self.thumbnail_service, "_pending_indices", None) or ()
            )
            if not isinstance(total_frames, int) or total_frames <= 0:
                return None
            remainder = [
                i
                for i in range(total_frames)
                if i not in generated and i not in pending
            ]
            if remainder:
                self.thumbnail_service.generate_additional_thumbnails(
                    remainder,
                    fps=self.editor_service.get_fps(),
                )
        except Exception:
            logger.debug("Idle thumbnail remainder fill skipped", exc_info=True)
        return None

    def on_timeline_viewport_changed(self):
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_coord viewportChanged ping gate_pending=%s", self._visible_refresh.is_pending())
        except Exception:
            pass
        self._visible_refresh.ping()

    def on_timeline_resized(self):
        # Do not queue GPU thumbnails while the strip is refitting; settle first.
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_coord resized ping gate_pending=%s", self._visible_refresh.is_pending())
        except Exception:
            pass
        self._visible_refresh.ping()

    def on_layout_settled(self):
        # Toolkit TimelineWidget emits layoutSettled after its own
        # _layout_settle (fit_view/update_fixed_width) finishes — at that
        # point get_visible_thumbnail_frame_indices returns a settled window.
        # Bypass the extra 240ms debounce and refresh immediately.
        try:
            from tabs.image_compare.debug import ic_video_debug
            ic_video_debug("thumb_coord layoutSettled cancel+refresh gate_pending=%s", self._visible_refresh.is_pending())
        except Exception:
            pass
        self._visible_refresh.cancel()
        self._refresh_visible_thumbnails()

    def _read_zoom_level(self) -> float | None:
        """Snapshot the timeline zoom scalar (None when unreadable).

        Prefers the ``_zoom_level`` scalar (the Z-T contract surface, stable
        across old per-tick and new coalesced commits — never assume
        exactly-1-commit-per-gesture), falling back to
        ``get_pixels_per_second``. None means "unknown": callers keep
        today's scroll-cancel behavior (fail-open).
        """
        try:
            tl = (
                getattr(self.view, "timeline", None)
                if self.view is not None
                else None
            )
            if tl is None:
                return None
            if hasattr(tl, "_zoom_level"):
                try:
                    return float(getattr(tl, "_zoom_level"))
                except (TypeError, ValueError):
                    pass
            getter = getattr(tl, "get_pixels_per_second", None)
            if callable(getter):
                try:
                    return float(getter())
                except (TypeError, ValueError):
                    return None
            return None
        except Exception:
            return None

    def _refresh_visible_thumbnails(self):
        # NOTE: TimelineWidget.resizeEvent already updates zoom/logical_width
        # synchronously, so visible window is fresh even while _layout_settle
        # is pending (that's only for update_layout_width). Previous guard
        # `if settle.is_pending(): return` deferred forever during drag and
        # caused the strip to die — see plan 2026-09-02 Phase 2.
        try:
            tl = getattr(self.view, "timeline", None) if self.view is not None else None
            settle = getattr(tl, "_layout_settle", None) if tl is not None else None
            if settle is not None and hasattr(settle, "is_pending") and settle.is_pending():
                try:
                    from tabs.image_compare.debug import ic_video_debug
                    ic_video_debug("thumb_coord _refresh layout_settle pending but proceed anyway (resizeEvent already fresh)")
                except Exception:
                    pass
        except Exception:
            pass
        visible_indices = self.get_visible_frame_indices()
        try:
            from tabs.image_compare.debug import ic_video_debug
            tl = getattr(self.view, "timeline", None) if self.view is not None else None
            zoom = getattr(tl, "_zoom_level", -1) if tl else -1
            lw = tl.get_pixels_per_second() if tl and hasattr(tl, "get_pixels_per_second") else -1
            ic_video_debug("thumb_coord _refresh vis_len=%s vis=%s zoom=%s pps=%s total=%s pending=%s generated=%s", len(visible_indices), visible_indices[:12], zoom, lw, self.editor_service.get_frame_count() if self.editor_service else -1, len(getattr(self.thumbnail_service, "_pending_indices", [])), len(getattr(self.thumbnail_service, "_generated_indices", [])))
        except Exception:
            pass
        if visible_indices:
            # P3 scroll-cancel: the refresh path queues same-generation
            # additional workers, so without a bump a scrolled-away wave
            # would still apply on arrival. When the wanted set changed,
            # retire it first — non-blocking (unlike cancel()), progress
            # in _generated_indices and the P2 disk cache survive, and
            # cache hits still emit instantly with no worker. Unchanged
            # window → no bump (debounce re-settles must not churn the
            # token); no baseline yet (None) → nothing to retire.
            # Z4 zoom-aware: a zoom change reshuffles geometry, not content
            # — completions are index-addressed (P3), so the in-flight wave
            # stays valid and must NOT retire (retiring here emptied the
            # strip on every wheel tick). Zoom-driven refresh requeues the
            # newly-visible indices and lets the membership filter in
            # _on_thumbnail_generated drop whatever scrolled out of view.
            current_zoom = self._read_zoom_level()
            zoom_changed = (
                self._last_zoom_level is not None
                and current_zoom is not None
                and current_zoom != self._last_zoom_level
            )
            if self._last_visible_indices is not None and set(
                visible_indices
            ) != set(self._last_visible_indices):
                should_retire = not zoom_changed
                try:
                    from tabs.image_compare.debug import ic_video_debug
                    ic_video_debug(
                        "thumb_coord _refresh zoom_vs_pan zoom_changed=%s zoom=%s last_zoom=%s retire=%s",
                        zoom_changed,
                        current_zoom,
                        self._last_zoom_level,
                        should_retire,
                    )
                except Exception:
                    pass
                if should_retire:
                    retire = getattr(
                        self.thumbnail_service, "retire_in_flight_thumbnails", None
                    )
                    if callable(retire):
                        retire()
            self._last_visible_indices = list(visible_indices)
            self._last_zoom_level = current_zoom
            push_window = getattr(
                self.thumbnail_service, "set_visible_window", None
            )
            if callable(push_window):
                push_window(visible_indices)
            self.thumbnail_service.generate_additional_thumbnails(
                visible_indices,
                fps=self.editor_service.get_fps(),
            )
        else:
            try:
                from tabs.image_compare.debug import ic_video_debug
                ic_video_debug("thumb_coord _refresh EMPTY no indices queued")
            except Exception:
                pass

    def get_visible_frame_indices(self, margin: int = 2) -> List[int]:
        if self.view is None or not hasattr(self.view, "timeline"):
            return []

        total_frames = self.editor_service.get_frame_count()
        if total_frames == 0:
            return []

        try:
            timeline = self.view.timeline
            if hasattr(timeline, "get_visible_thumbnail_frame_indices"):
                return [
                    idx
                    for idx in timeline.get_visible_thumbnail_frame_indices(
                        overscan_blocks=margin
                    )
                    if 0 <= idx < total_frames
                ]

            current_frame = self.playback_engine.get_current_frame()
            visible_range = 5
            start_idx = max(0, current_frame - visible_range - margin)
            end_idx = min(total_frames, current_frame + visible_range + margin)
            return list(range(start_idx, end_idx))
        except Exception as exc:
            logger.debug(f"Error calculating visible frames: {exc}")
            return list(range(min(10, total_frames)))

    def cleanup(self):
        self._visible_refresh.cancel()
        self.thumbnail_service.cancel()