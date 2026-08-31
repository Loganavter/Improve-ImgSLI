"""Reducer for the ``document`` session state slot — SlotSource only.

Owns list+index domain logic (slot == 1/2, image_list1/2,
current_index1/2). Pixels are owned by PipelineCache/PipelineView
(viewport), not document. Registered via slot_reducers registry.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.state_management.actions import (
    Action,
    ClearImageSlotDataAction,
    SetCurrentIndexAction,
)


class DocumentReducer:
    @staticmethod
    def reduce(document: Any, action: Action) -> Any:
        if document is None:
            return document
        if isinstance(action, SetCurrentIndexAction):
            if action.slot == 1:
                return replace(document, current_index1=action.index)
            return replace(document, current_index2=action.index)
        if isinstance(action, ClearImageSlotDataAction):
            if action.slot == 1:
                return replace(document, _last_display_name1="")
            return replace(document, _last_display_name2="")
        # deprecated pixel/path actions are no-ops — SlotSource is list+index only
        # (derived path). Keep for compat: return same document.
        return document
