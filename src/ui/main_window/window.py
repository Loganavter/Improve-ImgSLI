import logging
import PIL.Image
from PyQt6.QtCore import (
    QEvent,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QResizeEvent,
)
from PyQt6.QtWidgets import QApplication, QWidget

from core.bootstrap import ApplicationContext
from shared_toolkit.ui.overlay_layer import OverlayLayer
from ui.main_window.actions import MainWindowActions
from ui.main_window.appearance import MainWindowAppearance
from ui.main_window.lifecycle import (
    MainWindowShutdownPipeline,
    MainWindowStartupController,
)
from ui.main_window.runtime import MainWindowRuntime
from ui.main_window.startup import MainWindowStartupRuntime
from utils.geometry import GeometryManager
from utils.resource_loader import resource_path

PIL.Image.MAX_IMAGE_PIXELS = None
logger = logging.getLogger("ImproveImgSLI")

class MainWindow(QWidget):
    startupVisualReady = pyqtSignal()

    def __init__(self, parent=None, debug_mode: bool = False):
        super().__init__(parent)
        self.setObjectName("ImageComparisonApp")

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

        self.app_context = ApplicationContext(debug_mode)
        self.app_context.initialize()

        self.store = self.app_context.store
        self.settings_manager = self.app_context.settings_manager
        self.theme_manager = self.app_context.theme_manager
        self.notification_service = self.app_context.notification_service
        self.thread_pool = self.app_context.thread_pool

        app = QApplication.instance()
        if app:
            self.app_context.apply_theme_to_app(app)
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

    def apply_application_theme(self, theme_name: str):
        app = QApplication.instance()
        self.theme_manager.set_theme(theme_name, app)
        if self.ui is not None:
            self.ui.reapply_button_styles()

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:

            QTimer.singleShot(0, self.schedule_update)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
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
        self.runtime.handle_show()

    def mousePressEvent(self, event):
        focused = self.focusWidget()
        if self.ui is not None and focused in (self.ui.edit_name1, self.ui.edit_name2):
            focused.clearFocus()
        super().mousePressEvent(event)

    def schedule_update(self):
        if self.presenter is not None:
            self.presenter.schedule_canvas_update()

    def set_divider_button_color(self, color: QColor):
        if self.ui is not None and hasattr(self.ui, "btn_orientation"):
            self.ui.btn_orientation.set_color(color)

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

    def configure_diff_mode_actions(self, actions, current_value):
        if self.ui is not None and hasattr(self.ui, "btn_diff_mode"):
            self.ui.btn_diff_mode.set_actions(actions)
            self.ui.btn_diff_mode.set_current_by_data(current_value)

    def configure_channel_mode_actions(self, actions, current_value):
        if self.ui is not None and hasattr(self.ui, "btn_channel_mode"):
            self.ui.btn_channel_mode.set_actions(actions)
            self.ui.btn_channel_mode.set_current_by_data(current_value)
