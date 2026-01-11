from PyQt6.QtCore import QByteArray, QSettings
from PyQt6.QtWidgets import QWidget

class GeometryManager:
    def __init__(self, window: QWidget, settings: QSettings, store=None):
        self.window = window
        self.settings = settings
        self.store = store

        self.normal_geometry: QByteArray | None = None
        self.normal_rect_str: str | None = None
        self._freeze_normal_updates: bool = False

    def load_and_apply(self):

        if self.store and hasattr(self.store.settings, 'window_width'):
            was_maximized = self.store.settings.window_was_maximized
            window_width = max(200, self.store.settings.window_width)
            window_height = max(150, self.store.settings.window_height)
            window_x = self.store.settings.window_x
            window_y = self.store.settings.window_y

            self.window.setGeometry(window_x, window_y, window_width, window_height)
            self.normal_rect_str = f"{window_x},{window_y},{window_width},{window_height}"
        else:

            was_maximized = self.settings.value("window_was_maximized", False, type=bool)
            saved_normal_geom = self.settings.value("normal_geometry", QByteArray(), type=QByteArray)
            saved_normal_rect_str = self.settings.value("normal_rect", "", type=str)

            if saved_normal_rect_str:
                try:
                    parts = [int(p) for p in saved_normal_rect_str.split(",")]
                    if len(parts) == 4:
                        x, y, w, h = parts
                        self.window.setGeometry(x, y, max(200, w), max(150, h))
                        self.normal_rect_str = saved_normal_rect_str
                except Exception:
                    pass

            if not self.normal_rect_str:
                if saved_normal_geom and not saved_normal_geom.isNull():
                    self.normal_geometry = saved_normal_geom
                    self.window.restoreGeometry(self.normal_geometry)
                else:
                    self.window.setGeometry(100, 100, 1024, 768)
                    self.normal_geometry = self.window.saveGeometry()

        self._freeze_normal_updates = bool(was_maximized)

        if was_maximized:
            self.window.showMaximized()
        else:
            self.window.showNormal()

    def update_normal_geometry_if_needed(self):
        if self._freeze_normal_updates:
            return
        if not self.window.isMaximized() and not self.window.isFullScreen():
            try:
                self.normal_geometry = self.window.saveGeometry()
            except Exception:
                pass
            try:
                g = self.window.geometry()
                self.normal_rect_str = f"{g.x()},{g.y()},{g.width()},{g.height()}"
            except Exception:
                pass

    def save_on_close(self):
        is_maximized = self.window.isMaximized() or self.window.isFullScreen()

        if self.store and hasattr(self.store.settings, 'window_width'):
            self.store.settings.window_was_maximized = is_maximized

            if not is_maximized and self.normal_rect_str:
                try:
                    parts = [int(p) for p in self.normal_rect_str.split(",")]
                    if len(parts) == 4:
                        x, y, w, h = parts
                        self.store.settings.window_x = x
                        self.store.settings.window_y = y
                        self.store.settings.window_width = w
                        self.store.settings.window_height = h
                except Exception:
                    pass

        self.settings.setValue("window_was_maximized", is_maximized)

        if self.normal_geometry and not self.normal_geometry.isNull():
            self.settings.setValue("normal_geometry", self.normal_geometry)
        if self.normal_rect_str:
            self.settings.setValue("normal_rect", self.normal_rect_str)

        self.settings.sync()

    def on_left_maximized_state(self):
        self._freeze_normal_updates = False
        self.update_normal_geometry_if_needed()

    def begin_maximize_transition(self):
        try:
            g = self.window.geometry()
            self.normal_rect_str = f"{g.x()},{g.y()},{g.width()},{g.height()}"
        except Exception:
            pass
        self._freeze_normal_updates = True
