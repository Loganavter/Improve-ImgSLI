import logging
import PIL.Image
from PySide6.QtCore import (
    QEvent,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPalette,
    QResizeEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from core.bootstrap import ApplicationContext
from core.runtime_flags import RuntimeFlags
from shared_toolkit.ui.overlay_layer import OverlayLayer
from ui.main_window.actions import MainWindowActions
from ui.main_window.appearance import MainWindowAppearance
from ui.main_window.lifecycle import (
    MainWindowShutdownPipeline,
    MainWindowStartupController,
)
from ui.main_window.runtime import MainWindowRuntime
from ui.main_window.startup import MainWindowStartupRuntime
from ui.theming import install_application_theme, resolve_theme_color
from utils.geometry import GeometryManager
from utils.resource_loader import resource_path

PIL.Image.MAX_IMAGE_PIXELS = None
logger = logging.getLogger("ImproveImgSLI")


def _read_use_custom_decorations_setting() -> bool:
    try:
        from PySide6.QtCore import QSettings
        qs = QSettings("improve-imgsli", "improve-imgsli")
        if not qs.contains("use_custom_decorations"):
            return True
        return str(qs.value("use_custom_decorations")).lower() == "true"
    except Exception:
        return True

class MainWindow(QWidget):
    startupVisualReady = Signal()

    def __init__(
        self,
        parent=None,
        debug_mode: bool = False,
        runtime_flags: RuntimeFlags | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ImageComparisonApp")
        self.runtime_flags = runtime_flags or RuntimeFlags(debug=debug_mode)

        self._use_custom_decorations = _read_use_custom_decorations_setting()
        self.CORNER_RADIUS = 10
        self._window_bg_color = QColor("#1e1e1e")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        if self._use_custom_decorations:
            from sli_ui_toolkit import apply_frameless
            apply_frameless(self)

        self._is_ui_stable = False
        self._application_initialized = False
        self._main_app_bootstrapped = False
        self._main_app_revealed = False
        self._startup_expects_initial_canvas_content = False
        self._startup_visual_ready_emitted = False
        self._startup_canvas_first_frame_rendered = False
        self._startup_canvas_first_visual_ready = False
        self._offscreen_prewarm_active = False
        self._startup_controller = MainWindowStartupController()
        self._shutdown_pipeline = MainWindowShutdownPipeline()
        self.appearance = MainWindowAppearance(self)
        self.runtime = MainWindowRuntime(self)
        self.startup_runtime = MainWindowStartupRuntime(self)
        self.actions = MainWindowActions(self)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))

        self.app_context = ApplicationContext(runtime_flags=self.runtime_flags)
        self.app_context.initialize()

        self.store = self.app_context.store
        self.settings_manager = self.app_context.settings_manager
        self.theme_manager = self.app_context.theme_manager
        self.notification_service = self.app_context.notification_service
        self.thread_pool = self.app_context.thread_pool

        app = QApplication.instance()
        if app:
            install_application_theme(self.app_context, app)
            self.theme_manager.theme_changed.connect(self.appearance.on_theme_changed)

        self.ui = None
        self.overlay_layer = OverlayLayer(self)
        self.tray_manager = None
        self.main_controller = None
        self.event_handler = None
        self.presenter = None
        self.ui_resource_manager = None
        self._toast_manager = None
        self.save_task_counter = 0

        self.geometry_manager = GeometryManager(
            self,
            self.settings_manager.settings,
            self.store,
        )
        self.startup_runtime.build_shell()

        try:
            theme_bg = QColor(
                resolve_theme_color(self.theme_manager, "label.image.background")
            )
        except Exception:
            theme_bg = QColor("#1e1e1e")
        self._window_bg_color = theme_bg
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, theme_bg)
        pal.setColor(QPalette.ColorRole.Base, theme_bg)
        pal.setColor(self.backgroundRole(), theme_bg)
        self.setPalette(pal)

        try:
            from shared_toolkit.ui.managers.font_manager import FontManager

            self.font_path_absolute = FontManager.get_instance().get_font_path_for_image_text(self.store)
        except Exception:
            self.font_path_absolute = None

        self.setAcceptDrops(True)

        self._debounced_resize_timer = QTimer(self)
        self._debounced_resize_timer.setSingleShot(True)
        self._debounced_resize_timer.setInterval(150)
        self._debounced_resize_timer.timeout.connect(
            self.runtime.handle_debounced_resize
        )

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter, QPainterPath
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._window_bg_color)
        rect = QRectF(self.rect())
        use_custom = getattr(self, "_use_custom_decorations", False)
        radius = (
            float(self.CORNER_RADIUS)
            if use_custom and not (self.isMaximized() or self.isFullScreen())
            else 0.0
        )
        path = QPainterPath()
        if radius <= 0.0:
            path.addRect(rect)
        else:
            w, h, r = rect.width(), rect.height(), radius
            path.moveTo(0.0, h)
            path.lineTo(0.0, r)
            path.arcTo(0.0, 0.0, 2 * r, 2 * r, 180.0, -90.0)
            path.lineTo(w - r, 0.0)
            path.arcTo(w - 2 * r, 0.0, 2 * r, 2 * r, 90.0, -90.0)
            path.lineTo(w, h)
            path.closeSubpath()
        painter.drawPath(path)

    def _apply_rounded_mask(self) -> None:
        # QBitmap-based setMask is 1-bit (no AA) and chops the antialiased
        # rounded paintEvent edges into a staircase — visible as lighter pixels
        # on dark themes. WA_TranslucentBackground + AA paintEvent already gives
        # smooth corners on compositing systems, so we just keep the mask off.
        self.clearMask()

    def begin_offscreen_prewarm(self):
        self._offscreen_prewarm_active = True

    def end_offscreen_prewarm(self):
        self._offscreen_prewarm_active = False

    @property
    def toast_manager(self):
        if self._toast_manager is not None:
            return self._toast_manager
        try:
            layout_plugin = getattr(self.main_controller, "layout", None)
            toast_manager = (
                getattr(layout_plugin, "toast_manager", None)
                if layout_plugin is not None
                else None
            )
            if toast_manager is not None:
                self._toast_manager = toast_manager
                return self._toast_manager
        except Exception:
            logger.exception("Failed to resolve toast manager from layout plugin")
        return None

    def initialize_application(self):
        self._startup_controller.prepare(self)

    def start(self):
        self._startup_controller.start(self)

    def apply_decoration_mode(self, enabled: bool) -> None:
        if enabled == self._use_custom_decorations:
            return

        from sli_ui_toolkit import set_frameless_runtime

        self._use_custom_decorations = enabled
        set_frameless_runtime(self, enabled)

        title_bar = getattr(self, "_custom_title_bar", None)
        if title_bar is not None:
            title_bar.setVisible(enabled)

        self.startup_runtime.sync_cover_geometry()
        self._apply_rounded_mask()
        self.update()

    def apply_application_theme(self, theme_name: str):
        app = QApplication.instance()
        self.theme_manager.set_theme(theme_name, app)
        if self.ui is not None:
            self.ui.reapply_button_styles()

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._apply_rounded_mask()
            self.update()
            QTimer.singleShot(0, self.schedule_update)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._apply_rounded_mask()
        self.runtime.handle_resize()

    def closeEvent(self, event: QEvent):
        logger.debug("Начало закрытия главного окна...")
        self._shutdown_pipeline.run(self)

        logger.debug("Завершение закрытия главного окна")
        try:
            self.hide()
        except Exception:
            pass
        event.accept()
        super().closeEvent(event)
        try:
            self.deleteLater()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, lambda: app.exit(0))

    def moveEvent(self, event: QEvent):
        super().moveEvent(event)
        self.runtime.handle_move()

    def showEvent(self, event: QEvent):
        super().showEvent(event)
        self._apply_rounded_mask()
        self.runtime.handle_show()

    def mousePressEvent(self, event):
        focused = self.focusWidget()
        if self.ui is not None and focused in (self.ui.edit_name1, self.ui.edit_name2):
            focused.clearFocus()
        super().mousePressEvent(event)

    def schedule_update(self):
        if self.presenter is not None:
            self.presenter.schedule_canvas_update()

    def update_interpolation_combo_state(
        self, count: int, current_index: int, text: str, items: list[str]
    ):
        if self.ui is not None and hasattr(self.ui, "combo_interpolation"):
            self.ui.combo_interpolation.updateState(
                count=count,
                current_index=current_index,
                text=text,
                items=items,
            )

