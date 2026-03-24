from dataclasses import replace

from core.store import (
    DocumentModel,
    RenderConfig,
    SettingsState,
    ViewportState,
)

from .actions import (
    Action,
    ClearAllCachesAction,
    ClearImageSlotDataAction,
    InvalidateGeometryCacheAction,
    InvalidateRenderCacheAction,
    SetActiveMagnifierIdAction,
    SetAutoCropBlackBordersAction,
    SetCachedDiffImageAction,
    SetCaptureRingColorAction,
    SetCaptureSizeRelativeAction,
    SetChannelViewModeAction,
    SetCurrentIndexAction,
    SetDiffModeAction,
    SetDividerLineColorAction,
    SetDividerLineThicknessAction,
    SetDividerLineVisibleAction,
    SetDrawTextBackgroundAction,
    SetFileNameBgColorAction,
    SetFileNameColorAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetFullResImageAction,
    SetImagePathAction,
    SetIncludeFileNamesInSavedAction,
    SetIsDraggingSliderAction,
    SetLanguageAction,
    SetLaserSmoothingInterpolationMethodAction,
    SetMagnifierBorderColorAction,
    SetMagnifierDividerColorAction,
    SetMagnifierDividerThicknessAction,
    SetMagnifierDividerVisibleAction,
    SetMagnifierInternalSplitAction,
    SetMagnifierLaserColorAction,
    SetMagnifierMovementInterpolationMethodAction,
    SetMagnifierPositionAction,
    SetMagnifierSizeRelativeAction,
    SetMagnifierVisibilityAction,
    SetMovementSpeedAction,
    SetOriginalImageAction,
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
    SetTextAlphaPercentAction,
    SetTextPlacementModeAction,
    SetUIModeAction,
    ToggleFreezeMagnifierAction,
    ToggleMagnifierAction,
    ToggleMagnifierOrientationAction,
    ToggleOrientationAction,
    UpdateMagnifierCombinedStateAction,
)

