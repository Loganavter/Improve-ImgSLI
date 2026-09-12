from __future__ import annotations

import logging
import os
import traceback
from dataclasses import dataclass, field
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from shared_toolkit.ui.managers.font_manager import FontManager

logger = logging.getLogger("ImproveImgSLI")

class WindowStartupStep:
    name = "startup"

    def run(self, window) -> None:
        raise NotImplementedError

class WindowShutdownStep:
    name = "shutdown"

    def run(self, window) -> None:
        raise NotImplementedError

class LoadWindowStateStep(WindowStartupStep):
    name = "load_window_state"

    def run(self, window) -> None:
        window.geometry_manager.load_and_apply()

class ApplyThemeStep(WindowStartupStep):
    name = "apply_theme"

    def run(self, window) -> None:
        theme_from_env = os.getenv("APP_THEME", "auto").lower()
        final_theme_setting = (
            theme_from_env
            if theme_from_env != "auto"
            else window.store.settings.theme
        )
        window.apply_application_theme(final_theme_setting)

class ApplyUiScaleStep(WindowStartupStep):
    name = "apply_ui_scale"

    def run(self, window) -> None:
        # Re-assert the persisted factor (already applied at bootstrap) so
        # ApplyThemeStep's QSS push and BootstrapContentStep's widget
        # construction scale correctly even on code paths that skipped the
        # ApplicationContext bootstrap. No-op when unchanged.
        try:
            from sli_ui_toolkit.managers import UiScale

            UiScale.get_instance().set_factor(
                getattr(window.store.settings, "ui_scale_factor", 1.0) or 1.0
            )
        except Exception:
            pass

class ApplyFontSettingsStep(WindowStartupStep):
    name = "apply_fonts"

    def run(self, window) -> None:
        try:
            FontManager.get_instance().apply_from_state(window.store)
        except Exception:
            pass
        # Shell may already have menus; force a sync remasure after the face
        # is pinned so the first painted frame is not mid-jump.
        menu = getattr(window, "_menu_controller", None)
        strip = getattr(menu, "_menu_strip", None) if menu is not None else None
        remasure = getattr(strip, "remasure", None)
        if callable(remasure):
            try:
                remasure()
            except Exception:
                pass


class BootstrapContentStep(WindowStartupStep):
    name = "bootstrap_content"

    def run(self, window) -> None:
        window.startup_runtime.bootstrap_content()

class MarkShuttingDownStep(WindowShutdownStep):
    name = "mark_shutting_down"

    def run(self, window) -> None:
        window._closing = True
        if getattr(window, "app_context", None) is not None:
            window.app_context._is_shutting_down = True

class ShutdownTabsStep(WindowShutdownStep):
    name = "shutdown_tabs"

    def run(self, window) -> None:
        ui = getattr(window, "ui", None)
        registry = getattr(ui, "_tab_registry", None)
        if registry is None:
            return
        registry.notify_window_shutdown(window)
        registry.dispose_all()

class ShutdownPresenterStep(WindowShutdownStep):
    name = "shutdown_presenter"

    def run(self, window) -> None:
        presenter = getattr(window, "presenter", None)
        if presenter is None:
            return
        try:
            presenter.shutdown()
        except Exception as exc:
            logger.error(f"Ошибка при отмене экспортов: {exc}")

        image_presenter = presenter.get_feature("image_canvas")
        if image_presenter is not None and hasattr(
            image_presenter, "_update_scheduler_timer"
        ):
            image_presenter._update_scheduler_timer.stop()

class StopWindowTimersStep(WindowShutdownStep):
    name = "stop_window_timers"

    def run(self, window) -> None:
        runtime = getattr(window, "runtime", None)
        if runtime is not None and hasattr(runtime, "cancel_resize_settle"):
            runtime.cancel_resize_settle()

class CloseDerivedWindowsStep(WindowShutdownStep):
    name = "close_derived_windows"

    def run(self, window) -> None:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return

        for widget in list(app.topLevelWidgets()):  # ALLOWED: system-wide shutdown — closes every derived top-level generically, not tab-specific
            if widget is None or widget is window:
                continue
            try:
                widget.close()
            except Exception as exc:
                logger.error(f"Ошибка при закрытии производного окна {widget}: {exc}")
            try:
                if widget.isVisible():
                    widget.hide()
            except Exception:
                pass
            try:
                widget.deleteLater()
            except Exception:
                pass

class PersistWindowStateStep(WindowShutdownStep):
    name = "persist_window_state"

    def run(self, window) -> None:
        try:
            window.geometry_manager.update_normal_geometry_if_needed()
            window.geometry_manager.save_on_close()
            window.settings_manager.save_all_settings(window.store)
        except Exception as exc:
            logger.error(f"Ошибка при сохранении настроек: {exc}")

class ShutdownTrayStep(WindowShutdownStep):
    name = "shutdown_tray"

    def run(self, window) -> None:
        tray_manager = getattr(window, "tray_manager", None)
        if tray_manager is None:
            return
        try:
            tray_manager.shutdown()
        except Exception as exc:
            logger.error(f"Ошибка при остановке TrayManager: {exc}")

class ShutdownAppContextStep(WindowShutdownStep):
    name = "shutdown_app_context"

    def run(self, window) -> None:
        if getattr(window, "app_context", None) is None:
            return
        try:
            window.app_context.shutdown()
        except Exception as exc:
            logger.error(f"Ошибка при завершении ApplicationContext: {exc}")

