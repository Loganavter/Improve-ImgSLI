from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
)

from events.drag_drop_handler import DragAndDropService
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.composite.unified_flyout.model import (
    IndexRole,
    IsCurrentRole,
    NameRole,
    PathRole,
    RatingRole,
)
from toolkit.widgets.atomic.tooltips import PathTooltip
from ui.gesture_resolver import RatingGestureTransaction
from ui.icon_manager import AppIcon, get_app_icon

class RatingDelegate(QStyledItemDelegate):

    def __init__(
        self,
        parent=None,
        theme_manager=None,
        main_controller=None,
        main_window=None,
        store=None,
        image_number: int = 1,
        item_height: int = 36,
        item_font=None,
        item_type: str = "image",
    ):
        super().__init__(parent)
        self.theme_manager = theme_manager or ThemeManager.get_instance()
        self.main_controller = main_controller
        self.main_window = main_window
        self.store = store
        self.image_number = image_number
        self.item_height = item_height
        self.item_font = item_font or QApplication.font()
        self.item_type = item_type

        self.rating_width = 25
        self.btn_size = 22
        self.spacing = 6
        self.margin = 2

        self._hovered_index = None
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(500)
        self._tooltip_timer.timeout.connect(self._show_tooltip)

        self._drag_start_pos = QPoint()
        self._drag_start_pos_global = QPointF()
        self._is_drag_initiated = False
        self._active_button = None
        self._gesture_tx = None

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.item_height)

    def paint(self, painter, option, index):

        self.initStyleOption(option, index)

        name = index.data(NameRole) or "-----"
        rating = index.data(RatingRole) or 0
        is_current = index.data(IsCurrentRole) or False
        full_path = index.data(PathRole) or ""

        r = option.rect
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        under_mouse = option.state & QStyle.StateFlag.State_MouseOver
        if is_current or under_mouse:
            bg_color = self.theme_manager.get_color("list_item.background.hover")
        else:
            bg_color = self.theme_manager.get_color("list_item.background.normal")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        background_rect = r.adjusted(self.margin, self.margin, -self.margin, -self.margin)
        painter.drawRoundedRect(background_rect, 5, 5)

        if is_current:
            indicator_pen = QPen(self.theme_manager.get_color("accent"))
            indicator_pen.setWidth(3)
            indicator_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(indicator_pen)
            y1, y2 = r.top() + 7, r.bottom() - 7
            x = r.left() + indicator_pen.width()
            painter.drawLine(x, y1, x, y2)

        if self.item_type == "image":

            rating_rect = QRect(r.left() + self.margin, r.top(), self.rating_width, r.height())
            rating_font = QFont(self.item_font)
            base_px = self.item_font.pixelSize()
            if base_px <= 0:
                base_px = QFontMetrics(self.item_font).height()
            rating_font.setPixelSize(max(8, base_px - 3))
            painter.setFont(rating_font)
            painter.setPen(self.theme_manager.get_color("list_item.text.rating"))
            painter.drawText(rating_rect, Qt.AlignmentFlag.AlignCenter, str(rating))

            separator_color = self.theme_manager.get_color("separator.color")
            painter.setPen(QPen(separator_color, 1))
            x_pos = rating_rect.right() + self.spacing // 2
            painter.drawLine(x_pos, r.top() + 6, x_pos, r.bottom() - 6)

            name_x = rating_rect.right() + self.spacing
            name_width = r.width() - name_x - (self.btn_size * 2) - (self.spacing * 2) - self.margin
            name_rect = QRect(name_x, r.top(), max(0, name_width), r.height())
            painter.setFont(self.item_font)
            painter.setPen(self.theme_manager.get_color("list_item.text.normal"))

            metrics = QFontMetrics(self.item_font)
            elided_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, name_width)
            painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_name)

            btn_y = r.top() + (r.height() - self.btn_size) // 2
            btn_minus_x = r.right() - (self.btn_size * 2) - self.spacing - self.margin
            btn_plus_x = r.right() - self.btn_size - self.margin

            icon_minus = get_app_icon(AppIcon.REMOVE)
            icon_plus = get_app_icon(AppIcon.ADD)

            icon_size = 9
            icon_rect_minus = QRect(btn_minus_x + (self.btn_size - icon_size) // 2, btn_y + (self.btn_size - icon_size) // 2, icon_size, icon_size)
            icon_rect_plus = QRect(btn_plus_x + (self.btn_size - icon_size) // 2, btn_y + (self.btn_size - icon_size) // 2, icon_size, icon_size)

            painter.drawPixmap(icon_rect_minus, icon_minus.pixmap(icon_size, icon_size))
            painter.drawPixmap(icon_rect_plus, icon_plus.pixmap(icon_size, icon_size))
        else:

            name_width = r.width() - (self.margin * 2)
            name_rect = QRect(r.left() + self.margin, r.top(), max(0, name_width), r.height())
            painter.setFont(self.item_font)
            painter.setPen(self.theme_manager.get_color("list_item.text.normal"))

            metrics = QFontMetrics(self.item_font)
            elided_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, name_width)
            painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_name)

    def editorEvent(self, event, model, option, index):
        if self.item_type != "image":
            return super().editorEvent(event, model, option, index)

        r = option.rect
        btn_y = r.top() + (r.height() - self.btn_size) // 2
        btn_minus_x = r.right() - (self.btn_size * 2) - self.spacing - self.margin
        btn_plus_x = r.right() - self.btn_size - self.margin

        btn_minus_rect = QRect(btn_minus_x, btn_y, self.btn_size, self.btn_size)
        btn_plus_rect = QRect(btn_plus_x, btn_y, self.btn_size, self.btn_size)

        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.pos()

            if btn_plus_rect.contains(click_pos):
                self._active_button = "plus"
                self._drag_start_pos = click_pos
                self._drag_start_pos_global = event.globalPosition()

                target_list = (
                    self.store.document.image_list1
                    if self.image_number == 1
                    else self.store.document.image_list2
                )
                row = index.row()
                starting_score = 0
                if 0 <= row < len(target_list):
                    starting_score = target_list[row].rating

                self._gesture_tx = RatingGestureTransaction(
                    main_controller=self.main_controller,
                    image_number=self.image_number,
                    item_index=row,
                    starting_score=starting_score,
                )
                return True

            elif btn_minus_rect.contains(click_pos):
                self._active_button = "minus"
                self._drag_start_pos = click_pos
                self._drag_start_pos_global = event.globalPosition()

                target_list = (
                    self.store.document.image_list1
                    if self.image_number == 1
                    else self.store.document.image_list2
                )
                row = index.row()
                starting_score = 0
                if 0 <= row < len(target_list):
                    starting_score = target_list[row].rating

                self._gesture_tx = RatingGestureTransaction(
                    main_controller=self.main_controller,
                    image_number=self.image_number,
                    item_index=row,
                    starting_score=starting_score,
                )
                return True

        elif event.type() == QEvent.Type.MouseMove and (event.buttons() & Qt.MouseButton.LeftButton):
            if self._active_button and not self._is_drag_initiated:
                distance = (event.globalPosition() - self._drag_start_pos_global).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    if self._gesture_tx is not None:
                        self._gesture_tx.rollback()
                        self._gesture_tx = None
                    self._active_button = None

        elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.pos()

            if btn_plus_rect.contains(click_pos) and self._active_button == "plus":
                if self._gesture_tx is not None and not self._is_drag_initiated:
                    self._gesture_tx.apply_delta(+1)
                    self._gesture_tx.commit()
                    self._gesture_tx = None
                elif not self._gesture_tx:

                    if self.main_controller and self.main_controller.session_ctrl:
                        self.main_controller.session_ctrl.increment_rating(self.image_number, index.row())
                self._update_rating_in_model(model, index)
                self._active_button = None
                return True

            elif btn_minus_rect.contains(click_pos) and self._active_button == "minus":
                if self._gesture_tx is not None and not self._is_drag_initiated:
                    self._gesture_tx.apply_delta(-1)
                    self._gesture_tx.commit()
                    self._gesture_tx = None
                elif not self._gesture_tx:

                    if self.main_controller and self.main_controller.session_ctrl:
                        self.main_controller.session_ctrl.decrement_rating(self.image_number, index.row())
                self._update_rating_in_model(model, index)
                self._active_button = None
                return True

            if self._gesture_tx is not None:
                self._gesture_tx.commit()
                self._gesture_tx = None
            self._active_button = None

        return super().editorEvent(event, model, option, index)

    def _update_rating_in_model(self, model, index):
        target_list = (
            self.store.document.image_list1
            if self.image_number == 1
            else self.store.document.image_list2
        )
        row = index.row()
        if 0 <= row < len(target_list):
            model.setRating(row, target_list[row].rating)

    def _show_tooltip(self):
        if self._hovered_index and self._hovered_index.isValid():
            full_path = self._hovered_index.data(PathRole)
            if full_path:
                view = self.parent()
                if view:
                    rect = view.visualRect(self._hovered_index)
                    global_pos = view.mapToGlobal(rect.center())
                    PathTooltip.get_instance().show_tooltip(global_pos, full_path)

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.Type.ToolTip:
            full_path = index.data(PathRole)
            if full_path:
                self._hovered_index = index
                self._tooltip_timer.start()
            else:
                self._tooltip_timer.stop()
                PathTooltip.get_instance().hide_tooltip()
            return True
        elif event.type() == QEvent.Type.Leave:
            self._tooltip_timer.stop()
            PathTooltip.get_instance().hide_tooltip()
            self._hovered_index = None
        return super().helpEvent(event, view, option, index)

    def createEditor(self, parent, option, index):
        return None

