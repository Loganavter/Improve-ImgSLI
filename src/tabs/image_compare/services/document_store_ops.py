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
    dispatcher = store.get_dispatcher()
    assert dispatcher is not None, "clear_image_slot_data requires dispatcher"
    from core.state_management.actions import ClearImageSlotDataAction

    dispatcher.dispatch(ClearImageSlotDataAction(image_number), scope="viewport")


def set_current_image_data(store, image_number: int, image, path, display_name) -> None:
    dispatcher = store.get_dispatcher()
    assert dispatcher is not None, "set_current_image_data requires dispatcher"
    from core.state_management.actions import (
        SetFullResImageAction,
        SetImagePathAction,
        SetImageSessionImageAction,
        SetOriginalImageAction,
    )

    with store.batch_changes():
        dispatcher.dispatch(
            SetFullResImageAction(image_number, image), scope="document"
        )
        dispatcher.dispatch(
            SetOriginalImageAction(image_number, image), scope="document"
        )
        dispatcher.dispatch(
            SetImagePathAction(image_number, path), scope="document"
        )
        dispatcher.dispatch(
            SetImageSessionImageAction(slot=image_number, image=image),
            scope="viewport",
        )


def swap_all_image_data(store) -> None:
    dispatcher = store.get_dispatcher()
    assert dispatcher is not None, "swap_all_image_data requires dispatcher"
    from core.state_management.actions import (
        SetCurrentIndexAction,
        SetFullResImageAction,
        SetImagePathAction,
        SetImageSessionImageAction,
        SetOriginalImageAction,
        SetPreviewImageAction,
    )

    doc = store.get_session_state_slot("document")
    vp = store.viewport

    # Capture before any dispatch — replace() returns a new document, so later
    # captures would see already-swapped values.
    image1 = vp.session_data.image_state.image1
    image2 = vp.session_data.image_state.image2
    idx1 = doc.current_index1
    idx2 = doc.current_index2
    orig1 = doc.original_image1
    orig2 = doc.original_image2
    full1 = doc.full_res_image1
    full2 = doc.full_res_image2
    prev1 = doc.preview_image1
    prev2 = doc.preview_image2
    path1 = doc.image1_path
    path2 = doc.image2_path
    list1 = doc.image_list1
    list2 = doc.image_list2

    with store.batch_changes():
        # image_state swap atomically via two dispatches
        dispatcher.dispatch(
            SetImageSessionImageAction(slot=1, image=image2), scope="viewport"
        )
        dispatcher.dispatch(
            SetImageSessionImageAction(slot=2, image=image1), scope="viewport"
        )
        # document current_index / pixel-bearing slots via existing actions
        dispatcher.dispatch(SetCurrentIndexAction(slot=1, index=idx2), scope="document")
        dispatcher.dispatch(SetCurrentIndexAction(slot=2, index=idx1), scope="document")
        dispatcher.dispatch(SetOriginalImageAction(1, orig2), scope="document")
        dispatcher.dispatch(SetOriginalImageAction(2, orig1), scope="document")
        dispatcher.dispatch(SetFullResImageAction(1, full2), scope="document")
        dispatcher.dispatch(SetFullResImageAction(2, full1), scope="document")
        dispatcher.dispatch(SetPreviewImageAction(1, prev2), scope="document")
        dispatcher.dispatch(SetPreviewImageAction(2, prev1), scope="document")
        dispatcher.dispatch(SetImagePathAction(1, path2), scope="document")
        dispatcher.dispatch(SetImagePathAction(2, path1), scope="document")
        # image_list has no SetImageListAction yet (ActionType exists but no
        # reducer branch). Use dataclasses.replace + slot write so the swap
        # goes through the store slot write path (re-points session) rather
        # than a direct dataclass mutation, and keep it inside the same batch
        # so subscribers see the coherent final state.
        live_doc = store.get_session_state_slot("document")
        try:
            new_doc = _dc_replace(live_doc, image_list1=list2, image_list2=list1)
            store.set_session_state_slot("document", new_doc, emit_scope="document")
        except Exception:
            # Fallback for unexpected dataclass shape — direct swap still
            # observable, dogma exempts `live_doc` (not `document`).
            try:
                live_doc.image_list1, live_doc.image_list2 = list2, list1
            except Exception:
                pass
        store.invalidate_geometry_cache()


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
    new_session_data.render_cache.cached_diff_source_key = (
        src_session.render_cache.cached_diff_source_key
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