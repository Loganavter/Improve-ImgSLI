import logging
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal

logger = logging.getLogger("ImproveImgSLI")

class PlaybackEngine(QObject):
    """Live-playback clock: SINGLE OWNER of fps and frame position.

    Ownership (ve-p3): fps lives here. ``VideoProjectModel.fps`` and
    ``VideoEditorService._fps`` are read-through mirrors seeded from the same
    initial value and re-synced at bootstrap
    (``use_cases/initialization.py``) and at playback start; the frame
    position lives in ``_current_frame``/``_range`` (frame position is not
    stored in the model — selection comes from the view).
    """

    frameChanged = Signal(int)
    playbackStateChanged = Signal(bool)

    def __init__(self, fps=60):
        super().__init__()
        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)

        self._current_frame = 0
        self._total_frames = 0
        self._range = (0, 0)
        self._fps = max(1, int(fps))
        self._playback_speed = 1.0
        self._is_playing = False
        self._play_started_at = 0.0
        self._play_started_frame = 0

        self._update_timer_interval()

    def set_fps(self, fps):
        self._fps = max(1, int(fps))
        self._update_timer_interval()
        if self._is_playing:
            self._restart_playback_clock()

    def get_fps(self):
        return self._fps

    @property
    def fps(self) -> int:
        """Read-through accessor for the owned fps (mirrors get_fps)."""
        return self._fps

    @fps.setter
    def fps(self, value) -> None:
        self.set_fps(value)

    def set_playback_speed(self, speed: float):
        self._playback_speed = max(0.01, float(speed))
        self._update_timer_interval()
        if self._is_playing:
            self._restart_playback_clock()

    def _update_timer_interval(self):
        effective_fps = max(0.01, self._fps * self._playback_speed)
        self._timer.setInterval(max(1, int(1000 / effective_fps)))

    def set_total_frames(self, total_frames):
        self._total_frames = max(0, int(total_frames))
        # A shortened timeline must pull the range and position back inside:
        # a stale end past the new total would otherwise play wrong-time
        # frames (time math clamps to duration, repeating the tail).
        self._range = self._clamp_range(self._range)
        self._current_frame = max(
            0, min(self._current_frame, max(0, self._total_frames - 1))
        )

    def _clamp_range(self, rng):
        try:
            start, end = int(rng[0]), int(rng[1])
        except (TypeError, ValueError):
            start, end = 0, 0
        start, end = max(0, start), max(0, end)
        if end < start:
            start, end = end, start
        if self._total_frames > 0:
            hi = self._total_frames - 1
            start, end = min(start, hi), min(end, hi)
        return (start, end)

    def set_range(self, start, end):
        # Never address frames past the owned total: view selections go
        # stale after trims, and an unclamped end silently plays wrong-time
        # frames instead of stopping at the tail.
        self._range = self._clamp_range((start, end))

    def set_current_frame(self, frame):
        self._current_frame = max(0, min(frame, self._total_frames - 1))
        self.frameChanged.emit(self._current_frame)
        if self._is_playing:
            self._restart_playback_clock()

    def get_current_frame(self):
        return self._current_frame

    def is_playing(self):
        return self._is_playing

    def play(self):
        if self._total_frames == 0:
            logger.warning("Cannot play: no frames available")
            return

        self._restart_playback_clock()
        self._is_playing = True
        self._timer.start()
        self.playbackStateChanged.emit(True)

    def pause(self):
        self._is_playing = False
        self._timer.stop()
        self.playbackStateChanged.emit(False)

    def toggle(self):
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def seek(self, frame):
        self.set_current_frame(frame)

    def stop(self):
        self.pause()
        self.set_current_frame(0)

    def _restart_playback_clock(self):
        self._play_started_frame = self._current_frame
        self._play_started_at = time.perf_counter()

    def _on_tick(self):
        if not self._is_playing:
            return

        elapsed = max(0.0, time.perf_counter() - self._play_started_at)
        frames_elapsed = int(elapsed * self._fps * self._playback_speed)
        next_frame = self._play_started_frame + frames_elapsed

        if next_frame > self._range[1]:
            self._current_frame = self._range[1]
            self.frameChanged.emit(self._current_frame)
            self.pause()
            return

        if next_frame != self._current_frame:
            self._current_frame = next_frame
            self.frameChanged.emit(self._current_frame)
