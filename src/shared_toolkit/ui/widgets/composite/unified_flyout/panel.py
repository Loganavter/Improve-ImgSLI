from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from events.drag_drop_handler import DragAndDropService
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from shared_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from shared_toolkit.ui.widgets.list_items.rating_item import RatingListItem

class _ListOwnerProxy:
    def __init__(self, image_number: int):
        self.image_number = image_number

class _DropIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor("#00b7ff")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()

    def set_color(self, color: QColor):
        if color is None:
            color = QColor("#00b7ff")
        self._color = QColor(color)
        self._color.setAlpha(200)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if rect.isEmpty():
            return
        top_left = QPointF(rect.topLeft())
        top_right = QPointF(rect.topRight())
        gradient = QLinearGradient(top_left, top_right)
        middle = QColor(self._color)
        middle.setAlpha(200)
        transparent = QColor(middle)
        transparent.setAlpha(0)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.5, middle)
        gradient.setColorAt(1.0, transparent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

class _Panel(QWidget):
    MAX_VISIBLE_ITEMS = 10

    def __init__(
        self,
        image_number: int,
        item_height: int,
        item_font,
        get_current_index,
        get_rating,
        increment_rating,
        decrement_rating,
        create_rating_gesture,
        on_item_selected,
        on_item_context_menu,
        on_reorder,
        on_move_between_lists,
        on_update_drop_indicator,
        on_clear_drop_indicator,
        parent=None,
    ):
        super().__init__(parent)
        self.image_number = image_number
        self.item_height = item_height
        self.item_font = item_font
        self._get_current_index = get_current_index
        self._get_rating = get_rating
        self._increment_rating = increment_rating
        self._decrement_rating = decrement_rating
        self._create_rating_gesture = create_rating_gesture
        self._on_item_selected_cb = on_item_selected
        self._on_item_context_menu_cb = on_item_context_menu
        self._on_reorder = on_reorder
        self._on_move_between_lists = on_move_between_lists
        self._on_update_drop_indicator = on_update_drop_indicator
        self._on_clear_drop_indicator = on_clear_drop_indicator
        self.theme_manager = ThemeManager.get_instance()
        self.drop_indicator_y = -1
        self._container_height = 50
        self._owner_proxy = None
        self._list_type = "image"

        self.setObjectName("UnifiedFlyoutPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.layout_outer = QVBoxLayout(self)
        self.layout_outer.setContentsMargins(1, 1, 1, 1)
        self.layout_outer.setSpacing(0)

        self.scroll_area = OverlayScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.set_corner_radius(8)

        self.content_widget = QWidget()

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 4, 0, 4)
        self.content_layout.setSpacing(2)
        self.content_layout.addStretch(1)

        self.scroll_area.setWidget(self.content_widget)
        self.layout_outer.addWidget(self.scroll_area)

        self.drop_overlay = _DropIndicator(self.content_widget)

        self.setMinimumHeight(0)
        self.scroll_area.setMinimumHeight(0)

        self._apply_style()
        self.theme_manager.theme_changed.connect(self._apply_style)

    def sizeHint(self):

        return QSize(200, self._container_height)

    def _apply_style(self):

        try:
            accent = self.theme_manager.get_color("accent")
        except Exception:
            accent = QColor("#00b7ff")
        self.drop_overlay.set_color(accent)

    def clear_and_rebuild(
        self,
        image_list,
        owner_proxy,
        item_height,
        item_font,
        list_type="image",
        current_index=-1,
    ):
        PathTooltip.get_instance().hide_tooltip()
        self.clear_drop_indicator()

        self._owner_proxy = owner_proxy
        self._list_type = list_type
        self.item_height = item_height
        self.item_font = item_font
        preserve_scroll = self.isVisible()
        scrollbar = self.scroll_area.verticalScrollBar()
        previous_scroll_value = scrollbar.value() if preserve_scroll else 0

        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if current_index == -1:
            current_app_index = self._get_current_index(self.image_number)
        else:
            current_app_index = current_index

        if not image_list:
            self.recalculate_and_set_height()
            return

        total = len(image_list)
        for i, img_item in enumerate(image_list):
            is_current = i == current_app_index

            text = (
                img_item.display_name
                if hasattr(img_item, "display_name")
                else str(img_item)
            )
            rating = img_item.rating if hasattr(img_item, "rating") else 0
            full_path = img_item.path if hasattr(img_item, "path") else ""

            position = "middle"
            if total == 1:
                position = "only"
            elif i == 0:
                position = "first"
            elif i == total - 1:
                position = "last"

            item_widget = RatingListItem(
                index=i,
                text=text,
                rating=rating,
                full_path=full_path,
                image_number=owner_proxy.image_number,
                get_rating=self._get_rating,
                increment_rating=self._increment_rating,
                decrement_rating=self._decrement_rating,
                create_rating_gesture=self._create_rating_gesture,
                on_update_drop_indicator=self._on_update_drop_indicator,
                on_clear_drop_indicator=self._on_clear_drop_indicator,
                parent=self.content_widget,
                is_current=is_current,
                item_height=self.item_height,
                item_font=self.item_font,
                item_type=list_type,
                position=position,
            )

            item_widget.itemSelected.connect(self._on_item_clicked)
            item_widget.itemRightClicked.connect(self._on_context_menu)

            self.content_layout.insertWidget(
                self.content_layout.count() - 1, item_widget
            )

        self.recalculate_and_set_height()

        if preserve_scroll:
            QTimer.singleShot(
                0, lambda: scrollbar.setValue(min(previous_scroll_value, scrollbar.maximum()))
            )
        elif current_app_index >= 0:
            QTimer.singleShot(0, lambda: self._ensure_visible(current_app_index))

    def sync_with_list(
        self,
        image_list,
        owner_proxy,
        item_height,
        item_font,
        list_type="image",
        current_index=-1,
    ):
        self._owner_proxy = owner_proxy
        self._list_type = list_type
        self.item_height = item_height
        self.item_font = item_font

        if current_index == -1:
            current_app_index = self._get_current_index(self.image_number)
        else:
            current_app_index = current_index

        existing_widgets = self._item_widgets()
        if not existing_widgets or list_type != "image":
            self.clear_and_rebuild(
                image_list, owner_proxy, item_height, item_font, list_type, current_index
            )
            return

        target_paths = [getattr(item, "path", "") for item in image_list]
        existing_paths = [getattr(widget, "full_path", "") for widget in existing_widgets]

        if existing_paths == target_paths:
            self._refresh_widgets_from_list(image_list, current_app_index)
            return

        if len(existing_paths) == len(target_paths) + 1:
            removal_index = self._find_removed_index(existing_paths, target_paths)
            if removal_index is not None:
                self._remove_widget_at(removal_index)
                self._refresh_widgets_from_list(image_list, current_app_index)
                return

        if len(existing_paths) + 1 == len(target_paths):
            insert_index = self._find_inserted_index(existing_paths, target_paths)
            if insert_index is not None:
                self._insert_widget_at(insert_index, image_list[insert_index], current_app_index)
                self._refresh_widgets_from_list(image_list, current_app_index)
                return

        if len(existing_paths) == len(target_paths) and set(existing_paths) == set(target_paths):
            self._reorder_widgets_to_match(target_paths)
            self._refresh_widgets_from_list(image_list, current_app_index)
            return

        self.clear_and_rebuild(
            image_list, owner_proxy, item_height, item_font, list_type, current_index
        )

    def _ensure_visible(self, index):
        if 0 <= index < (self.content_layout.count() - 1):
            item = self.content_layout.itemAt(index)
            if item and item.widget():
                self.scroll_area.ensureWidgetVisible(item.widget())

    def _item_widgets(self):
        widgets = []
        for i in range(self.content_layout.count() - 1):
            layout_item = self.content_layout.itemAt(i)
            if layout_item and layout_item.widget():
                widgets.append(layout_item.widget())
        return widgets

    def _make_item_position(self, index: int, total: int) -> str:
        if total <= 1:
            return "only"
        if index == 0:
            return "first"
        if index == total - 1:
            return "last"
        return "middle"

    def _apply_item_data(self, widget, index, img_item, current_index, total):
        widget.index = index
        widget.full_path = img_item.path if hasattr(img_item, "path") else ""
        widget.is_current = index == current_index
        widget.position = self._make_item_position(index, total)
        widget.name_label.setText(
            img_item.display_name if hasattr(img_item, "display_name") else str(img_item)
        )
        if hasattr(widget, "rating_label"):
            rating = img_item.rating if hasattr(img_item, "rating") else 0
            widget.rating_label.setText(str(rating))
        widget.update()

    def _refresh_widgets_from_list(self, image_list, current_index):
        total = len(image_list)
        widgets = self._item_widgets()
        if len(widgets) != total:
            self.clear_and_rebuild(
                image_list,
                self._owner_proxy,
                self.item_height,
                self.item_font,
                self._list_type,
                current_index,
            )
            return

        for index, (widget, img_item) in enumerate(zip(widgets, image_list)):
            self._apply_item_data(widget, index, img_item, current_index, total)

        self.recalculate_and_set_height()

    def _find_removed_index(self, existing_paths, target_paths):
        for idx in range(len(existing_paths)):
            if existing_paths[:idx] + existing_paths[idx + 1 :] == target_paths:
                return idx
        return None

    def _find_inserted_index(self, existing_paths, target_paths):
        for idx in range(len(target_paths)):
            if target_paths[:idx] + target_paths[idx + 1 :] == existing_paths:
                return idx
        return None

    def _remove_widget_at(self, index: int):
        layout_item = self.content_layout.takeAt(index)
        if layout_item and layout_item.widget():
            layout_item.widget().deleteLater()

    def _build_item_widget(self, index, img_item, current_index, total):
        text = img_item.display_name if hasattr(img_item, "display_name") else str(img_item)
        rating = img_item.rating if hasattr(img_item, "rating") else 0
        full_path = img_item.path if hasattr(img_item, "path") else ""
        item_widget = RatingListItem(
            index=index,
            text=text,
            rating=rating,
            full_path=full_path,
            image_number=self._owner_proxy.image_number,
            get_rating=self._get_rating,
            increment_rating=self._increment_rating,
            decrement_rating=self._decrement_rating,
            create_rating_gesture=self._create_rating_gesture,
            on_update_drop_indicator=self._on_update_drop_indicator,
            on_clear_drop_indicator=self._on_clear_drop_indicator,
            parent=self.content_widget,
            is_current=index == current_index,
            item_height=self.item_height,
            item_font=self.item_font,
            item_type=self._list_type,
            position=self._make_item_position(index, total),
        )
        item_widget.itemSelected.connect(self._on_item_clicked)
        item_widget.itemRightClicked.connect(self._on_context_menu)
        return item_widget

    def _insert_widget_at(self, index: int, img_item, current_index: int):
        total = self.content_layout.count()
        item_widget = self._build_item_widget(index, img_item, current_index, total)
        self.content_layout.insertWidget(index, item_widget)

    def _reorder_widgets_to_match(self, target_paths):
        widget_by_path = {
            getattr(widget, "full_path", ""): widget for widget in self._item_widgets()
        }
        for index, path in enumerate(target_paths):
            widget = widget_by_path.get(path)
            if widget is None:
                return
            self.content_layout.removeWidget(widget)
            self.content_layout.insertWidget(index, widget)

    def recalculate_and_set_height(self):
        import logging

        logger = logging.getLogger("ImproveImgSLI")

        num_items = self.content_layout.count() - 1

        if num_items <= 0:
            row_h = self.item_height if self.item_height > 0 else 36
            final_height = row_h
            self._container_height = final_height
            self.setMinimumHeight(0)
            self.setMaximumHeight(final_height)
            return final_height

        row_h = self.item_height if self.item_height > 0 else 36
        spacing = self.content_layout.spacing()

        total_h = (num_items * row_h) + (max(0, num_items - 1) * spacing)

        if num_items <= 8:
            final_h = total_h + 10
            self._container_height = final_h

            self.setMinimumHeight(final_h)
            self.setMaximumHeight(final_h)

            self.scroll_area.setMinimumHeight(final_h)
            self.scroll_area.setMaximumHeight(final_h)

            self.scroll_area.setWidgetResizable(True)
            self.content_widget.setMinimumHeight(final_h)
            self.content_widget.setMaximumHeight(final_h)

            for i in range(num_items):
                layout_item = self.content_layout.itemAt(i)
                if layout_item and layout_item.widget():
                    widget = layout_item.widget()
                    widget.setFixedHeight(row_h)
                    widget.setSizePolicy(
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                    )

        else:

            visible_items = min(num_items, self.MAX_VISIBLE_ITEMS)
            max_h = (visible_items * row_h) + (max(0, visible_items - 1) * spacing)
            max_h += 10
            total_h += 8
            final_h = min(total_h, max_h)
            self._container_height = final_h
            self.setMinimumHeight(0)
            self.setMaximumHeight(final_h)
            self.scroll_area.setMinimumHeight(0)
            self.scroll_area.setMaximumHeight(final_h)

            self.scroll_area.setWidgetResizable(True)
            self.content_widget.setMinimumHeight(0)
            self.content_widget.setMaximumHeight(16777215)

            for i in range(num_items):
                layout_item = self.content_layout.itemAt(i)
                if layout_item and layout_item.widget():
                    widget = layout_item.widget()
                    widget.setMinimumHeight(0)
                    widget.setMaximumHeight(16777215)
                    widget.setSizePolicy(
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                    )

        if hasattr(self.scroll_area, "_update_scrollbar_visibility"):

            QTimer.singleShot(
                20,
                lambda: self.scroll_area._update_scrollbar_visibility(
                    min_items_count=num_items
                ),
            )

        return final_h

    def find_drop_target(self, local_pos_y: int) -> tuple[int, int]:
        count = self.content_layout.count() - 1
        if count == 0:
            return 0, 0

        for i in range(count):
            item = self.content_layout.itemAt(i)
            widget = item.widget()
            if not widget or not widget.isVisible():
                continue

            geo = widget.geometry()
            center_y = geo.center().y()

            if local_pos_y < center_y:
                return i, geo.top()

        last_item = self.content_layout.itemAt(count - 1)
        if last_item and last_item.widget():
            return count, last_item.widget().geometry().bottom()

        return count, 0

    def _should_hide_drop_indicator(self, dest_index: int) -> bool:
        try:
            service = DragAndDropService.get_instance()
        except Exception:
            return False

        if not service or not service.is_dragging():
            return False

        payload = None
        try:
            payload = (
                service.get_source_data()
                if hasattr(service, "get_source_data")
                else None
            )
        except Exception:
            payload = None
        if not payload:
            payload = getattr(service, "_source_data", None)

        if not isinstance(payload, dict):
            return False

        if payload.get("list_num") != self.image_number:
            return False

        src_index = payload.get("index")
        if not isinstance(src_index, int) or src_index < 0:
            return False

        return dest_index in (src_index, src_index + 1)

    def update_drop_indicator(self, global_pos: QPointF):
        local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())
        dest_index, indicator_y = self.find_drop_target(local_pos.y())

        if self._should_hide_drop_indicator(dest_index):
            indicator_y = -1

        if self.drop_indicator_y != indicator_y:
            self.drop_indicator_y = indicator_y
            self._show_overlay_indicator()

    def _show_overlay_indicator(self):
        if self.drop_indicator_y < 0:
            self.drop_overlay.hide()
            return

        x = 2
        width = max(4, self.content_widget.width() - 4)
        height = 3

        y = int(self.drop_indicator_y) - height // 2

        self.drop_overlay.setGeometry(x, y, width, height)
        self.drop_overlay.raise_()
        self.drop_overlay.show()

    def clear_drop_indicator(self):
        if self.drop_indicator_y != -1:
            self.drop_indicator_y = -1
            self.drop_overlay.hide()

    def handle_drop(self, payload: dict, global_pos: QPointF):
        self.clear_drop_indicator()
        source_list_num = payload.get("list_num", -1)
        source_index = payload.get("index", -1)

        local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())
        dest_index, _ = self.find_drop_target(local_pos.y())

        if source_list_num == self.image_number:
            QTimer.singleShot(
                0,
                lambda: self._on_reorder(
                    self.image_number,
                    source_index,
                    dest_index,
                ),
            )
        else:
            self._on_move_between_lists(
                source_list_num,
                source_index,
                self.image_number,
                dest_index,
            )

    def update_rating_for_item(self, index: int):
        if 0 <= index < (self.content_layout.count() - 1):
            item = self.content_layout.itemAt(index)
            if (
                item
                and item.widget()
                and hasattr(item.widget(), "_update_label_from_store")
            ):
                item.widget()._update_label_from_store()

    def _on_item_clicked(self, index):
        self._on_item_selected_cb(self.image_number, index)

    def _on_context_menu(self, index):
        self._on_item_context_menu_cb(self.image_number, index)
