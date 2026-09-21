"""Document slot updates — extracted from _session_controller.py"""

from __future__ import annotations


def update_image_slot(controller, slot_number: int, *, image=None, path=None, emit=True, is_preview=False, is_full_res=False):
    """Publish a slot image through live actions (dispatch-first).

    The deprecated document-scope pixel/path actions
    (``SetFullResImageAction`` / ``SetPreviewImageAction`` /
    ``SetImagePathAction``) have no owning reducer — ``DocumentReducer``
    returns the document unchanged — so publishing them silently dropped
    the update. Pixels now go to the pipeline slot (Bucket C
    ``PutPixelAction`` / ``PutPreviewAction`` with scope="pipeline");
    the document path is derived from list+index and needs no publish.
    """
    from tabs.image_compare.state.actions import PutPixelAction, PutPreviewAction

    actions = []
    if image is not None and path is not None:
        if is_preview:
            actions.append(PutPreviewAction(path=path, qimage=image))
        elif is_full_res:
            actions.append(PutPixelAction(path=path, store=image))
    if not actions:
        if emit:
            controller.store.emit_state_change("document")
        return
    try:
        if hasattr(controller.store, "transact"):
            controller.store.transact(actions, scope="pipeline")
        else:
            raise AttributeError
    except Exception:
        try:
            dispatcher = controller.store.get_dispatcher()
            for a in actions:
                dispatcher.dispatch(a, scope="pipeline")
        except Exception:
            pass
    if emit:
        controller.store.emit_state_change("document")
