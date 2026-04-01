from PyQt6.QtCore import QTimer

from shared_toolkit.ui.widgets.composite.unified_flyout.common import FlyoutMode

class _UnifiedFlyoutContentMixin:
    def populate(self, list_num: int, items: list, list_type="image", current_index=-1):
        panel = (
            self.panel_left
            if (list_num == 1 or list_type == "simple")
            else self.panel_right
        )
        owner = (
            self._owner_proxy_simple
            if list_type == "simple"
            else (self._owner_proxy_left if list_num == 1 else self._owner_proxy_right)
        )
        panel.clear_and_rebuild(
            items, owner, self.item_height, self.item_font, list_type, current_index
        )
        if self.mode == FlyoutMode.DOUBLE:
            self.refreshGeometry()

    def sync_from_store(self):
        if not self.isVisible() or self._is_simple_mode:
            return

        self.panel_left.sync_with_list(
            self.store.document.image_list1,
            self._owner_proxy_left,
            self.item_height,
            self.item_font,
            "image",
            self.store.document.current_index1,
        )
        self.panel_right.sync_with_list(
            self.store.document.image_list2,
            self._owner_proxy_right,
            self.item_height,
            self.item_font,
            "image",
            self.store.document.current_index2,
        )
        QTimer.singleShot(0, lambda: self.refreshGeometry(immediate=True))

    def update_rating_for_item(self, image_number: int, index: int):
        if not self.isVisible():
            return
        panel = self.panel_left if image_number == 1 else self.panel_right
        if panel and panel.isVisible():
            panel.update_rating_for_item(index)
