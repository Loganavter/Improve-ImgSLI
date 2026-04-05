from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from PyQt6.QtWidgets import QApplication

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

class ApplyFontSettingsStep(WindowStartupStep):
    name = "apply_fonts"

    def run(self, window) -> None:
        try:
            FontManager.get_instance().apply_from_state(window.store)
        except Exception:
            pass

class BootstrapContentStep(WindowStartupStep):
    name = "bootstrap_content"

    def run(self, window) -> None:
        if window._should_show_onboarding():
            window._show_onboarding_page()
        else:
            window._bootstrap_main_app()

class RefreshWindowUiStep(WindowStartupStep):
    name = "refresh_ui"

    def run(self, window) -> None:
        if window.ui is None:
            return
        window._update_image_label_background()

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

class MarkShuttingDownStep(WindowShutdownStep):
    name = "mark_shutting_down"

    def run(self, window) -> None:
        window._closing = True
        if getattr(window, "app_context", None) is not None:
            window.app_context._is_shutting_down = True

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
        if hasattr(window, "_debounced_resize_timer"):
            window._debounced_resize_timer.stop()

class CloseDerivedWindowsStep(WindowShutdownStep):
    name = "close_derived_windows"

    def run(self, window) -> None:
        app = QApplication.instance()
        if app is None:
            return

        for widget in list(app.topLevelWidgets()):
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
        ApplyThemeStep(),
        ApplyFontSettingsStep(),
        BootstrapContentStep(),
        RefreshWindowUiStep(),
    )

    def run(self, window) -> None:
        for step in self.steps:
            logger.debug("Main window startup step: %s", step.name)
            step.run(window)

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
        window.show()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def start(self, window) -> None:
        self.show(window)

@dataclass(slots=True)
class MainWindowShutdownPipeline:
    steps: tuple[WindowShutdownStep, ...] = (
        MarkShuttingDownStep(),
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