class ViewportReducer:
    @staticmethod
    def reduce(state: ViewportState, action: Action) -> ViewportState:
        for action_type, handler in ViewportReducer._handlers():
            if isinstance(action, action_type):
                return handler(state, action)
        return state

    @staticmethod
    def _handlers():
        return (
            (SetSplitPositionAction, ViewportReducer._reduce_split_position),
            (SetSplitPositionVisualAction, ViewportReducer._reduce_split_position_visual),
            (ToggleOrientationAction, ViewportReducer._reduce_orientation),
            (SetMagnifierSizeRelativeAction, ViewportReducer._reduce_magnifier_size),
            (SetCaptureSizeRelativeAction, ViewportReducer._reduce_capture_size),
            (ToggleMagnifierAction, ViewportReducer._reduce_toggle_magnifier),
            (SetMagnifierVisibilityAction, ViewportReducer._reduce_magnifier_visibility),
            (ToggleMagnifierOrientationAction, ViewportReducer._reduce_magnifier_orientation),
            (ToggleFreezeMagnifierAction, ViewportReducer._reduce_freeze_magnifier),
            (SetMagnifierPositionAction, ViewportReducer._reduce_magnifier_position),
            (SetMagnifierInternalSplitAction, ViewportReducer._reduce_internal_split),
            (SetMovementSpeedAction, ViewportReducer._reduce_movement_speed),
            (UpdateMagnifierCombinedStateAction, ViewportReducer._reduce_combined_state),
            (SetIsDraggingSliderAction, ViewportReducer._reduce_dragging_slider),
            (SetActiveMagnifierIdAction, ViewportReducer._reduce_active_magnifier_id),
            (SetDiffModeAction, ViewportReducer._reduce_diff_mode),
            (SetChannelViewModeAction, ViewportReducer._reduce_channel_view_mode),
            (SetCachedDiffImageAction, ViewportReducer._reduce_cached_diff_image),
            (InvalidateRenderCacheAction, ViewportReducer._reduce_invalidate_render_cache),
            (InvalidateGeometryCacheAction, ViewportReducer._reduce_invalidate_geometry_cache),
            (ClearAllCachesAction, ViewportReducer._reduce_clear_all_caches),
            (ClearImageSlotDataAction, ViewportReducer._reduce_clear_image_slot_data),
        )

    @staticmethod
    def _with_view_state(state: ViewportState, **kwargs) -> ViewportState:
        return ViewportState(
            render_config=state.render_config,
            session_data=state.session_data,
            view_state=replace(state.view_state, **kwargs),
        )

    @staticmethod
    def _with_session_data(state: ViewportState, **kwargs) -> ViewportState:
        return ViewportState(
            render_config=state.render_config,
            session_data=replace(state.session_data, **kwargs),
            view_state=state.view_state,
        )

    @staticmethod
    def _with_view_and_session(
        state: ViewportState, *, view_kwargs=None, session_kwargs=None
    ) -> ViewportState:
        return ViewportState(
            render_config=state.render_config,
            session_data=replace(state.session_data, **(session_kwargs or {})),
            view_state=replace(state.view_state, **(view_kwargs or {})),
        )

    @staticmethod
    def _reduce_split_position(state: ViewportState, action: SetSplitPositionAction) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, split_position=max(0.0, min(1.0, action.position))
        )

    @staticmethod
    def _reduce_split_position_visual(
        state: ViewportState, action: SetSplitPositionVisualAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, split_position_visual=max(0.0, min(1.0, action.position))
        )

    @staticmethod
    def _reduce_orientation(state: ViewportState, action: ToggleOrientationAction) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, is_horizontal=action.is_horizontal
        )

    @staticmethod
    def _reduce_magnifier_size(
        state: ViewportState, action: SetMagnifierSizeRelativeAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, magnifier_size_relative=action.size
        )

    @staticmethod
    def _reduce_capture_size(
        state: ViewportState, action: SetCaptureSizeRelativeAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, capture_size_relative=action.size
        )

    @staticmethod
    def _reduce_toggle_magnifier(
        state: ViewportState, action: ToggleMagnifierAction
    ) -> ViewportState:
        kwargs = {"use_magnifier": action.enabled}
        if action.enabled and not state.view_state.active_magnifier_id:
            kwargs["active_magnifier_id"] = "default"
        return ViewportReducer._with_view_state(state, **kwargs)

    @staticmethod
    def _reduce_magnifier_visibility(
        state: ViewportState, action: SetMagnifierVisibilityAction
    ) -> ViewportState:
        payload = action.get_payload()
        kwargs = {}
        if payload.get("left") is not None:
            kwargs["magnifier_visible_left"] = payload["left"]
        if payload.get("center") is not None:
            kwargs["magnifier_visible_center"] = payload["center"]
        if payload.get("right") is not None:
            kwargs["magnifier_visible_right"] = payload["right"]
        if not kwargs:
            return state
        return ViewportReducer._with_view_state(state, **kwargs)

    @staticmethod
    def _reduce_magnifier_orientation(
        state: ViewportState, action: ToggleMagnifierOrientationAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, magnifier_is_horizontal=action.is_horizontal
        )

    @staticmethod
    def _reduce_freeze_magnifier(
        state: ViewportState, action: ToggleFreezeMagnifierAction
    ) -> ViewportState:
        payload = action.get_payload()
        return ViewportReducer._with_view_state(
            state,
            freeze_magnifier=payload["freeze"],
            frozen_capture_point_relative=payload.get("frozen_position"),
            magnifier_offset_relative=payload.get("new_offset")
            or state.view_state.magnifier_offset_relative,
            magnifier_offset_relative_visual=payload.get("new_offset")
            or state.view_state.magnifier_offset_relative_visual,
        )

    @staticmethod
    def _reduce_magnifier_position(
        state: ViewportState, action: SetMagnifierPositionAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, capture_position_relative=action.position
        )

    @staticmethod
    def _reduce_internal_split(
        state: ViewportState, action: SetMagnifierInternalSplitAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, magnifier_internal_split=max(0.0, min(1.0, action.split))
        )

    @staticmethod
    def _reduce_movement_speed(
        state: ViewportState, action: SetMovementSpeedAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, movement_speed_per_sec=action.speed
        )

    @staticmethod
    def _reduce_combined_state(
        state: ViewportState, action: UpdateMagnifierCombinedStateAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, is_magnifier_combined=action.is_combined
        )

    @staticmethod
    def _reduce_dragging_slider(
        state: ViewportState, action: SetIsDraggingSliderAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, is_dragging_any_slider=action.is_dragging
        )

    @staticmethod
    def _reduce_active_magnifier_id(
        state: ViewportState, action: SetActiveMagnifierIdAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, active_magnifier_id=action.magnifier_id
        )

    @staticmethod
    def _reduce_diff_mode(state: ViewportState, action: SetDiffModeAction) -> ViewportState:
        return ViewportReducer._with_view_and_session(
            state,
            view_kwargs={"diff_mode": action.mode},
            session_kwargs={"cached_diff_image": None},
        )

    @staticmethod
    def _reduce_channel_view_mode(
        state: ViewportState, action: SetChannelViewModeAction
    ) -> ViewportState:
        return ViewportReducer._with_view_state(
            state, channel_view_mode=action.mode
        )

    @staticmethod
    def _reduce_cached_diff_image(
        state: ViewportState, action: SetCachedDiffImageAction
    ) -> ViewportState:
        return ViewportReducer._with_session_data(
            state, cached_diff_image=action.image
        )

    @staticmethod
    def _reduce_invalidate_render_cache(
        state: ViewportState, _action: InvalidateRenderCacheAction
    ) -> ViewportState:
        return ViewportReducer._with_view_and_session(
            state,
            view_kwargs={
                "text_bg_visual_height": 0.0,
                "text_bg_visual_width": 0.0,
            },
            session_kwargs={
                "caches": {},
                "magnifier_cache": {},
                "cached_split_base_image": None,
                "last_split_cached_params": None,
            },
        )

    @staticmethod
    def _reduce_invalidate_geometry_cache(
        state: ViewportState, _action: InvalidateGeometryCacheAction
    ) -> ViewportState:
        return ViewportReducer._with_session_data(
            state,
            scaled_image1_for_display=None,
            scaled_image2_for_display=None,
            cached_scaled_image_dims=None,
            display_cache_image1=None,
            display_cache_image2=None,
            last_display_cache_params=None,
        )

    @staticmethod
    def _reduce_clear_all_caches(
        state: ViewportState, _action: ClearAllCachesAction
    ) -> ViewportState:
        return ViewportReducer._with_view_and_session(
            state,
            view_kwargs={
                "text_bg_visual_height": 0.0,
                "text_bg_visual_width": 0.0,
            },
            session_kwargs={
                "unified_image_cache": state.session_data.unified_image_cache.__class__(),
                "scaled_image1_for_display": None,
                "scaled_image2_for_display": None,
                "cached_scaled_image_dims": None,
                "display_cache_image1": None,
                "display_cache_image2": None,
                "last_display_cache_params": None,
                "caches": {},
                "magnifier_cache": {},
                "cached_split_base_image": None,
                "last_split_cached_params": None,
            },
        )

    @staticmethod
    def _reduce_clear_image_slot_data(
        state: ViewportState, action: ClearImageSlotDataAction
    ) -> ViewportState:
        session_kwargs = (
            {
                "image1": None,
                "display_cache_image1": None,
                "scaled_image1_for_display": None,
            }
            if action.slot == 1
            else {
                "image2": None,
                "display_cache_image2": None,
                "scaled_image2_for_display": None,
            }
        )
        session_kwargs.update(
            {
                "scaled_image1_for_display": None,
                "scaled_image2_for_display": None,
                "cached_scaled_image_dims": None,
                "last_display_cache_params": None,
            }
        )
        return ViewportReducer._with_session_data(state, **session_kwargs)

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
            return replace(
                config, magnifier_movement_interpolation_method=action.method
            )

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

        elif isinstance(action, ClearImageSlotDataAction):
            if action.slot == 1:
                return replace(
                    document,
                    original_image1=None,
                    full_res_image1=None,
                    preview_image1=None,
                    image1_path=None,
                )
            else:
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

    def reduce(self, store: "Store", action: Action) -> "Store":
        from core.store import Store

        new_viewport = self.viewport_reducer.reduce(store.viewport, action)

        new_render_config = self.render_config_reducer.reduce(
            new_viewport.render_config, action
        )
        if new_render_config is not new_viewport.render_config:

            new_viewport = ViewportState(
                render_config=new_render_config,
                session_data=new_viewport.session_data,
                view_state=new_viewport.view_state,
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
