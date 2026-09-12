"""Document slot updates — extracted from _session_controller.py"""

from __future__ import annotations


def update_image_slot(controller, slot_number: int, *, image=None, path=None, emit=True, is_preview=False, is_full_res=False):
    from core.state_management.actions import SetFullResImageAction, SetImagePathAction, SetPreviewImageAction
    actions=[]
    if is_full_res and image is not None: actions.append(SetFullResImageAction(slot=slot_number, image=image))
    if is_preview and image is not None: actions.append(SetPreviewImageAction(slot=slot_number, image=image))
    if path is not None: actions.append(SetImagePathAction(slot=slot_number, path=path))
    if not actions:
        if emit: controller.store.emit_state_change("document")
        return
    try:
        if hasattr(controller.store, "transact"):
            controller.store.transact(actions, scope="document")
            return
    except Exception: pass
    dispatcher=controller.store.get_dispatcher()
    for a in actions: dispatcher.dispatch(a, scope="document")
    if emit: controller.store.emit_state_change("document")
