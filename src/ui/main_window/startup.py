from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from plugins.onboarding import host as onboarding_host
from shared_toolkit.ui.decorate_dialog import resolve_csd_band
from ui.main_window.ui import Ui_ImageComparisonApp
from ui.widgets.themed_surface import ThemedSurface

logger = logging.getLogger("ImproveImgSLI")


def _startup_ffd_log(message: str) -> None:
    """Env-gated (IMGSLI_IC_FIRST_FRAME_DEBUG) startup-cover timeline log."""
    flag = os.environ.get("IMGSLI_IC_FIRST_FRAME_DEBUG", "").strip().lower()
    if flag in ("", "0", "false", "no", "off"):
        return
    try:
        logging.getLogger("ImproveImgSLI").info("[ic-first-frame] startup: %s", message)
    except Exception:
        pass


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
        _startup_ffd_log("show_cover")
        self.sync_cover_geometry()
        window._startup_cover.show()
        window._startup_cover.raise_()

    def hide_cover(self) -> None:
        window = self.window
        if getattr(window, "_startup_cover", None) is None:
            return
        _startup_ffd_log("hide_cover")
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
        # The legacy main-window shell widget comes from the single tab that
        # registers its assembled page into ``legacy_tab_widgets``. There is
        # no privileged "shell host" role — the widget is read straight from
        # that registry.  With lazy tab initialization the widget may not
        # exist yet (the page is created on first show), so treat a missing
        # widget as a deferred state rather than a fatal error.
        image_compare_widget = next(
            iter(window.ui.legacy_tab_widgets.values()), None
        )
        window.image_compare_widget = image_compare_widget
        window._startup_expects_initial_canvas_content = self.has_initial_canvas_content()
        window._startup_canvas_first_frame_rendered = False
        window._startup_canvas_first_visual_ready = False
        window.appearance.update_image_label_background()
        self.show_cover()
        if image_compare_widget is not None:
            image_label = image_compare_widget.image_label
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

        # NavigationManager must be installed AFTER EventHandler on QApplication
        # so its event filter runs first (Qt LIFO order).
        from sli_ui_toolkit.managers import NavigationManager

        nav_manager = NavigationManager.get_instance()

        # CSD title bar is a toolkit widget without widget_descriptor;
        # register its navigation section manually (must be first = topmost
        # so that _neighbor(owner, -1) from the tab strip finds it).
        title_bar = getattr(window, "_custom_title_bar", None)
        if title_bar is not None:
            from ui.main_window.title_bar_navigation import TitleBarNavigationSection

            nav_manager.register(title_bar, TitleBarNavigationSection(title_bar))
            logger.debug("[nav-titlebar] registered title bar section")

        nav_manager.auto_register_from_descriptors()

        window.appearance.update_image_label_background()
        if window.main_controller and window.main_controller.sessions:
            window.main_controller.sessions.initialize_app_display()
        if image_compare_widget is not None:
            image_compare_widget.reapply_button_styles()
        from tabs.registry import TabRegistry

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
        _startup_ffd_log(
            "reveal_if_ready canvas_ready=True "
            f"first_frame={window._startup_canvas_first_frame_rendered} "
            f"first_visual={window._startup_canvas_first_visual_ready}"
        )
        if onboarding_host.is_active(window):
            # App is warm under onboarding — load deferred work, but do NOT mark
            # revealed: QStackedLayout only sizes the *current* page, so app_host
            # must get its first geometry pass when we switch after Start.
            widget = window.image_compare_widget
            if widget is not None:
                widget.image_startup_placeholder.hide()
            self.emit_visual_ready()
            return
        if not window._main_app_revealed:
            window._startup_stack.setCurrentWidget(window._app_host)
            window._main_app_revealed = True
            self._sync_app_host_geometry()
        widget = window.image_compare_widget
        if widget is not None:
            # Hide the per-canvas placeholder only once the canvas actually
            # rendered its first frame. The active-tab gate above is about
            # the window-level startup cover (session_picker must not hold it
            # up); the canvas placeholder covers the image_label itself, and
            # hiding it on the gate bypass exposed the transparent subsurface
            # for the first frame(s) when the workspace current tab was not
            # the image pair tab at bootstrap.
            image_label = getattr(widget, "image_label", None)
            if image_label is not None and getattr(
                image_label, "_first_frame_rendered_emitted", False
            ):
                _startup_ffd_log(
                    "reveal_if_ready hiding image_startup_placeholder "
                    "(first frame emitted)"
                )
                widget.image_startup_placeholder.hide()
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
        self._refresh_session_picker_surface()

    def _refresh_session_picker_surface(self) -> None:
        """Force Session Picker opaque fills after the host becomes visible."""
        window = self.window
        ui = getattr(window, "ui", None)
        registry = getattr(ui, "_tab_registry", None) if ui is not None else None
        if registry is None:
            return
        picker = registry.get_page("session_picker")
        if picker is None:
            return
        recover = getattr(picker, "_sync_opaque_page_fills", None)
        if callable(recover):
            recover()
        # Ensure create-cards + recent are present before the cover lifts
        # (idempotent if _build already populated them).
        show_hook = getattr(picker, "refresh", None)
        if callable(show_hook):
            show_hook()
        recent = getattr(picker, "_recent_panel", None)
        if recent is not None:
            on_shown = getattr(recent, "on_page_shown", None)
            if callable(on_shown):
                on_shown()
            recover_recent = getattr(recent, "recover_opaque_surface", None)
            if callable(recover_recent):
                recover_recent()
        picker.update()

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
            picker = ui._tab_registry.get_page("session_picker")
            sync_icons = getattr(picker, "sync_icons", None)
            if callable(sync_icons):
                sync_icons()
            menu = getattr(window, "_menu_controller", None)
            wire = getattr(menu, "_wire_session_picker_recent", None)
            if callable(wire):
                wire()

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
            widget = window.image_compare_widget
            if widget is not None:
                widget.image_startup_placeholder.hide()
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