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
    InvalidateRenderCacheAction,
    SetAutoCalculatePsnrAction,
    SetAutoCalculateSsimAction,
    SetCachedDiffImageAction,
    SetDrawTextBackgroundAction,
    SetFileNameBgColorAction,
    SetFileNameColorAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetImageSessionImageAction,
    SetIncludeFileNamesInSavedAction,
    SetInterpolationMethodAction,
    SetMaxNameLengthAction,
    SetMovementInterpolationMethodAction,
    SetPendingUnificationPathsAction,
    SetPredictedUnifiedSizeAction,
    SetPsnrValueAction,
    SetSsimValueAction,
    SetTextAlphaPercentAction,
    SetTextPlacementModeAction,
    SetUnificationInProgressAction,
    SetZoomInterpolationMethodAction,
)
from tabs.image_compare.state.models import (
    ImageSessionState,
    PipelineCacheState,
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
        if isinstance(action, SetCachedDiffImageAction):
            return replace(cache_state, cached_diff_image=action.image)
        if isinstance(action, SetUnificationInProgressAction):
            return replace(cache_state, unification_in_progress=action.enabled)
        if isinstance(action, SetPendingUnificationPathsAction):
            return replace(cache_state, pending_unification_paths=action.paths)
        if isinstance(action, SetPredictedUnifiedSizeAction):
            return replace(cache_state, predicted_unified_size=action.predicted_size)
        if isinstance(action, InvalidateRenderCacheAction):
            for feature in sorted(
                registry().get_widget_features(),
                key=lambda item: (item.reducer_order, item.name),
            ):
                if feature.reduce_cache_state is not None:
                    cache_state = feature.reduce_cache_state(cache_state, action)
            return cache_state
        if isinstance(action, ClearAllCachesAction):
            for feature in sorted(
                registry().get_widget_features(),
                key=lambda item: (item.reducer_order, item.name),
            ):
                if feature.reduce_cache_state is not None:
                    cache_state = feature.reduce_cache_state(cache_state, action)
            if getattr(cache_state, "predicted_unified_size", None) is not None:
                return replace(cache_state, predicted_unified_size=None)
            return cache_state
        return cache_state


class SessionDataReducer:
    def __init__(self):
        self.image_session_reducer = ImageSessionReducer()
        self.render_cache_reducer = RenderCacheReducer()

    def reduce(self, session_data: SessionData, action: Action) -> SessionData:
        if session_data.render_cache is None:
            return session_data
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


class PipelineCacheReducer:
    """Bucket C — PipelineCache as Store slot (plan_render_dispatch_and_gap_fix.md).

    Owns the three LRU tiers; all ``put_*`` goes via ``Put*Action`` + ``transact``
    (single Store alloc). ``get_pixel`` is_open check lives here as replace +
    ``close_pixel_store`` defer. ``EvictPipelineAction`` sweeps
    ``pyramid_registry``.
    """

    @staticmethod
    def reduce(state: PipelineCacheState | None, action: Action) -> PipelineCacheState | None:
        if state is None:
            state = PipelineCacheState()
        try:
            from tabs.image_compare.state.actions import (
                EvictPipelineAction,
                PutPixelAction,
                PutPreviewAction,
                PutUnifiedAction,
            )
        except Exception:
            return state
        if isinstance(action, PutPixelAction):
            return PipelineCacheReducer._put_pixel(state, action)
        if isinstance(action, PutPreviewAction):
            return PipelineCacheReducer._put_preview(state, action)
        if isinstance(action, PutUnifiedAction):
            return PipelineCacheReducer._put_unified(state, action)
        if isinstance(action, EvictPipelineAction):
            return PipelineCacheReducer._evict(state, action)
        if isinstance(action, ClearAllCachesAction):
            for s in list(state.pixel.values()):
                PipelineCacheReducer._close_store(s)
            for v in list(state.unify.values()):
                if isinstance(v, tuple):
                    for x in v:
                        PipelineCacheReducer._close_store(x)
            return PipelineCacheState()
        return state

    @staticmethod
    def _close_store(store) -> None:
        try:
            from shared.image_processing.tiled_pixel_store import close_pixel_store
            close_pixel_store(store)
        except Exception:
            pass

    @staticmethod
    def _put_pixel(state: PipelineCacheState, action) -> PipelineCacheState:
        from collections import OrderedDict
        import os
        try:
            from tabs.image_compare.pipeline.cache import _PIXEL_CACHE_MAX, _pixel_key
        except Exception:
            _PIXEL_CACHE_MAX = 8
            def _pixel_key(path, crop_service=None, auto_crop=None):
                import os as _os
                try:
                    st = _os.stat(path)
                    mtime = st.st_mtime_ns
                    size = st.st_size
                except OSError:
                    mtime = 0
                    size = 0
                return (_os.path.normpath(path), mtime, size, bool(crop_service), None)
        store = action.store
        if store is None:
            return state
        try:
            is_open = getattr(store, "is_open", None)
            if is_open is not None:
                if callable(is_open):
                    if not is_open():
                        return state
                elif not is_open:
                    return state
        except Exception:
            pass
        path = action.path
        crop_service = action.crop_service
        auto_crop = action.auto_crop
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        if isinstance(crop_service, bool):
            auto_crop = crop_service
            crop_service = None
        try:
            key = _pixel_key(path, crop_service, auto_crop)
        except Exception:
            key = (os.path.normpath(path), 0, 0, bool(crop_service), None)
        new_pixel = OrderedDict(state.pixel)
        if key in new_pixel:
            try:
                old = new_pixel[key]
                if old is not store:
                    PipelineCacheReducer._close_store(old)
            except Exception:
                pass
            new_pixel.pop(key, None)
        new_pixel[key] = store
        while len(new_pixel) > _PIXEL_CACHE_MAX:
            try:
                _k, _old = new_pixel.popitem(last=False)
                PipelineCacheReducer._close_store(_old)
            except Exception:
                break
        return replace(state, pixel=new_pixel)

    @staticmethod
    def _put_preview(state: PipelineCacheState, action) -> PipelineCacheState:
        from collections import OrderedDict
        import os
        try:
            from tabs.image_compare.pipeline.cache import _PREVIEW_CACHE_MAX, _preview_key
        except Exception:
            _PREVIEW_CACHE_MAX = 8
            def _preview_key(path, crop_service=None, auto_crop=None):
                import os as _os
                try:
                    st = _os.stat(path)
                    mtime = st.st_mtime_ns
                    size = st.st_size
                except OSError:
                    mtime = 0
                    size = 0
                return (_os.path.normpath(path), mtime, size, bool(crop_service), None, 1024)
        qimage = action.qimage
        if qimage is None:
            return state
        try:
            if hasattr(qimage, "isNull") and qimage.isNull():
                return state
        except Exception:
            pass
        path = action.path
        crop_service = action.crop_service
        auto_crop = action.auto_crop
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        if isinstance(crop_service, bool):
            auto_crop = crop_service
            crop_service = None
        try:
            key = _preview_key(path, crop_service, auto_crop)
        except Exception:
            key = (os.path.normpath(path), 0, 0, bool(crop_service), None, 1024)
        new_preview = OrderedDict(state.preview)
        if key in new_preview:
            new_preview.pop(key, None)
        new_preview[key] = qimage
        while len(new_preview) > _PREVIEW_CACHE_MAX:
            try:
                new_preview.popitem(last=False)
            except Exception:
                break
        return replace(state, preview=new_preview)

    @staticmethod
    def _put_unified(state: PipelineCacheState, action) -> PipelineCacheState:
        from collections import OrderedDict
        try:
            from tabs.image_compare.pipeline.cache import _UNIFY_CACHE_MAX, _unify_key
        except Exception:
            _UNIFY_CACHE_MAX = 8
            def _unify_key(uid1, uid2, method, w, h):
                return (uid1, uid2, method, int(w), int(h))
        if action.pair is None:
            return state
        try:
            key = _unify_key(action.uid1, action.uid2, action.method, action.w, action.h)
        except Exception:
            key = (action.uid1, action.uid2, action.method, int(action.w), int(action.h))
        try:
            for s in action.pair:
                if hasattr(s, "isNull") and s.isNull():
                    return state
                is_open = getattr(s, "is_open", None)
                if is_open is not None:
                    if callable(is_open):
                        if not is_open():
                            return state
                    elif not is_open:
                        return state
        except Exception:
            pass
        new_unify = OrderedDict(state.unify)
        if key in new_unify:
            new_unify.pop(key, None)
        new_unify[key] = action.pair
        while len(new_unify) > _UNIFY_CACHE_MAX:
            try:
                new_unify.popitem(last=False)
            except Exception:
                break
        return replace(state, unify=new_unify)

    @staticmethod
    def _evict(state: PipelineCacheState, action) -> PipelineCacheState:
        import os
        from collections import OrderedDict
        path = action.path
        try:
            from tabs.image_compare.pipeline.cache import pop_embedded_cache
            pop_embedded_cache(path)
        except Exception:
            pass
        norm = os.path.normpath(path)
        new_pixel = OrderedDict(state.pixel)
        to_drop = [k for k in list(new_pixel.keys()) if k[0] == norm]
        for k in to_drop:
            old = new_pixel.pop(k, None)
            PipelineCacheReducer._close_store(old)
        new_preview = OrderedDict(state.preview)
        to_drop_prev = [k for k in list(new_preview.keys()) if k[0] == norm]
        for k in to_drop_prev:
            new_preview.pop(k, None)
        try:
            from shared.rendering.pyramid_registry import get_pyramid_registry
            reg = get_pyramid_registry()
            if reg is not None:
                try:
                    reg.sweep(path)
                except TypeError:
                    reg.sweep()
        except Exception:
            try:
                from shared.image_processing import pyramid_registry
                pyramid_registry.sweep()
            except Exception:
                pass
        return replace(state, pixel=new_pixel, preview=new_preview)


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
        return config