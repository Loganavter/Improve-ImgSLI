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
    SetKeyboardOverridesAction,
    SetMaxNameLengthAction,
    SetSystemNotificationsEnabledAction,
    SetThemeAction,
    SetUIFontFamilyAction,
    SetUIFontModeAction,
    SetUIScaleFactorAction,
    SetUIModeAction,
    SetVideoRecordingFpsAction,
    SetZoomInterpolationMethodAction,
)
from shared_toolkit.ui.managers.font_manager import FontManager
from ui.theming import reapply_application_theme, refresh_application_styles

from .models import SettingsDialogData





def _flush_deferred_scale_resyncs(app) -> None:
    """Run the singleShot(0)-deferred scale resyncs synchronously.

    Called while top-level paints are frozen (see
    ``SettingsApplicationService._apply_ui_scale_settings``), so the first
    painted frame after the scale change is already the final layout —
    nothing needs a later event-loop tick to settle.
    """
    if app is None:
        return
    for top in app.topLevelWidgets():  # ALLOWED: system-wide scale fan-out — applies UiScale to every top-level window generically, not tab-specific
        try:
            bar = getattr(top, "_custom_title_bar", None) or getattr(
                top, "_csd_title_bar", None
            )
            sync = getattr(bar, "_sync_balance_spacer", None)
            if callable(sync):
                sync()
        except Exception:
            pass
        try:
            ui = getattr(top, "ui", None)
            strip = getattr(ui, "workspace_tabs", None) if ui is not None else None
            finish = getattr(strip, "_finish_scale_resync", None)
            if callable(finish):
                finish()
        except Exception:
            pass

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
        self._apply_ui_scale_settings(data)
        render_update_needed = self._apply_viewport_interactive_settings(
            data, render_update_needed
        )
        self._apply_misc_settings(data)

        # Single funnel: the settings file is only ever written as a full
        # snapshot of the Store (see SettingsManager.schedule_persist) — the
        # apply path mutates the Store via dispatches above and schedules the
        # snapshot here. Incremental per-key writes from widget state are
        # forbidden (a stale dialog widget silently overwrites good values
        # with defaults; contract test dogma 4).
        self._schedule_persist()

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

        if data.max_name_length != self.store.viewport.render_config.max_name_length:
            dispatcher.dispatch(
                SetMaxNameLengthAction(data.max_name_length), scope="viewport"
            )
            render_update_needed = True

        if data.debug_enabled != self.store.settings.debug_mode_enabled:
            dispatcher.dispatch(SetDebugModeEnabledAction(data.debug_enabled))

        if (
            getattr(self.store.settings, "system_notifications_enabled", True)
            != data.system_notifications_enabled
        ):
            dispatcher.dispatch(
                SetSystemNotificationsEnabledAction(data.system_notifications_enabled)
            )
            self.store.emit_state_change("settings")
        # Always push the live store flag into NotificationService (even when
        # the checkbox did not change) so a stale _enabled cannot outlive OK.
        self._sync_notification_service_enabled()

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

    def _apply_ui_scale_settings(self, data: SettingsDialogData) -> None:
        new_factor = float(getattr(data, "ui_scale_factor", 1.0) or 1.0)
        current = float(
            getattr(self.store.settings, "ui_scale_factor", 1.0) or 1.0
        )
        if abs(new_factor - current) < 1e-9:
            return

        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetUIScaleFactorAction(new_factor))

        from sli_ui_toolkit.managers import UiFont, UiScale, ThemeManager

        app = QApplication.instance()
        # Atomic one-pass apply, same as the theme change: freeze top-level
        # paints across the whole scale fan-out (UiScale.scale_changed
        # handlers, the QSS re-push, font re-apply) and flush the deferred
        # layout resyncs synchronously while frozen — otherwise the
        # singleShot(0)-deferred relayouts (title-bar balance, tab-strip
        # reflow) paint intermediate stale frames and the UI visibly
        # "transforms in steps" instead of one pass.
        with ThemeManager.get_instance().suspend_widget_updates(app):
            UiScale.get_instance().set_factor(new_factor)

            # Order matters (trap §2.7.1): the QSS push below resets
            # WA_SetFont-pinned fonts WITHOUT firing ApplicationFontChange, and
            # FontManager's app.setFont() re-cascade is a no-op event-wise here
            # (the app font itself never changes with the factor, so Qt does not
            # emit ApplicationFontChange for an identical font). Therefore the
            # guaranteed font_changed must come AFTER both, or every Label /
            # UiFont.apply() pin / HUD label ends up stuck on the reset default
            # size.
            if app is not None:
                try:
                    reapply_application_theme(app)
                except Exception:
                    logging.getLogger("ImproveImgSLI").warning(
                        "reapply_application_theme failed during UI-scale apply",
                        exc_info=True,
                    )
            try:
                FontManager.get_instance().apply_from_state(self.store)
            except Exception:
                logging.getLogger("ImproveImgSLI").warning(
                    "font re-apply failed during UI-scale apply",
                    exc_info=True,
                )
            UiFont.get_instance().sync_from_application()
            _flush_deferred_scale_resyncs(app)

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

        window_shell = self.main_controller.window_shell if self.main_controller else None
        if window_shell is not None:
            try:
                main_window = window_shell.main_window_app
                if hasattr(main_window, "font_path_absolute"):
                    main_window.font_path_absolute = (
                        font_manager.get_font_path_for_image_text(self.store)
                    )
            except Exception:
                logging.getLogger("ImproveImgSLI").warning(
                    "font_path_absolute sync failed after font change",
                    exc_info=True,
                )

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
            # Tab viewport apply used to write its own keys incrementally;
            # it now only needs to schedule the full snapshot (the store was
            # already mutated via dispatches) — same single-funnel rule as
            # the rest of the apply path.
            lambda _key, _value: self._schedule_persist(),
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
        self._emit_update_requested()
        return True

    def _apply_misc_settings(self, data: SettingsDialogData) -> None:
        dispatcher = self.store.get_dispatcher()

        if (
            getattr(self.store.settings, "auto_crop_black_borders", True)
            != data.auto_crop_black_borders
        ):
            dispatcher.dispatch(SetAutoCropBlackBordersAction(data.auto_crop_black_borders))
            # Инвалидируем явные кэши всех CropService (DI, без глобала)
            try:
                from shared.image_processing.autocrop import invalidate_all_services

                invalidate_all_services()
            except Exception:
                pass
            # NB: сессионные crop-дефолты (ImageSession/Cache) синхронизирует
            # сам таб в _on_store_scoped_change — хосту запрещён импорт
            # внутренностей таба (contract test_ui_tab_sandbox).
            # Совместимость: старый глобальный кэш (если ещё жив)
            try:
                from shared.image_processing.autocrop_service import invalidate_all as _legacy_inv

                _legacy_inv()
            except Exception:
                pass

        if getattr(self.store.settings, "ui_mode", "beginner") != data.ui_mode:
            dispatcher.dispatch(SetUIModeAction(data.ui_mode))
            self._emit_ui_mode_changed(data.ui_mode)

        if (
            getattr(self.store.settings, "video_recording_fps", 60)
            != data.video_recording_fps
        ):
            dispatcher.dispatch(SetVideoRecordingFpsAction(data.video_recording_fps))

        prev_backend = getattr(self.store.settings, "rhi_backend", "default") or "default"
        new_backend = (data.rhi_backend or "default").strip().lower()
        if new_backend != prev_backend:
            self.store.settings.rhi_backend = new_backend
            self._notify_render_backend_restart_required(new_backend)

        self._apply_keyboard_overrides(data)

    def _apply_keyboard_overrides(self, data: SettingsDialogData) -> None:
        import json

        from ui.actions.keymap import exclusive_overrides
        from plugins.settings.pages.keyboard import _collect_defaults

        defaults = _collect_defaults()
        defaults_map = {
            entry.action_id: (entry.default_shortcut, entry.owner_tab)
            for entry in defaults.all_entries()
        }
        new_overrides = exclusive_overrides(
            defaults_map,
            dict(getattr(data, "keyboard_overrides", None) or {}),
        )
        current = dict(getattr(self.store.settings, "keyboard_overrides", None) or {})
        if new_overrides == current:
            return
        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetKeyboardOverridesAction(new_overrides))
        try:
            from ui.actions.binder import resync_action_shortcuts

            window_shell = (
                self.main_controller.window_shell if self.main_controller else None
            )
            window = (
                getattr(window_shell, "main_window_app", None)
                if window_shell is not None
                else None
            )
            if window is None:
                window = getattr(self.parent(), "parent_widget", None)
            resync_action_shortcuts(window, overrides=new_overrides)
            # Keep CSD menu shortcut labels in sync with remapped chords.
            menu = getattr(window, "_menu_controller", None) if window else None
            rebuild = getattr(menu, "_on_language_changed", None) if menu else None
            if callable(rebuild):
                rebuild(getattr(self.store.settings, "current_language", "en"))
        except Exception:
            import logging

            logging.getLogger("ImproveImgSLI").exception(
                "Failed to resync action shortcuts after keyboard override apply"
            )

    def _notify_render_backend_restart_required(self, backend: str) -> None:
        from shared_toolkit.ui.message_dialog import AppMessageDialog

        window_shell = self.main_controller.window_shell if self.main_controller else None
        parent = getattr(window_shell, "main_window_app", None) if window_shell else None
        tr_lang = getattr(self.store.settings, "current_language", "en")
        try:
            from resources.translations import tr as app_tr
            title = app_tr("settings.render_backend_restart_title", tr_lang)
            text = app_tr("settings.render_backend_restart_message", tr_lang)
            ok_text = app_tr("common.ok", tr_lang)
        except Exception:
            title = "Restart required"
            text = "The render backend will change after restart."
            ok_text = "OK"
        AppMessageDialog.information(
            parent,
            title,
            text.format(backend=backend),
            ok_text=ok_text,
        )

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

    def _schedule_persist(self) -> None:
        """Schedule the debounced full-snapshot save (single funnel).

        The apply path never writes individual keys — the file is only ever
        written as a coherent snapshot of the Store (see
        ``SettingsManager.schedule_persist``), so a stale dialog widget
        cannot silently overwrite good values with its defaults.
        """
        if (
            self.main_controller is not None
            and self.main_controller.settings_manager is not None
        ):
            self.main_controller.settings_manager.schedule_persist(self.store)

    def _resolve_main_window(self):
        window_shell = (
            self.main_controller.window_shell if self.main_controller else None
        )
        window = (
            getattr(window_shell, "main_window_app", None)
            if window_shell is not None
            else None
        )
        if window is None:
            parent = self.parent()
            window = getattr(parent, "parent_widget", None) if parent is not None else None
        return window

    def _sync_notification_service_enabled(self) -> None:
        window = self._resolve_main_window()
        service = getattr(window, "notification_service", None) if window else None
        if service is None:
            return
        enabled = bool(
            getattr(self.store.settings, "system_notifications_enabled", True)
        )
        service.set_enabled(enabled)

    def _emit_update_requested(self) -> None:
        if self.main_controller is not None:
            self.main_controller.update_requested.emit()