@dataclass(slots=True)
class MainWindowStartupPipeline:
    steps: tuple[WindowStartupStep, ...] = (
        LoadWindowStateStep(),
        ApplyUiScaleStep(),
        ApplyThemeStep(),
        ApplyFontSettingsStep(),
        BootstrapContentStep(),
    )

    def run(self, window) -> None:
        for step in self.steps:
            logger.debug("Main window startup step: %s", step.name)
            try:
                step.run(window)
            except Exception as exc:
                formatted = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
                logger.error(
                    "Main window startup step failed: %s\n%s",
                    step.name,
                    formatted,
                )
                raise

@dataclass(slots=True)
class MainWindowStartupController:
    pipeline: MainWindowStartupPipeline = field(
        default_factory=MainWindowStartupPipeline
    )

    def prepare(self, window) -> None:
        if getattr(window, "_application_initialized", False):
            return
        logger.debug("Main window startup controller: prepare")
        self.pipeline.run(window)
        window._application_initialized = True

    def show(self, window) -> None:
        logger.debug("Main window startup controller: show")
        self.prepare(window)
        # Final CSD menu widths + balance while still hidden, so the first
        # exposed frame does not remasure and ghost «Справка».
        menu = getattr(window, "_menu_controller", None)
        strip = getattr(menu, "_menu_strip", None) if menu is not None else None
        remasure = getattr(strip, "remasure", None)
        if callable(remasure):
            try:
                remasure()
            except Exception:
                pass
        title_bar = getattr(window, "_custom_title_bar", None)
        if title_bar is not None:
            sync = getattr(title_bar, "_sync_balance_spacer", None)
            if callable(sync):
                try:
                    sync()
                except Exception:
                    pass
        window.show()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        # The window may have been shown before its layout ever ran: the
        # root layout sizes the title bar only on the first real pass, and
        # the bar's own layout can stay at its construction-time activation
        # (zones squeezed to a few px — clipped File/Help buttons, elided
        # title) for the first visible frame. Force both layouts now, before
        # the compositor paints the first buffer.
        try:
            root_layout = window.layout()
            if root_layout is not None:
                root_layout.invalidate()
                root_layout.activate()
            bar = getattr(window, "_custom_title_bar", None)
            if bar is not None:
                sync = getattr(bar, "_sync_balance_spacer", None)
                if callable(sync):
                    sync()
                update = getattr(bar, "update", None)
                if callable(update):
                    update()
        except Exception:
            pass
        # Widgets that size against the first real layout defer their reflow
        # to 0-timers (e.g. the Session Picker recent shelf: deferred
        # relayout -> height settle -> chrome refresh). Those timers would
        # otherwise fire only after the deferred plugin loading that blocks
        # the loop right after show(), leaving the first visible frames at
        # the pre-layout arrangement for a full second. Drain the pending
        # timer turns here, while the event loop is still free, so the first
        # presented frame is already settled.
        if app is not None:
            for _ in range(4):
                app.processEvents()
                logger.debug(
                    "Main window startup drain pass %d: window=%s maximized=%s",
                    _ + 1,
                    window.size().toTuple(),
                    window.isMaximized(),
                )
        logger.debug(
            "Main window startup drain done: window=%s maximized=%s",
            window.size().toTuple(),
            window.isMaximized(),
        )
        # Ensure initial focus lands on the tab strip add button, not on a
        # CSD menu trigger (which is now StrongFocus after keyboard nav was
        # added to the title bar).
        ui = getattr(window, "ui", None)
        tab_strip = getattr(ui, "workspace_tabs", None) if ui is not None else None
        if tab_strip is not None:
            add_btn = getattr(tab_strip, "add_button", None)
            target = add_btn if add_btn is not None and add_btn.isVisible() else tab_strip
            target.setFocus(Qt.FocusReason.MouseFocusReason)
        self._log_layout_summary(window)
        # Onboarding is built during prepare() before the window has a real
        # layout; re-apply geometry/scale after the first show pass.
        from plugins.onboarding import host as onboarding_host

        onboarding_host.prepare_after_show(window)

        self._log_layout_summary(window)

    def _log_layout_summary(self, window) -> None:
        """Log a compact summary of the main window widget tree for debug."""
        from PySide6.QtWidgets import QWidget
        from PySide6.QtCore import Qt

        def _tree(w, depth=0, max_depth=3):
            if depth > max_depth:
                return
            cls = type(w).__name__
            name = w.objectName() or ""
            geo = w.geometry()
            vis = "v" if w.isVisible() else "h"
            parts = [f"{'  ' * depth}{cls}({name}) [{geo.width()}x{geo.y()}+{geo.x()},{geo.y()}] {vis}"]
            if depth < max_depth:
                for child in w.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                    parts.extend(_tree(child, depth + 1, max_depth))
            return parts

        lines = _tree(window)
        if lines:
            logger.debug(
                "[layout-tree] main window tree:\n  %s",
                "\n  ".join(lines),
            )

    def start(self, window) -> None:
        self.show(window)

@dataclass(slots=True)
class MainWindowShutdownPipeline:
    steps: tuple[WindowShutdownStep, ...] = (
        MarkShuttingDownStep(),
        ShutdownTabsStep(),
        ShutdownPresenterStep(),
        StopWindowTimersStep(),
        CloseDerivedWindowsStep(),
        PersistWindowStateStep(),
        ShutdownTrayStep(),
        ShutdownAppContextStep(),
    )

    def run(self, window) -> None:
        for step in self.steps:
            step.run(window)