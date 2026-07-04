from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QTimer

from tabs.image_compare.video_editor.services.keyframing import (
    FrameSnapshot,
    KeyframeToolAdapter,
    KeyframedRecording,
)

logger = logging.getLogger("ImproveImgSLI")

class Recorder(QObject):
    def __init__(
        self,
        store,
        extra_adapters: tuple[KeyframeToolAdapter, ...] = (),
    ):
        super().__init__()
        self.store = store
        self._extra_adapters = tuple(extra_adapters)
        self.is_recording = False
        self.is_paused = False
        self.start_time = 0.0
        self.pause_start_time = 0.0
        self.total_paused_time = 0.0
        initial_fps = getattr(self.store.settings, "video_recording_fps", 60)
        self._recording = KeyframedRecording(
            fps=initial_fps,
            extra_adapters=self._extra_adapters,
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
            extra_adapters=self._extra_adapters,
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

        from dataclasses import replace

        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        live = registry.create_service("live_frame_snapshot", self.store)
        if live is None:
            vp_snapshot = self.store.viewport.freeze_for_export()
            st_snapshot = self.store.settings.freeze_for_export()
            snapshot = FrameSnapshot(
                timestamp=elapsed,
                viewport_state=vp_snapshot,
                settings_state=st_snapshot,
                sources=(),
                names=(),
            )
        else:
            snapshot = replace(live, timestamp=elapsed)
            vp_snapshot = snapshot.viewport_state
        try:
            from tabs.image_compare.video_editor.services.canvas_feature_gateway import (
                execute_canvas_feature_alias,
            )

            proxy = type("StoreProxy", (), {"viewport": vp_snapshot})()
            n_models = int(
                execute_canvas_feature_alias("overlay.total_count", proxy, default=0)
                or 0
            )
            enabled = bool(
                execute_canvas_feature_alias("overlay.enabled", proxy, default=False)
            )
            if n_models != getattr(self, "_last_recorded_mag_count", n_models) or enabled != getattr(self, "_last_recorded_mag_enabled", enabled):
                logger.debug(
                    "capture_frame: mag count=%d→%d, enabled=%s→%s at t=%.3f",
                    getattr(self, "_last_recorded_mag_count", n_models),
                    n_models,
                    getattr(self, "_last_recorded_mag_enabled", enabled),
                    enabled,
                    elapsed,
                )
            self._last_recorded_mag_count = n_models
            self._last_recorded_mag_enabled = enabled
        except Exception:
            pass
        self._recording.append(snapshot)
