from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QPointF, QSize, Qt, QTimer, QRect
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QWheelEvent
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from events.drag_drop_handler import DragAndDropService
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.atomic.tooltips import PathTooltip
from toolkit.widgets.list_items.rating_item import RatingListItem
from toolkit.widgets.atomic.minimalist_scrollbar import OverlayScrollArea

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

    def __init__(self, store, main_controller, main_window, image_number: int, item_height: int, item_font, parent=None):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.main_window = main_window
        self.image_number = image_number
        self.item_height = item_height
        self.item_font = item_font
        self.theme_manager = ThemeManager.get_instance()
        self.drop_indicator_y = -1
        self._container_height = 50

        self.setObjectName("UnifiedFlyoutPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.layout_outer = QVBoxLayout(self)
        self.layout_outer.setContentsMargins(0, 0, 0, 0)
        self.layout_outer.setSpacing(0)

        self.scroll_area = OverlayScrollArea(self)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_area.setWidgetResizable(True)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: transparent;")

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
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

    def clear_and_rebuild(self, image_list, owner_proxy, item_height, item_font, list_type="image", current_index=-1):
        PathTooltip.get_instance().hide_tooltip()

        self.item_height = item_height
        self.item_font = item_font

        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if current_index == -1:
            current_app_index = (
                self.store.document.current_index1 if self.image_number == 1 else self.store.document.current_index2
            )
        else:
            current_app_index = current_index

        if not image_list:
            self.recalculate_and_set_height()
            return

        for i, img_item in enumerate(image_list):
            is_current = (i == current_app_index)

            text = img_item.display_name if hasattr(img_item, 'display_name') else str(img_item)
            rating = img_item.rating if hasattr(img_item, 'rating') else 0
            full_path = img_item.path if hasattr(img_item, 'path') else ""

            item_widget = RatingListItem(
                index=i,
                text=text,
                rating=rating,
                full_path=full_path,
                store=self.store,
                main_controller=self.main_controller,
                main_window=self.main_window,
                owner_flyout=owner_proxy,
                parent=self.content_widget,
                is_current=is_current,
                item_height=self.item_height,
                item_font=self.item_font,
                item_type=list_type
            )

            item_widget.itemSelected.connect(self._on_item_clicked)
            item_widget.itemRightClicked.connect(self._on_context_menu)

            self.content_layout.insertWidget(self.content_layout.count() - 1, item_widget)

        self.recalculate_and_set_height()

        if current_app_index >= 0:
            QTimer.singleShot(0, lambda: self._ensure_visible(current_app_index))

    def _ensure_visible(self, index):
        if 0 <= index < (self.content_layout.count() - 1):
            item = self.content_layout.itemAt(index)
            if item and item.widget():
                self.scroll_area.ensureWidgetVisible(item.widget())

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
            final_h = total_h + 4
            self._container_height = final_h

            self.setMinimumHeight(final_h)
            self.setMaximumHeight(final_h)

            self.scroll_area.setMinimumHeight(final_h)
            self.scroll_area.setMaximumHeight(final_h)

            self.scroll_area.setWidgetResizable(True)
            self.content_widget.setMinimumHeight(total_h)
            self.content_widget.setMaximumHeight(total_h)

            for i in range(num_items):
                layout_item = self.content_layout.itemAt(i)
                if layout_item and layout_item.widget():
                    widget = layout_item.widget()
                    widget.setFixedHeight(row_h)
                    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        else:

            visible_items = min(num_items, self.MAX_VISIBLE_ITEMS)
            max_h = (visible_items * row_h) + (max(0, visible_items - 1) * spacing)
            max_h += 4
            total_h += 4
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
                    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if hasattr(self.scroll_area, '_update_scrollbar_visibility'):

            QTimer.singleShot(20, lambda: self.scroll_area._update_scrollbar_visibility(min_items_count=num_items))

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
            payload = service.get_source_data() if hasattr(service, "get_source_data") else None
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
                lambda: self.main_controller.session_ctrl.reorder_item_in_list(
                    image_number=self.image_number,
                    source_index=source_index,
                    dest_index=dest_index,
                ) if self.main_controller and self.main_controller.session_ctrl else None,
            )
        else:
            if self.main_controller and self.main_controller.session_ctrl:
                self.main_controller.session_ctrl.move_item_between_lists(
                    source_list_num=source_list_num,
                    source_index=source_index,
                    dest_list_num=self.image_number,
                    dest_index=dest_index,
                )

    def update_rating_for_item(self, index: int):
        if 0 <= index < (self.content_layout.count() - 1):
            item = self.content_layout.itemAt(index)
            if item and item.widget() and hasattr(item.widget(), '_update_label_from_store'):
                item.widget()._update_label_from_store()

    def _on_item_clicked(self, index):
        uf = self.main_window.presenter.ui_manager.unified_flyout
        uf._on_item_selected(self.image_number, index)

    def _on_context_menu(self, index):
        uf = self.main_window.presenter.ui_manager.unified_flyout
        uf._on_item_right_clicked(self.image_number, index)
