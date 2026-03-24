from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QObject, QTimer

from plugins.video_editor.services.keyframes import FrameSnapshot, KeyframedRecording
from plugins.video_editor.services.track_defs import ViewportTrackSpec

logger = logging.getLogger("ImproveImgSLI")

class Recorder(QObject):
    def __init__(
        self,
        store,
        extra_specs: tuple[ViewportTrackSpec, ...] = (),
    ):
        super().__init__()
        self.store = store
        self._extra_specs = tuple(extra_specs)
        self.is_recording = False
        self.is_paused = False
        self.start_time = 0.0
        self.pause_start_time = 0.0
        self.total_paused_time = 0.0
        initial_fps = getattr(self.store.settings, "video_recording_fps", 60)
        self._recording = KeyframedRecording(
            fps=initial_fps,
            extra_specs=self._extra_specs,
        )

        self.sample_timer = QTimer(self)

        target_fps = getattr(self.store.settings, "video_recording_fps", 60)
        target_fps = max(10, min(144, target_fps))
        interval = int(1000 / target_fps)
        self.sample_timer.setInterval(interval)
        self.sample_timer.timeout.connect(self.capture_frame)

    @property
    def snapshots(self) -> list[FrameSnapshot]:
        return self._recording.materialize_snapshots()

    @property
    def keyframes(self):
        return self._recording.tracks

    @property
    def recording(self) -> KeyframedRecording:
        return self._recording

    def start(self):
        self.is_recording = True
        self.is_paused = False
        self.total_paused_time = 0.0
        self.start_time = time.time()

        target_fps = getattr(self.store.settings, "video_recording_fps", 60)
        target_fps = max(10, min(144, target_fps))
        self._recording = KeyframedRecording(
            fps=target_fps,
            extra_specs=self._extra_specs,
        )

        interval = int(1000 / target_fps)
        self.sample_timer.setInterval(interval)
        self.sample_timer.start()
        QTimer.singleShot(0, self.capture_frame)

    def stop(self, finalize: bool = True):
        self.is_recording = False
        self.is_paused = False
        self.sample_timer.stop()
        self.capture_frame(force_advance_frame=True)
        if finalize:
            self.finalize_recording()

    def has_recording_data(self) -> bool:
        return bool(self._recording.timeline.sample_timestamps)

    def finalize_recording(self) -> KeyframedRecording:
        self._recording.finalize_tail_keyframes()
        return self._recording

    def toggle_pause(self):
        if not self.is_recording:
            return False

        if self.is_paused:
            self.is_paused = False
            duration = time.time() - self.pause_start_time
            self.total_paused_time += duration
            self.sample_timer.start()
            logger.info("Recording resumed")
        else:
            self.is_paused = True
            self.pause_start_time = time.time()
            self.sample_timer.stop()
            logger.info("Recording paused")

        return self.is_paused

    def capture_frame(self, force_advance_frame: bool = False):
        if not self.store or self.is_paused:
            return

        elapsed = (time.time() - self.start_time) - self.total_paused_time
        if force_advance_frame:
            fps = max(1, int(getattr(self._recording, "fps", 60)))
            frame_duration = 1.0 / float(fps)
            if self._recording.timeline.sample_timestamps:
                elapsed = max(
                    elapsed,
                    float(self._recording.timeline.sample_timestamps[-1]) + frame_duration,
                )

        vp_snapshot = self.store.viewport.freeze_for_export()
        st_snapshot = self.store.settings.freeze_for_export()
        doc = self.store.document

        def get_path_at_index(img_list, index):
            if 0 <= index < len(img_list):
                try:
                    item = img_list[index]
                    if hasattr(item, "path"):
                        return item.path

                    if isinstance(item, (list, tuple)) and len(item) > 1:
                        return item[1]
                except (IndexError, TypeError, AttributeError):
                    return None
            return None

        snapshot = FrameSnapshot(
            timestamp=elapsed,
            viewport_state=vp_snapshot,
            settings_state=st_snapshot,
            image1_path=get_path_at_index(doc.image_list1, doc.current_index1),
            image2_path=get_path_at_index(doc.image_list2, doc.current_index2),
            name1=doc.get_current_display_name(1),
            name2=doc.get_current_display_name(2),
        )
        self._recording.append(snapshot)
