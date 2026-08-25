import logging
import PIL.Image
from PySide6.QtCore import (
    QEvent,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QMoveEvent,
    QShowEvent,
    QColor,
    QIcon,
    QPalette,
    QResizeEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from core.bootstrap import ApplicationContext
from core.runtime_flags import RuntimeFlags
from shared_toolkit.ui.decorate_dialog import (
    CUSTOM_DECORATION_RESIZE_MARGIN,
    resolve_csd_band,
)
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
from tabs.registry import get_shared_tab_registry
from utils.geometry import GeometryManager
from utils.resource_loader import resource_path

PIL.Image.MAX_IMAGE_PIXELS = None
logger = logging.getLogger("ImproveImgSLI")


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

        self.CORNER_RADIUS = 10
        self._window_bg_color = QColor("#1e1e1e")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        from sli_ui_toolkit import apply_frameless

        # Outer resize band: the surface carries transparent margin beyond
        # the visible body so the frameless edge can be grabbed from outside
        # (the same band the dialogs get via WindowChrome).
        apply_frameless(self, outer_band=CUSTOM_DECORATION_RESIZE_MARGIN)

        from ui.canvas_infra.rhi.rhi_backend import ensure_window_rhi

        ensure_window_rhi(self)

        self._is_ui_stable = False
        self._application_initialized = False
        self._main_app_bootstrapped = False
        self._main_app_revealed = False
        self._startup_expects_initial_canvas_content = False
        self._startup_visual_ready_emitted = False
        self._deferred_startup_loaded = False
        self._startup_canvas_first_frame_rendered = False
        self._startup_canvas_first_visual_ready = False
        self._offscreen_prewarm_active = False
        self._startup_controller = MainWindowStartupController()
        self._shutdown_pipeline = MainWindowShutdownPipeline()
        self.appearance = MainWindowAppearance(self)
        self.runtime = MainWindowRuntime(self)
        self.startup_runtime = MainWindowStartupRuntime(self)
        self.action_registry = MainWindowActions(self)
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
        self._menu_controller = None  # set in startup.build_shell()
        # Title-bar File/Help widths are measured at strip construction. Apply
        # the UI face first so Cyrillic labels are not sized with a fallback
        # font (Help then sits where File should be until FontChange remasure).
        try:
            from shared_toolkit.ui.managers.font_manager import FontManager

            FontManager.get_instance().apply_from_state(self.store)
        except Exception:
            pass
        self.startup_runtime.build_shell()
        self._wire_csd_scale_resync()

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

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter

        from sli_ui_toolkit.ui.windows.rounded_body import (
            paint_rounded_window_background,
        )

        painter = QPainter(self)
        try:
            squared = self.isMaximized() or self.isFullScreen()
            band = resolve_csd_band(self)
            paint_rounded_window_background(
                painter,
                QRectF(self.rect()).adjusted(band, band, -band, -band),
                color=self._window_bg_color,
                radius=float(self.CORNER_RADIUS),
                squared=squared,
            )
        finally:
            painter.end()

    def _sync_csd_content_band(self) -> None:
        """Zero the root-layout band inset in maximized/fullscreen.

        The root layout insets all content by the outer resize band (so the
        visible body sits inside the transparent grab margin). In
        maximized/fullscreen the band is gone (see ``resolve_csd_band``) —
        keeping the inset would leave a strip of window background around
        the content. Re-insets when the window returns to windowed mode.
        """
        layout = getattr(self, "_root_layout", None)
        if layout is None:
            return
        band = resolve_csd_band(self)
        layout.setContentsMargins(band, band, band, band)
        layout.invalidate()
        layout.activate()
        startup_runtime = getattr(self, "startup_runtime", None)
        if startup_runtime is not None:
            try:
                startup_runtime.sync_cover_geometry()
            except Exception:
                pass

    def _apply_rounded_mask(self) -> None:
        from sli_ui_toolkit.ui.windows.rounded_body import (
            apply_bottom_rounded_mask,
        )

        squared = self.isMaximized() or self.isFullScreen()
        # Shell paints an AA rounded fill — do not setMask it (binary masks
        # destroy the antialiased edge). Clip opaque child hosts instead.
        self.clearMask()
        stack = getattr(self, "_startup_stack", None)
        host = getattr(self, "_app_host", None)
        # Non-current stack pages do not receive QStackedLayout geometry. Keep
        # app_host sized with the stack before masking, otherwise a resize
        # during first-run onboarding freezes a ~100x30 mask on the warm host.
        if (
            stack is not None
            and host is not None
            and stack.width() >= 64
            and stack.height() >= 64
            and (host.width() != stack.width() or host.height() != stack.height())
        ):
            host.resize(stack.size())
        for attr in ("_startup_stack", "_startup_cover", "_app_host"):
            child = getattr(self, attr, None)
            if child is None:
                continue
            apply_bottom_rounded_mask(
                child,
                radius=float(self.CORNER_RADIUS),
                squared=squared,
            )

    def begin_offscreen_prewarm(self):
        self._offscreen_prewarm_active = True

    def end_offscreen_prewarm(self):
        self._offscreen_prewarm_active = False

    @property
    def menu_controller(self):
        """Public accessor for the CSD/title-bar controller.

        Prefer over ``getattr(window, "_menu_controller")`` (private
        attribute hunt flagged by cross-module review C7).
        """
        return getattr(self, "_menu_controller", None)

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
        # ThemeManager.set_theme (sli-ui-toolkit ≥ 3.1.5) batches top-level
        # updates across QSS apply + theme_changed so the UI does not fill in
        # gradually mid-freeze.
        app = QApplication.instance()
        self.theme_manager.set_theme(theme_name, app)

    def changeEvent(self, event: QEvent):
        from shared_toolkit.ui.layout_sizing import defer_dialog_geometry
        from ui.layout_geometry import apply_main_window_minimum

        if event.type() == QEvent.Type.ApplicationFontChange:
            defer_dialog_geometry(self, lambda: apply_main_window_minimum(self))
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_csd_content_band()
            self._apply_rounded_mask()
            self.update()
            QTimer.singleShot(0, self.schedule_update)

    def resizeEvent(self, event: QResizeEvent):
        # Mark resize_in_progress before layout so the canvas skips heavy PIL
        # letterbox rebuilds while still doing live shader geometry + redraw.
        self.runtime.notify_resize()
        super().resizeEvent(event)
        self._apply_rounded_mask()
        # CSD: the title bar's layout can stay at its construction-time
        # activation (zones squeezed to tiny widths — clipped File/Help
        # buttons, elided title) until the first real geometry lands; on
        # Wayland that arrives as an asynchronous configure AFTER the window
        # is shown. Force a fresh bar layout + balance on the first real
        # resize so the first visible frame is correct.
        bar = getattr(self, "_custom_title_bar", None)
        if bar is not None:
            sync = getattr(bar, "_sync_balance_spacer", None)
            if callable(sync):
                try:
                    sync()
                except Exception:
                    pass

    def _wire_csd_scale_resync(self) -> None:
        """Force title-bar repaints shortly after a live UiScale change.

        The deferred bar relayout heals the geometry on the next tick; on
        some Wayland compositors the healed frame is never repainted
        (translucent-window quirk) and the stale CSD stays on screen until
        a window resize. Force synchronous repaints after the heal so the
        correct state is guaranteed visible.
        """
        try:
            from PySide6.QtCore import QTimer

            from sli_ui_toolkit.managers import UiScale

            self._csd_scale_resync_connection = (
                UiScale.get_instance().scale_changed.connect(
                    lambda _factor: (
                        QTimer.singleShot(50, self._force_csd_repaint),
                        QTimer.singleShot(250, self._force_csd_repaint),
                    )
                )
            )
            self.destroyed.connect(self._drop_csd_scale_resync)
        except Exception:
            pass

    def _force_csd_repaint(self) -> None:
        try:
            bar = getattr(self, "_custom_title_bar", None)
            if bar is not None:
                bar.repaint()
            self.repaint()
            from PySide6.QtWidgets import QApplication

            for top in QApplication.topLevelWidgets():
                dialog_bar = getattr(top, "_csd_title_bar", None)
                if dialog_bar is not None and dialog_bar is not getattr(
                    self, "_custom_title_bar", None
                ):
                    dialog_bar.repaint()
        except Exception:
            pass
    def _drop_csd_scale_resync(self, *_args) -> None:
        try:
            from sli_ui_toolkit.managers import UiScale

            UiScale.get_instance().scale_changed.disconnect(
                self._csd_scale_resync_connection
            )
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent):
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

    def moveEvent(self, event: QMoveEvent):
        super().moveEvent(event)
        self.runtime.handle_move()

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        self._apply_rounded_mask()
        self.runtime.handle_show()

    def mousePressEvent(self, event):
        focused = self.focusWidget()
        tab = get_shared_tab_registry().get_active_tab()
        if tab is not None:
            tab.create_service("clear_transient_text_focus", focused)
        super().mousePressEvent(event)

    def schedule_update(self):
        if self.presenter is not None:
            self.presenter.schedule_canvas_update()

