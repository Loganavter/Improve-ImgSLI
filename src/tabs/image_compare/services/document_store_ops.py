"""Document/image-pair store operations that belong to image_compare.

These manipulate DocumentModel (SlotSource: image_list1/2 + current_index1/2
+ derived image1_path/2) and viewport image_state (PipelineView).
Pixels live in PipelineCache, not DocumentModel. See
plan_loading_simplification.md Phase 3.
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


def set_crop_override(store, list_num: int, index: int, value: bool | None) -> None:
    """Persist a per-image autocrop tristate override via dispatch (W5).

    Scope ``document`` like the rest of the document pattern — the
    dispatcher emits, so no manual ``emit_state_change`` is needed on the
    dispatch path. Unlike the rating path (in-place item mutation), this
    never touches ``ImageItem`` directly; ``DocumentReducer`` replaces it.
    """
    dispatcher = store.get_dispatcher()
    assert dispatcher is not None, "set_crop_override requires dispatcher"
    from core.state_management.actions import SetCropOverrideAction

    dispatcher.dispatch(
        SetCropOverrideAction(slot=list_num, index=index, value=value),
        scope="document",
    )


def set_current_image_data(store, image_number: int, image, path, display_name) -> None:
    # SlotSource: path is derived from list+index, no document pixel write.
    # PipelineView via single Transaction (1 dispatch, 1 emit).
    from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction

    try:
        store.transact(
            [
                SetImageSessionImageAction(slot=image_number, image=image),
                InvalidateGeometryCacheAction(),
            ],
            scope="viewport",
        )
    except Exception:
        dispatcher = store.get_dispatcher()
        assert dispatcher is not None
        with store.batch_changes():
            dispatcher.dispatch(SetImageSessionImageAction(slot=image_number, image=image), scope="viewport")
            dispatcher.dispatch(InvalidateGeometryCacheAction(), scope="viewport")


def swap_current_pair(store) -> bool:
    """Swap the pair's two *current* images through the dispatcher.

    A swap is ONE user-visible transition, so it must be published as one
    copy-on-write document+viewport batch — never by mutating
    ``DocumentModel.image_list1/image_list2`` in place. The in-place write was
    a Store-contract violation with an identity consequence: the pair's PATHS
    moved underneath every consumer that already held the document (undo
    snapshot, feature-worker snapshot, persistence capture, a listener that
    re-reads on a later ``document`` emit) while the paired
    ``image_state.image1/2`` pixels did not move with them, and no
    ``document`` scope was emitted, so nothing re-read the new pairing. A
    consumer left in that state resolves slot N's path to the OTHER slot's
    pixels for the frames until something else republishes the pair — the
    canvas then draws the other slot's content in this slot (owner report
    2026-10-27: a pair swap/replace flashing an image from the other slot or
    the previous one).

    Indexes are untouched: each list keeps its length and the current item is
    exchanged in place, so the pair's paths still derive from
    ``image_listN[current_indexN]`` and now name the image the viewport slot
    just received.

    No geometry invalidation: a swap exchanges the two images of ONE pair, so
    the comparison envelope ``max(w1,w2) x max(h1,h2)`` is unchanged (#737 —
    zeroing ``pixmap_width/height`` dropped the declared-visible loupe for a
    couple of frames). ``swap_all_image_data`` keeps its invalidation: there
    the current images themselves change.

    Returns ``False`` (nothing dispatched) when either slot has no current
    item, which is the legacy early-return behaviour.
    """
    dispatcher = store.get_dispatcher()
    if dispatcher is None:
        return False
    from core.state_management.actions import SetImageSessionImageAction
    from core.state_management.document_actions import SetImageListAction

    doc = store.get_session_state_slot("document")
    if doc is None:
        return False
    idx1 = doc.current_index1
    idx2 = doc.current_index2
    # Copies: the publication is copy-on-write, so no holder of the previous
    # document can observe this transition (see the docstring).
    list1 = list(doc.image_list1)
    list2 = list(doc.image_list2)
    if not (0 <= idx1 < len(list1) and 0 <= idx2 < len(list2)):
        return False
    list1[idx1], list2[idx2] = list2[idx2], list1[idx1]

    image_state = getattr(
        getattr(store.viewport, "session_data", None), "image_state", None
    )
    image1 = getattr(image_state, "image1", None) if image_state is not None else None
    image2 = getattr(image_state, "image2", None) if image_state is not None else None

    # One batch ⇒ one flush per scope, in first-emitted order: listeners only
    # ever see the coherent post-swap pair (paths and pixels together).
    with store.batch_changes():
        dispatcher.dispatch(SetImageListAction(slot=1, items=list1), scope="document")
        dispatcher.dispatch(SetImageListAction(slot=2, items=list2), scope="document")
        dispatcher.dispatch(
            SetImageSessionImageAction(slot=1, image=image2), scope="viewport"
        )
        dispatcher.dispatch(
            SetImageSessionImageAction(slot=2, image=image1), scope="viewport"
        )
    return True


def swap_all_image_data(store) -> None:
    dispatcher = store.get_dispatcher()
    assert dispatcher is not None, "swap_all_image_data requires dispatcher"
    from core.state_management.actions import InvalidateGeometryCacheAction, SetCurrentIndexAction, SetImageSessionImageAction

    doc = store.get_session_state_slot("document")
    vp = store.viewport

    # Capture before any dispatch — replace() returns a new document, so later
    # captures would see already-swapped values.
    image1 = vp.session_data.image_state.image1
    image2 = vp.session_data.image_state.image2
    idx1 = doc.current_index1
    idx2 = doc.current_index2
    list1 = doc.image_list1
    list2 = doc.image_list2

    with store.batch_changes():
        # viewport PipelineView swap
        dispatcher.dispatch(SetImageSessionImageAction(slot=1, image=image2), scope="viewport")
        dispatcher.dispatch(SetImageSessionImageAction(slot=2, image=image1), scope="viewport")
        # SlotSource swap
        dispatcher.dispatch(SetCurrentIndexAction(slot=1, index=idx2), scope="document")
        dispatcher.dispatch(SetCurrentIndexAction(slot=2, index=idx1), scope="document")
        # image_list swap via slot write (no SetImageListAction yet).
        # Copies: the published document must not alias the lists of a
        # document another holder still describes (same contract as
        # ``swap_current_pair``).
        live_doc = store.get_session_state_slot("document")
        new_doc = _dc_replace(
            live_doc, image_list1=list(list2), image_list2=list(list1)
        )
        store.set_session_state_slot("document", new_doc, emit_scope="document")
        dispatcher.dispatch(InvalidateGeometryCacheAction(), scope="viewport")


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
