from __future__ import annotations

from PyQt6.QtCore import QTimer

from core.events import (
    AnalysisSetDiffModeEvent,
    SettingsSetDividerLineThicknessEvent,
    SettingsSetMagnifierDividerThicknessEvent,
    SettingsToggleDividerLineVisibilityEvent,
    SettingsToggleIncludeFilenamesInSavedEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
    ViewportOnSliderReleasedEvent,
    ViewportSetMagnifierVisibilityEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportToggleMagnifierEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleOrientationEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
)
from domain.types import Point

class ViewportActions:
    def __init__(self, controller):
        self.controller = controller

    def toggle_orientation(self, is_horizontal_checked: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportToggleOrientationEvent(is_horizontal_checked)
            )
            self.controller.event_bus.emit(
                ViewportToggleMagnifierOrientationEvent(is_horizontal_checked)
            )

        window_shell = self.controller.window_shell
        if window_shell is not None:
            window_shell.set_magnifier_orientation_checked(is_horizontal_checked)
        self.controller.settings_manager._save_setting(
            "is_horizontal", is_horizontal_checked
        )
        self.controller.settings_manager._save_setting(
            "magnifier_is_horizontal", is_horizontal_checked
        )

    def toggle_magnifier(self, use_magnifier_checked: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportToggleMagnifierEvent(use_magnifier_checked)
            )
        else:
            dispatcher = getattr(self.controller.store, "_dispatcher", None)
            if dispatcher:
                from core.state_management.actions import (
                    SetActiveMagnifierIdAction,
                    ToggleMagnifierAction,
                )

                dispatcher.dispatch(
                    ToggleMagnifierAction(use_magnifier_checked), scope="viewport"
                )
                if (
                    use_magnifier_checked
                    and not self.controller.store.viewport.view_state.active_magnifier_id
                ):
                    dispatcher.dispatch(
                        SetActiveMagnifierIdAction("default"), scope="viewport"
                    )
            elif (
                self.controller.store
                and self.controller.store.viewport.view_state.use_magnifier
                != use_magnifier_checked
            ):
                self.controller.store.viewport.view_state.use_magnifier = use_magnifier_checked
                if (
                    use_magnifier_checked
                    and not self.controller.store.viewport.view_state.active_magnifier_id
                ):
                    self.controller.store.viewport.view_state.active_magnifier_id = "default"
                self.controller.store.emit_state_change()
                self.controller.update_requested.emit()

        self.controller.settings_manager._save_setting(
            "use_magnifier", use_magnifier_checked
        )
        self.controller.settings_manager.settings.sync()

        window_shell = self.controller.window_shell
        if window_shell is not None:
            def update_ui():
                actual_state = self.controller.store.viewport.view_state.use_magnifier
                window_shell.toggle_magnifier_panel_visibility(actual_state)

            QTimer.singleShot(10, update_ui)

    def toggle_include_filenames_in_saved(self, include_checked: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                SettingsToggleIncludeFilenamesInSavedEvent(include_checked)
            )

        if (
            self.controller.store
            and self.controller.store.viewport.render_config.include_file_names_in_saved
            != include_checked
        ):
            dispatcher = getattr(self.controller.store, "_dispatcher", None)
            if dispatcher:
                from core.state_management.actions import (
                    InvalidateRenderCacheAction,
                    SetIncludeFileNamesInSavedAction,
                )

                dispatcher.dispatch(
                    SetIncludeFileNamesInSavedAction(include_checked),
                    scope="viewport",
                )
                dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
            else:
                self.controller.store.viewport.render_config.include_file_names_in_saved = include_checked
                self.controller.store.invalidate_render_cache()
            self.controller.store.emit_state_change()
            self.controller.update_requested.emit()

        try:
            self.controller.settings_manager._save_setting(
                "include_file_names_in_saved", include_checked
            )
            self.controller.settings_manager.settings.sync()
        except Exception:
            pass

    def toggle_magnifier_orientation(self, is_horizontal_checked: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportToggleMagnifierOrientationEvent(is_horizontal_checked)
            )
        self.controller.settings_manager._save_setting(
            "magnifier_is_horizontal", is_horizontal_checked
        )

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportToggleFreezeMagnifierEvent(freeze_checked)
            )
        self.controller.settings_manager._save_setting(
            "freeze_magnifier", freeze_checked
        )

    def on_slider_released(self, setting_name: str, value_to_save_provider):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportOnSliderReleasedEvent(setting_name, value_to_save_provider)
            )
        if self.controller.settings_manager:
            self.controller.settings_manager._save_setting(
                setting_name, value_to_save_provider()
            )

    def set_magnifier_visibility(
        self,
        left: bool | None = None,
        center: bool | None = None,
        right: bool | None = None,
    ):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportSetMagnifierVisibilityEvent(
                    left or False, center or False, right or False
                )
            )
            self.controller.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

    def set_diff_mode(self, mode: str):
        if self.controller.event_bus:
            self.controller.event_bus.emit(AnalysisSetDiffModeEvent(mode))
            self.controller.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

    def toggle_divider_line_visibility(self, visible: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                SettingsToggleDividerLineVisibilityEvent(visible)
            )
        elif self.controller.settings and hasattr(
            self.controller.settings, "toggle_divider_line_visibility"
        ):
            self.controller.settings.toggle_divider_line_visibility(visible)

    def set_divider_line_thickness(self, thickness: int):
        is_visible = thickness > 0
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                SettingsToggleDividerLineVisibilityEvent(is_visible)
            )
            self.controller.event_bus.emit(
                SettingsSetDividerLineThicknessEvent(thickness)
            )
        self.controller.update_requested.emit()

    def set_magnifier_divider_thickness(self, thickness: int):
        is_visible = thickness > 0
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                SettingsToggleMagnifierDividerVisibilityEvent(is_visible)
            )
            self.controller.event_bus.emit(
                SettingsSetMagnifierDividerThicknessEvent(thickness)
            )
        self.controller.update_requested.emit()

    def toggle_magnifier_guides(self, enabled: bool):
        dispatcher = getattr(self.controller.store, "_dispatcher", None)
        if dispatcher:
            from core.state_management.actions import (
                InvalidateRenderCacheAction,
                SetShowMagnifierGuidesAction,
            )

            dispatcher.dispatch(SetShowMagnifierGuidesAction(enabled), scope="viewport")
            dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        else:
            self.controller.store.viewport.render_config.show_magnifier_guides = enabled
            self.controller.store.invalidate_render_cache()
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def set_magnifier_guides_thickness(self, thickness: int):
        dispatcher = getattr(self.controller.store, "_dispatcher", None)
        if dispatcher:
            from core.state_management.actions import (
                InvalidateRenderCacheAction,
                SetMagnifierGuidesThicknessAction,
                SetShowMagnifierGuidesAction,
            )

            dispatcher.dispatch(
                SetMagnifierGuidesThicknessAction(thickness), scope="viewport"
            )
            dispatcher.dispatch(
                SetShowMagnifierGuidesAction(thickness != 0), scope="viewport"
            )
            dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        else:
            self.controller.store.viewport.render_config.magnifier_guides_thickness = thickness
            self.controller.store.viewport.render_config.show_magnifier_guides = thickness != 0
            self.controller.store.invalidate_render_cache()
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def add_magnifier(self, position: Point = None):
        if not self.controller.magnifier:
            return
        self.controller.magnifier.add_magnifier(position=position or Point(0.5, 0.5))
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def remove_active_magnifier(self):
        if not self.controller.magnifier:
            return
        active = self.controller.store.viewport.view_state.active_magnifier_id
        if active:
            self.controller.magnifier.remove_magnifier(active)
            self.controller.store.emit_state_change()
            self.controller.update_requested.emit()

    def set_active_magnifier(self, mag_id: str):
        dispatcher = getattr(self.controller.store, "_dispatcher", None)
        if dispatcher:
            from core.state_management.actions import SetActiveMagnifierIdAction

            dispatcher.dispatch(SetActiveMagnifierIdAction(mag_id), scope="viewport")
        else:
            self.controller.store.viewport.view_state.active_magnifier_id = mag_id
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def toggle_magnifier_instance_visibility(self, mag_id: str, visible: bool):
        if not self.controller.magnifier:
            return
        self.controller.magnifier.set_magnifier_visibility(mag_id, visible)
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def trigger_metrics_if_needed(self):
        if self.controller.metrics_service:
            self.controller.metrics_service.trigger_metrics_calculation_if_needed()
