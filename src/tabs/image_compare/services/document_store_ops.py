"""Document/image-pair store operations that belong to image_compare.

These directly manipulate ``DocumentModel`` (``tabs/image_compare/state/document.py``)
and the image1/image2 fields of ``ViewportState.session_data`` — both are
image_compare's own "pair of images" concept, not a generic core one. They
used to live on ``core.store_operations.StoreOperationsMixin`` alongside
truly generic viewport-cache operations; see step 9 in
``tabs/image_compare/docs/MIGRATION_PLAN.md``.
"""

from __future__ import annotations

from dataclasses import replace as _dc_replace

from core.store_viewport import SessionData, ViewportState
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState
from tabs.image_compare.canvas.registry import registry


def clear_image_slot_data(store, image_number: int) -> None:
    if store.get_dispatcher():
        from core.state_management.actions import ClearImageSlotDataAction

        store.get_dispatcher().dispatch(
            ClearImageSlotDataAction(image_number), scope="viewport"
        )
        return

    document = store.get_session_state_slot("document")
    cache = store.viewport.session_data.render_cache
    image_state = store.viewport.session_data.image_state
    if image_number == 1:
        document.original_image1 = None
        document.full_res_image1 = None
        document.preview_image1 = None
        document.image1_path = None
        document.clear_last_display_name(1)
        image_state.image1 = None
        cache.display_cache_image1 = None
        cache.scaled_image1_for_display = None
    else:
        document.original_image2 = None
        document.full_res_image2 = None
        document.preview_image2 = None
        document.image2_path = None
        document.clear_last_display_name(2)
        image_state.image2 = None
        cache.display_cache_image2 = None
        cache.scaled_image2_for_display = None

    cache.cached_scaled_image_dims = None
    cache.last_display_cache_params = None
    store.invalidate_render_cache()


def set_current_image_data(store, image_number: int, image, path, display_name) -> None:
    if store.get_dispatcher():
        from core.state_management.actions import (
            SetFullResImageAction,
            SetImagePathAction,
            SetOriginalImageAction,
        )

        dispatcher = store.get_dispatcher()
        dispatcher.dispatch(
            SetFullResImageAction(image_number, image), scope="document"
        )
        dispatcher.dispatch(
            SetOriginalImageAction(image_number, image), scope="document"
        )
        dispatcher.dispatch(
            SetImagePathAction(image_number, path), scope="document"
        )
        return

    document = store.get_session_state_slot("document")
    if image_number == 1:
        document.full_res_image1 = image
        document.original_image1 = image
        document.image1_path = path
        store.viewport.session_data.image_state.image1 = image
    else:
        document.full_res_image2 = image
        document.original_image2 = image
        document.image2_path = path
        store.viewport.session_data.image_state.image2 = image
    store.emit_state_change("document")


def swap_all_image_data(store) -> None:
    doc = store.get_session_state_slot("document")
    vp = store.viewport

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

    vp.session_data.image_state.image1, vp.session_data.image_state.image2 = (
        vp.session_data.image_state.image2,
        vp.session_data.image_state.image1,
    )
    vp.session_data.render_cache.display_cache_image1, vp.session_data.render_cache.display_cache_image2 = (
        vp.session_data.render_cache.display_cache_image2,
        vp.session_data.render_cache.display_cache_image1,
    )
    vp.session_data.render_cache.scaled_image1_for_display, vp.session_data.render_cache.scaled_image2_for_display = (
        vp.session_data.render_cache.scaled_image2_for_display,
        vp.session_data.render_cache.scaled_image1_for_display,
    )

    store.invalidate_geometry_cache()
    store.emit_state_change("document")


def copy_for_worker(store):
    src_render = store.viewport.render_config
    new_render_config = src_render.clone()
    src_view = store.viewport.view_state
    new_view_state = src_view.clone()
    new_view_state.split_position = src_view.split_position_visual
    src_session = store.viewport.session_data
    new_session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )

    new_session_data.image_state.loaded_image1_paths = list(
        src_session.image_state.loaded_image1_paths
    )
    new_session_data.image_state.loaded_image2_paths = list(
        src_session.image_state.loaded_image2_paths
    )
    new_session_data.render_cache.cached_diff_image = (
        src_session.render_cache.cached_diff_image
    )

    new_viewport = ViewportState(
        new_render_config,
        new_session_data,
        new_view_state,
        store.viewport.interaction_state.clone(),
        store.viewport.geometry_state.clone(),
    )
    registry().prepare_feature_worker_viewport(store, new_viewport)

    document = store.get_session_state_slot("document")
    new_doc = _dc_replace(
        document,
        image_list1=list(document.image_list1),
        image_list2=list(document.image_list2),
        preview_image1=None,
        preview_image2=None,
        full_res_ready1=False,
        full_res_ready2=False,
        preview_ready1=False,
        preview_ready2=False,
        progressive_load_in_progress1=False,
        progressive_load_in_progress2=False,
        _last_display_name1="",
        _last_display_name2="",
    )

    return store.build_worker_snapshot(new_viewport, new_doc)
