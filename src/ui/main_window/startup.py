from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from core.store import INITIAL_WORKSPACE_SESSION_TYPE
from plugins.onboarding import host as onboarding_host
from shared_toolkit.ui.decorate_dialog import resolve_csd_band
from tabs.registry import TabRegistry
from ui.main_window.ui import Ui_ImageComparisonApp
from ui.widgets.themed_surface import ThemedSurface

logger = logging.getLogger("ImproveImgSLI")


class MainWindowStartupRuntime:
    def __init__(self, window):
        self.window = window

    def build_shell(self) -> None:
        window = self.window

        window._root_layout = QVBoxLayout(window)
        # The outer resize band insets the whole content by the band on every
        # side (the surface carries the transparent band beyond the visible
        # body — same contract the dialogs get from WindowChrome). The band
        # collapses to 0 in maximized/fullscreen, re-synced by
        # ``MainWindow._sync_csd_content_band`` on WindowStateChange.
        band = resolve_csd_band(window)
        window._root_layout.setContentsMargins(band, band, band, band)
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
        window.onboarding_host = None
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
        # Keep the cover inside the outer resize band (transparent margin);
        # the band collapses to 0 in maximized/fullscreen.
        band = resolve_csd_band(window)
        rect = window.rect().adjusted(band, band, -band, -band)
        title_bar = getattr(window, "_custom_title_bar", None)
        if title_bar is not None and title_bar.isVisible():
            top = band + title_bar.height()
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

    def bootstrap_content(self) -> None:
        # Always build the real app first so opening a tab is only a stack
        # switch in the same window. Onboarding is no longer shown here — it
        # now triggers when the first onboarding-capable compare tab is
        # opened, via the onboarding plugin's
        # WorkspaceSessionActivatedEvent subscription.
        self.bootstrap_main_app()

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
        # Compose attached the transition mask while ``ui.main_window`` was still
        # ``_app_host``; ensure the MainWindow keeps the same reference.
        host_mask = getattr(window._app_host, "_workspace_transition_mask", None)
        if host_mask is not None:
            window._workspace_transition_mask = host_mask
        window.appearance.update_image_label_background()
        self.show_cover()

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
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(window.event_handler)

        # NavigationManager must be installed AFTER EventHandler on QApplication
        # so its event filter runs first (Qt LIFO order).
        from core.app_shell_navigation import register_app_shell_navigation

        register_app_shell_navigation(window)

        window.appearance.update_image_label_background()
        if window.main_controller and window.main_controller.sessions:
            window.main_controller.sessions.initialize_app_display()

        _tab_registry = TabRegistry()
        _tab_registry.discover(tier="bootstrap")
        _tab_registry.notify_all("refresh_startup_button_visuals", window.ui)

        from core.startup_trace import startup_mark

        startup_mark("main.bootstrap_main_app")

        window._main_app_bootstrapped = True
        if getattr(window.runtime_flags, "ui_inspector", False):
            app = QApplication.instance()
            if app is not None:
                from devtools.ui_inspector.installer import install_ui_inspector

                install_ui_inspector(app, window, window.theme_manager)
        window._startup_stack.setCurrentWidget(window._app_host)
        self.sync_cover_geometry()
        self.reveal_if_ready()

    def _active_tab(self):
        """The tab whose page is currently shown in the workspace stack."""
        window = self.window
<<<<<<< Updated upstream
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
=======
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
>>>>>>> Stashed changes

    def reveal_if_ready(self) -> None:
        window = self.window
        if window.ui is None:
            return
        if onboarding_host.is_active(window):
            # App is warm under onboarding — load deferred work, but do NOT mark
            # revealed: QStackedLayout only sizes the *current* page, so app_host
            # must get its first geometry pass when we switch after Start.
            self.emit_visual_ready()
            return
        if not window._main_app_revealed:
            window._startup_stack.setCurrentWidget(window._app_host)
            window._main_app_revealed = True
            self._sync_app_host_geometry()
        self.hide_cover()
        self.emit_visual_ready()

    def _sync_app_host_geometry(self) -> None:
        """Size the warm app host to the startup stack (below CSD)."""
        window = self.window
        stack = getattr(window, "_startup_stack", None)
        host = getattr(window, "_app_host", None)
        if stack is None or host is None:
            return
        if stack.width() >= 64 and stack.height() >= 64:
            host.setGeometry(0, 0, stack.width(), stack.height())
        host.updateGeometry()
        layout = host.layout()
        if layout is not None:
            layout.activate()
        host.show()
        host.raise_()
        # Resizes during onboarding only re-mask the *current* stack page.
        # app_host kept a stale tiny mask (~100x30) → white hole + strip corner.
        apply_mask = getattr(window, "_apply_rounded_mask", None)
        if callable(apply_mask):
            apply_mask()
        host.update()
        window.update()
        self._notify_active_tab_host_revealed()

    def _notify_active_tab_host_revealed(self) -> None:
        """Notify the active tab that the host is visible — generic hook."""
        window = self.window
        ui = getattr(window, "ui", None)
        registry = getattr(ui, "_tab_registry", None) if ui is not None else None
        stack = getattr(ui, "workspace_stack", None) if ui is not None else None
        if registry is None or stack is None:
            return
        current = stack.currentWidget()
        for session_type in registry.registered_types:
            if registry.get_page(session_type) is not current:
                continue
            tab = registry.get_tab(session_type)
            if tab is not None:
                try:
                    tab.on_host_revealed()
                except Exception:
                    pass
            break

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
            # Deferred tab pages are created lazily on first show — no need
            # to call install_missing_pages() here.
            # Cards were built from a tab-package scan; only refresh icons now
            # that deferred tabs can answer get_tab_icon.
            picker = ui._tab_registry.get_page(INITIAL_WORKSPACE_SESSION_TYPE)
            if picker is not None:
                picker.sync_icons()
            menu = getattr(window, "_menu_controller", None)
            if menu is not None:
                menu._wire_session_picker_recent()

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
                    tab_reg
                )

        if ctx.settings_manager is not None and ctx.store is not None:
            ctx.settings_manager._load_canvas_feature_settings(ctx.store.viewport)

        startup_mark("startup.deferred_complete")

    def on_onboarding_completed(self, mode_key: str) -> None:
        """Reveal the warm app, then apply the chosen UI mode."""
        window = self.window

        if not window._main_app_bootstrapped:
            self.bootstrap_main_app()
        else:
            # Do NOT re-show the startup cover here. Canvas first-frame signals
            # already fired while the app was warm under onboarding; waiting on
            # them again leaves a permanent white StartupCover.
            window._startup_stack.setCurrentWidget(window._app_host)
            window._main_app_revealed = True
            self._sync_app_host_geometry()
            self.hide_cover()
            self.emit_visual_ready()

        # Apply mode after app_host is current so layout_manager sizes visible chrome.
        plugin = onboarding_host.resolve_plugin(window)
        if plugin is not None:
            plugin.apply_ui_mode(mode_key)

        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        self._sync_app_host_geometry()
        window.schedule_update()

        # Second pass after mode rebuild (AdaptiveTabStrip / toolbars).
        QTimer.singleShot(0, self._post_onboarding_tick)
        QTimer.singleShot(50, self._post_onboarding_tick)

    def _post_onboarding_tick(self) -> None:
        self.hide_cover()
        self._sync_app_host_geometry()
        window = self.window
        stack = getattr(window, "_startup_stack", None)
        host = getattr(window, "_app_host", None)
        if stack is not None and host is not None and stack.currentWidget() is not host:
            stack.setCurrentWidget(host)
        if window is not None:
            window.schedule_update()