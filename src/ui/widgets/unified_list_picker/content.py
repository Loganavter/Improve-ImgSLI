from ui.widgets.unified_list_picker.debug import double_geom_debug
from ui.widgets.unified_list_picker.common import (
    FlyoutMode,
    ListItemType,
    _UnifiedFlyoutBase,
    current_index_for_list,
    items_for_list,
)

class _UnifiedFlyoutContentMixin(_UnifiedFlyoutBase):
    def populate(
        self,
        list_num: int,
        items: list,
        list_type: ListItemType = "image",
        current_index=-1,
    ):
        panel = (
            self.panel_left
            if (list_num == 1 or list_type == "simple")
            else self.panel_right
        )
        panel.clear_and_rebuild(
            items, self.item_height, self.item_font, list_type, current_index
        )
        double_geom_debug(
            "populate list=%s n=%s cur=%s mode=%s panel_h=%s",
            list_num,
            len(items),
            current_index,
            getattr(self.mode, "name", self.mode),
            panel._container_height,
        )
        if self.mode == FlyoutMode.DOUBLE:
            self.refreshGeometry()

    def sync_from_store(self):
        if not self.isVisible() or self._is_simple_mode:
            return

        doc = self._document()
        self.panel_left.sync_with_list(
            items_for_list(doc, 1),
            self.item_height,
            self.item_font,
            "image",
            current_index_for_list(doc, 1),
        )
        self.panel_right.sync_with_list(
            items_for_list(doc, 2),
            self.item_height,
            self.item_font,
            "image",
            current_index_for_list(doc, 2),
        )
        self.refreshGeometry(immediate=True)

    def update_rating_for_item(self, list_num: int, index: int):
        if not self.isVisible():
            return
        panel = self.panel_left if list_num == 1 else self.panel_right
        if panel and panel.isVisible():
            panel.update_item(index)