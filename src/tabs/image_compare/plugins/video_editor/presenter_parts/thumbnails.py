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
        self._visible_refresh = SettleGate(
            on_settle=self._refresh_visible_thumbnails,
            interval_ms=SettleGate.DEFAULT_INTERVAL_MS,
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
        if self.view is not None and hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "clear_thumbnails"
        ):
            self.view.timeline.clear_thumbnails()

        recording = self.editor_service.get_current_recording()
        if not recording:
            return

        self.thumbnail_service.generate_thumbnails(
            recording,
            target_count=self.calculate_optimal_thumbnail_count(),
            auto_crop=VIDEO_EDITOR_AUTO_CROP,
            priority_indices=self.get_visible_frame_indices(),
            fps=self.editor_service.get_fps(),
        )

    def on_single_thumbnail_ready(self, index: int, pixmap: QPixmap):
        if self.view is not None and hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "add_thumbnail"
        ):
            self.view.timeline.add_thumbnail(index, pixmap)

    def on_thumbnails_generated(self, thumbnails: Dict[int, QPixmap]):
        self.emit_thumbnails_updated(thumbnails)

    def on_thumbnails_generation_finished(self):
        return None

    def on_timeline_viewport_changed(self):
        self._visible_refresh.ping()

    def on_timeline_resized(self):
        # Do not queue GPU thumbnails while the strip is refitting; settle first.
        self._visible_refresh.ping()

    def _refresh_visible_thumbnails(self):
        visible_indices = self.get_visible_frame_indices()
        if visible_indices:
            self.thumbnail_service.generate_additional_thumbnails(
                visible_indices,
                fps=self.editor_service.get_fps(),
            )

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
