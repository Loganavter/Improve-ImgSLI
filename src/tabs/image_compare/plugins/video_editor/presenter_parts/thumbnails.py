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