"""Reducers for the ``session_data`` / ``render_config`` fields of
``ViewportState``.

These are not ``state_slots`` (unlike ``document``) — they are named fields
on ``core.store_viewport.ViewportState``, which stays platform-owned because
the shared QRhi canvas widget is typed against it (see step 9 in
``docs/MIGRATION_PLAN.md``). Only the reduce *logic* is tab-owned; it is
registered against core's generic extension-reducer registry
(``core.state_management.extension_reducers``) by ``ComparisonPlugin``, so
``RootReducer`` can run it without importing this module.
"""

from dataclasses import replace

from core.state_management.actions import (
    Action,
    ClearAllCachesAction,
    ClearImageSlotDataAction,
    InvalidateGeometryCacheAction,
    InvalidateRenderCacheAction,
    SetAutoCalculatePsnrAction,
    SetAutoCalculateSsimAction,
    SetCachedDiffImageAction,
    SetCachedScaledImageDimsAction,
    SetDisplayCacheImageAction,
    SetDisplayResolutionLimitAction,
    SetDrawTextBackgroundAction,
    SetFileNameBgColorAction,
    SetFileNameColorAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetImageSessionImageAction,
    SetIncludeFileNamesInSavedAction,
    SetInterpolationMethodAction,
    SetLastDisplayCacheParamsAction,
    SetMaxNameLengthAction,
    SetMovementInterpolationMethodAction,
    SetPendingUnificationPathsAction,
    SetPsnrValueAction,
    SetScaledImageForDisplayAction,
    SetSsimValueAction,
    SetTextAlphaPercentAction,
    SetTextPlacementModeAction,
    SetUnificationInProgressAction,
    SetZoomInterpolationMethodAction,
)
from tabs.image_compare.state.models import (
    ImageSessionState,
    RenderCacheState,
    RenderConfig,
    SessionData,
)
from tabs.image_compare.canvas.registry import registry


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
            field_name = (
                "display_cache_image1" if action.slot == 1 else "display_cache_image2"
            )
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
            cache_state = replace(
                cache_state,
                caches={},
                cached_split_base_image=None,
                last_split_cached_params=None,
            )
            for feature in sorted(
                registry().get_widget_features(),
                key=lambda item: (item.reducer_order, item.name),
            ):
                if feature.reduce_cache_state is not None:
                    cache_state = feature.reduce_cache_state(cache_state, action)
            return cache_state
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
            cache_state = replace(
                cache_state,
                unified_image_cache=cache_state.unified_image_cache.__class__(),
                scaled_image1_for_display=None,
                scaled_image2_for_display=None,
                cached_scaled_image_dims=None,
                display_cache_image1=None,
                display_cache_image2=None,
                last_display_cache_params=None,
                caches={},
                cached_split_base_image=None,
                last_split_cached_params=None,
            )
            for feature in sorted(
                registry().get_widget_features(),
                key=lambda item: (item.reducer_order, item.name),
            ):
                if feature.reduce_cache_state is not None:
                    cache_state = feature.reduce_cache_state(cache_state, action)
            return cache_state
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


class ImageRenderConfigReducer:
    @staticmethod
    def reduce(config: RenderConfig, action: Action) -> RenderConfig:
        for feature in sorted(
            registry().get_widget_features(),
            key=lambda item: (item.reducer_order, item.name),
        ):
            reduced = feature.reduce_render_config(config, action)
            if reduced is not config:
                return reduced
        if isinstance(action, SetInterpolationMethodAction):
            return replace(config, interpolation_method=action.method)
        if isinstance(action, SetMovementInterpolationMethodAction):
            return replace(config, movement_interpolation_method=action.method)
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
        if isinstance(action, SetMaxNameLengthAction):
            return replace(config, max_name_length=action.length)
        if isinstance(action, SetDisplayResolutionLimitAction):
            return replace(config, display_resolution_limit=action.limit)
        return config
