from dataclasses import replace

from core.store import (
    DocumentModel,
    GeometryState,
    ImageSessionState,
    InteractionState,
    RenderCacheState,
    RenderConfig,
    SessionData,
    SettingsState,
    ViewState,
    ViewportState,
)

from .actions import (
    Action,
    ClearAllCachesAction,
    ClearImageSlotDataAction,
    InvalidateGeometryCacheAction,
    InvalidateRenderCacheAction,
    SetActiveMagnifierIdAction,
    SetAutoCalculatePsnrAction,
    SetAutoCalculateSsimAction,
    SetAutoCropBlackBordersAction,
    SetCachedDiffImageAction,
    SetCachedScaledImageDimsAction,
    SetCaptureRingColorAction,
    SetCaptureSizeRelativeAction,
    SetChannelViewModeAction,
    SetCurrentIndexAction,
    SetDiffModeAction,
    SetDisplayCacheImageAction,
    SetDisplayResolutionLimitAction,
    SetDividerLineColorAction,
    SetDividerLineThicknessAction,
    SetDividerLineVisibleAction,
    SetDraggingCapturePointAction,
    SetDraggingSplitInMagnifierAction,
    SetDraggingSplitLineAction,
    SetDrawTextBackgroundAction,
    SetFileNameBgColorAction,
    SetFileNameColorAction,
    SetFixedLabelDimensionsAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetFullResImageAction,
    SetHighlightedMagnifierElementAction,
    SetImageDisplayRectAction,
    SetImagePathAction,
    SetImageSessionImageAction,
    SetIncludeFileNamesInSavedAction,
    SetInteractionSessionIdAction,
    SetInteractiveModeAction,
    SetInterpolationMethodAction,
    SetIsDraggingSliderAction,
    SetLanguageAction,
    SetLastDisplayCacheParamsAction,
    SetLastHorizontalMovementKeyAction,
    SetLastSpacingMovementKeyAction,
    SetLastVerticalMovementKeyAction,
    SetLaserSmoothingInterpolationMethodAction,
    SetMagnifierBorderColorAction,
    SetMagnifierDividerColorAction,
    SetMagnifierDividerThicknessAction,
    SetMagnifierDividerVisibleAction,
    SetMagnifierGuidesThicknessAction,
    SetMagnifierInternalSplitAction,
    SetMagnifierLaserColorAction,
    SetMagnifierMovementInterpolationMethodAction,
    SetMagnifierOffsetRelativeAction,
    SetMagnifierOffsetRelativeVisualAction,
    SetMagnifierPositionAction,
    SetMagnifierScreenCenterAction,
    SetMagnifierScreenSizeAction,
    SetMagnifierSizeRelativeAction,
    SetMagnifierSpacingRelativeAction,
    SetMagnifierSpacingRelativeVisualAction,
    SetMagnifierVisibilityAction,
    SetMaxNameLengthAction,
    SetMovementInterpolationMethodAction,
    SetMovementSpeedAction,
    SetOptimizeLaserSmoothingAction,
    SetOptimizeMagnifierMovementAction,
    SetOriginalImageAction,
    SetPendingUnificationPathsAction,
    SetPixmapDimensionsAction,
    SetPressedKeysAction,
    SetPsnrValueAction,
    SetResizeInProgressAction,
    SetScaledImageForDisplayAction,
    SetShowingSingleImageModeAction,
    SetShowCaptureAreaOnMainImageAction,
    SetShowMagnifierGuidesAction,
    SetSpaceBarPressedAction,
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
    SetSsimValueAction,
    SetTextAlphaPercentAction,
    SetTextPlacementModeAction,
    SetUIModeAction,
    SetUnificationInProgressAction,
    SetUserInteractingAction,
    SetZoomInterpolationMethodAction,
    ToggleFreezeMagnifierAction,
    ToggleMagnifierAction,
    ToggleMagnifierOrientationAction,
    ToggleOrientationAction,
    UpdateMagnifierCombinedStateAction,
)

