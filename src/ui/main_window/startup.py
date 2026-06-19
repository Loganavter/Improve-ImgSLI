from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from ui.main_window.ui import Ui_ImageComparisonApp
from ui.onboarding import OnboardingOverlay
from ui.widgets.gl_canvas.contracts import BaseCanvasProtocol
from ui.widgets.gl_canvas.helpers import get_canvas

logger = logging.getLogger("ImproveImgSLI")

class MainWindowStartupRuntime:
    def __init__(self, window):
        self.window = window

    def build_shell(self) -> None:
        window = self.window
        window._root_layout = QVBoxLayout(window)
        window._root_layout.setContentsMargins(0, 0, 0, 0)
        window._root_layout.setSpacing(0)
        window._startup_stack = QStackedWidget(window)
        window._root_layout.addWidget(window._startup_stack)
        window._startup_placeholder = QWidget(window)
        window._startup_placeholder.setObjectName("StartupPlaceholder")
        window._startup_placeholder.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        window._startup_stack.addWidget(window._startup_placeholder)
        window._app_host = QWidget(window)
        window._startup_stack.addWidget(window._app_host)
        window._startup_stack.setCurrentWidget(window._startup_placeholder)
        window._startup_cover = QWidget(window)
        window._startup_cover.setObjectName("StartupCover")
        window._startup_cover.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        window._startup_cover.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        window._startup_cover.hide()
        window.onboarding_overlay = None
        self.sync_cover_geometry()

    def sync_cover_geometry(self) -> None:
        window = self.window
        if getattr(window, "_startup_cover", None) is None:
            return
        window._startup_cover.setGeometry(window.rect())
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
        image_label: BaseCanvasProtocol = window.ui.image_label
        logger.debug("Main window UI bootstrapped")
        window._startup_expects_initial_canvas_content = self.has_initial_canvas_content()
        window._startup_canvas_first_frame_rendered = False
        window._startup_canvas_first_visual_ready = False
        window.appearance.update_image_label_background()
        self.show_cover()
        image_label.firstFrameRendered.connect(self.on_image_label_first_frame_rendered)
        image_label.firstFrameRendered.connect(
            lambda: logger.debug("Main window received image_label.firstFrameRendered")
        )
        image_label.firstVisualFrameReady.connect(
            lambda: logger.debug("Main window received image_label.firstVisualFrameReady")
        )
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
        if window.main_controller and window.main_controller.sessions:
            window.main_controller.sessions.initialize_app_display()
        window.ui.reapply_button_styles()
        for attr_name in (
            "btn_magnifier_color_settings",
            "btn_magnifier_color_settings_beginner",
        ):
            button = getattr(window.ui, attr_name, None)
            if button is not None and hasattr(button, "refresh_visual_state"):
                button.refresh_visual_state()

        window._startup_stack.setCurrentWidget(window._app_host)
        window._main_app_bootstrapped = True
        if getattr(window.runtime_flags, "ui_inspector", False):
            app = QApplication.instance()
            if app is not None:
                from devtools.ui_inspector.installer import install_ui_inspector

                install_ui_inspector(app, window, window.theme_manager)
        self.reveal_if_ready()

    def has_initial_canvas_content(self) -> bool:
        window = self.window
        document = getattr(window.store, "document", None)
        viewport = getattr(window.store, "viewport", None)
        if document is None:
            return False
        if getattr(document, "image1_path", None) and getattr(document, "image2_path", None):
            return True
        single_mode = int(
            getattr(
                getattr(viewport, "view_state", None),
                "showing_single_image_mode",
                0,
            )
            or 0
        )
        if single_mode == 1:
            return bool(
                getattr(document, "image1_path", None)
                or getattr(document, "original_image1", None)
            )
        if single_mode == 2:
            return bool(
                getattr(document, "image2_path", None)
                or getattr(document, "original_image2", None)
            )
        return False

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
        if window._startup_expects_initial_canvas_content:
            return (
                window._startup_canvas_first_frame_rendered
                and window._startup_canvas_first_visual_ready
                and self.is_canvas_content_ready()
            )
        return window._startup_canvas_first_visual_ready

    def is_canvas_content_ready(self) -> bool:
        window = self.window
        if window.ui is None:
            return False
        image_label = get_canvas(window.ui)
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
        logger.debug("Main window startupVisualReady emitted")
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
