"""Active-tab create_service handlers for image_compare.

Host capabilities resolve through TabRegistry.create_service →
ImageCompareTab.create_service → this module. Keep service_id
strings stable; only move wiring here, not behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tabs.image_compare.tab import ImageCompareTab


def create_service(
    tab: "ImageCompareTab",
    service_id: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    if service_id == "contribute_settings":
        registry = args[0] if args else kwargs.get("registry")
        if registry is None:
            return None
        tab._register_settings(registry)
        return True
    if service_id == "contribute_actions":
        registry = args[0] if args else kwargs.get("registry")
        if registry is None:
            return None
        tab._register_actions(registry)
        return True
    if service_id == "contribute_keymap_defaults":
        registry = args[0] if args else kwargs.get("registry")
        if registry is None:
            return None
        from tabs.image_compare.actions import contribute_keymap_defaults

        contribute_keymap_defaults(registry)
        return True
    if service_id == "contribute_help":
        registry = args[0] if args else kwargs.get("registry")
        if registry is None:
            return None
        from tabs.image_compare.help import contribute_help

        contribute_help(registry)
        return True
    if service_id == "snapshot_frame_renderer":
        from tabs.image_compare.services.video_snapshot_rendering import (
            SnapshotFrameRenderer,
        )

        return SnapshotFrameRenderer(*args, **kwargs)
    if service_id == "still_snapshot_bounds":
        from tabs.image_compare.services.snapshot_render_plan_builder import (
            calculate_still_snapshot_bounds,
        )

        return calculate_still_snapshot_bounds(*args, **kwargs)
    if service_id == "global_canvas_bounds":
        from tabs.image_compare.services.snapshot_render_plan_builder import (
            calculate_global_canvas_bounds,
        )

        return calculate_global_canvas_bounds(*args, **kwargs)
    if service_id == "live_frame_snapshot":
        from tabs.image_compare.services.live_snapshot import (
            build_live_frame_snapshot,
        )

        return build_live_frame_snapshot(*args, **kwargs)
    if service_id == "export_save_context_builder":
        from tabs.image_compare.services.export_context_builder import (
            ExportContextBuilder,
        )

        return ExportContextBuilder(*args, **kwargs)
    if service_id == "export_state_coordinator":
        from tabs.image_compare.services.export_state import ExportStateCoordinator

        return ExportStateCoordinator(*args, **kwargs)
    if service_id == "export_save_flow":
        from tabs.image_compare.services.export_save_flow import (
            ExportSaveFlowCoordinator,
        )

        return ExportSaveFlowCoordinator(*args, **kwargs)
    if service_id == "image_export_service":
        from tabs.image_compare.services.image_export import ExportService

        return ExportService(*args, **kwargs)
    if service_id == "clipboard_paste_service":
        from tabs.image_compare.services.clipboard import ClipboardService

        return ClipboardService(*args, widget=tab._widget, **kwargs)
    if service_id == "begin_pending_image_insert":
        from tabs.image_compare.pending_image_insert import begin_pending_image_insert

        paths = args[0] if args else kwargs.get("paths")
        if paths is None:
            return False
        return begin_pending_image_insert(tab, paths)
    if service_id == "layout_manager":
        if tab._widget is None:
            return None
        from tabs.image_compare.ui.layout_manager import ImageCompareLayoutManager

        # First positional arg is the caller's host `ui`
        # (`Ui_ImageComparisonApp`) — image_compare's buttons/containers
        # live on `tab._widget` (see `ImageComparePrimitivesFactory`),
        # not on the host object, so substitute it here rather than
        # forwarding the host's blindly.
        parent_window = args[1] if len(args) > 1 else kwargs.get("parent_window")
        return ImageCompareLayoutManager(tab._widget, parent_window)
    if service_id == "settings_color_picker_coordinator":
        from tabs.image_compare.ui.settings_color_pickers import (
            SettingsColorPickerCoordinator,
        )

        return SettingsColorPickerCoordinator(*args, **kwargs)
    if service_id == "settings_viewport_application":
        from tabs.image_compare.ui.settings_application import (
            ImageCompareSettingsApplication,
        )

        return ImageCompareSettingsApplication(*args, **kwargs).apply()
    if service_id == "settings_metrics_query":
        from tabs.image_compare.ui.settings_persistence import (
            query_image_compare_metrics_settings,
        )

        return query_image_compare_metrics_settings(*args, **kwargs)
    if service_id == "session_has_content":
        store = args[0] if args else kwargs.get("store")
        image_state = store.viewport.session_data.image_state
        return image_state is not None and bool(image_state.image1)
    if service_id == "settings_canvas_feature_load":
        from tabs.image_compare.ui.settings_persistence import (
            load_image_compare_feature_settings,
        )

        load_image_compare_feature_settings(*args, **kwargs)
        return True
    if service_id == "settings_canvas_feature_save":
        from tabs.image_compare.ui.settings_persistence import (
            save_image_compare_feature_settings,
        )

        save_image_compare_feature_settings(*args, **kwargs)
        return True
    if service_id == "magnifier_visibility_flyout":
        from tabs.image_compare.ui.magnifier_visibility_flyout import (
            MagnifierVisibilityFlyout,
        )

        return MagnifierVisibilityFlyout(*args, **kwargs)
    if service_id == "magnifier_visibility_controller":
        from tabs.image_compare.ui.transient_magnifier import (
            MagnifierVisibilityController,
        )

        return MagnifierVisibilityController(*args, widget=tab._widget, **kwargs)
    if service_id == "magnifier_instances_popup_controller":
        from tabs.image_compare.ui.transient_magnifier_instances import (
            MagnifierInstancesPopupController,
        )

        return MagnifierInstancesPopupController(
            *args, widget=tab._widget, **kwargs
        )
    if service_id == "toolbar_presenter":
        from tabs.image_compare.presenters.toolbar_presenter import (
            ToolbarPresenter,
        )

        return ToolbarPresenter(*args, widget=tab._widget, **kwargs)
    if service_id == "install_translations":
        if tab._widget is None:
            return False
        from tabs.image_compare.ui.translations import (
            install_image_compare_translations,
        )

        # Broadcast arg is the host `ui`, which no longer carries
        # image_compare's widgets (those live on `tab._widget` since
        # the primitives factory attaches them there, see
        # `assemble_host_page`/`ImageComparePrimitivesFactory`).
        install_image_compare_translations(tab._widget)
        return True
    if service_id == "canvas_widget_class":
        from tabs.image_compare.canvas.widget import get_canvas_widget_class

        return get_canvas_widget_class()
    if service_id == "canvas_render_scene":
        from tabs.image_compare.canvas.scene import build_render_scene

        return build_render_scene(*args, **kwargs)
    if service_id == "canvas_reset_overlays":
        from tabs.image_compare.canvas.helpers import reset_canvas_overlays

        canvas = args[0]
        reset_canvas_overlays(canvas)
        return True
    if service_id == "canvas_feature_command":
        from tabs.image_compare.canvas.registry import registry

        feature_name, command_id, *command_args = args
        command = registry().get_feature_command(feature_name, command_id)
        if command is None:
            return None
        return command(*command_args, **kwargs)
    if service_id == "canvas_feature_command_alias":
        from tabs.image_compare.canvas.registry import registry

        alias, *command_args = args
        command = registry().get_feature_command_by_alias(alias)
        if command is None:
            return None
        return command(*command_args, **kwargs)
    if service_id == "canvas_plan_split_sync":
        from tabs.image_compare.canvas.registry import registry

        command = registry().get_feature_command_by_alias("splitter.sync_split_position")
        if command is None:
            return None
        return command(*args, **kwargs)
    if service_id == "canvas_live_runtime_overlays":
        from tabs.image_compare.canvas.registry import registry

        store, canvas = args
        return registry().apply_feature_live_runtime_overlays(store, canvas)
    if service_id == "canvas_snapshot_overlay_params":
        canvas, plan = args
        canvas.set_guides_params(
            plan.guides_enabled,
            plan.guides_color,
            plan.guides_thickness,
        )
        canvas.set_capture_color(plan.capture_color)
        return True
    if service_id == "canvas_plan_runtime_overlays":
        from tabs.image_compare.canvas.presentation.plan_applicator import (
            apply_plan_runtime_overlays,
        )

        return apply_plan_runtime_overlays(*args, **kwargs)
    if service_id == "canvas_sync_geometry_state":
        from tabs.image_compare.canvas.presentation.plan_applicator import (
            sync_geometry_state,
        )

        return sync_geometry_state(*args, **kwargs)
    if service_id == "canvas_legacy_render_plan":
        from tabs.image_compare.canvas.presentation.plan_applicator import (
            apply_legacy_canvas_render_plan,
        )

        canvas, plan = args
        return apply_legacy_canvas_render_plan(canvas, plan, **kwargs)
    if service_id == "unified_flyout_controller":
        from tabs.image_compare.ui.transient_flyouts import FlyoutController

        return FlyoutController(*args, widget=tab._widget, **kwargs)
    if service_id == "interpolation_flyout_controller":
        from tabs.image_compare.ui.transient_interpolation import (
            InterpolationFlyoutController,
        )

        return InterpolationFlyoutController(*args, widget=tab._widget, **kwargs)
    if service_id == "font_settings_flyout_controller":
        from tabs.image_compare.ui.transient_font_settings import (
            FontSettingsController,
        )

        return FontSettingsController(*args, widget=tab._widget, **kwargs)
    if service_id == "popup_close_extension":
        from tabs.image_compare.ui.popup_closing import ImageComparePopupClosing

        return ImageComparePopupClosing(*args, widget=tab._widget, **kwargs)
    if service_id == "has_initial_canvas_content":
        from tabs.image_compare.ui.startup_readiness import (
            has_initial_canvas_content,
        )

        return has_initial_canvas_content(*args, **kwargs)
    if service_id == "requires_first_frame_startup_gate":
        return True
    if service_id == "refresh_startup_button_visuals":
        if tab._widget is None:
            return False
        from tabs.image_compare.ui.startup_readiness import (
            refresh_startup_button_visuals,
        )

        refresh_startup_button_visuals(tab._widget)
        return True
    if service_id == "clear_transient_text_focus":
        return tab._clear_transient_text_focus(*args, **kwargs)
    if service_id == "sync_interpolation_combo_state":
        return tab._sync_interpolation_combo_state(*args, **kwargs)
    if service_id == "setup_view_mode_buttons":
        return tab._setup_view_mode_buttons(*args, **kwargs)
    if service_id == "is_canvas_content_ready":
        return tab._is_canvas_content_ready()
    return None
