"""Reducer for the ``document`` session state slot.

Owns the two-image-list domain logic (``slot == 1/2``, ``image_list1/2``,
``current_index1/2`` etc.) — this is image_compare's ``DocumentModel``
shape, not something core should branch on. Registered against core's
generic slot-reducer registry (``core.state_management.slot_reducers``) by
``ComparisonPlugin``, so ``RootReducer`` can run it without importing this
module.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.state_management.actions import (
    Action,
    ClearImageSlotDataAction,
    SetCurrentIndexAction,
    SetFullResImageAction,
    SetImagePathAction,
    SetOriginalImageAction,
    SetPreviewImageAction,
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
        if isinstance(action, SetOriginalImageAction):
            if action.slot == 1:
                return replace(document, original_image1=action.image)
            return replace(document, original_image2=action.image)
        if isinstance(action, SetFullResImageAction):
            if action.slot == 1:
                return replace(document, full_res_image1=action.image)
            return replace(document, full_res_image2=action.image)
        if isinstance(action, SetPreviewImageAction):
            if action.slot == 1:
                return replace(document, preview_image1=action.image)
            return replace(document, preview_image2=action.image)
        if isinstance(action, SetImagePathAction):
            if action.slot == 1:
                return replace(document, image1_path=action.path)
            return replace(document, image2_path=action.path)
        if isinstance(action, ClearImageSlotDataAction):
            if action.slot == 1:
                return replace(
                    document,
                    original_image1=None,
                    full_res_image1=None,
                    preview_image1=None,
                    image1_path=None,
                    _last_display_name1="",
                )
            return replace(
                document,
                original_image2=None,
                full_res_image2=None,
                preview_image2=None,
                image2_path=None,
                _last_display_name2="",
            )
        return document
