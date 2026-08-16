"""Self-contained adapter so UnifiedFlyout can be used without an external
store/controller/main_window — accepts plain item lists and two anchor widgets.
"""
from __future__ import annotations

from dataclasses import dataclass

from ui.widgets.unified_list_picker.common import (
    items_for_list,
    set_items_for_list,
)


@dataclass
class UnifiedFlyoutItem:
    display_name: str
    rating: int = 0
    path: str = ""


class _Document:
    def __init__(self) -> None:
        self.list1: list[UnifiedFlyoutItem] = []
        self.list2: list[UnifiedFlyoutItem] = []
        self.current_index1: int = -1
        self.current_index2: int = -1

    # Host-domain aliases (Improve-ImgSLI document still uses these names).
    @property
    def image_list1(self) -> list[UnifiedFlyoutItem]:
        return self.list1

    @image_list1.setter
    def image_list1(self, value: list[UnifiedFlyoutItem]) -> None:
        self.list1 = value

    @property
    def image_list2(self) -> list[UnifiedFlyoutItem]:
        return self.list2

    @image_list2.setter
    def image_list2(self, value: list[UnifiedFlyoutItem]) -> None:
        self.list2 = value


class SimpleUnifiedFlyoutStore:
    """Minimal store with the same shape that UnifiedFlyout reads.

    Lets hosts use the widget standalone without supplying their own document
    object.
    """

    def __init__(self) -> None:
        self.doc = _Document()

    def set_lists(
        self,
        left: list[UnifiedFlyoutItem | str],
        right: list[UnifiedFlyoutItem | str],
        *,
        current_left: int = -1,
        current_right: int = -1,
    ) -> None:
        self.doc.list1 = [_coerce(i) for i in left]
        self.doc.list2 = [_coerce(i) for i in right]
        self.doc.current_index1 = current_left
        self.doc.current_index2 = current_right


class SimpleUnifiedFlyoutController:
    """Receives selection / reorder callbacks from UnifiedFlyout panels."""

    def __init__(self, store: SimpleUnifiedFlyoutStore) -> None:
        self._store = store

    def on_combobox_changed(self, list_num: int, index: int) -> None:
        if list_num == 1:
            self._store.doc.current_index1 = index
        elif list_num == 2:
            self._store.doc.current_index2 = index

    def remove_item_from_list(self, list_num: int, index: int) -> None:
        target = items_for_list(self._store.doc, list_num)
        if 0 <= index < len(target):
            target.pop(index)

    # Legacy alias — prefer ``remove_item_from_list``.
    remove_specific_image_from_list = remove_item_from_list

    def increment_rating(self, list_num: int, index: int) -> None:
        item = self._item(list_num, index)
        if item is not None:
            item.rating = min(5, item.rating + 1)

    def decrement_rating(self, list_num: int, index: int) -> None:
        item = self._item(list_num, index)
        if item is not None:
            item.rating = max(0, item.rating - 1)

    def reorder_item_in_list(
        self, list_num: int, source_index: int, dest_index: int
    ) -> None:
        self.reorder_items_in_list(
            list_num=list_num,
            indices=[source_index],
            dest_index=dest_index,
        )

    def reorder_items_in_list(
        self, *, list_num: int, indices, dest_index: int
    ) -> None:
        from sli_ui_toolkit.ui.widgets.helpers.multi_move import (
            reorder_many,
        )

        target = items_for_list(self._store.doc, list_num)
        rebuilt = reorder_many(target, indices, dest_index)
        set_items_for_list(self._store.doc, list_num, rebuilt)

    def move_item_between_lists(
        self,
        *,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        self.move_items_between_lists(
            source_list_num=source_list_num,
            indices=[source_index],
            dest_list_num=dest_list_num,
            dest_index=dest_index,
        )

    def move_items_between_lists(
        self,
        *,
        source_list_num: int,
        indices,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        from sli_ui_toolkit.ui.widgets.helpers.multi_move import (
            move_many,
        )

        src = items_for_list(self._store.doc, source_list_num)
        dst = items_for_list(self._store.doc, dest_list_num)
        new_src, new_dst = move_many(src, dst, indices, dest_index)
        set_items_for_list(self._store.doc, source_list_num, new_src)
        set_items_for_list(self._store.doc, dest_list_num, new_dst)

    sessions = property(lambda self: self)

    def _item(self, list_num: int, index: int) -> UnifiedFlyoutItem | None:
        target = items_for_list(self._store.doc, list_num)
        return target[index] if 0 <= index < len(target) else None


def make_main_window_proxy(host_window, anchor_left, anchor_right):
    """Deprecated shim — prefer ``UnifiedFlyout.set_list_anchors``."""
    flyout = getattr(host_window, "_unified_flyout", None)
    if flyout is not None and hasattr(flyout, "set_list_anchors"):
        flyout.set_list_anchors(anchor_left, anchor_right)
    return host_window


def _coerce(item) -> UnifiedFlyoutItem:
    if isinstance(item, UnifiedFlyoutItem):
        return item
    if isinstance(item, str):
        return UnifiedFlyoutItem(display_name=item)
    if isinstance(item, dict):
        return UnifiedFlyoutItem(**item)
    return UnifiedFlyoutItem(display_name=str(item))