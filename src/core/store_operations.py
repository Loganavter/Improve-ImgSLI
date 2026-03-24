from __future__ import annotations

from core.store_document import DocumentModel
from core.store_viewport import SessionData, ViewportState

class StoreOperationsMixin:
    def clear_all_caches(self):
        if self._dispatcher:
            from core.state_management.actions import ClearAllCachesAction

            self._dispatcher.dispatch(ClearAllCachesAction(), scope="viewport")
        else:
            self.viewport.session_data.unified_image_cache.clear()
            self.invalidate_geometry_cache()

    def invalidate_render_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateRenderCacheAction

            self._dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        else:
            session = self.viewport.session_data
            session.caches.clear()
            session.magnifier_cache.clear()
            session.cached_split_base_image = None
            session.last_split_cached_params = None

    def invalidate_geometry_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateGeometryCacheAction

            self._dispatcher.dispatch(InvalidateGeometryCacheAction(), scope="viewport")
        else:
            session = self.viewport.session_data
            session.scaled_image1_for_display = None
            session.scaled_image2_for_display = None
            session.cached_scaled_image_dims = None
            session.display_cache_image1 = None
            session.display_cache_image2 = None
            session.last_display_cache_params = None
            self.invalidate_render_cache()

    def clear_interactive_caches(self):
        self.invalidate_render_cache()

    def clear_image_slot_data(self, image_number: int):
        if self._dispatcher:
            from core.state_management.actions import ClearImageSlotDataAction

            self._dispatcher.dispatch(
                ClearImageSlotDataAction(image_number), scope="viewport"
            )
        else:
            if image_number == 1:
                self.document.original_image1 = None
                self.document.full_res_image1 = None
                self.document.preview_image1 = None
                self.document.image1_path = None
                self.viewport.image1 = None
                self.viewport.display_cache_image1 = None
            else:
                self.document.original_image2 = None
                self.document.full_res_image2 = None
                self.document.preview_image2 = None
                self.document.image2_path = None
                self.viewport.image2 = None
                self.viewport.display_cache_image2 = None

            session = self.viewport.session_data
            session.scaled_image1_for_display = None
            session.scaled_image2_for_display = None
            session.cached_scaled_image_dims = None
            session.last_display_cache_params = None
            self.invalidate_render_cache()

    def set_current_image_data(self, image_number: int, image, path, display_name):
        if self._dispatcher:
            from core.state_management.actions import (
                SetFullResImageAction,
                SetImagePathAction,
                SetOriginalImageAction,
            )

            self._dispatcher.dispatch(
                SetFullResImageAction(image_number, image), scope="document"
            )
            self._dispatcher.dispatch(
                SetOriginalImageAction(image_number, image), scope="document"
            )
            self._dispatcher.dispatch(
                SetImagePathAction(image_number, path), scope="document"
            )
        else:
            if image_number == 1:
                self.document.full_res_image1 = image
                self.document.original_image1 = image
                self.document.image1_path = path
                self.viewport.image1 = image
            else:
                self.document.full_res_image2 = image
                self.document.original_image2 = image
                self.document.image2_path = path
                self.viewport.image2 = image
            self.emit_state_change("document")

    def swap_all_image_data(self):
        doc = self.document
        vp = self.viewport

        doc.image_list1, doc.image_list2 = doc.image_list2, doc.image_list1
        doc.current_index1, doc.current_index2 = doc.current_index2, doc.current_index1

        doc.original_image1, doc.original_image2 = (
            doc.original_image2,
            doc.original_image1,
        )
        doc.full_res_image1, doc.full_res_image2 = (
            doc.full_res_image2,
            doc.full_res_image1,
        )
        doc.preview_image1, doc.preview_image2 = doc.preview_image2, doc.preview_image1
        doc.image1_path, doc.image2_path = doc.image2_path, doc.image1_path

        vp.image1, vp.image2 = vp.image2, vp.image1
        vp.display_cache_image1, vp.display_cache_image2 = (
            vp.display_cache_image2,
            vp.display_cache_image1,
        )
        vp.scaled_image1_for_display, vp.scaled_image2_for_display = (
            vp.scaled_image2_for_display,
            vp.scaled_image1_for_display,
        )

        self.invalidate_geometry_cache()
        self.emit_state_change("document")

    def copy_for_worker(self):
        src_render = self.viewport.render_config
        new_render_config = src_render.clone()

        src_view = self.viewport.view_state
        new_view_state = src_view.clone()

        new_view_state.split_position = src_view.split_position_visual
        new_view_state.magnifier_offset_relative = src_view.magnifier_offset_relative_visual
        new_view_state.magnifier_spacing_relative = (
            src_view.magnifier_spacing_relative_visual
        )

        src_session = self.viewport.session_data
        new_session_data = SessionData()

        new_session_data.loaded_image1_paths = list(src_session.loaded_image1_paths)
        new_session_data.loaded_image2_paths = list(src_session.loaded_image2_paths)

        new_viewport = ViewportState(
            new_render_config, new_session_data, new_view_state
        )

        new_doc = DocumentModel()
        new_doc.current_index1 = self.document.current_index1
        new_doc.current_index2 = self.document.current_index2
        new_doc.image_list1 = list(self.document.image_list1)
        new_doc.image_list2 = list(self.document.image_list2)
        new_doc.full_res_image1 = self.document.full_res_image1
        new_doc.full_res_image2 = self.document.full_res_image2
        new_doc.original_image1 = self.document.original_image1
        new_doc.original_image2 = self.document.original_image2

        return self._build_worker_snapshot(new_viewport, new_doc)
