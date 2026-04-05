import logging
import PIL.Image
from PyQt6.QtCore import (
    QEvent,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QResizeEvent,
)
from PyQt6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from core.bootstrap import ApplicationContext
from shared_toolkit.ui.managers.font_manager import FontManager
from shared_toolkit.ui.overlay_layer import OverlayLayer
from ui.main_window_lifecycle import (
    MainWindowShutdownPipeline,
    MainWindowStartupController,
)
from ui.main_window_ui import Ui_ImageComparisonApp
from ui.onboarding import OnboardingOverlay
from ui.widgets.gl_canvas.contracts import BaseCanvasProtocol
from ui.widgets.gl_canvas.helpers import get_canvas
from utils.resource_loader import resource_path
from utils.geometry import GeometryManager

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
        self._offscreen_prewarm_active = False
        self._startup_controller = MainWindowStartupController()
        self._shutdown_pipeline = MainWindowShutdownPipeline()
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
            self.theme_manager.apply_theme_to_app(app)
            self.theme_manager.theme_changed.connect(self._on_theme_changed)

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
        self._build_startup_shell()

        try:
            self.font_path_absolute = (
                FontManager.get_instance().get_font_path_for_image_text(self.store)
            )
        except Exception:
            self.font_path_absolute = None

        self.setAcceptDrops(True)

        self._debounced_resize_timer = QTimer(self)
        self._debounced_resize_timer.setSingleShot(True)
        self._debounced_resize_timer.setInterval(150)
        self._debounced_resize_timer.timeout.connect(self._handle_debounced_resize)

    def _build_startup_shell(self):
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self._startup_stack = QStackedWidget(self)
        self._root_layout.addWidget(self._startup_stack)
        self._startup_placeholder = QWidget(self)
        self._startup_stack.addWidget(self._startup_placeholder)
        self._app_host = QWidget(self)
        self._startup_stack.addWidget(self._app_host)
        self._startup_stack.setCurrentWidget(self._startup_placeholder)
        self.onboarding_overlay = None

    def _should_show_onboarding(self) -> bool:
        return self.settings_manager.is_first_run()

    def _show_onboarding_page(self):
        if self.onboarding_overlay is None:
            self.onboarding_overlay = OnboardingOverlay(
                self.settings_manager,
                self.store,
                self,
            )
            self.onboarding_overlay.completed.connect(self._on_onboarding_completed)
            self._startup_stack.insertWidget(0, self.onboarding_overlay)
        self.onboarding_overlay.resize(self.size())
        self._startup_stack.setCurrentWidget(self.onboarding_overlay)

    def _bootstrap_main_app(self):
        if self._main_app_bootstrapped:
            self._startup_stack.setCurrentWidget(self._app_host)
            return

        self.ui = Ui_ImageComparisonApp()
        self.ui.setupUi(self._app_host)
        self.ui.main_window = self
        image_label: BaseCanvasProtocol = self.ui.image_label
        logger.debug("Main window UI bootstrapped")
        self._startup_expects_initial_canvas_content = self._has_initial_canvas_content()
        self._update_image_label_background()
        image_label.firstFrameRendered.connect(
            self.ui.hide_image_startup_placeholder
        )
        image_label.firstFrameRendered.connect(
            self._emit_startup_visual_ready
        )
        image_label.firstFrameRendered.connect(
            lambda: logger.debug("Main window received image_label.firstFrameRendered")
        )
        image_label.firstVisualFrameReady.connect(
            lambda: logger.debug("Main window received image_label.firstVisualFrameReady")
        )
        image_label.firstVisualFrameReady.connect(
            self._on_image_label_first_visual_frame_ready
        )

        self.ui.install_rating_wheel_handlers()

        components = self.app_context.create_window_dependent_components(self)
        self.geometry_manager = components["geometry_manager"]
        self.tray_manager = components["tray_manager"]
        self.main_controller = components["main_controller"]
        self.event_handler = components["event_handler"]
        self.presenter = components["presenter"]
        self.ui_resource_manager = components["ui_resource_manager"]

        self.installEventFilter(self.event_handler)
        self.ui.image_label.installEventFilter(self.event_handler)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self.event_handler)

        self._update_image_label_background()
        if self.main_controller and self.main_controller.sessions:
            self.main_controller.sessions.initialize_app_display()
        self.ui.reapply_button_styles()
        for attr_name in (
            "btn_magnifier_color_settings",
            "btn_magnifier_color_settings_beginner",
        ):
            button = getattr(self.ui, attr_name, None)
            if button is not None and hasattr(button, "refresh_visual_state"):
                button.refresh_visual_state()

        self._startup_stack.setCurrentWidget(self._app_host)
        self._main_app_revealed = True
        self._main_app_bootstrapped = True

    def _has_initial_canvas_content(self) -> bool:
        document = getattr(self.store, "document", None)
        viewport = getattr(self.store, "viewport", None)
        if document is None:
            return False
        if getattr(document, "image1_path", None) and getattr(document, "image2_path", None):
            return True
        single_mode = int(getattr(getattr(viewport, "view_state", None), "showing_single_image_mode", 0) or 0)
        if single_mode == 1:
            return bool(getattr(document, "image1_path", None) or getattr(document, "original_image1", None))
        if single_mode == 2:
            return bool(getattr(document, "image2_path", None) or getattr(document, "original_image2", None))
        return False

    def _on_image_label_first_visual_frame_ready(self):
        if self._startup_expects_initial_canvas_content:
            return
        logger.debug("Main window hiding startup placeholder on first visual frame (empty startup)")
        self.ui.hide_image_startup_placeholder()
        self._emit_startup_visual_ready()

    def _emit_startup_visual_ready(self):
        if self._startup_visual_ready_emitted:
            return
        self._startup_visual_ready_emitted = True
        logger.debug("Main window startupVisualReady emitted")
        self.startupVisualReady.emit()

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
        if self.store.settings.theme != theme_name:
            self.store.settings.theme = theme_name
        if self.ui is not None:
            self.ui.reapply_button_styles()

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:

            QTimer.singleShot(0, self.schedule_update)

    def _handle_debounced_resize(self):
        if self.store.viewport.interaction_state.resize_in_progress:
            self.store.viewport.interaction_state.resize_in_progress = False
            self.schedule_update()
        if not self.isMaximized() and not self.isFullScreen():
            self.geometry_manager.update_normal_geometry_if_needed()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self.ui is not None and hasattr(self.ui, "sync_image_startup_placeholder"):
            self.ui.sync_image_startup_placeholder()

        if hasattr(self, "onboarding_overlay") and self.onboarding_overlay:
            self.onboarding_overlay.resize(self.size())

        if self.presenter is not None:
            flyout = getattr(self.presenter.ui_manager, "unified_flyout", None)
            if flyout is not None:
                try:
                    flyout.hide()
                except RuntimeError as exc:
                    if "UnifiedFlyout has been deleted" in str(exc):
                        self.presenter.ui_manager.transient.host.unified_flyout = None
                    else:
                        raise

        if not self.store.viewport.interaction_state.resize_in_progress:
            self.store.viewport.interaction_state.resize_in_progress = True

        if self.ui is not None:
            self.ui.update_drag_overlays(
                self.store.viewport.view_state.is_horizontal,
                self.ui.is_drag_overlay_visible(),
            )
        self._debounced_resize_timer.start()

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
        if self.ui is not None and hasattr(self.ui, "sync_image_startup_placeholder"):
            self.ui.sync_image_startup_placeholder()
        if hasattr(self, "onboarding_overlay") and self.onboarding_overlay:
            self.onboarding_overlay.resize(self.size())
        if self.presenter is not None:
            flyout = getattr(self.presenter.ui_manager, "unified_flyout", None)
            if flyout is not None:
                try:
                    flyout.hide()
                except RuntimeError as exc:
                    if "UnifiedFlyout has been deleted" in str(exc):
                        self.presenter.ui_manager.transient.host.unified_flyout = None
                    else:
                        raise
        if not self.isMaximized() and not self.isFullScreen():
            self.geometry_manager.update_normal_geometry_if_needed()

    def showEvent(self, event: QEvent):
        super().showEvent(event)
        if self._offscreen_prewarm_active:
            logger.debug("Main window showEvent (offscreen prewarm)")
        else:
            logger.debug("Main window showEvent")
        if self.ui is not None and hasattr(self.ui, "sync_image_startup_placeholder"):
            self.ui.sync_image_startup_placeholder()
        if self.onboarding_overlay is not None and not self._startup_visual_ready_emitted:
            self._emit_startup_visual_ready()
        if self._offscreen_prewarm_active:
            return
        if not self._is_ui_stable:
            QTimer.singleShot(
                50,
                lambda: setattr(self, "_is_ui_stable", True) or self.schedule_update(),
            )

    def mousePressEvent(self, event):
        focused = self.focusWidget()
        if self.ui is not None and focused in (self.ui.edit_name1, self.ui.edit_name2):
            focused.clearFocus()
        super().mousePressEvent(event)

    def schedule_update(self):
        if self.presenter is not None:
            self.presenter.schedule_canvas_update()

    def _update_image_label_background(self):
        bg = self.theme_manager.get_color("label.image.background")
        bg_hex = bg.name(QColor.NameFormat.HexArgb)
        image_label = get_canvas(self.ui) if self.ui is not None else None
        if image_label is not None:
            pal = image_label.palette()
            pal.setColor(image_label.backgroundRole(), bg)
            pal.setColor(image_label.foregroundRole(), bg)
            from PyQt6.QtGui import QPalette
            pal.setColor(QPalette.ColorRole.Window, bg)
            pal.setColor(QPalette.ColorRole.Base, bg)
            image_label.setPalette(pal)
            image_label.setStyleSheet(
                f"background-color: {bg_hex};"
            )
            if hasattr(self.ui, "set_image_startup_placeholder_color"):
                self.ui.set_image_startup_placeholder_color(bg)

    def _on_theme_changed(self):
        self._update_image_label_background()

        try:

            FontManager.get_instance().apply_from_state(self.store)

            current_font = QApplication.font()
            self.setFont(current_font)

        except Exception as e:
            logger.error(f"Error enforcing font style: {e}")

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def notify_system(
        self,
        title: str,
        message: str,
        image_path: str | None = None,
        timeout_ms: int = 4000,
    ):
        enabled = getattr(self.store.settings, "system_notifications_enabled", True)
        if enabled:
            try:
                self.notification_service.send(title, message, image_path, timeout_ms)
            except Exception:
                logger.exception("notify_system send failed")

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

    def update_tray_actions_visibility(self):
        if self.tray_manager:
            path = getattr(self, "_last_saved_path", None)
            self.tray_manager.set_last_saved_path(path)

    def _toggle_main_window_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.showMinimized()
        else:
            self.show()
            self.setWindowState(
                (self.windowState() & ~Qt.WindowState.WindowMinimized)
                | Qt.WindowState.WindowActive
            )
            self.raise_()
            self.activateWindow()

    def _open_last_saved_file(self):
        path = getattr(self, "_last_saved_path", None)
        if path and os.path.isfile(path):
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_last_saved_folder(self):
        path = getattr(self, "_last_saved_path", None)
        folder = (
            os.path.dirname(path)
            if path
            else (self.store.settings.export_default_dir or os.path.expanduser("~"))
        )
        if folder and os.path.isdir(folder):
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_onboarding_completed(self, mode_key: str):
        self.store.settings.ui_mode = mode_key
        if hasattr(self, "onboarding_overlay") and self.onboarding_overlay:
            try:
                self._startup_stack.removeWidget(self.onboarding_overlay)
            except Exception:
                pass
            self.onboarding_overlay.hide()
            self.onboarding_overlay.deleteLater()
        self.onboarding_overlay = None
        self._bootstrap_main_app()
        self.schedule_update()
