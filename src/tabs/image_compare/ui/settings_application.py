from __future__ import annotations

from typing import Callable

from tabs.image_compare.canvas.registry import registry


class ImageCompareSettingsApplication:
    def __init__(
        self,
        store,
        data,
        render_update_needed: bool,
        save_setting: Callable,
        emit_update_requested: Callable,
        event_bus=None,
    ):
        self.store = store
        self.data = data
        self.render_update_needed = bool(render_update_needed)
        self._save_setting = save_setting
        self._emit_update_requested = emit_update_requested
        self.event_bus = event_bus

    def apply(self) -> bool:
        self._apply_magnifier_movement_optimization()
        self._apply_magnifier_interpolation()
        self._apply_laser_interpolation()
        self._apply_magnifier_behavior_settings()
        self._apply_metrics_settings()
        return self.render_update_needed

    def _apply_metrics_settings(self) -> bool:
        image_state = self.store.viewport.session_data.image_state
        if image_state is None:
            return False

        from core.state_management.actions import (
            SetAutoCalculatePsnrAction,
            SetAutoCalculateSsimAction,
        )
        from plugins.settings.events import SettingsAnalysisMetricsRequestedEvent

        dispatcher = self.store.get_dispatcher()
        metrics_changed = False

        if self.data.auto_calculate_psnr != image_state.auto_calculate_psnr:
            dispatcher.dispatch(
                SetAutoCalculatePsnrAction(self.data.auto_calculate_psnr),
                scope="viewport",
            )
            self._save_setting("auto_calculate_psnr", self.data.auto_calculate_psnr)
            metrics_changed = True

        if self.data.auto_calculate_ssim != image_state.auto_calculate_ssim:
            dispatcher.dispatch(
                SetAutoCalculateSsimAction(self.data.auto_calculate_ssim),
                scope="viewport",
            )
            self._save_setting("auto_calculate_ssim", self.data.auto_calculate_ssim)
            metrics_changed = True

        if metrics_changed:
            self.store.emit_state_change("viewport")
            if self.event_bus is not None:
                updated_state = self.store.viewport.session_data.image_state
                self.event_bus.emit(
                    SettingsAnalysisMetricsRequestedEvent(
                        payload={
                            "psnr": updated_state.auto_calculate_psnr,
                            "ssim": updated_state.auto_calculate_ssim,
                        }
                    )
                )
        return metrics_changed

    def _execute_alias(self, alias: str, *args):
        command = registry().get_feature_command_by_alias(alias)
        if command is None:
            return None
        return command(*args)

    def _apply_magnifier_movement_optimization(self) -> None:
        view = self.store.viewport.view_state
        value = self.data.optimize_magnifier_movement
        if value == view.optimize_interactive_movement:
            return
        if self._execute_alias(
            "overlay.settings.set_optimize_movement",
            self.store,
            value,
        ):
            self.render_update_needed = True
            self._save_setting("optimize_magnifier_movement", value)

    def _apply_magnifier_interpolation(self) -> None:
        method = self.data.magnifier_interpolation_method
        if not self._execute_alias(
            "overlay.settings.set_movement_interpolation",
            self.store,
            method,
        ):
            return

        self.store.emit_state_change()
        self._save_setting("magnifier_movement_interpolation_method", method)
        self._emit_update_requested()
        self.render_update_needed = True

    def _apply_laser_interpolation(self) -> None:
        vp = self.store.viewport
        guides_state = self._execute_alias("guides.widget_state", vp.view_state) or type(
            "_GuidesFallback",
            (),
            {
                "smoothing_enabled": False,
                "smoothing_interpolation_method": "BILINEAR",
            },
        )()

        smoothing_enabled = self.data.optimize_laser_smoothing
        if smoothing_enabled != guides_state.smoothing_enabled:
            self._execute_alias(
                "guides.set_smoothing_enabled",
                self.store,
                smoothing_enabled,
            )
            self.render_update_needed = True
            self._save_setting("guides.smoothing.enabled", smoothing_enabled)

        method = self.data.laser_interpolation_method
        if method == guides_state.smoothing_interpolation_method:
            return

        self._execute_alias(
            "guides.set_smoothing_interpolation_method",
            self.store,
            method,
        )
        self.store.emit_state_change()
        self._save_setting("guides.smoothing.interpolation_method", method)
        self._emit_update_requested()
        self.render_update_needed = True

    def _apply_magnifier_behavior_settings(self) -> None:
        changes = self._execute_alias(
            "overlay.settings.apply_behavior",
            self.store,
            {
                "intersection_highlight_enabled": (
                    self.data.magnifier_intersection_highlight_enabled
                ),
                "auto_color_new_instances": (
                    self.data.magnifier_auto_color_new_instances
                ),
            },
        )
        if not changes:
            return
        if "intersection_highlight_enabled" in changes:
            self._save_setting(
                "magnifier.intersection_highlight.enabled",
                changes["intersection_highlight_enabled"],
            )
        if "auto_color_new_instances" in changes:
            self._save_setting(
                "magnifier.auto_color_new_instances.enabled",
                changes["auto_color_new_instances"],
            )
        self.store.emit_state_change("viewport")
        self._emit_update_requested()
        self.render_update_needed = True
