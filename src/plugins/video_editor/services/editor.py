from __future__ import annotations

import math
import logging
from dataclasses import replace
from typing import Any

from plugins.video_editor.services.keyframes import FrameSnapshot, KeyframedRecording

logger = logging.getLogger("ImproveImgSLI")

class VideoEditorService:
    def __init__(self, initial_snapshots: list[Any], fps: int = 60):
        self._source_recording = None
        if hasattr(initial_snapshots, "evaluate_at") and hasattr(
            initial_snapshots, "get_duration"
        ):
            self._source_recording = initial_snapshots
            self._current_snapshots = None
        else:
            self._current_snapshots = list(initial_snapshots or [])
        self._fps = max(1, int(fps))
        self._cut_timestamps: list[float] = []
        self._undo_stack: list[tuple[list[FrameSnapshot], list[float]]] = []
        self._redo_stack: list[tuple[list[FrameSnapshot], list[float]]] = []
        self._cached_recording: KeyframedRecording | None = None
        self._cached_materialized_snapshots: list[FrameSnapshot] | None = None

    def _invalidate_caches(self) -> None:
        self._cached_recording = None
        self._cached_materialized_snapshots = None

    def _ensure_materialized_snapshots(self) -> list[FrameSnapshot]:
        if self._current_snapshots is None:
            if self._source_recording is not None:
                self._current_snapshots = self._source_recording.materialize_snapshots()
            else:
                self._current_snapshots = []
        return self._current_snapshots

    def set_fps(self, fps: int):
        new_fps = max(1, int(fps))
        if new_fps == self._fps:
            return
        self._fps = new_fps
        self._invalidate_caches()

    def get_fps(self) -> int:
        return self._fps

    def get_frame_count(self):
        duration = self.get_duration()
        if duration <= 0:
            snapshots = self._current_snapshots
            return 0 if not snapshots else 1
        return max(1, int(math.ceil(duration * self._fps)) + 1)

    def get_snapshot_at(self, index):
        timestamp = self.get_time_for_frame(index)
        return self.get_snapshot_at_time(timestamp)

    def get_snapshot_at_time(self, timestamp: float):
        recording = self.get_current_recording()
        if not recording:
            return None
        return recording.evaluate_at(timestamp)

    def get_time_for_frame(self, frame_index: int) -> float:
        if frame_index <= 0:
            return 0.0
        if self._fps <= 0:
            return 0.0
        return min(float(frame_index) / float(self._fps), self.get_duration())

    def get_frame_for_time(self, timestamp: float) -> int:
        if self._fps <= 0:
            return 0
        return max(0, min(int(round(max(0.0, timestamp) * self._fps)), max(0, self.get_frame_count() - 1)))

    def get_current_snapshots(self):
        if self._cached_materialized_snapshots is None:
            self._cached_materialized_snapshots = list(
                self._ensure_materialized_snapshots()
            )
        return self._cached_materialized_snapshots

    def get_current_recording(self) -> KeyframedRecording:
        if self._cached_recording is None:
            source_fps = (
                max(1, int(getattr(self._source_recording, "fps", self._fps)))
                if self._source_recording is not None
                else self._fps
            )
            if (
                self._source_recording is not None
                and self._current_snapshots is None
                and not self._cut_timestamps
                and source_fps == self._fps
            ):
                self._cached_recording = self._source_recording
            else:
                self._cached_recording = KeyframedRecording.from_snapshots(
                    self._ensure_materialized_snapshots(), fps=self._fps
                )
                self._cached_recording.apply_cut_markers(self._cut_timestamps)
        return self._cached_recording

    def get_timeline_model(self):
        return self.get_current_recording().timeline

    def get_duration(self) -> float:
        if self._current_snapshots is not None:
            if not self._current_snapshots:
                return 0.0
            return float(self._current_snapshots[-1].timestamp)
        if self._source_recording is not None:
            return float(self._source_recording.get_duration())
        return 0.0

    def delete_selection(self, start_idx: int, end_idx: int):
        snapshots = self._ensure_materialized_snapshots()
        if not snapshots:
            return False

        start_frame = max(0, min(start_idx, end_idx))
        end_frame = max(0, max(start_idx, end_idx))
        start_time = self.get_time_for_frame(start_frame)
        end_time = self.get_time_for_frame(end_frame)
        if end_time < start_time:
            start_time, end_time = end_time, start_time

        self._undo_stack.append((list(snapshots), list(self._cut_timestamps)))
        self._redo_stack.clear()

        before = [
            snapshot
            for snapshot in snapshots
            if float(snapshot.timestamp) < start_time
        ]
        after = [
            snapshot
            for snapshot in snapshots
            if float(snapshot.timestamp) > end_time
        ]
        if len(before) == len(snapshots) and len(after) == len(snapshots):
            self._undo_stack.pop()
            return False

        shift = 0.0
        seam_timestamp = None
        if after:
            first_after_timestamp = float(after[0].timestamp)
            seam_timestamp = 0.0 if not before else start_time
            shift = first_after_timestamp - seam_timestamp
            after = [
                replace(snapshot, timestamp=float(snapshot.timestamp) - shift)
                for snapshot in after
            ]

        self._current_snapshots = before + after

        updated_cut_timestamps: list[float] = []
        for ts in self._cut_timestamps:
            ts = float(ts)
            if ts < start_time:
                updated_cut_timestamps.append(ts)
                continue
            if shift > 0.0 and ts >= end_time:
                updated_cut_timestamps.append(ts - shift)

        if seam_timestamp is not None and before and after:
            updated_cut_timestamps = [
                ts
                for ts in updated_cut_timestamps
                if not math.isclose(float(ts), seam_timestamp, abs_tol=1e-9)
            ]
            updated_cut_timestamps.append(seam_timestamp)

        self._cut_timestamps = sorted(updated_cut_timestamps)
        self._invalidate_caches()
        return True

    def undo(self):
        if not self._undo_stack:
            return False

        self._redo_stack.append((list(self._ensure_materialized_snapshots()), list(self._cut_timestamps)))
        self._current_snapshots, self._cut_timestamps = self._undo_stack.pop()
        self._invalidate_caches()
        return True

    def redo(self):
        if not self._redo_stack:
            return False

        self._undo_stack.append((list(self._ensure_materialized_snapshots()), list(self._cut_timestamps)))
        self._current_snapshots, self._cut_timestamps = self._redo_stack.pop()
        self._invalidate_caches()
        return True

    def can_undo(self):
        return len(self._undo_stack) > 0

    def can_redo(self):
        return len(self._redo_stack) > 0
