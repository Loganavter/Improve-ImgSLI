from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from plugins.settings.events import (
    SettingsChangeLanguageEvent,
    SettingsUIModeChangedEvent,
)
from core.state_management.actions import (
    SetAutoCropBlackBordersAction,
    SetDebugModeEnabledAction,
    SetDisplayResolutionLimitAction,
    SetMaxNameLengthAction,
    SetShowWorkspaceTabsAction,
    SetSystemNotificationsEnabledAction,
    SetThemeAction,
    SetUIFontFamilyAction,
    SetUIFontModeAction,
    SetUIModeAction,
    SetVideoRecordingFpsAction,
    SetZoomInterpolationMethodAction,
)
from shared_toolkit.ui.managers.font_manager import FontManager
from ui.theming import refresh_application_styles

from .models import SettingsDialogData

class SettingsApplicationService(QObject):
    def __init__(self, store, main_controller, event_bus=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.event_bus = event_bus

    def apply(self, data: SettingsDialogData) -> None:
        render_update_needed = self._apply_general_settings(data)
        self._apply_language_settings(data)
        self._apply_ui_font_settings(data)
        render_update_needed = self._apply_viewport_interactive_settings(
            data, render_update_needed
        )
        self._apply_misc_settings(data)

        if render_update_needed:
            self.store.emit_state_change()
            self._emit_update_requested()

    def _apply_general_settings(self, data: SettingsDialogData) -> bool:
        render_update_needed = False
        dispatcher = self.store.get_dispatcher()

        if data.theme != self.store.settings.theme:
            dispatcher.dispatch(SetThemeAction(data.theme))
            window_shell = (
                self.main_controller.window_shell if self.main_controller else None
            )
            if window_shell is not None:
                window_shell.main_window_app.apply_application_theme(data.theme)
            self._save_setting("theme", data.theme)

        if data.resolution_limit != self.store.viewport.render_config.display_resolution_limit:
            dispatcher.dispatch(
                SetDisplayResolutionLimitAction(data.resolution_limit),
                scope="viewport",
            )
            self.store.invalidate_geometry_cache()
            render_update_needed = True
            self._save_setting("display_resolution_limit", data.resolution_limit)

        if data.max_name_length != self.store.viewport.render_config.max_name_length:
            dispatcher.dispatch(
                SetMaxNameLengthAction(data.max_name_length), scope="viewport"
            )
            self._save_setting("max_name_length", data.max_name_length)
            render_update_needed = True

        if data.debug_enabled != self.store.settings.debug_mode_enabled:
            dispatcher.dispatch(SetDebugModeEnabledAction(data.debug_enabled))
            self._save_setting("debug_mode_enabled", data.debug_enabled)

        if (
            getattr(self.store.settings, "system_notifications_enabled", True)
            != data.system_notifications_enabled
        ):
            dispatcher.dispatch(
                SetSystemNotificationsEnabledAction(data.system_notifications_enabled)
            )
            self._save_setting(
                "system_notifications_enabled",
                data.system_notifications_enabled,
            )
            window_shell = (
                self.main_controller.window_shell if self.main_controller else None
            )
            window = getattr(window_shell, "main_window_app", None)
            notification_service = getattr(window, "notification_service", None)
            if notification_service is not None:
                notification_service.set_enabled(data.system_notifications_enabled)
            self.store.emit_state_change("settings")

        if data.show_workspace_tabs != getattr(
            self.store.settings, "show_workspace_tabs", True
        ):
            dispatcher.dispatch(SetShowWorkspaceTabsAction(data.show_workspace_tabs))
            self._save_setting("show_workspace_tabs", data.show_workspace_tabs)
            window_shell = (
                self.main_controller.window_shell if self.main_controller else None
            )
            window = getattr(window_shell, "main_window_app", None)
            ui = getattr(window, "ui", None)
            if ui is not None:
                ui.workspace_tabs.setVisible(data.show_workspace_tabs)
                ui.btn_new_session.setVisible(data.show_workspace_tabs)
                container = getattr(ui, "workspace_tabs_bar", None)
                if container is not None:
                    container.setVisible(data.show_workspace_tabs)

        if data.use_custom_decorations != getattr(
            self.store.settings, "use_custom_decorations", True
        ):
            self.store.settings.use_custom_decorations = data.use_custom_decorations
            self._save_setting("use_custom_decorations", data.use_custom_decorations)
            window_shell = (
                self.main_controller.window_shell if self.main_controller else None
            )
            window = getattr(window_shell, "main_window_app", None)
            if window is not None and hasattr(window, "apply_decoration_mode"):
                window.apply_decoration_mode(data.use_custom_decorations)

        return render_update_needed

    def _apply_language_settings(self, data: SettingsDialogData) -> None:
        if data.language == self.store.settings.current_language:
            return
        if self.event_bus is not None:
            self.event_bus.emit(SettingsChangeLanguageEvent(data.language))
        elif (
            self.main_controller is not None
            and self.main_controller.event_bus is not None
        ):
            self.main_controller.event_bus.emit(
                SettingsChangeLanguageEvent(data.language)
            )

    def _apply_ui_font_settings(self, data: SettingsDialogData) -> None:
        font_mode_normalized = (
            "system_default" if data.ui_font_mode == "system" else data.ui_font_mode
        )
        font_mode_changed = font_mode_normalized != getattr(
            self.store.settings, "ui_font_mode", "builtin"
        )
        font_family_changed = (data.ui_font_family or "") != (
            getattr(self.store.settings, "ui_font_family", "") or ""
        )
        if not (font_mode_changed or font_family_changed):
            return

        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetUIFontModeAction(font_mode_normalized))
        dispatcher.dispatch(SetUIFontFamilyAction(data.ui_font_family or ""))

        font_manager = FontManager.get_instance()
        font_manager.apply_from_state(self.store)
        app = QApplication.instance()
        if app is not None:
            refresh_application_styles(app)

        self._save_setting("ui_font_mode", font_mode_normalized)
        self._save_setting("ui_font_family", data.ui_font_family or "")

        window_shell = self.main_controller.window_shell if self.main_controller else None
        if window_shell is not None:
            try:
                main_window = window_shell.main_window_app
                if hasattr(main_window, "font_path_absolute"):
                    main_window.font_path_absolute = (
                        font_manager.get_font_path_for_image_text(self.store)
                    )
            except Exception:
                pass

    def _apply_viewport_interactive_settings(
        self, data: SettingsDialogData, render_update_needed: bool
    ) -> bool:
        render_update_needed = self._apply_tab_viewport_settings(
            data, render_update_needed
        )
        render_update_needed = self._apply_zoom_interpolation(
            data, render_update_needed
        )
        return render_update_needed

    def _apply_tab_viewport_settings(
        self, data: SettingsDialogData, render_update_needed: bool
    ) -> bool:
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        result = registry.create_service(
            "settings_viewport_application",
            self.store,
            data,
            render_update_needed,
            self._save_setting,
            self._emit_update_requested,
            self.event_bus,
        )
        if result is None:
            return render_update_needed
        return bool(result)

    def _apply_zoom_interpolation(
        self, data: SettingsDialogData, render_update_needed: bool
    ) -> bool:
        vp = self.store.viewport
        dispatcher = self.store.get_dispatcher()
        if (
            data.zoom_interpolation_method
            == getattr(vp.render_config, "zoom_interpolation_method", "BILINEAR")
        ):
            return render_update_needed

        dispatcher.dispatch(
            SetZoomInterpolationMethodAction(data.zoom_interpolation_method),
            scope="viewport",
        )
        self.store.emit_state_change("viewport")
        self._save_setting(
            "zoom_interpolation_method",
            data.zoom_interpolation_method,
        )
        self._emit_update_requested()
        return True

    def _apply_misc_settings(self, data: SettingsDialogData) -> None:
        dispatcher = self.store.get_dispatcher()

        if (
            getattr(self.store.settings, "auto_crop_black_borders", True)
            != data.auto_crop_black_borders
        ):
            dispatcher.dispatch(SetAutoCropBlackBordersAction(data.auto_crop_black_borders))
            self._save_setting("auto_crop_black_borders", data.auto_crop_black_borders)

        if getattr(self.store.settings, "ui_mode", "beginner") != data.ui_mode:
            dispatcher.dispatch(SetUIModeAction(data.ui_mode))
            self._save_setting("ui_mode", data.ui_mode)
            self._emit_ui_mode_changed(data.ui_mode)

        if (
            getattr(self.store.settings, "video_recording_fps", 60)
            != data.video_recording_fps
        ):
            dispatcher.dispatch(SetVideoRecordingFpsAction(data.video_recording_fps))
            self._save_setting("video_recording_fps", data.video_recording_fps)

        prev_backend = getattr(self.store.settings, "rhi_backend", "default") or "default"
        new_backend = (data.rhi_backend or "default").strip().lower()
        if new_backend != prev_backend:
            self.store.settings.rhi_backend = new_backend
            self._save_setting("rhi_backend", new_backend)
            self._notify_render_backend_restart_required(new_backend)

    def _notify_render_backend_restart_required(self, backend: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        window_shell = self.main_controller.window_shell if self.main_controller else None
        parent = getattr(window_shell, "main_window_app", None) if window_shell else None
        tr_lang = getattr(self.store.settings, "current_language", "en")
        try:
            from resources.translations import tr as app_tr
            title = app_tr("settings.render_backend_restart_title", tr_lang)
            text = app_tr("settings.render_backend_restart_message", tr_lang)
        except Exception:
            title = "Restart required"
            text = "The render backend will change after restart."
        QMessageBox.information(parent, title, text.format(backend=backend))

    def _emit_ui_mode_changed(self, ui_mode: str) -> None:
        if self.event_bus is not None:
            self.event_bus.emit(SettingsUIModeChangedEvent(ui_mode))
        elif (
            self.main_controller is not None
            and self.main_controller.event_bus is not None
        ):
            self.main_controller.event_bus.emit(
                SettingsUIModeChangedEvent(ui_mode)
            )

    def _save_setting(self, key, value) -> None:
        if (
            self.main_controller is not None
            and self.main_controller.settings_manager is not None
        ):
            self.main_controller.settings_manager._save_setting(key, value)

    def _emit_update_requested(self) -> None:
        if self.main_controller is not None:
            self.main_controller.update_requested.emit()