def _build_viewport_state(
    state: ViewportState,
    *,
    render_config: RenderConfig | None = None,
    session_data: SessionData | None = None,
    view_state: ViewState | None = None,
    interaction_state: InteractionState | None = None,
    geometry_state: GeometryState | None = None,
) -> ViewportState:
    return ViewportState(
        render_config=render_config or state.render_config,
        session_data=session_data or state.session_data,
        view_state=view_state or state.view_state,
        interaction_state=interaction_state or state.interaction_state,
        geometry_state=geometry_state or state.geometry_state,
    )

class ViewStateReducer:
    @staticmethod
    def reduce(view_state: ViewState, action: Action) -> ViewState:
        if isinstance(action, SetSplitPositionAction):
            return replace(
                view_state, split_position=max(0.0, min(1.0, action.position))
            )
        if isinstance(action, SetSplitPositionVisualAction):
            return replace(
                view_state, split_position_visual=max(0.0, min(1.0, action.position))
            )
        if isinstance(action, ToggleOrientationAction):
            return replace(view_state, is_horizontal=action.is_horizontal)
        if isinstance(action, SetMagnifierSizeRelativeAction):
            return replace(view_state, magnifier_size_relative=action.size)
        if isinstance(action, SetCaptureSizeRelativeAction):
            return replace(view_state, capture_size_relative=action.size)
        if isinstance(action, ToggleMagnifierAction):
            kwargs = {"use_magnifier": action.enabled}
            if action.enabled and not view_state.active_magnifier_id:
                kwargs["active_magnifier_id"] = "default"
            return replace(view_state, **kwargs)
        if isinstance(action, SetMagnifierVisibilityAction):
            payload = action.get_payload()
            kwargs = {}
            if payload.get("left") is not None:
                kwargs["magnifier_visible_left"] = payload["left"]
            if payload.get("center") is not None:
                kwargs["magnifier_visible_center"] = payload["center"]
            if payload.get("right") is not None:
                kwargs["magnifier_visible_right"] = payload["right"]
            return view_state if not kwargs else replace(view_state, **kwargs)
        if isinstance(action, ToggleMagnifierOrientationAction):
            return replace(view_state, magnifier_is_horizontal=action.is_horizontal)
        if isinstance(action, ToggleFreezeMagnifierAction):
            payload = action.get_payload()
            return replace(
                view_state,
                freeze_magnifier=payload["freeze"],
                frozen_capture_point_relative=payload.get("frozen_position"),
                magnifier_offset_relative=payload.get("new_offset")
                or view_state.magnifier_offset_relative,
                magnifier_offset_relative_visual=payload.get("new_offset")
                or view_state.magnifier_offset_relative_visual,
            )
        if isinstance(action, SetMagnifierPositionAction):
            return replace(view_state, capture_position_relative=action.position)
        if isinstance(action, SetMagnifierInternalSplitAction):
            return replace(
                view_state, magnifier_internal_split=max(0.0, min(1.0, action.split))
            )
        if isinstance(action, SetMovementSpeedAction):
            return replace(view_state, movement_speed_per_sec=action.speed)
        if isinstance(action, UpdateMagnifierCombinedStateAction):
            return replace(view_state, is_magnifier_combined=action.is_combined)
        if isinstance(action, SetActiveMagnifierIdAction):
            return replace(view_state, active_magnifier_id=action.magnifier_id)
        if isinstance(action, SetDiffModeAction):
            return replace(view_state, diff_mode=action.mode)
        if isinstance(action, SetChannelViewModeAction):
            return replace(view_state, channel_view_mode=action.mode)
        if isinstance(action, SetShowingSingleImageModeAction):
            return replace(view_state, showing_single_image_mode=action.mode)
        if isinstance(action, SetMagnifierOffsetRelativeAction):
            return replace(view_state, magnifier_offset_relative=action.offset)
        if isinstance(action, SetMagnifierSpacingRelativeAction):
            return replace(view_state, magnifier_spacing_relative=action.spacing)
        if isinstance(action, SetMagnifierOffsetRelativeVisualAction):
            return replace(view_state, magnifier_offset_relative_visual=action.offset)
        if isinstance(action, SetMagnifierSpacingRelativeVisualAction):
            return replace(
                view_state, magnifier_spacing_relative_visual=action.spacing
            )
        if isinstance(action, SetOptimizeMagnifierMovementAction):
            return replace(view_state, optimize_magnifier_movement=action.enabled)
        if isinstance(action, SetHighlightedMagnifierElementAction):
            return replace(view_state, highlighted_magnifier_element=action.element)
        if isinstance(action, InvalidateRenderCacheAction):
            return replace(view_state, text_bg_visual_height=0.0, text_bg_visual_width=0.0)
        if isinstance(action, ClearAllCachesAction):
            return replace(view_state, text_bg_visual_height=0.0, text_bg_visual_width=0.0)
        return view_state

