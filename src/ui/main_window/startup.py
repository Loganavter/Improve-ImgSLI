from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from ui.main_window.ui import Ui_ImageComparisonApp
from ui.onboarding import OnboardingOverlay
from ui.widgets.themed_surface import ThemedSurface

logger = logging.getLogger("ImproveImgSLI")

class MainWindowStartupRuntime:
    def __init__(self, window):
        self.window = window

    def build_shell(self) -> None:
        window = self.window

        window._root_layout = QVBoxLayout(window)
        window._root_layout.setContentsMargins(0, 0, 0, 0)
        window._root_layout.setSpacing(0)

        window._custom_title_bar = self._build_custom_title_bar()
        window._root_layout.addWidget(window._custom_title_bar)
        window._custom_title_bar.setVisible(True)

        window._startup_stack = QStackedWidget(window)
        window._root_layout.addWidget(window._startup_stack)
        window._startup_placeholder = ThemedSurface(window)
        window._startup_placeholder.setObjectName("StartupPlaceholder")
        window._startup_stack.addWidget(window._startup_placeholder)
        window._app_host = QWidget(window)
        window._startup_stack.addWidget(window._app_host)
        window._startup_stack.setCurrentWidget(window._startup_placeholder)
        window._startup_cover = ThemedSurface(window)
        window._startup_cover.setObjectName("StartupCover")
        window._startup_cover.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        window._startup_cover.hide()
        window.onboarding_overlay = None
        self.sync_cover_geometry()

    def _build_custom_title_bar(self):
        from ui.main_window.menu_controller import MainWindowMenuController

        window = self.window
        window._menu_controller = MainWindowMenuController(window)
        title_bar = window._menu_controller.build_title_bar()
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
        bootstrap_tab = window.ui._tab_registry.bootstrap_default_tab()
        image_compare_widget = window.ui.legacy_tab_widgets.get(
            bootstrap_tab.session_type
        )
        window.image_compare_widget = image_compare_widget
        image_label = image_compare_widget.image_label
        window._startup_expects_initial_canvas_content = self.has_initial_canvas_content()
        window._startup_canvas_first_frame_rendered = False
        window._startup_canvas_first_visual_ready = False
        window.appearance.update_image_label_background()
        self.show_cover()
        image_label.firstFrameRendered.connect(self.on_image_label_first_frame_rendered)
        image_label.firstVisualFrameReady.connect(
            self.on_image_label_first_visual_frame_ready
        )

        components = window.app_context.create_window_dependent_components(window)
        window.geometry_manager = components.geometry_manager
        window.tray_manager = components.tray_manager
        window.main_controller = components.main_controller
        window.event_handler = components.event_handler
        window.presenter = components.presenter
        window.ui_resource_manager = components.ui_resource_manager

        menu = getattr(window, "_menu_controller", None)
        if menu is not None:
            menu.refresh_platform_action_targets()

        window.installEventFilter(window.event_handler)
        image_label.installEventFilter(window.event_handler)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(window.event_handler)

        window.appearance.update_image_label_background()
        if window.main_controller and window.main_controller.sessions:
            window.main_controller.sessions.initialize_app_display()
        image_compare_widget.reapply_button_styles()
        from tabs.registry import TabRegistry

        _tab_registry = TabRegistry()
        _tab_registry.discover(tier="bootstrap")
        _tab_registry.notify_all("refresh_startup_button_visuals", window.ui)

        from core.startup_trace import startup_mark

        startup_mark("main.bootstrap_main_app")

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
        registry.discover(tier="bootstrap")
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
        if not self._active_tab_requires_first_frame_gate():
            return True
        if window._startup_expects_initial_canvas_content:
            return (
                window._startup_canvas_first_frame_rendered
                and window._startup_canvas_first_visual_ready
                and self.is_canvas_content_ready()
            )
        return window._startup_canvas_first_visual_ready

    def _active_tab(self):
        # The tab whose page is currently shown in the workspace stack —
        # the single resolution point shared by every startup hook below
        # that needs to ask "what is on screen right now".
        window = self.window
        tab_registry = getattr(window.ui, "_tab_registry", None)
        stack = getattr(window.ui, "workspace_stack", None)
        if tab_registry is None or stack is None:
            return None
        current_widget = stack.currentWidget()
        for session_type in tab_registry.registered_types:
            if tab_registry.get_page(session_type) is not current_widget:
                continue
            return tab_registry.get_tab(session_type)
        return None

    def _active_tab_requires_first_frame_gate(self) -> bool:
        # The startup cover is gated on the active tab's canvas rendering its
        # first frame, but that signal only fires for tabs whose canvas
        # opts in (via the "requires_first_frame_startup_gate" service). If
        # a tab without that signal (e.g. session_picker) is shown at
        # startup, the cover would stay up forever, so the gate does not
        # apply then.
        tab = self._active_tab()
        if tab is None:
            return True
        try:
            return bool(tab.create_service("requires_first_frame_startup_gate"))
        except Exception:
            return True

    def is_canvas_content_ready(self) -> bool:
        window = self.window
        if window.ui is None:
            return False
        tab = self._active_tab()
        if tab is None:
            return False
        return bool(tab.create_service("is_canvas_content_ready"))

    def reveal_if_ready(self) -> None:
        window = self.window
        if window.ui is None:
            return
        if not self.is_canvas_ready():
            return
        if not window._main_app_revealed:
            window._startup_stack.setCurrentWidget(window._app_host)
            window._main_app_revealed = True
        widget = window.image_compare_widget
        if widget is not None:
            widget.image_startup_placeholder.hide()
        self.hide_cover()
        self.emit_visual_ready()

    def emit_visual_ready(self) -> None:
        window = self.window
        if window._startup_visual_ready_emitted:
            return
        window._startup_visual_ready_emitted = True
        from core.startup_trace import startup_mark

        startup_mark("startup.visual_ready")
        window.startupVisualReady.emit()
        QTimer.singleShot(0, self._load_deferred_startup_modules)

    def _load_deferred_startup_modules(self) -> None:
        window = self.window
        if getattr(window, "_deferred_startup_loaded", False):
            return
        window._deferred_startup_loaded = True

        from core.startup_trace import startup_mark
        from tabs.registry import TabRegistry

        ctx = window.app_context
        if ctx is None:
            return

        ctx.load_deferred_plugins()

        tab_registry = TabRegistry()
        tab_registry.discover(tier="deferred")

        ui = window.ui
        if ui is not None and getattr(ui, "_tab_registry", None) is not None:
            ui._tab_registry.discover(tier="deferred")
            stack = getattr(ui, "workspace_stack", None)
            if stack is not None:
                ui._tab_registry.install_missing_pages(stack)
            # Cards were built from a tab-package scan; only refresh icons now
            # that deferred tabs can answer get_tab_icon.
            picker = ui._tab_registry.get_page("session_picker")
            sync_icons = getattr(picker, "sync_icons", None)
            if callable(sync_icons):
                sync_icons()

        main_controller = window.main_controller
        presenter = window.presenter
        if main_controller is not None and presenter is not None:
            main_controller.attach_deferred_plugins(presenter)

        coordinator = getattr(ctx, "plugin_coordinator", None)
        settings_plugin = (
            coordinator.get_plugin("settings") if coordinator is not None else None
        )
        if settings_plugin is not None:
            tab_reg = (
                getattr(ui, "_tab_registry", None)
                if ui is not None
                else tab_registry
            )
            if tab_reg is not None:
                settings_plugin.register_canvas_feature_bindings(
                    tab_reg, tab_types=("multi_compare",)
                )

        if ctx.settings_manager is not None and ctx.store is not None:
            ctx.settings_manager._load_canvas_feature_settings(ctx.store.viewport)

        startup_mark("startup.deferred_complete")

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
