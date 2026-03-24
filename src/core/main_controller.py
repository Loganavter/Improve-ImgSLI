import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

from domain.types import Point

from core.events import (
    AnalysisSetDiffModeEvent,
    ComparisonUIUpdateEvent,
    CoreErrorOccurredEvent,
    CoreUpdateRequestedEvent,
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
from core.plugin_system.interfaces import IServicePlugin
from plugins.analysis.services.metrics import MetricsService
from shared_toolkit.workers import GenericWorker

if TYPE_CHECKING:
    from core.bootstrap import ApplicationContext

logger = logging.getLogger("ImproveImgSLI")

class MainController(QObject):

    error_occurred = pyqtSignal(str)
    update_requested = pyqtSignal()
    ui_update_requested = pyqtSignal(list)
    start_interactive_movement = pyqtSignal()
    stop_interactive_movement = pyqtSignal()

    video_export_progress = pyqtSignal(int)
    video_export_finished = pyqtSignal(bool)

    def __init__(self, context: "ApplicationContext"):
        super().__init__()
        self.context = context
        self.store = context.store
        self.thread_pool = context.thread_pool
        self.settings_manager = context.settings_manager
        self.event_bus = context.event_bus
        self.plugin_coordinator = context.plugin_coordinator
        self.session_manager = context.session_manager
        self.presenter = None

        self.recorder = None
        self.video_exporter = None
        self.clipboard_service = None

        self.metrics_service: MetricsService | None = None
        self.analysis_plugin = (
            self.plugin_coordinator.get_plugin("analysis")
            if self.plugin_coordinator
            else None
        )
        if self.analysis_plugin:
            self.metrics_service = getattr(
                self.analysis_plugin, "metrics_service", None
            )
            self.analysis_ctrl = self.analysis_plugin.get_controller()
        else:
            self.analysis_ctrl = None

        self.magnifier_plugin = (
            self.plugin_coordinator.get_plugin("magnifier")
            if self.plugin_coordinator
            else None
        )
        self.viewport_plugin = (
            self.plugin_coordinator.get_plugin("viewport")
            if self.plugin_coordinator
            else None
        )
        self.viewport_ctrl = (
            self.viewport_plugin.get_controller() if self.viewport_plugin else None
        )

        self.export_plugin = (
            self.plugin_coordinator.get_plugin("export")
            if self.plugin_coordinator
            else None
        )

        if self.export_plugin:
            self.export_plugin.configure_controller(main_controller=self)

            recording_plugin = (
                self.plugin_coordinator.get_plugin_by_capability("recording")
                if self.plugin_coordinator
                else None
            )
            if recording_plugin and isinstance(recording_plugin, IServicePlugin):
                self.recorder = recording_plugin.get_service()
            else:

                self.recorder = getattr(self.export_plugin, "recorder", None)

            if self.recorder:
                self.store.set_recorder(self.recorder)
                self.store.recorder = self.recorder
            self.video_exporter = getattr(self.export_plugin, "video_exporter", None)
            self.clipboard_service = getattr(
                self.export_plugin, "clipboard_service", None
            )
            self.export_ctrl = self.export_plugin.get_controller()
        else:
            self.export_ctrl = None
        self.settings_plugin = (
            self.plugin_coordinator.get_plugin("settings")
            if self.plugin_coordinator
            else None
        )
        self.settings_ctrl = (
            self.settings_plugin.get_controller() if self.settings_plugin else None
        )

        self.comparison_plugin = (
            self.plugin_coordinator.get_plugin("comparison")
            if self.plugin_coordinator
            else None
        )
        self.session_ctrl = (
            getattr(self.comparison_plugin, "session_ctrl", None)
            if self.comparison_plugin
            else None
        )

        if self.event_bus:

            self.event_bus.subscribe(
                CoreUpdateRequestedEvent, self._on_core_update_requested
            )
            self.event_bus.subscribe(
                CoreErrorOccurredEvent, self._on_core_error_occurred
            )
            self.event_bus.subscribe(
                ComparisonUIUpdateEvent, self._on_comparison_ui_update
            )

    def _on_core_update_requested(self, event: CoreUpdateRequestedEvent):
        self.update_requested.emit()

    def _on_core_error_occurred(self, event: CoreErrorOccurredEvent):
        self.error_occurred.emit(event.error)

    def _on_comparison_ui_update(self, event: ComparisonUIUpdateEvent):

        self.ui_update_requested.emit(list(event.components))

    def set_presenter(self, presenter_ref):
        self.presenter = presenter_ref

        if self.comparison_plugin:
            self.comparison_plugin.set_presenter(presenter_ref)
        if self.session_ctrl:
            self.session_ctrl.presenter = presenter_ref
        if self.export_plugin:
            self.export_plugin.set_presenter(presenter_ref)
        elif self.export_ctrl:
            self.export_ctrl.presenter = presenter_ref
        if self.settings_plugin:
            self.settings_plugin.set_presenter(presenter_ref)
        elif self.settings_ctrl:
            self.settings_ctrl.presenter = presenter_ref

    def list_session_blueprints(self):
        if not self.session_manager:
            return ()
        return self.session_manager.list_session_blueprints()

    def create_workspace_session(
        self,
        session_type: str,
        *,
        activate: bool = True,
        title: str | None = None,
        metadata: dict | None = None,
    ):
        if not self.session_manager:
            raise RuntimeError("SessionManager is not available")
        return self.session_manager.create_session(
            session_type,
            activate=activate,
            title=title,
            metadata=metadata,
        )

    def switch_workspace_session(self, session_id: str) -> bool:
        if not self.session_manager:
            return False
        return self.session_manager.switch_to_session(session_id)

    def toggle_orientation(self, is_horizontal_checked: bool):
        if self.event_bus:
            self.event_bus.emit(ViewportToggleOrientationEvent(is_horizontal_checked))
            self.event_bus.emit(
                ViewportToggleMagnifierOrientationEvent(is_horizontal_checked)
            )

        if self.presenter:
            self.presenter.ui.btn_magnifier_orientation.setChecked(
                is_horizontal_checked, emit_signal=False
            )
        self.settings_manager._save_setting("is_horizontal", is_horizontal_checked)
        self.settings_manager._save_setting(
            "magnifier_is_horizontal", is_horizontal_checked
        )

    def toggle_magnifier(self, use_magnifier_checked: bool):
        if self.event_bus:

            self.event_bus.emit(ViewportToggleMagnifierEvent(use_magnifier_checked))
        else:

            dispatcher = getattr(self.store, "_dispatcher", None)
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
                    and not self.store.viewport.active_magnifier_id
                ):
                    dispatcher.dispatch(
                        SetActiveMagnifierIdAction("default"), scope="viewport"
                    )
            else:

                if (
                    self.store
                    and getattr(self.store.viewport, "use_magnifier", None)
                    != use_magnifier_checked
                ):
                    self.store.viewport.use_magnifier = use_magnifier_checked
                    if (
                        use_magnifier_checked
                        and not self.store.viewport.active_magnifier_id
                    ):
                        self.store.viewport.active_magnifier_id = "default"
                    self.store.emit_state_change()
                    self.update_requested.emit()

        self.settings_manager._save_setting("use_magnifier", use_magnifier_checked)
        self.settings_manager.settings.sync()

        if self.presenter:
            from PyQt6.QtCore import QTimer

            def update_ui():

                actual_state = getattr(self.store.viewport, "use_magnifier", False)
                self.presenter.ui.toggle_magnifier_panel_visibility(actual_state)

            QTimer.singleShot(10, update_ui)

    def toggle_include_filenames_in_saved(self, include_checked: bool):
        if self.event_bus:
            self.event_bus.emit(
                SettingsToggleIncludeFilenamesInSavedEvent(include_checked)
            )

        if (
            self.store
            and getattr(self.store.viewport, "include_file_names_in_saved", None)
            != include_checked
        ):
            self.store.viewport.include_file_names_in_saved = include_checked

            self.store.invalidate_render_cache()
            self.store.emit_state_change()
            self.update_requested.emit()

        try:
            self.settings_manager._save_setting(
                "include_file_names_in_saved", include_checked
            )
            self.settings_manager.settings.sync()
        except Exception:
            pass

    def toggle_magnifier_orientation(self, is_horizontal_checked: bool):
        if self.event_bus:
            self.event_bus.emit(
                ViewportToggleMagnifierOrientationEvent(is_horizontal_checked)
            )

        self.settings_manager._save_setting(
            "magnifier_is_horizontal", is_horizontal_checked
        )

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        if self.event_bus:
            self.event_bus.emit(ViewportToggleFreezeMagnifierEvent(freeze_checked))

        self.settings_manager._save_setting("freeze_magnifier", freeze_checked)

    def on_slider_released(self, setting_name: str, value_to_save_provider):
        if self.event_bus:
            self.event_bus.emit(
                ViewportOnSliderReleasedEvent(setting_name, value_to_save_provider)
            )

        if hasattr(self, "settings_manager") and self.settings_manager:
            value = value_to_save_provider()
            self.settings_manager._save_setting(setting_name, value)

    def set_magnifier_visibility(
        self,
        left: bool | None = None,
        center: bool | None = None,
        right: bool | None = None,
    ):
        if self.event_bus:
            self.event_bus.emit(
                ViewportSetMagnifierVisibilityEvent(
                    left or False, center or False, right or False
                )
            )
        if self.event_bus:
            self.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

    def export_video_from_editor(
        self, frames, fps, resolution=(1920, 1080), options=None
    ):

        if not self.video_exporter:
            return

        w, h = resolution

        if w % 2 != 0:
            w += 1
        if h % 2 != 0:
            h += 1
        safe_resolution = (w, h)

        def export_task(progress_callback):
            return self.video_exporter.export_recorded_video(
                safe_resolution,
                fps,
                snapshots_override=frames,
                export_options=options,
                progress_callback=progress_callback,
            )

        worker = GenericWorker(export_task)
        export_completed = {"signaled": False}

        worker.signals.progress.connect(self.video_export_progress.emit)

        worker.kwargs["progress_callback"] = worker.signals.progress

        def on_success(path):
            export_completed["signaled"] = True
            if path:
                logger.info(f"Video export finished: {path}")
                self.video_export_finished.emit(True)

                if self.presenter and hasattr(
                    self.presenter.main_window_app, "notify_system"
                ):
                    self.presenter.main_window_app.notify_system(
                        "Video Exported", f"Saved to: {path}", image_path=None
                    )
            else:
                self.video_export_finished.emit(False)

        def on_error(err):
            export_completed["signaled"] = True
            logger.error(f"Video export failed: {err}")
            self.error_occurred.emit(f"Video export failed: {err}")
            self.video_export_finished.emit(False)

        def on_finished():
            if not export_completed["signaled"]:
                self.video_export_finished.emit(False)

        worker.signals.result.connect(on_success)
        worker.signals.error.connect(on_error)
        worker.signals.finished.connect(on_finished)

        self.thread_pool.start(worker)

    def get_video_export_image(self, path: str, auto_crop: bool = False):
        if not self.video_exporter:
            return None
        return self.video_exporter._get_image(path, auto_crop)

    def cancel_video_export(self):
        if self.video_exporter:
            self.video_exporter.request_cancel()

    def invalidate_video_export_bounds_cache(self):
        if self.video_exporter:
            self.video_exporter.invalidate_bounds_cache()

    def calculate_video_export_global_bounds(self, snapshots, auto_crop: bool = False):
        if not self.video_exporter:
            return None
        return self.video_exporter.calculate_global_canvas_bounds(snapshots, auto_crop)

    def set_diff_mode(self, mode: str):
        if self.event_bus:
            self.event_bus.emit(AnalysisSetDiffModeEvent(mode))
            self.event_bus.emit(ViewportUpdateMagnifierCombinedStateEvent())

    def set_divider_line_thickness(self, thickness: int):
        is_visible = thickness > 0

        if self.event_bus:
            self.event_bus.emit(
                SettingsToggleDividerLineVisibilityEvent(not is_visible)
            )
            self.event_bus.emit(SettingsSetDividerLineThicknessEvent(thickness))
        self.update_requested.emit()

    def set_magnifier_divider_thickness(self, thickness: int):
        is_visible = thickness > 0

        if self.event_bus:
            self.event_bus.emit(
                SettingsToggleMagnifierDividerVisibilityEvent(not is_visible)
            )
            self.event_bus.emit(SettingsSetMagnifierDividerThicknessEvent(thickness))
        self.update_requested.emit()

    def toggle_magnifier_guides(self, enabled: bool):
        self.store.viewport.show_magnifier_guides = enabled

        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        self.update_requested.emit()

    def set_magnifier_guides_thickness(self, thickness: int):
        self.store.viewport.magnifier_guides_thickness = thickness

        if thickness == 0:
            self.store.viewport.show_magnifier_guides = False
        else:
            self.store.viewport.show_magnifier_guides = True

        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        self.update_requested.emit()

    def add_magnifier(self, position: Point = None):
        if not self.magnifier_plugin:
            return
        if position is None:
            position = Point(0.5, 0.5)
        self.magnifier_plugin.add_magnifier(position=position)
        self.store.emit_state_change()
        self.update_requested.emit()

    def remove_active_magnifier(self):
        if not self.magnifier_plugin:
            return
        active = self.store.viewport.active_magnifier_id
        if active:
            self.magnifier_plugin.remove_magnifier(active)
            self.store.emit_state_change()
            self.update_requested.emit()

    def set_active_magnifier(self, mag_id: str):
        self.store.viewport.active_magnifier_id = mag_id
        self.store.emit_state_change()
        self.update_requested.emit()

    def toggle_magnifier_instance_visibility(self, mag_id: str, visible: bool):
        if not self.magnifier_plugin:
            return
        self.magnifier_plugin.set_magnifier_visibility(mag_id, visible)
        self.store.emit_state_change()
        self.update_requested.emit()

    def _trigger_metrics_calculation_if_needed(self):
        if self.metrics_service:
            self.metrics_service.trigger_metrics_calculation_if_needed()