class InteractionStateReducer:
    @staticmethod
    def reduce(interaction_state: InteractionState, action: Action) -> InteractionState:
        if isinstance(action, SetIsDraggingSliderAction):
            return replace(
                interaction_state, is_dragging_any_slider=action.is_dragging
            )
        if isinstance(action, SetResizeInProgressAction):
            return replace(interaction_state, resize_in_progress=action.enabled)
        if isinstance(action, SetInteractiveModeAction):
            return replace(interaction_state, is_interactive_mode=action.enabled)
        if isinstance(action, SetDraggingSplitLineAction):
            return replace(interaction_state, is_dragging_split_line=action.enabled)
        if isinstance(action, SetDraggingCapturePointAction):
            return replace(interaction_state, is_dragging_capture_point=action.enabled)
        if isinstance(action, SetDraggingSplitInMagnifierAction):
            return replace(
                interaction_state, is_dragging_split_in_magnifier=action.enabled
            )
        if isinstance(action, SetPressedKeysAction):
            return replace(interaction_state, pressed_keys=set(action.keys))
        if isinstance(action, SetSpaceBarPressedAction):
            return replace(interaction_state, space_bar_pressed=action.enabled)
        if isinstance(action, SetInteractionSessionIdAction):
            return replace(interaction_state, interaction_session_id=action.session_id)
        if isinstance(action, SetUserInteractingAction):
            return replace(interaction_state, is_user_interacting=action.enabled)
        if isinstance(action, SetLastHorizontalMovementKeyAction):
            return replace(interaction_state, last_horizontal_movement_key=action.key)
        if isinstance(action, SetLastVerticalMovementKeyAction):
            return replace(interaction_state, last_vertical_movement_key=action.key)
        if isinstance(action, SetLastSpacingMovementKeyAction):
            return replace(interaction_state, last_spacing_movement_key=action.key)
        return interaction_state

class GeometryStateReducer:
    @staticmethod
    def reduce(geometry_state: GeometryState, action: Action) -> GeometryState:
        if isinstance(action, SetPixmapDimensionsAction):
            return replace(
                geometry_state, pixmap_width=action.width, pixmap_height=action.height
            )
        if isinstance(action, SetImageDisplayRectAction):
            return replace(geometry_state, image_display_rect_on_label=action.rect)
        if isinstance(action, SetFixedLabelDimensionsAction):
            return replace(
                geometry_state,
                fixed_label_width=action.width,
                fixed_label_height=action.height,
            )
        if isinstance(action, SetMagnifierScreenCenterAction):
            return replace(geometry_state, magnifier_screen_center=action.center)
        if isinstance(action, SetMagnifierScreenSizeAction):
            return replace(geometry_state, magnifier_screen_size=action.size)
        return geometry_state

