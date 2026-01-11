

from dataclasses import replace
from typing import Any
from PyQt6.QtCore import QPointF, QPoint, QRect
from PyQt6.QtGui import QColor

from .actions import (
    Action,
    ActionType,
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
    ToggleOrientationAction,
    SetMagnifierSizeRelativeAction,
    SetCaptureSizeRelativeAction,
    ToggleMagnifierAction,
    SetMagnifierVisibilityAction,
    ToggleMagnifierOrientationAction,
    ToggleFreezeMagnifierAction,
    SetMagnifierPositionAction,
    SetMagnifierInternalSplitAction,
    SetMovementSpeedAction,
    UpdateMagnifierCombinedStateAction,
    SetIsDraggingSliderAction,
    SetActiveMagnifierIdAction,
    SetDiffModeAction,
    SetChannelViewModeAction,
    SetCachedDiffImageAction,
    SetDividerLineVisibleAction,
    SetDividerLineColorAction,
    SetDividerLineThicknessAction,
    SetMagnifierDividerVisibleAction,
    SetMagnifierDividerColorAction,
    SetMagnifierDividerThicknessAction,
    SetMagnifierBorderColorAction,
    SetMagnifierLaserColorAction,
    SetCaptureRingColorAction,
    SetMagnifierMovementInterpolationMethodAction,
    SetLaserSmoothingInterpolationMethodAction,
    SetIncludeFileNamesInSavedAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetTextAlphaPercentAction,
    SetFileNameColorAction,
    SetFileNameBgColorAction,
    SetDrawTextBackgroundAction,
    SetTextPlacementModeAction,
    SetCurrentIndexAction,
    SetOriginalImageAction,
    SetFullResImageAction,
    SetImagePathAction,
    SetLanguageAction,
    SetUIModeAction,
    SetAutoCropBlackBordersAction,
    InvalidateRenderCacheAction,
    InvalidateGeometryCacheAction,
    ClearAllCachesAction,
    ClearImageSlotDataAction,
)

from core.store import (
    ViewportState,
    ViewState,
    RenderConfig,
    DocumentModel,
    SettingsState,
    SessionData,
)

