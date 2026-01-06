

import logging
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger("ImproveImgSLI")

class PlaybackEngine(QObject):

    frameChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(bool)

    def __init__(self, fps=60):
        super().__init__()
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)

        self._current_frame = 0
        self._total_frames = 0
        self._range = (0, 0)
        self._fps = max(1, fps)
        self._is_playing = False

        self._timer.setInterval(int(1000 / self._fps))

    def set_fps(self, fps):
        self._fps = max(1, fps)
        self._timer.setInterval(int(1000 / self._fps))

    def get_fps(self):
        return self._fps

    def set_total_frames(self, total_frames):
        self._total_frames = max(0, total_frames)

    def get_total_frames(self):
        return self._total_frames

    def set_range(self, start, end):
        self._range = (max(0, start), max(0, end))

    def get_range(self):
        return self._range

    def set_current_frame(self, frame):
        self._current_frame = max(0, min(frame, self._total_frames - 1))
        self.frameChanged.emit(self._current_frame)

    def get_current_frame(self):
        return self._current_frame

    def is_playing(self):
        return self._is_playing

    def play(self):
        if self._total_frames == 0:
            logger.warning("Cannot play: no frames available")
            return

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

    def _on_tick(self):
        next_frame = self._current_frame + 1

        if next_frame > self._range[1]:
            self.pause()
            return

        self._current_frame = next_frame
        self.frameChanged.emit(self._current_frame)

