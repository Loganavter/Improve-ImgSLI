from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from ui.main_window.ui import Ui_ImageComparisonApp
from ui.onboarding import OnboardingOverlay
from ui.theming import resolve_theme_color


def _paint_opaque_theme_background(widget: QWidget, color: QColor) -> None:
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Window, color)
    pal.setColor(QPalette.ColorRole.Base, color)
    pal.setColor(widget.backgroundRole(), color)
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

logger = logging.getLogger("ImproveImgSLI")

class MainWindowStartupRuntime:
    def __init__(self, window):
        self.window = window

    def build_shell(self) -> None:
        window = self.window

        try:
            theme_bg = QColor(
                resolve_theme_color(window.theme_manager, "label.image.background")
            )
        except Exception:
            theme_bg = QColor("#1e1e1e")

        window._root_layout = QVBoxLayout(window)
        window._root_layout.setContentsMargins(0, 0, 0, 0)
        window._root_layout.setSpacing(0)

        window._custom_title_bar = self._build_custom_title_bar()
        window._root_layout.addWidget(window._custom_title_bar)
        window._custom_title_bar.setVisible(
            bool(getattr(window, "_use_custom_decorations", False))
        )

        window._startup_stack = QStackedWidget(window)
        window._root_layout.addWidget(window._startup_stack)
        window._startup_placeholder = QWidget(window)
        window._startup_placeholder.setObjectName("StartupPlaceholder")
        _paint_opaque_theme_background(window._startup_placeholder, theme_bg)
        window._startup_stack.addWidget(window._startup_placeholder)
        window._app_host = QWidget(window)
        window._startup_stack.addWidget(window._app_host)
        window._startup_stack.setCurrentWidget(window._startup_placeholder)
        window._startup_cover = QWidget(window)
        window._startup_cover.setObjectName("StartupCover")
        _paint_opaque_theme_background(window._startup_cover, theme_bg)
        window._startup_cover.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        window._startup_cover.hide()
        window.onboarding_overlay = None
        self.sync_cover_geometry()

    def _build_custom_title_bar(self):
        from sli_ui_toolkit import CustomTitleBar
        from ui.icon_manager import AppIcon, get_app_icon

        window = self.window
        title_bar = CustomTitleBar(
            parent=window,
            title=window.windowTitle() or "Improve ImgSLI",
            icon=None,
            minimize_icon=get_app_icon(AppIcon.MINIMIZE),
            maximize_icon=get_app_icon(AppIcon.MAXIMIZE),
            restore_icon=get_app_icon(AppIcon.RESTORE),
            close_icon=get_app_icon(AppIcon.WINDOW_CLOSE),
        )
        title_bar.attach_window(window)
        return title_bar

    def sync_cover_geometry(self) -> None:
        window = self.window
        if getattr(window, "_startup_cover", None) is None:
            return
        rect = window.rect()
        title_bar = getattr(window, "_custom_title_bar", None)
        if title_bar is not None and title_bar.isVisible():
            top = title_bar.height()
            rect.setTop(top)
        window._startup_cover.setGeometry(rect)
        window._startup_cover.raise_()

    def show_cover(self) -> None:
        window = self.window
        if getattr(window, "_startup_cover", None) is None:
            return
        self.sync_cover_geometry()
        window._startup_cover.show()
        window._startup_cover.raise_()

    def hide_cover(self) -> None:
        window = self.window
        if getattr(window, "_startup_cover", None) is None:
            return
        window._startup_cover.hide()

    def should_show_onboarding(self) -> bool:
        return self.window.settings_manager.is_first_run()

    def bootstrap_content(self) -> None:
        if self.should_show_onboarding():
            self.show_onboarding_page()
        else:
            self.bootstrap_main_app()

    def show_onboarding_page(self) -> None:
        window = self.window
        if window.onboarding_overlay is None:
            window.onboarding_overlay = OnboardingOverlay(
                window.settings_manager,
                window.store,
                window,
            )
            window.onboarding_overlay.completed.connect(self.on_onboarding_completed)
        if window._startup_stack.indexOf(window.onboarding_overlay) < 0:
            window._startup_stack.insertWidget(0, window.onboarding_overlay)
        window.onboarding_overlay.resize(window.size())
        window._startup_stack.setCurrentWidget(window.onboarding_overlay)
        self.hide_cover()

    def bootstrap_main_app(self) -> None:
        window = self.window
        if window._main_app_bootstrapped:
            window._startup_stack.setCurrentWidget(window._app_host)
            self.reveal_if_ready()
            return

        window.ui = Ui_ImageComparisonApp()
        window._app_host.store = window.store
        window.ui.setupUi(window._app_host)
        window.ui.main_window = window
        from ui.main_window.layouts import apply_workspace_tabs_visibility
        apply_workspace_tabs_visibility(window.ui)
        image_label = window.ui.image_label
        window._startup_expects_initial_canvas_content = self.has_initial_canvas_content()
        window._startup_canvas_first_frame_rendered = False
        window._startup_canvas_first_visual_ready = False
        window.appearance.update_image_label_background()
        window.appearance.update_chrome_background()
        self.show_cover()
        image_label.firstFrameRendered.connect(self.on_image_label_first_frame_rendered)
        image_label.firstVisualFrameReady.connect(
            self.on_image_label_first_visual_frame_ready
        )

        window.ui.install_rating_wheel_handlers()

        components = window.app_context.create_window_dependent_components(window)
        window.geometry_manager = components.geometry_manager
        window.tray_manager = components.tray_manager
        window.main_controller = components.main_controller
        window.event_handler = components.event_handler
        window.presenter = components.presenter
        window.ui_resource_manager = components.ui_resource_manager

        window.installEventFilter(window.event_handler)
        window.ui.image_label.installEventFilter(window.event_handler)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(window.event_handler)

        window.appearance.update_image_label_background()
        window.appearance.update_chrome_background()
        if window.main_controller and window.main_controller.sessions:
            window.main_controller.sessions.initialize_app_display()
        window.ui.reapply_button_styles()
        from tabs.registry import TabRegistry

        _tab_registry = TabRegistry()
        _tab_registry.discover()
        _tab_registry.create_service("refresh_startup_button_visuals", window.ui)

        window._startup_stack.setCurrentWidget(window._app_host)
        self.sync_cover_geometry()
        window._main_app_bootstrapped = True
        if getattr(window.runtime_flags, "ui_inspector", False):
            app = QApplication.instance()
            if app is not None:
                from devtools.ui_inspector.installer import install_ui_inspector

                install_ui_inspector(app, window, window.theme_manager)
        self.reveal_if_ready()

    def has_initial_canvas_content(self) -> bool:
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        result = registry.create_service(
            "has_initial_canvas_content", self.window.store
        )
        return bool(result)

    def on_image_label_first_frame_rendered(self) -> None:
        self.window._startup_canvas_first_frame_rendered = True
        self.reveal_if_ready()

    def on_image_label_first_visual_frame_ready(self) -> None:
        self.window._startup_canvas_first_visual_ready = True
        self.reveal_if_ready()

    def is_canvas_ready(self) -> bool:
        window = self.window
        if window.onboarding_overlay is not None:
            return True
        if window.ui is None:
            return False
        if not self._is_image_compare_page_active():
            return True
        if window._startup_expects_initial_canvas_content:
            return (
                window._startup_canvas_first_frame_rendered
                and window._startup_canvas_first_visual_ready
                and self.is_canvas_content_ready()
            )
        return window._startup_canvas_first_visual_ready

    def _is_image_compare_page_active(self) -> bool:
        # The startup cover is gated on the image_compare canvas rendering its
        # first frame, but QRhiWidget only renders while it is the visible
        # stack page. If a different tab (e.g. session_picker) is shown at
        # startup, that signal never fires and the cover would stay up
        # forever, so the gate does not apply then.
        window = self.window
        tab_registry = getattr(window.ui, "_tab_registry", None)
        stack = getattr(window.ui, "workspace_stack", None)
        if tab_registry is None or stack is None:
            return True
        image_compare_page = tab_registry.get_page("image_compare")
        if image_compare_page is None:
            return True
        return stack.currentWidget() is image_compare_page

    def is_canvas_content_ready(self) -> bool:
        window = self.window
        if window.ui is None:
            return False
        image_label = getattr(window.ui, "image_label", None)
        if image_label is None:
            return False

        source_ready = bool(getattr(image_label, "_source_images_ready", False))
        if source_ready:
            return True

        uploaded = getattr(image_label, "_images_uploaded", None)
        if isinstance(uploaded, (list, tuple)) and any(bool(item) for item in uploaded):
            return True

        runtime_state = getattr(image_label, "runtime_state", None)
        if runtime_state is not None:
            uploaded = getattr(runtime_state, "_images_uploaded", None)
            if isinstance(uploaded, (list, tuple)) and any(bool(item) for item in uploaded):
                return True
            background = getattr(runtime_state, "_background_pixmap", None)
            if background is not None and not background.isNull():
                return True

        stored_qimages = getattr(image_label, "_stored_qimages", None)
        if isinstance(stored_qimages, (list, tuple)):
            for image in stored_qimages:
                if image is not None and not image.isNull():
                    return True

        return False

    def reveal_if_ready(self) -> None:
        window = self.window
        if window.ui is None:
            return
        if not self.is_canvas_ready():
            return
        if not window._main_app_revealed:
            window._startup_stack.setCurrentWidget(window._app_host)
            window._main_app_revealed = True
        window.ui.image_startup_placeholder.hide()
        self.hide_cover()
        self.emit_visual_ready()

    def emit_visual_ready(self) -> None:
        window = self.window
        if window._startup_visual_ready_emitted:
            return
        window._startup_visual_ready_emitted = True
        window.startupVisualReady.emit()

    def on_onboarding_completed(self, mode_key: str) -> None:
        window = self.window
        window.store.settings.ui_mode = mode_key
        if window.onboarding_overlay:
            try:
                window._startup_stack.removeWidget(window.onboarding_overlay)
            except Exception:
                pass
            window.onboarding_overlay.hide()
            window.onboarding_overlay.deleteLater()
        window.onboarding_overlay = None
        self.bootstrap_main_app()
        window.schedule_update()
