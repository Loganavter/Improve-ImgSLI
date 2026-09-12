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
    SetCropOverrideAction,
    SetCurrentIndexAction,
)


class DocumentReducer:
    @staticmethod
    def _set_crop_override(document: Any, action) -> Any:
        """Per-item tristate override via ``dataclasses.replace`` (no in-place edit)."""
        value = getattr(action, "value", None)
        value = None if value is None else bool(value)
        if getattr(action, "slot", 0) == 1:
            items = list(document.image_list1)
            if not (0 <= getattr(action, "index", -1) < len(items)):
                return document
            items[action.index] = replace(items[action.index], crop_override=value)
            return replace(document, image_list1=items)
        if getattr(action, "slot", 0) == 2:
            items = list(document.image_list2)
            if not (0 <= getattr(action, "index", -1) < len(items)):
                return document
            items[action.index] = replace(items[action.index], crop_override=value)
            return replace(document, image_list2=items)
        return document

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
        if isinstance(action, SetCropOverrideAction):
            return DocumentReducer._set_crop_override(document, action)
        # Phase 3 lightweight: list ops via Transaction (no direct lst.append)
        try:
            from core.state_management.document_actions import AppendImageItemsAction, SetImageListAction

            if isinstance(action, AppendImageItemsAction):
                if action.slot == 1:
                    new_list = list(document.image_list1) + list(action.items)
                    return replace(document, image_list1=new_list)
                new_list = list(document.image_list2) + list(action.items)
                return replace(document, image_list2=new_list)
            if isinstance(action, SetImageListAction):
                if action.slot == 1:
                    return replace(document, image_list1=list(action.items))
                return replace(document, image_list2=list(action.items))
        except Exception:
            pass
        # deprecated pixel/path actions are no-ops — SlotSource is list+index only
        # (derived path). Keep for compat: return same document.
        return document