class ViewportReducer:

    @staticmethod
    def reduce(state: ViewportState, action: Action) -> ViewportState:

        if isinstance(action, SetSplitPositionAction):

            new_pos = max(0.0, min(1.0, action.position))
            new_view_state = replace(state.view_state, split_position=new_pos)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetSplitPositionVisualAction):
            new_pos = max(0.0, min(1.0, action.position))
            new_view_state = replace(state.view_state, split_position_visual=new_pos)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, ToggleOrientationAction):
            new_view_state = replace(state.view_state, is_horizontal=action.is_horizontal)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetMagnifierSizeRelativeAction):
            new_view_state = replace(state.view_state, magnifier_size_relative=action.size)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetCaptureSizeRelativeAction):
            new_view_state = replace(state.view_state, capture_size_relative=action.size)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, ToggleMagnifierAction):
            new_view_state = replace(state.view_state, use_magnifier=action.enabled)

            if action.enabled and not state.view_state.active_magnifier_id:
                new_view_state = replace(new_view_state, active_magnifier_id="default")
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetMagnifierVisibilityAction):
            payload = action.get_payload()
            new_view_state = state.view_state
            kwargs = {}
            if payload.get("left") is not None: kwargs['magnifier_visible_left'] = payload["left"]
            if payload.get("center") is not None: kwargs['magnifier_visible_center'] = payload["center"]
            if payload.get("right") is not None: kwargs['magnifier_visible_right'] = payload["right"]

            if kwargs:
                new_view_state = replace(new_view_state, **kwargs)

            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, ToggleMagnifierOrientationAction):
            new_view_state = replace(state.view_state, magnifier_is_horizontal=action.is_horizontal)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, ToggleFreezeMagnifierAction):
            payload = action.get_payload()
            new_view_state = replace(
                state.view_state,
                freeze_magnifier=payload["freeze"],
                frozen_capture_point_relative=payload.get("frozen_position"),
                magnifier_offset_relative=payload.get("new_offset") or state.view_state.magnifier_offset_relative,
                magnifier_offset_relative_visual=payload.get("new_offset") or state.view_state.magnifier_offset_relative_visual
            )
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetMagnifierPositionAction):
            new_view_state = replace(state.view_state, capture_position_relative=action.position)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetMagnifierInternalSplitAction):
            new_split = max(0.0, min(1.0, action.split))
            new_view_state = replace(state.view_state, magnifier_internal_split=new_split)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetMovementSpeedAction):
            new_view_state = replace(state.view_state, movement_speed_per_sec=action.speed)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, UpdateMagnifierCombinedStateAction):
            new_view_state = replace(state.view_state, is_magnifier_combined=action.is_combined)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetIsDraggingSliderAction):
            new_view_state = replace(state.view_state, is_dragging_any_slider=action.is_dragging)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetActiveMagnifierIdAction):
            new_view_state = replace(state.view_state, active_magnifier_id=action.magnifier_id)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetDiffModeAction):
            new_view_state = replace(state.view_state, diff_mode=action.mode)

            new_session_data = replace(state.session_data, cached_diff_image=None)
            return ViewportState(
                render_config=state.render_config,
                session_data=new_session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetChannelViewModeAction):
            new_view_state = replace(state.view_state, channel_view_mode=action.mode)
            return ViewportState(
                render_config=state.render_config,
                session_data=state.session_data,
                view_state=new_view_state
            )

        elif isinstance(action, SetCachedDiffImageAction):
            new_session_data = replace(state.session_data, cached_diff_image=action.image)
            return ViewportState(
                render_config=state.render_config,
                session_data=new_session_data,
                view_state=state.view_state
            )

        elif isinstance(action, InvalidateRenderCacheAction):

            new_session_data = replace(
                state.session_data,
                caches={},
                magnifier_cache={},
                cached_split_base_image=None,
                last_split_cached_params=None
            )
            new_view_state = replace(
                state.view_state,
                text_bg_visual_height=0.0,
                text_bg_visual_width=0.0
            )
            return ViewportState(
                render_config=state.render_config,
                session_data=new_session_data,
                view_state=new_view_state
            )

        elif isinstance(action, InvalidateGeometryCacheAction):

            new_session_data = replace(
                state.session_data,
                scaled_image1_for_display=None,
                scaled_image2_for_display=None,
                cached_scaled_image_dims=None,
                display_cache_image1=None,
                display_cache_image2=None,
                last_display_cache_params=None
            )
            return ViewportState(
                render_config=state.render_config,
                session_data=new_session_data,
                view_state=state.view_state
            )

        elif isinstance(action, ClearAllCachesAction):

            new_session_data = replace(
                state.session_data,
                unified_image_cache=state.session_data.unified_image_cache.__class__(),
                scaled_image1_for_display=None,
                scaled_image2_for_display=None,
                cached_scaled_image_dims=None,
                display_cache_image1=None,
                display_cache_image2=None,
                last_display_cache_params=None,
                caches={},
                magnifier_cache={},
                cached_split_base_image=None,
                last_split_cached_params=None
            )
            new_view_state = replace(
                state.view_state,
                text_bg_visual_height=0.0,
                text_bg_visual_width=0.0
            )
            return ViewportState(
                render_config=state.render_config,
                session_data=new_session_data,
                view_state=new_view_state
            )

        elif isinstance(action, ClearImageSlotDataAction):

            new_session_data = state.session_data
            if action.slot == 1:
                new_session_data = replace(
                    state.session_data,
                    image1=None,
                    display_cache_image1=None,
                    scaled_image1_for_display=None
                )
            else:
                new_session_data = replace(
                    state.session_data,
                    image2=None,
                    display_cache_image2=None,
                    scaled_image2_for_display=None
                )

            new_session_data = replace(
                new_session_data,
                scaled_image1_for_display=None,
                scaled_image2_for_display=None,
                cached_scaled_image_dims=None,
                last_display_cache_params=None
            )
            return ViewportState(
                render_config=state.render_config,
                session_data=new_session_data,
                view_state=state.view_state
            )

        return state

