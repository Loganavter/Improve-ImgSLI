from __future__ import annotations

class StoreOperationsMixin:
    def clear_all_caches(self):
        if self._dispatcher:
            from core.state_management.actions import ClearAllCachesAction

            self._dispatcher.dispatch(ClearAllCachesAction(), scope="viewport")
        else:
            render_cache = self.viewport.session_data.render_cache
            if render_cache is not None:
                render_cache.unified_image_cache.clear()
            self.invalidate_geometry_cache()

    def invalidate_render_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateRenderCacheAction

            self._dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        else:
            render_cache = self.viewport.session_data.render_cache
            if render_cache is not None:
                render_cache.caches.clear()
                render_cache.feature_caches.clear()
                render_cache.cached_split_base_image = None
                render_cache.last_split_cached_params = None

    def invalidate_geometry_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateGeometryCacheAction

            self._dispatcher.dispatch(InvalidateGeometryCacheAction(), scope="viewport")
        else:
            render_cache = self.viewport.session_data.render_cache
            if render_cache is not None:
                render_cache.scaled_image1_for_display = None
                render_cache.scaled_image2_for_display = None
                render_cache.cached_scaled_image_dims = None
                render_cache.display_cache_image1 = None
                render_cache.display_cache_image2 = None
                render_cache.last_display_cache_params = None
            self.invalidate_render_cache()

    def clear_interactive_caches(self):
        self.invalidate_render_cache()