class ImageSessionReducer:
    @staticmethod
    def reduce(image_state: ImageSessionState, action: Action) -> ImageSessionState:
        if isinstance(action, SetImageSessionImageAction):
            field_name = "image1" if action.slot == 1 else "image2"
            return replace(image_state, **{field_name: action.image})
        if isinstance(action, SetAutoCalculatePsnrAction):
            return replace(image_state, auto_calculate_psnr=action.enabled)
        if isinstance(action, SetAutoCalculateSsimAction):
            return replace(image_state, auto_calculate_ssim=action.enabled)
        if isinstance(action, SetPsnrValueAction):
            return replace(image_state, psnr_value=action.value)
        if isinstance(action, SetSsimValueAction):
            return replace(image_state, ssim_value=action.value)
        if isinstance(action, ClearImageSlotDataAction):
            field_name = "image1" if action.slot == 1 else "image2"
            return replace(image_state, **{field_name: None})
        return image_state

class RenderCacheReducer:
    @staticmethod
    def reduce(cache_state: RenderCacheState, action: Action) -> RenderCacheState:
        if isinstance(action, SetDisplayCacheImageAction):
            field_name = "display_cache_image1" if action.slot == 1 else "display_cache_image2"
            return replace(cache_state, **{field_name: action.image})
        if isinstance(action, SetScaledImageForDisplayAction):
            field_name = (
                "scaled_image1_for_display"
                if action.slot == 1
                else "scaled_image2_for_display"
            )
            return replace(cache_state, **{field_name: action.image})
        if isinstance(action, SetCachedScaledImageDimsAction):
            return replace(cache_state, cached_scaled_image_dims=action.dims)
        if isinstance(action, SetLastDisplayCacheParamsAction):
            return replace(cache_state, last_display_cache_params=action.params)
        if isinstance(action, SetCachedDiffImageAction):
            return replace(cache_state, cached_diff_image=action.image)
        if isinstance(action, SetUnificationInProgressAction):
            return replace(cache_state, unification_in_progress=action.enabled)
        if isinstance(action, SetPendingUnificationPathsAction):
            return replace(cache_state, pending_unification_paths=action.paths)
        if isinstance(action, InvalidateRenderCacheAction):
            return replace(
                cache_state,
                caches={},
                magnifier_cache={},
                cached_split_base_image=None,
                last_split_cached_params=None,
            )
        if isinstance(action, InvalidateGeometryCacheAction):
            return replace(
                cache_state,
                scaled_image1_for_display=None,
                scaled_image2_for_display=None,
                cached_scaled_image_dims=None,
                display_cache_image1=None,
                display_cache_image2=None,
                last_display_cache_params=None,
            )
        if isinstance(action, ClearAllCachesAction):
            return replace(
                cache_state,
                unified_image_cache=cache_state.unified_image_cache.__class__(),
                scaled_image1_for_display=None,
                scaled_image2_for_display=None,
                cached_scaled_image_dims=None,
                display_cache_image1=None,
                display_cache_image2=None,
                last_display_cache_params=None,
                caches={},
                magnifier_cache={},
                cached_split_base_image=None,
                last_split_cached_params=None,
            )
        if isinstance(action, ClearImageSlotDataAction):
            kwargs = (
                {
                    "display_cache_image1": None,
                    "scaled_image1_for_display": None,
                }
                if action.slot == 1
                else {
                    "display_cache_image2": None,
                    "scaled_image2_for_display": None,
                }
            )
            kwargs.update(
                {
                    "scaled_image1_for_display": None,
                    "scaled_image2_for_display": None,
                    "cached_scaled_image_dims": None,
                    "last_display_cache_params": None,
                }
            )
            return replace(cache_state, **kwargs)
        return cache_state

