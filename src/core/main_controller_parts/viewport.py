from __future__ import annotations

from PyQt6.QtCore import QTimer

from core.events import (
    AnalysisSetDiffModeEvent,
    SettingsToggleIncludeFilenamesInSavedEvent,
    ViewportOnSliderReleasedEvent,
    ViewportSetMagnifierVisibilityEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportToggleMagnifierEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleOrientationEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
)
from domain.types import Point
from ui.canvas_features.magnifier import MagnifierModeService, MagnifierStoreService
from ui.canvas_features.magnifier.events import (
    SettingsSetMagnifierDividerThicknessEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
)
from ui.canvas_features.magnifier.store import active_magnifier_id, magnifier_enabled

class ViewportActions:
    def __init__(self, controller):
        self.controller = controller
        self._scene_state = MagnifierStoreService(controller.store)
        self._mode_state = MagnifierModeService(controller.store)

    @staticmethod
    def _resolve_new_magnifier_position(active) -> Point:
        if active is None or getattr(active, "position", None) is None:
            return Point(0.5, 0.5)

        base_x = float(active.position.x)
        base_y = float(active.position.y)
        size = float(getattr(active, "size_relative", 0.2) or 0.2)
        step = max(0.06, min(0.32, size * 1.25))

        dir_x = -1.0 if base_x >= 0.7 else 1.0
        dir_y = -1.0 if base_y >= 0.7 else 1.0

        capture_size = float(getattr(active, "capture_size_relative", 0.1) or 0.1)
        safe_margin = max(0.05, min(0.2, capture_size * 0.6))
        min_pos = safe_margin
        max_pos = 1.0 - safe_margin
        if min_pos > max_pos:
            min_pos, max_pos = 0.1, 0.9

        return Point(
            max(min_pos, min(max_pos, base_x + (dir_x * step))),
            max(min_pos, min(max_pos, base_y + (dir_y * step))),
        )

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
            "magnifier_layout_horizontal", is_horizontal_checked
        )

    def toggle_magnifier(self, use_magnifier_checked: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportToggleMagnifierEvent(use_magnifier_checked)
            )
        else:
            if self.controller.store:
                self._mode_state.toggle_from_button(use_magnifier_checked)
                self.controller.store.emit_state_change()
                self.controller.update_requested.emit()
                return
        self.controller.settings_manager._save_setting(
            "use_magnifier",
            magnifier_enabled(self.controller.store.viewport.view_state),
        )
        self.controller.settings_manager.settings.sync()

        window_shell = self.controller.window_shell
        if window_shell is not None:
            def update_ui():
                actual_state = self._mode_state.should_show_panel()
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
            "magnifier_layout_horizontal", is_horizontal_checked
        )

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        if self.controller.event_bus:
            self.controller.event_bus.emit(
                ViewportToggleFreezeMagnifierEvent(freeze_checked)
            )
        self.controller.settings_manager._save_setting(
            "magnifier_freeze", freeze_checked
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
            )
            from ui.canvas_features.guides.actions import SetGuidesEnabledAction

            dispatcher.dispatch(SetGuidesEnabledAction(enabled), scope="viewport")
            dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        else:
            from ui.canvas_features.guides.state import get_guides_widget_state

            state = get_guides_widget_state(self.controller.store.viewport.view_state)
            state.enabled = bool(enabled)
            self.controller.store.invalidate_render_cache()
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def set_magnifier_guides_thickness(self, thickness: int):
        dispatcher = getattr(self.controller.store, "_dispatcher", None)
        if dispatcher:
            from core.state_management.actions import (
                InvalidateRenderCacheAction,
            )
            from ui.canvas_features.guides.actions import (
                SetGuidesEnabledAction,
                SetGuidesThicknessAction,
            )

            dispatcher.dispatch(
                SetGuidesThicknessAction(thickness), scope="viewport"
            )
            dispatcher.dispatch(
                SetGuidesEnabledAction(thickness != 0), scope="viewport"
            )
            dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        else:
            from ui.canvas_features.guides.state import get_guides_widget_state

            state = get_guides_widget_state(self.controller.store.viewport.view_state)
            state.thickness = max(0, int(thickness))
            state.enabled = thickness != 0
            self.controller.store.invalidate_render_cache()
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def add_magnifier(self, position: Point = None):
        if not self.controller.magnifier:
            return
        self._mode_state.prepare_for_add()
        if position is None:
            active = self._scene_state.get_active_or_first_magnifier()
            position = self._resolve_new_magnifier_position(active)
        self.controller.magnifier.add_magnifier(position=position)
        self.controller.store.invalidate_render_cache()
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def remove_active_magnifier(self):
        if not self.controller.magnifier:
            return
        if len(self._scene_state.iter_magnifiers()) <= 1:
            return
        active = active_magnifier_id(self.controller.store.viewport.view_state)
        if active:
            self.controller.magnifier.remove_magnifier(active)
            self._mode_state.normalize_after_remove()
            self.controller.store.invalidate_render_cache()
            self.controller.store.emit_state_change()
            self.controller.update_requested.emit()

    def set_active_magnifier(self, mag_id: str):
        self._scene_state.set_active_object(mag_id)
        self.controller.store.invalidate_render_cache()
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def toggle_magnifier_instance_visibility(self, mag_id: str, visible: bool):
        if not self.controller.magnifier:
            return
        self.controller.magnifier.set_magnifier_visibility(mag_id, visible)
        self.controller.store.invalidate_render_cache()
        self.controller.store.emit_state_change()
        self.controller.update_requested.emit()

    def trigger_metrics_if_needed(self):
        if self.controller.metrics_service:
            self.controller.metrics_service.trigger_metrics_calculation_if_needed()
