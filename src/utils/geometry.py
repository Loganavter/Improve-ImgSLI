from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtWidgets import QWidget


def fit_into(
    geometry: tuple[int, int, int, int],
    available: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int]:
    """Clamp *geometry* (x, y, w, h) into *available* -- never off-screen.

    A saved size outlives the display it was saved on: restored on a smaller
    screen it leaves part of the window unpainted, which reads as "the widget
    is broken" -- a live capture of that window is part black exactly where
    the toolbar/footer hang off the edge (2026-10-17: a restored 2090x1381
    window on a 1600x1000 private Xvfb; the same window is fine on the
    display it was saved on, so nothing looks wrong until someone measures).
    Size is clamped to the screen; the position is pulled back inside so the
    title bar stays reachable. Pure function: no Qt, no window, no raising.
    """
    if available is None:
        return geometry
    try:
        x, y, w, h = (int(v) for v in geometry)
        ax, ay, aw, ah = (int(v) for v in available)
    except (TypeError, ValueError):
        return geometry
    if aw <= 0 or ah <= 0:
        return geometry
    w = max(1, min(w, aw))
    h = max(1, min(h, ah))
    x = max(ax, min(x, ax + aw - w))
    y = max(ay, min(y, ay + ah - h))
    return x, y, w, h


def _geometry_debug() -> bool:
    """``IMGSLI_GEOMETRY_DEBUG=1`` (alias ``BLINKTABLE_GEOMETRY_DEBUG``) — trace geometry.

    Why this exists (owner, 2026-10-26): "the window size is not remembered between
    runs" could not be reproduced on a private Xvfb (1500x1000 restored as
    1516x1000, 640x520 was raised to the session-picker floor 720x560), so the
    answer had to come from the owner's own multi-monitor session. The trace names
    the REQUESTED rect, the AVAILABLE rect it was fitted into and the APPLIED one,
    on restore and on save — enough to tell a clamp apart from a lost value.
    """
    try:
        from shared.debug_flags import env_flag

        return env_flag("IMGSLI_GEOMETRY_DEBUG")
    except Exception:
        return False


def _geo_log(message: str, *args) -> None:
    if not _geometry_debug():
        return
    try:
        import logging

        logging.getLogger("BlinkTable.geometry").info(message, *args)
    except Exception:
        pass


class GeometryManager:
    def __init__(self, window: QWidget, settings: QSettings, store=None):
        self.window = window
        self.settings = settings
        self.store = store

        self.normal_geometry: QByteArray | None = None
        self.normal_rect_str: str | None = None
        self._freeze_normal_updates: bool = False

    def _available_rect(self) -> tuple[int, int, int, int] | None:
        """The current screen's available geometry, or ``None``. Never raises."""
        try:
            from PySide6.QtWidgets import QApplication

            screen = self.window.screen() or QApplication.primaryScreen()
            if screen is None:
                return None
            rect = screen.availableGeometry()
            return (rect.x(), rect.y(), rect.width(), rect.height())
        except Exception:
            return None

    def _apply_fit(self, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
        """``setGeometry`` through :func:`fit_into`; returns what was applied."""
        available = self._available_rect()
        fit_x, fit_y, fit_w, fit_h = fit_into((x, y, w, h), available)
        _geo_log(
            "geometry apply: asked=%dx%d@%d,%d available=%s applied=%dx%d@%d,%d%s",
            w, h, x, y, available, fit_w, fit_h, fit_x, fit_y,
            "" if (fit_w, fit_h) == (w, h) else "  <-- CLAMPED BY THE AVAILABLE RECT",
        )
        self.window.setGeometry(fit_x, fit_y, fit_w, fit_h)
        return fit_x, fit_y, fit_w, fit_h

    def load_and_apply(self):
        if self.store and hasattr(self.store.settings, "window_width"):
            was_maximized = self.store.settings.window_was_maximized
            window_width = max(200, self.store.settings.window_width)
            window_height = max(150, self.store.settings.window_height)
            window_x = self.store.settings.window_x
            window_y = self.store.settings.window_y
            _geo_log(
                "geometry restore: stored=%dx%d@%d,%d maximized=%s",
                window_width, window_height, window_x, window_y, was_maximized,
            )

            x, y, w, h = self._apply_fit(
                window_x, window_y, window_width, window_height
            )
            self.normal_rect_str = f"{x},{y},{w},{h}"
        else:

            was_maximized = self.settings.value(
                "window_was_maximized", False, type=bool
            )
            saved_normal_geom = self.settings.value(
                "normal_geometry", QByteArray(), type=QByteArray
            )
            saved_normal_rect_str = self.settings.value("normal_rect", "", type=str)

            if saved_normal_rect_str:
                try:
                    parts = [int(p) for p in saved_normal_rect_str.split(",")]
                    if len(parts) == 4:
                        x, y, w, h = self._apply_fit(
                            parts[0], parts[1], max(200, parts[2]), max(150, parts[3])
                        )
                        self.normal_rect_str = f"{x},{y},{w},{h}"
                except Exception:
                    pass

            if not self.normal_rect_str:
                if saved_normal_geom and not saved_normal_geom.isNull():
                    self.normal_geometry = saved_normal_geom
                    self.window.restoreGeometry(self.normal_geometry)
                    try:
                        rect = self.window.geometry()
                        self._apply_fit(
                            rect.x(), rect.y(), rect.width(), rect.height()
                        )
                    except Exception:
                        pass
                else:
                    self._apply_fit(100, 100, 1024, 768)
                    self.normal_geometry = self.window.saveGeometry()

        self._freeze_normal_updates = bool(was_maximized)

        state = self.window.windowState()
        if was_maximized:
            self.window.setWindowState(state | Qt.WindowState.WindowMaximized)
        else:
            self.window.setWindowState(state & ~Qt.WindowState.WindowMaximized)

    def update_normal_geometry_if_needed(self):
        if self._freeze_normal_updates:
            _geo_log("geometry save: SKIPPED (normal updates frozen)")
            return
        if self.window.isMaximized() or self.window.isFullScreen():
            _geo_log(
                "geometry save: SKIPPED (maximized/fullscreen) — the previous normal rect is kept"
            )
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
        from core.state_management.actions import SetWindowGeometryAction, SetWindowWasMaximizedAction
        is_maximized = self.window.isMaximized() or self.window.isFullScreen()

        if self.store and hasattr(self.store.settings, "window_width"):
            dispatcher = self.store.get_dispatcher()
            dispatcher.dispatch(SetWindowWasMaximizedAction(is_maximized))

            if not is_maximized and self.normal_rect_str:
                try:
                    parts = [int(p) for p in self.normal_rect_str.split(",")]
                    if len(parts) == 4:
                        x, y, w, h = parts
                        dispatcher.dispatch(SetWindowGeometryAction(x, y, w, h))
                except Exception:
                    pass

        _geo_log(
            "geometry save: normal=%s maximized=%s",
            self.normal_rect_str or "-", is_maximized,
        )
        self.settings.setValue("window_was_maximized", is_maximized)

        if self.normal_geometry and not self.normal_geometry.isNull():
            self.settings.setValue("normal_geometry", self.normal_geometry)
        if self.normal_rect_str:
            self.settings.setValue("normal_rect", self.normal_rect_str)

        self.settings.sync()