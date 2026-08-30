"""Session bootstrap — initialize display, resync slots, ensure helpers.

Extracted from ``loading.py`` to keep that file <500. Re-exported via ``loading.py``.
"""

from __future__ import annotations

import logging

from core.state_management.actions import SetCurrentIndexAction

logger = logging.getLogger("ImproveImgSLI")


def ensure_current_slot(controller, image_number: int, force_refresh: bool = False) -> bool:
    """Thin wrapper delegating to ``slot.ensure_current_slot`` to avoid cycle."""
    from tabs.image_compare.use_cases.slot import ensure_current_slot as _impl

    return _impl(controller, image_number, force_refresh=force_refresh)


def initialize_app_display(controller):
    if controller.store.get_session_state_slot("document") is None:
        return
    document = controller.store.get_session_state_slot("document")
    d = getattr(controller.store, "get_dispatcher", lambda: None)()
    if d is not None:
        isd = controller.store.viewport.session_data.image_state
        if 0 <= isd.loaded_current_index1 < len(document.image_list1):
            d.dispatch(SetCurrentIndexAction(slot=1, index=isd.loaded_current_index1), scope="document")
        elif document.image_list1:
            d.dispatch(SetCurrentIndexAction(slot=1, index=0), scope="document")
        if 0 <= isd.loaded_current_index2 < len(document.image_list2):
            d.dispatch(SetCurrentIndexAction(slot=2, index=isd.loaded_current_index2), scope="document")
        elif document.image_list2:
            d.dispatch(SetCurrentIndexAction(slot=2, index=0), scope="document")
    controller.set_current_image(1, emit_signal=False)
    controller.set_current_image(2, emit_signal=False)
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(["combobox", "file_names", "resolution", "ratings"])
        controller.presenter.update_minimum_window_size()
    controller.store.emit_state_change("document")


def resync_current_image_slots(controller) -> None:
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return
    for n in (1, 2):
        ensure_current_slot(controller, n, force_refresh=True)