class SessionDataReducer:
    def __init__(self):
        self.image_session_reducer = ImageSessionReducer()
        self.render_cache_reducer = RenderCacheReducer()

    def reduce(self, session_data: SessionData, action: Action) -> SessionData:
        new_image_state = self.image_session_reducer.reduce(
            session_data.image_state, action
        )
        new_render_cache = self.render_cache_reducer.reduce(
            session_data.render_cache, action
        )
        if (
            new_image_state is session_data.image_state
            and new_render_cache is session_data.render_cache
        ):
            return session_data
        return SessionData(image_state=new_image_state, render_cache=new_render_cache)

class RenderConfigReducer:
    @staticmethod
    def reduce(config: RenderConfig, action: Action) -> RenderConfig:
        if isinstance(action, SetDividerLineVisibleAction):
            return replace(config, divider_line_visible=action.visible)
        if isinstance(action, SetDividerLineColorAction):
            return replace(config, divider_line_color=action.color)
        if isinstance(action, SetDividerLineThicknessAction):
            return replace(config, divider_line_thickness=action.thickness)
        if isinstance(action, SetMagnifierDividerVisibleAction):
            return replace(config, magnifier_divider_visible=action.visible)
        if isinstance(action, SetMagnifierDividerColorAction):
            return replace(config, magnifier_divider_color=action.color)
        if isinstance(action, SetMagnifierDividerThicknessAction):
            return replace(config, magnifier_divider_thickness=action.thickness)
        if isinstance(action, SetMagnifierBorderColorAction):
            return replace(config, magnifier_border_color=action.color)
        if isinstance(action, SetMagnifierLaserColorAction):
            return replace(config, magnifier_laser_color=action.color)
        if isinstance(action, SetCaptureRingColorAction):
            return replace(config, capture_ring_color=action.color)
        if isinstance(action, SetInterpolationMethodAction):
            return replace(config, interpolation_method=action.method)
        if isinstance(action, SetMovementInterpolationMethodAction):
            return replace(config, movement_interpolation_method=action.method)
        if isinstance(action, SetMagnifierMovementInterpolationMethodAction):
            return replace(
                config,
                magnifier_movement_interpolation_method=action.method,
                movement_interpolation_method=action.method,
            )
        if isinstance(action, SetLaserSmoothingInterpolationMethodAction):
            return replace(config, laser_smoothing_interpolation_method=action.method)
        if isinstance(action, SetOptimizeLaserSmoothingAction):
            return replace(config, optimize_laser_smoothing=action.enabled)
        if isinstance(action, SetZoomInterpolationMethodAction):
            return replace(config, zoom_interpolation_method=action.method)
        if isinstance(action, SetIncludeFileNamesInSavedAction):
            return replace(config, include_file_names_in_saved=action.enabled)
        if isinstance(action, SetFontSizePercentAction):
            return replace(config, font_size_percent=action.size)
        if isinstance(action, SetFontWeightAction):
            return replace(config, font_weight=action.weight)
        if isinstance(action, SetTextAlphaPercentAction):
            return replace(config, text_alpha_percent=action.alpha)
        if isinstance(action, SetFileNameColorAction):
            return replace(config, file_name_color=action.color)
        if isinstance(action, SetFileNameBgColorAction):
            return replace(config, file_name_bg_color=action.color)
        if isinstance(action, SetDrawTextBackgroundAction):
            return replace(config, draw_text_background=action.enabled)
        if isinstance(action, SetTextPlacementModeAction):
            return replace(config, text_placement_mode=action.mode)
        if isinstance(action, SetShowMagnifierGuidesAction):
            return replace(config, show_magnifier_guides=action.enabled)
        if isinstance(action, SetMagnifierGuidesThicknessAction):
            return replace(config, magnifier_guides_thickness=action.thickness)
        if isinstance(action, SetMaxNameLengthAction):
            return replace(config, max_name_length=action.length)
        if isinstance(action, SetShowCaptureAreaOnMainImageAction):
            return replace(config, show_capture_area_on_main_image=action.enabled)
        if isinstance(action, SetDisplayResolutionLimitAction):
            return replace(config, display_resolution_limit=action.limit)
        return config

