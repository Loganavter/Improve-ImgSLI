from PyQt6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QCursor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from sli_ui_toolkit.config import get_dragdrop_service
from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import AutoRepeatButton
from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip

DEFAULT_MINUS_ICON = "remove"
DEFAULT_PLUS_ICON = "add"

class RatingListItem(QWidget):
    itemSelected = pyqtSignal(int)
    itemRightClicked = pyqtSignal(int)

    def __init__(
        self,
        index,
        text,
        rating,
        full_path: str,
        image_number: int,
        get_rating,
        increment_rating,
        decrement_rating,
        create_rating_gesture,
        on_update_drop_indicator,
        on_clear_drop_indicator,
        parent,
        is_current: bool = False,
        item_height: int = 36,
        item_font: QFont = None,
        item_type="image",
        position="middle",
    ):
        super().__init__(parent=parent)
        self.index = index
        self.full_path = full_path
        self.image_number = image_number
        self._get_rating = get_rating
        self._increment_rating = increment_rating
        self._decrement_rating = decrement_rating
        self._create_rating_gesture = create_rating_gesture
        self._on_update_drop_indicator = on_update_drop_indicator
        self._on_clear_drop_indicator = on_clear_drop_indicator
        self.is_current = is_current
        self.item_type = item_type
        self.position = position

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update_styles)

        self.drag_start_pos = QPoint()
        self._drag_start_pos_global = QPointF()
        self._is_being_dragged = False

        self.tooltip_timer = QTimer(self)
        self.tooltip_timer.setSingleShot(True)
        self.tooltip_timer.setInterval(500)
        self.tooltip_timer.timeout.connect(self._show_tooltip)

        self.layout = QHBoxLayout(self)

        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(6)

        if self.item_type == "image":
            self.rating_label = QLabel(str(rating), self)
            self.rating_label.setFixedWidth(25)
            self.rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rating_label.setObjectName("ratingLabel")

        self.name_label = QLabel(text, self)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setMinimumWidth(0)
        self.name_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )

        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        base_font = item_font if item_font else QApplication.font(self)
        self.name_label.setFont(base_font)

        if self.item_type == "image":

            base_px = base_font.pixelSize()
            if base_px <= 0:
                base_px = QFontMetrics(base_font).height()
            rating_font = QFont(base_font)
            rating_font.setPixelSize(max(8, base_px - 3))
            self.rating_label.setFont(rating_font)

            self.btn_minus = AutoRepeatButton(resolve_icon(DEFAULT_MINUS_ICON), parent=self)
            self.btn_plus = AutoRepeatButton(resolve_icon(DEFAULT_PLUS_ICON), parent=self)
            self.btn_minus.setObjectName("minusButton")
            self.btn_plus.setObjectName("plusButton")
            for btn in [self.btn_minus, self.btn_plus]:
                btn.setFixedSize(22, 22)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            self.layout.addWidget(self.rating_label)
            self.layout.addWidget(self.name_label, 1)
            self.layout.addWidget(self.btn_minus)
            self.layout.addWidget(self.btn_plus)

            self.btn_plus.clicked.connect(self._on_plus_clicked)
            self.btn_minus.clicked.connect(self._on_minus_clicked)
            self.btn_plus.pressed.connect(lambda: self._on_button_pressed(self.btn_plus))
            self.btn_minus.pressed.connect(lambda: self._on_button_pressed(self.btn_minus))
            self.btn_plus.released.connect(
                lambda: self._on_button_released(self.btn_plus)
            )
            self.btn_minus.released.connect(
                lambda: self._on_button_released(self.btn_minus)
            )
            self._gesture_tx = None
            self._active_button = None
            self._is_drag_initiated = False
            self.btn_plus.installEventFilter(self)
            self.btn_minus.installEventFilter(self)
        else:
            self.layout.addWidget(self.name_label, 1)

        self.update_styles()

    def set_dragging_state(self, is_dragging: bool):
        if self._is_being_dragged != is_dragging:
            self._is_being_dragged = is_dragging
            self.update()

    def eventFilter(self, obj, event):
        if self.item_type != "image":
            return super().eventFilter(obj, event)

        if obj in (self.btn_plus, self.btn_minus):
            if event.type() == QEvent.Type.MouseMove and (
                event.buttons() & Qt.MouseButton.LeftButton
            ):
                if self._active_button is obj and not self._is_drag_initiated:
                    try:
                        obj._initial_delay_timer.stop()
                        obj._repeat_timer.stop()
                    except Exception:
                        pass
                    distance = (
                        event.globalPosition() - self._drag_start_pos_global
                    ).manhattanLength()
                    if distance >= QApplication.startDragDistance():
                        self._cancel_button_interaction()

                return True

        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if self.item_type != "image":
            return

        pos = event.position().toPoint()

        if self.rating_label.geometry().contains(pos):
            delta = event.angleDelta().y()
            if delta > 0:
                self._increment_rating(self.image_number, self.index)
            else:
                self._decrement_rating(self.image_number, self.index)
            self._update_label_from_store()
            event.accept()
        else:

            event.ignore()

    def update_styles(self):
        if self.item_type == "image":
            self.btn_minus.setIcon(resolve_icon(DEFAULT_MINUS_ICON))
            self.btn_plus.setIcon(resolve_icon(DEFAULT_PLUS_ICON))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = self.theme_manager

        if self._is_being_dragged:
            painter.setOpacity(0.35)

        under_mouse = self.underMouse()

        if self.is_current or under_mouse:
            bg_color = tm.get_color("list_item.background.hover")
        else:
            bg_color = tm.get_color("list_item.background.normal")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        background_rect = self.rect().adjusted(2, 2, -2, -2)

        inner_r = 5
        outer_r = 8
        pos = self.position
        if pos == "middle":
            painter.drawRoundedRect(background_rect, inner_r, inner_r)
        else:
            r = background_rect
            path = QPainterPath()
            tl = outer_r if pos in ("first", "only") else inner_r
            tr = outer_r if pos in ("first", "only") else inner_r
            bl = outer_r if pos in ("last", "only") else inner_r
            br = outer_r if pos in ("last", "only") else inner_r
            path.moveTo(r.left() + tl, r.top())
            path.lineTo(r.right() - tr, r.top())
            path.arcTo(r.right() - 2 * tr, r.top(), 2 * tr, 2 * tr, 90, -90)
            path.lineTo(r.right(), r.bottom() - br)
            path.arcTo(r.right() - 2 * br, r.bottom() - 2 * br, 2 * br, 2 * br, 0, -90)
            path.lineTo(r.left() + bl, r.bottom())
            path.arcTo(r.left(), r.bottom() - 2 * bl, 2 * bl, 2 * bl, -90, -90)
            path.lineTo(r.left(), r.top() + tl)
            path.arcTo(r.left(), r.top(), 2 * tl, 2 * tl, 180, -90)
            path.closeSubpath()
            painter.drawPath(path)

        if self.is_current:
            indicator_pen = QPen(tm.get_color("accent"))
            indicator_pen.setWidth(3)
            indicator_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(indicator_pen)
            y1, y2 = self.rect().top() + 7, self.rect().bottom() - 7
            x = self.rect().left() + indicator_pen.width()
            painter.drawLine(x, y1, x, y2)

        if self.item_type == "image":
            separator_color = tm.get_color("separator.color")
            painter.setPen(QPen(separator_color, 1))
            x_pos = self.rating_label.geometry().right() + self.layout.spacing() // 2
            painter.drawLine(x_pos, 6, x_pos, self.height() - 6)

        if self._is_being_dragged:
            painter.setOpacity(1.0)

    def enterEvent(self, event):
        if self.full_path:
            self.tooltip_timer.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        self.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()

        if event.button() == Qt.MouseButton.LeftButton:
            if self.item_type == "image":
                child = self.childAt(event.pos())
                if child is not self.btn_plus and child is not self.btn_minus:
                    self.drag_start_pos = event.pos()
                    self._drag_start_pos_global = event.globalPosition()
            else:
                self.drag_start_pos = event.pos()
                self._drag_start_pos_global = event.globalPosition()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        if self._is_drag_initiated:
            return

        if self.item_type == "image":

            child = self.childAt(event.pos())
            if child is self.btn_plus or child is self.btn_minus:
                event.accept()
                return

        current_global_pos = self.mapToGlobal(event.pos())
        start_global_pos = self.mapToGlobal(self.drag_start_pos)
        distance = (current_global_pos - start_global_pos).manhattanLength()

        if distance >= QApplication.startDragDistance():

            if self.item_type == "image" and self._active_button:
                try:
                    self._active_button._initial_delay_timer.stop()
                    self._active_button._repeat_timer.stop()
                except Exception:
                    pass
                if self._gesture_tx is not None:
                    self._gesture_tx.rollback()
                    self._gesture_tx = None

            self.tooltip_timer.stop()
            PathTooltip.get_instance().hide_tooltip()

            self._is_drag_initiated = True
            service = get_dragdrop_service()
            if service is not None and not service.is_dragging():
                service.start_drag(self, event)
            self._notify_flyout_drop_indicator(event.globalPosition())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._is_drag_initiated:
            if self.rect().contains(event.pos()):
                if event.button() == Qt.MouseButton.LeftButton:
                    should_select = True
                    if self.item_type == "image":

                        child = self.childAt(event.pos())
                        if child is self.btn_plus or child is self.btn_minus:
                            should_select = False
                        else:

                            is_on_plus = self.btn_plus.geometry().contains(event.pos())
                            is_on_minus = self.btn_minus.geometry().contains(
                                event.pos()
                            )
                            if is_on_plus or is_on_minus:
                                should_select = False

                    if should_select:
                        self.itemSelected.emit(self.index)
                elif event.button() == Qt.MouseButton.RightButton:
                    self.itemRightClicked.emit(self.index)

        if (
            self.item_type == "image"
            and self._gesture_tx is not None
            and self._active_button is None
        ):
            self._gesture_tx.commit()
            self._gesture_tx = None
            self._update_label_from_store()

        self._is_drag_initiated = False
        self._active_button = None
        self._notify_flyout_clear_indicator()
        super().mouseReleaseEvent(event)

    def _on_plus_clicked(self):
        if self._is_drag_initiated or self._active_button not in (None, self.btn_plus):
            return
        if self._gesture_tx is not None:
            self._gesture_tx.apply_delta(+1)
        else:
            self._increment_rating(self.image_number, self.index)
        self._update_label_from_store()

    def _on_minus_clicked(self):
        if self._is_drag_initiated or self._active_button not in (None, self.btn_minus):
            return
        if self._gesture_tx is not None:
            self._gesture_tx.apply_delta(-1)
        else:
            self._decrement_rating(self.image_number, self.index)
        self._update_label_from_store()

    def _on_button_pressed(self, button):
        if self.item_type != "image":
            return
        self._active_button = button
        self._drag_start_pos_global = QPointF(QCursor.pos())
        self.drag_start_pos = self.mapFromGlobal(QCursor.pos())
        starting_score = self._get_rating(self.image_number, self.index)
        self._gesture_tx = self._create_rating_gesture(
            self.image_number,
            self.index,
            starting_score,
        )

    def _on_button_released(self, button):
        if self._active_button is not button:
            return
        if self._gesture_tx is not None and not self._is_drag_initiated:
            self._gesture_tx.commit()
            self._gesture_tx = None
            self._update_label_from_store()
        self._active_button = None

    def _cancel_button_interaction(self):
        if self._gesture_tx is not None:
            self._gesture_tx.rollback()
            self._gesture_tx = None
        self._active_button = None

    def _update_label_from_store(self):
        if self.item_type != "image":
            return
        self.rating_label.setText(str(self._get_rating(self.image_number, self.index)))

    def _show_tooltip(self):
        if self.full_path:
            PathTooltip.get_instance().show_tooltip(
                QCursor.pos(), self.full_path
            )

    def _notify_flyout_drop_indicator(self, global_pos):
        self._on_update_drop_indicator(global_pos)

    def _notify_flyout_clear_indicator(self):
        self._on_clear_drop_indicator()