class RenderConfigReducer:

    @staticmethod
    def reduce(config: RenderConfig, action: Action) -> RenderConfig:

        if isinstance(action, SetDividerLineVisibleAction):
            return replace(config, divider_line_visible=action.visible)

        elif isinstance(action, SetDividerLineColorAction):
            return replace(config, divider_line_color=action.color)

        elif isinstance(action, SetDividerLineThicknessAction):
            return replace(config, divider_line_thickness=action.thickness)

        elif isinstance(action, SetMagnifierDividerVisibleAction):
            return replace(config, magnifier_divider_visible=action.visible)

        elif isinstance(action, SetMagnifierDividerColorAction):
            return replace(config, magnifier_divider_color=action.color)

        elif isinstance(action, SetMagnifierDividerThicknessAction):
            return replace(config, magnifier_divider_thickness=action.thickness)

        elif isinstance(action, SetMagnifierBorderColorAction):
            return replace(config, magnifier_border_color=action.color)

        elif isinstance(action, SetMagnifierLaserColorAction):
            return replace(config, magnifier_laser_color=action.color)

        elif isinstance(action, SetCaptureRingColorAction):
            return replace(config, capture_ring_color=action.color)

        elif isinstance(action, SetIncludeFileNamesInSavedAction):
            return replace(config, include_file_names_in_saved=action.enabled)

        elif isinstance(action, SetFontSizePercentAction):
            return replace(config, font_size_percent=action.size)

        elif isinstance(action, SetFontWeightAction):
            return replace(config, font_weight=action.weight)

        elif isinstance(action, SetTextAlphaPercentAction):
            return replace(config, text_alpha_percent=action.alpha)

        elif isinstance(action, SetFileNameColorAction):
            return replace(config, file_name_color=action.color)

        elif isinstance(action, SetFileNameBgColorAction):
            return replace(config, file_name_bg_color=action.color)

        elif isinstance(action, SetDrawTextBackgroundAction):
            return replace(config, draw_text_background=action.enabled)

        elif isinstance(action, SetTextPlacementModeAction):
            return replace(config, text_placement_mode=action.mode)

        elif isinstance(action, SetMagnifierMovementInterpolationMethodAction):
            return replace(config, magnifier_movement_interpolation_method=action.method)

        elif isinstance(action, SetLaserSmoothingInterpolationMethodAction):
            return replace(config, laser_smoothing_interpolation_method=action.method)

        return config

class DocumentReducer:

    @staticmethod
    def reduce(document: DocumentModel, action: Action) -> DocumentModel:

        if isinstance(action, SetCurrentIndexAction):
            if action.slot == 1:
                return replace(document, current_index1=action.index)
            else:
                return replace(document, current_index2=action.index)

        elif isinstance(action, SetOriginalImageAction):
            if action.slot == 1:
                return replace(document, original_image1=action.image)
            else:
                return replace(document, original_image2=action.image)

        elif isinstance(action, SetFullResImageAction):
            if action.slot == 1:
                return replace(document, full_res_image1=action.image)
            else:
                return replace(document, full_res_image2=action.image)

        elif isinstance(action, SetImagePathAction):
            if action.slot == 1:
                return replace(document, image1_path=action.path)
            else:
                return replace(document, image2_path=action.path)

        return document

class SettingsReducer:

    @staticmethod
    def reduce(settings: SettingsState, action: Action) -> SettingsState:

        if isinstance(action, SetLanguageAction):
            return replace(settings, current_language=action.language)

        elif isinstance(action, SetUIModeAction):
            return replace(settings, ui_mode=action.mode)

        elif isinstance(action, SetAutoCropBlackBordersAction):
            return replace(settings, auto_crop_black_borders=action.enabled)

        return settings

class RootReducer:

    def __init__(self):
        self.viewport_reducer = ViewportReducer()
        self.render_config_reducer = RenderConfigReducer()
        self.document_reducer = DocumentReducer()
        self.settings_reducer = SettingsReducer()

    def reduce(self, store: 'Store', action: Action) -> 'Store':
        from core.store import Store

        new_viewport = self.viewport_reducer.reduce(store.viewport, action)

        new_render_config = self.render_config_reducer.reduce(new_viewport.render_config, action)
        if new_render_config is not new_viewport.render_config:

            new_viewport = ViewportState(
                render_config=new_render_config,
                session_data=new_viewport.session_data,
                view_state=new_viewport.view_state
            )

        new_document = self.document_reducer.reduce(store.document, action)

        new_settings = self.settings_reducer.reduce(store.settings, action)

        viewport_changed = new_viewport is not store.viewport
        document_changed = new_document is not store.document
        settings_changed = new_settings is not store.settings

        if viewport_changed or document_changed or settings_changed:
            new_store = Store()
            new_store.viewport = new_viewport
            new_store.document = new_document
            new_store.settings = new_settings
            new_store.recorder = store.recorder
            new_store._dispatcher = store._dispatcher
            return new_store

        return store

