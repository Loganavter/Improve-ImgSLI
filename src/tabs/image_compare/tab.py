"""Image-compare tab contract implementation.

Stages 1-10 of MIGRATION_PLAN.md.

The tab owns the page widget (``ImageCompareWidget``) and exposes the
tab-contract lifecycle. The host (``ui.main_window``) still creates
the primitive widgets (buttons, sliders, canvas) and calls
``widget.assemble(ui)`` once those primitives exist; long-term the
intent is to move primitive ownership into this tab as well.
"""

from __future__ import annotations

from pathlib import Path
import logging

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract, TabTransitionHint

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".jxl"}
_STATE_SLOT = "image_compare.state"
logger = logging.getLogger("ImproveImgSLI")


class ImageCompareTab(TabContract):
    def __init__(self):
        self._widget: "ImageCompareWidget | None" = None
        self._active_session_id: str | None = None

    @property
    def session_type(self) -> str:
        return "image_compare"

    @property
    def display_name(self) -> str:
        return "Image Compare"

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "image_compare"

    def localized_display_name(self, language: str) -> str:
        from sli_ui_toolkit.i18n import tr

        key = "image_compare.session_type"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        from tabs.image_compare.widget import ImageCompareWidget

        self._widget = ImageCompareWidget(parent, context=context)
        return self._widget

    @property
    def widget(self) -> "ImageCompareWidget | None":
        return self._widget

    def assemble_host_page(self, ui) -> bool:
        if self._widget is None:
            return False
        widgets = getattr(ui, "legacy_tab_widgets", None)
        if widgets is None:
            widgets = {}
            ui.legacy_tab_widgets = widgets
        widgets[self.session_type] = self._widget
        from tabs.image_compare.ui.primitives import ImageComparePrimitivesFactory

        parent = getattr(ui, "main_window", None) or self._widget
        ImageComparePrimitivesFactory(ui).build(parent)
        self._widget.assemble(ui)
        return True

    def apply_host_session_mode(self, ui, session_title: str | None = None) -> bool:
        edit_layout = getattr(ui, "edit_layout_widget", None)
        file_names = getattr(ui, "btn_file_names", None)
        if edit_layout is None or file_names is None:
            return False
        edit_layout.setVisible(bool(file_names.isChecked()))
        return True

    def transition_hint(self) -> TabTransitionHint:
        # QRhi warm-up can be long; widen the mask window vs the default 300 ms.
        return TabTransitionHint(
            cover_on_enter=True, min_duration_ms=50, max_duration_ms=400
        )

    def on_activated(self, context: TabContext) -> None:
        new_id = self._resolve_active_session_id(context)
        if new_id != self._active_session_id:
            self._snapshot_into(context, self._active_session_id)
            self._active_session_id = new_id
            self._restore_from(context, new_id)
        if self._widget is not None:
            self._widget.setFocus()
        # The transition mask is released by ImageCompareWidget when the
        # canvas emits ``firstVisualFrameReady`` — no host-side release here.

    def on_deactivated(self, context: TabContext) -> None:
        self._snapshot_into(context, self._active_session_id)

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        # Slot is auto-allocated by SessionBlueprint.state_slots; nothing to do.
        return

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None

    def _resolve_active_session_id(self, context: TabContext) -> str | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        if session is None or getattr(session, "session_type", None) != self.session_type:
            return None
        return getattr(session, "id", None)

    def _snapshot_into(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None:
            return
        store = getattr(context, "store", None)
        if store is None or not hasattr(store, "set_session_state_slot"):
            return
        ui = getattr(self._widget._context, "main_window", None) if self._widget._context else None
        ui = getattr(ui, "ui", None) if ui is not None else None
        if ui is None:
            return
        from tabs.image_compare.models import ImageCompareState

        state = ImageCompareState(
            show_file_names=bool(getattr(getattr(ui, "btn_file_names", None), "isChecked", lambda: False)()),
            edit_name_1=getattr(getattr(ui, "edit_name1", None), "text", lambda: "")(),
            edit_name_2=getattr(getattr(ui, "edit_name2", None), "text", lambda: "")(),
        )
        try:
            store.set_session_state_slot(
                _STATE_SLOT, state, session_id=session_id, emit_scope=None,
            )
        except Exception:
            pass

    def _restore_from(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None:
            return
        store = getattr(context, "store", None)
        if store is None or not hasattr(store, "ensure_session_state_slot"):
            return
        from tabs.image_compare.models import ImageCompareState

        try:
            state = store.ensure_session_state_slot(
                _STATE_SLOT, session_id=session_id, factory=ImageCompareState,
            )
        except Exception:
            return
        if state is None:
            return
        ui = getattr(self._widget._context, "main_window", None) if self._widget._context else None
        ui = getattr(ui, "ui", None) if ui is not None else None
        if ui is None:
            return
        btn = getattr(ui, "btn_file_names", None)
        if btn is not None and hasattr(btn, "setChecked"):
            btn.setChecked(bool(state.show_file_names))
        for attr, value in (("edit_name1", state.edit_name_1), ("edit_name2", state.edit_name_2)):
            edit = getattr(ui, attr, None)
            if edit is not None and hasattr(edit, "setText"):
                edit.setText(value or "")

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> bool:
        from PySide6.QtCore import QTimer

        widget = self._widget
        if widget is None:
            logger.warning("ImageCompareTab.handle_drop: widget is not initialized")
            return False
        main_window = getattr(widget._context, "main_window", None) if widget._context else None
        if main_window is None:
            logger.warning("ImageCompareTab.handle_drop: main_window is unavailable")
            return False
        controller = getattr(main_window, "main_controller", None)
        if controller is None:
            presenter = getattr(main_window, "presenter", None)
            controller = getattr(presenter, "main_controller", None)
        sessions = getattr(controller, "sessions", None) if controller else None
        if sessions is None:
            logger.warning(
                "ImageCompareTab.handle_drop: sessions controller unavailable "
                "(main_controller=%r presenter=%r)",
                getattr(main_window, "main_controller", None),
                getattr(main_window, "presenter", None),
            )
            return False
        image_paths = [str(p) for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if not image_paths:
            logger.debug(
                "ImageCompareTab.handle_drop: no supported image paths in %s",
                paths,
            )
            return False
        slot = 1
        if hint is not None:
            if "slot" in hint:
                slot = 1 if int(hint.get("slot") or 1) == 1 else 2
            elif "is_left_area" in hint:
                slot = 1 if bool(hint.get("is_left_area")) else 2
        logger.debug(
            "ImageCompareTab.handle_drop: scheduling load paths=%s slot=%s hint=%s",
            image_paths,
            slot,
            hint,
        )
        QTimer.singleShot(
            0, lambda: sessions.load_images_from_paths(image_paths, slot)
        )
        return True

    def contribute_settings(self, registry) -> None:
        from plugins.settings.pages.analysis import build as build_analysis
        from plugins.settings.registry import SettingsSection
        from tabs.image_compare.ui.settings_performance import build_image_perf_extras
        from ui.icon_manager import AppIcon

        registry.add(
            SettingsSection(
                section_id="image_compare.analysis",
                title_key="label.details",
                icon=AppIcon.HIGHLIGHT_DIFFERENCES,
                build=build_analysis,
                owner_tab=self.session_type,
                order=40,
            )
        )
        registry.add_section_extra(
            "builtin.performance",
            build_image_perf_extras,
            owner_tab=self.session_type,
            order=10,
        )

    def create_main_window_feature(self, feature_id: str, **kwargs):
        if feature_id != "image_canvas":
            return None
        from tabs.image_compare.presenters.image_canvas.presenter import (
            ImageCanvasPresenter,
        )

        return ImageCanvasPresenter(
            kwargs["store"],
            kwargs["main_controller"],
            kwargs["ui"],
            kwargs["main_window_app"],
        )

    def create_service(self, service_id: str, *args, **kwargs):
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

            return ClipboardService(*args, **kwargs)
        if service_id == "layout_manager":
            from tabs.image_compare.ui.layout_manager import ImageCompareLayoutManager

            return ImageCompareLayoutManager(*args, **kwargs)
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

            return MagnifierVisibilityController(*args, **kwargs)
        if service_id == "magnifier_instances_popup_controller":
            from tabs.image_compare.ui.transient_magnifier_instances import (
                MagnifierInstancesPopupController,
            )

            return MagnifierInstancesPopupController(*args, **kwargs)
        if service_id == "toolbar_presenter":
            from tabs.image_compare.presenters.toolbar_presenter import (
                ToolbarPresenter,
            )

            return ToolbarPresenter(*args, **kwargs)
        if service_id == "install_translations":
            from tabs.image_compare.ui.translations import (
                install_image_compare_translations,
            )

            install_image_compare_translations(*args, **kwargs)
            return True
        if service_id == "canvas_widget_class":
            from tabs.image_compare.canvas.widget import get_canvas_widget_class

            return get_canvas_widget_class()
        if service_id == "canvas_gl_render_scene":
            from tabs.image_compare.canvas.scene import build_gl_render_scene

            return build_gl_render_scene(*args, **kwargs)
        if service_id == "canvas_reset_overlays":
            from tabs.image_compare.canvas.helpers import reset_canvas_overlays

            canvas = args[0]
            reset_canvas_overlays(canvas)
            return True
        if service_id == "canvas_feature_command":
            from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command

            feature_name, command_id, *command_args = args
            command = get_canvas_feature_command(feature_name, command_id)
            if command is None:
                return None
            return command(*command_args, **kwargs)
        if service_id == "canvas_feature_command_alias":
            from ui.canvas_infra.scene.widget_registry import (
                get_canvas_feature_command_by_alias,
            )

            alias, *command_args = args
            command = get_canvas_feature_command_by_alias(alias)
            if command is None:
                return None
            return command(*command_args, **kwargs)
        if service_id == "canvas_plan_split_sync":
            from ui.canvas_infra.scene.widget_registry import (
                get_canvas_feature_command_by_alias,
            )

            command = get_canvas_feature_command_by_alias("splitter.sync_split_position")
            if command is None:
                return None
            return command(*args, **kwargs)
        if service_id == "canvas_live_runtime_overlays":
            from ui.canvas_infra.scene.widget_registry import (
                apply_canvas_feature_live_runtime_overlays,
            )

            store, canvas = args
            return apply_canvas_feature_live_runtime_overlays(store, canvas)
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

            return FlyoutController(*args, **kwargs)
        if service_id == "popup_close_extension":
            from tabs.image_compare.ui.popup_closing import ImageComparePopupClosing

            return ImageComparePopupClosing(*args, **kwargs)
        if service_id == "has_initial_canvas_content":
            from tabs.image_compare.ui.startup_readiness import (
                has_initial_canvas_content,
            )

            return has_initial_canvas_content(*args, **kwargs)
        if service_id == "refresh_startup_button_visuals":
            from tabs.image_compare.ui.startup_readiness import (
                refresh_startup_button_visuals,
            )

            refresh_startup_button_visuals(*args, **kwargs)
            return True
        return None

    def register_canvas_features(self) -> None:
        import tabs.image_compare.canvas.features as features_pkg
        from ui.canvas_infra.scene.feature_registry import (
            register_canvas_scene_feature_package,
        )
        from ui.canvas_infra.scene.gl_pass_registry import (
            register_canvas_gl_pass_feature_package,
        )
        from ui.canvas_infra.scene.pass_registry import (
            register_canvas_render_pass_feature_package,
        )
        from ui.canvas_infra.scene.widget_registry import (
            register_canvas_widget_feature_package,
        )

        register_canvas_scene_feature_package(features_pkg)
        register_canvas_widget_feature_package(features_pkg)
        register_canvas_gl_pass_feature_package(features_pkg)
        register_canvas_render_pass_feature_package(features_pkg)

    def apply_appearance(self, host_window) -> None:
        from tabs.image_compare.ui.appearance import apply_image_canvas_appearance

        apply_image_canvas_appearance(host_window)

    def dispose(self) -> None:
        self._widget = None
