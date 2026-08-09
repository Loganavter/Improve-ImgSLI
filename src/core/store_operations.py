from __future__ import annotations

class StoreOperationsMixin:
    def clear_all_caches(self):
        if self._dispatcher:
            from core.state_management.actions import ClearAllCachesAction

            self._dispatcher.dispatch(ClearAllCachesAction(), scope="viewport")
        else:
            self.invalidate_geometry_cache()

    def invalidate_render_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateRenderCacheAction

            self._dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")

    def invalidate_geometry_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateGeometryCacheAction

            self._dispatcher.dispatch(InvalidateGeometryCacheAction(), scope="viewport")
        else:
            self.invalidate_render_cache()

    def clear_interactive_caches(self):
        self.invalidate_render_cache()