class ViewportReducer:
    def __init__(self):
        self.view_state_reducer = ViewStateReducer()
        self.interaction_state_reducer = InteractionStateReducer()
        self.geometry_state_reducer = GeometryStateReducer()
        self.session_data_reducer = SessionDataReducer()

    def reduce(self, state: ViewportState, action: Action) -> ViewportState:
        new_view_state = self.view_state_reducer.reduce(state.view_state, action)
        new_interaction_state = self.interaction_state_reducer.reduce(
            state.interaction_state, action
        )
        new_geometry_state = self.geometry_state_reducer.reduce(
            state.geometry_state, action
        )
        new_session_data = self.session_data_reducer.reduce(state.session_data, action)

        if (
            new_view_state is state.view_state
            and new_interaction_state is state.interaction_state
            and new_geometry_state is state.geometry_state
            and new_session_data is state.session_data
        ):
            return state

        return _build_viewport_state(
            state,
            session_data=new_session_data,
            view_state=new_view_state,
            interaction_state=new_interaction_state,
            geometry_state=new_geometry_state,
        )

class DocumentReducer:
    @staticmethod
    def reduce(document: DocumentModel, action: Action) -> DocumentModel:
        if isinstance(action, SetCurrentIndexAction):
            if action.slot == 1:
                return replace(document, current_index1=action.index)
            return replace(document, current_index2=action.index)
        if isinstance(action, SetOriginalImageAction):
            if action.slot == 1:
                return replace(document, original_image1=action.image)
            return replace(document, original_image2=action.image)
        if isinstance(action, SetFullResImageAction):
            if action.slot == 1:
                return replace(document, full_res_image1=action.image)
            return replace(document, full_res_image2=action.image)
        if isinstance(action, SetImagePathAction):
            if action.slot == 1:
                return replace(document, image1_path=action.path)
            return replace(document, image2_path=action.path)
        if isinstance(action, ClearImageSlotDataAction):
            if action.slot == 1:
                return replace(
                    document,
                    original_image1=None,
                    full_res_image1=None,
                    preview_image1=None,
                    image1_path=None,
                )
            return replace(
                document,
                original_image2=None,
                full_res_image2=None,
                preview_image2=None,
                image2_path=None,
            )
        return document

class SettingsReducer:
    @staticmethod
    def reduce(settings: SettingsState, action: Action) -> SettingsState:
        if isinstance(action, SetLanguageAction):
            return replace(settings, current_language=action.language)
        if isinstance(action, SetUIModeAction):
            return replace(settings, ui_mode=action.mode)
        if isinstance(action, SetAutoCropBlackBordersAction):
            return replace(settings, auto_crop_black_borders=action.enabled)
        return settings

class RootReducer:
    def __init__(self):
        self.viewport_reducer = ViewportReducer()
        self.render_config_reducer = RenderConfigReducer()
        self.document_reducer = DocumentReducer()
        self.settings_reducer = SettingsReducer()

    def reduce(self, store: "Store", action: Action) -> "Store":
        from core.store import Store

        new_viewport = self.viewport_reducer.reduce(store.viewport, action)
        new_render_config = self.render_config_reducer.reduce(
            new_viewport.render_config, action
        )
        if new_render_config is not new_viewport.render_config:
            new_viewport = _build_viewport_state(
                new_viewport, render_config=new_render_config
            )

        new_document = self.document_reducer.reduce(store.document, action)
        new_settings = self.settings_reducer.reduce(store.settings, action)

        if (
            new_viewport is store.viewport
            and new_document is store.document
            and new_settings is store.settings
        ):
            return store

        new_store = Store()
        new_store.viewport = new_viewport
        new_store.document = new_document
        new_store.settings = new_settings
        new_store.recorder = store.recorder
        new_store._dispatcher = store._dispatcher
        return new_store
