import time
import logging
from dataclasses import dataclass
from typing import List, Any
from PyQt6.QtCore import QObject, QTimer

logger = logging.getLogger("ImproveImgSLI")

@dataclass(frozen=True)
class FrameSnapshot:
    timestamp: float
    viewport_state: Any
    settings_state: Any
    image1_path: str
    image2_path: str

    name1: str
    name2: str

class Recorder(QObject):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.is_recording = False
        self.is_paused = False
        self.start_time = 0.0
        self.pause_start_time = 0.0
        self.total_paused_time = 0.0
        self.snapshots: List[FrameSnapshot] = []

        self.sample_timer = QTimer(self)

        target_fps = getattr(self.store.settings, 'video_recording_fps', 60)
        target_fps = max(10, min(144, target_fps))
        interval = int(1000 / target_fps)
        self.sample_timer.setInterval(interval)
        self.sample_timer.timeout.connect(self.capture_frame)

    def start(self):
        self.snapshots.clear()
        self.is_recording = True
        self.is_paused = False
        self.total_paused_time = 0.0
        self.start_time = time.time()

        target_fps = getattr(self.store.settings, 'video_recording_fps', 60)

        target_fps = max(10, min(144, target_fps))

        interval = int(1000 / target_fps)

        self.sample_timer.setInterval(interval)
        self.sample_timer.start()
        self.capture_frame()

    def stop(self):
        self.is_recording = False
        self.is_paused = False
        self.sample_timer.stop()
        self.capture_frame()

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

    def capture_frame(self):
        if not self.store or self.is_paused: return

        elapsed = (time.time() - self.start_time) - self.total_paused_time

        vp_snapshot = self.store.viewport.freeze_for_export()
        st_snapshot = self.store.settings.freeze_for_export()

        doc = self.store.document

        def get_path_at_index(img_list, index):
            if 0 <= index < len(img_list):
                try:

                    item = img_list[index]
                    if hasattr(item, 'path'):
                        return item.path

                    if isinstance(item, (list, tuple)) and len(item) > 1:
                        return item[1]
                except (IndexError, TypeError, AttributeError):
                    return None
            return None

        path1 = get_path_at_index(doc.image_list1, doc.current_index1)
        path2 = get_path_at_index(doc.image_list2, doc.current_index2)

        snapshot = FrameSnapshot(
            timestamp=elapsed,
            viewport_state=vp_snapshot,
            settings_state=st_snapshot,
            image1_path=path1,
            image2_path=path2,
            name1=doc.get_current_display_name(1),
            name2=doc.get_current_display_name(2)
        )

        self.snapshots.append(snapshot)

