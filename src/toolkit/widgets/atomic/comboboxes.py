import logging
import time

from PyQt6.QtCore import (
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPen,
    QPolygon,
    QPainter,
)
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
)

from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)

logger = logging.getLogger("ImproveImgSLI")

class ScrollableComboBox(QWidget):
    currentIndexChanged = pyqtSignal(int)
    clicked = pyqtSignal()
    wheelScrolledToIndex = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_index = -1
        self._count = 0
        self._text = ""
        self._items = []

        self._hovered = False
        self._pressed = False
        self._flyout_is_open = False
        self._flyout_open_timestamp = 0.0
        self._auto_width = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._apply_debounced_index)
        self._pending_index = -1

        self.setFixedHeight(33)
        self.setMinimumWidth(0)
        self.setProperty("class", "primary")

        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)
        self.setMouseTracking(True)

    def _style_prefix(self) -> str:
        btn_class = str(self.property("class") or "")
        return "button.primary" if "primary" in btn_class else "button.default"

    def setAutoWidthEnabled(self, enabled: bool):
        self._auto_width = bool(enabled)
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def showEvent(self, event):
        super().showEvent(event)

        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def _adjustWidthToContent(self):
        if not self._auto_width:
            return

        try:
            font = self.getItemFont()
        except Exception:
            font = self.font()
        fm = QFontMetrics(font)

        max_text_w = 0

        if self._items:
            for item_text in self._items:
                w = fm.horizontalAdvance(str(item_text))
                if w > max_text_w:
                    max_text_w = w

        current_text_w = fm.horizontalAdvance(self._text or "")
        if current_text_w > max_text_w:
            max_text_w = current_text_w

        needed = max_text_w + 60
        needed = max(80, needed)

        if self.width() != int(needed):
            logger.debug(f"ScrollableComboBox: Resizing from {self.width()} to {int(needed)}. Items: {len(self._items)}")
            self.setFixedWidth(int(needed))
            self.updateGeometry()

    def count(self):
        return self._count

    def currentIndex(self):
        return self._current_index

    def currentText(self):
        return self._text

    def setText(self, text: str):
        self._text = text
        self.update()
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def setCurrentIndex(self, index: int):
        if 0 <= index < self._count and index != self._current_index:
            self._current_index = index
            if 0 <= index < len(self._items):
                self._text = self._items[index]
            self.update()
            if self._auto_width:
                QTimer.singleShot(0, self._adjustWidthToContent)
            self.currentIndexChanged.emit(index)

    def _apply_debounced_index(self):
        if self._pending_index != -1 and self._pending_index != self.currentIndex():
            self.wheelScrolledToIndex.emit(self._pending_index)
        self._pending_index = -1

    def updateState(self, count: int, current_index: int, text: str = "", items: list = None):
        self._count = count
        self._current_index = current_index
        if text:
            self._text = text
        if items is not None:
            self._items = items[:]
        self.update()
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def addItem(self, text: str):
        self._items.append(text)
        self._count = len(self._items)
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tm = self.theme_manager
        is_dark = tm.is_dark()

        if not self.isEnabled():
            bg_color = tm.get_color("button.primary.background")
            text_color = QColor(131, 131, 131) if not is_dark else QColor(161, 161, 161)
        elif self._pressed:
            bg_color = tm.get_color("button.primary.background.pressed")
            text_color = tm.get_color("button.primary.text")
        elif self._flyout_is_open:
            bg_color = tm.get_color("button.primary.background")
            text_color = tm.get_color("button.primary.text")
        elif self._hovered:
            bg_color = tm.get_color("button.primary.background.hover")
            text_color = tm.get_color("button.primary.text")
        else:
            bg_color = tm.get_color("button.primary.background")
            text_color = tm.get_color("button.primary.text")

        rect = self.rect()
        rectf = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rectf, 6, 6)

        prefix = self._style_prefix()
        border_color = QColor(tm.get_color(f"{prefix}.border"))
        pen_border = QPen(border_color)
        pen_border.setWidthF(1.0)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, 6, 6)

        draw_bottom_underline(painter, rect, tm, UnderlineConfig(alpha=40, thickness=1.0, arc_radius=4.0))

        painter.setPen(QPen(text_color))
        font = self.getItemFont()
        painter.setFont(font)
        fm = QFontMetrics(font)

        text_rect = rect.adjusted(12, 0, -28, 0)
        elided_text = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_text)

        arrow_color = text_color
        painter.setPen(QPen(arrow_color, 1.5))
        center_x = rect.width() - 14
        center_y = rect.center().y()
        p1 = QPoint(center_x - 4, center_y - 1)
        p2 = QPoint(center_x, center_y + 2)
        p3 = QPoint(center_x + 4, center_y - 1)
        painter.drawPolyline(QPolygon([p1, p2, p3]))

    def getItemFont(self) -> QFont:
        return self.font()

    def getItemHeight(self) -> int:
        return self.height() - 2

    def enterEvent(self, event):
        self._hovered = True
        logger.debug("ScrollableComboBox: enterEvent")
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        logger.debug("ScrollableComboBox: leaveEvent")
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            logger.debug(f"ScrollableComboBox: Mouse Pressed at {event.pos()}")
            self._pressed = True

            self.setFocus()
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            logger.debug(f"ScrollableComboBox: Mouse Released. Pressed={self._pressed}")
            if self._pressed:
                self._pressed = False
                self.update()
                if self.rect().contains(event.pos()):
                    logger.debug("ScrollableComboBox: Click Validated -> Emitting clicked()")
                    self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if not self.isEnabled() or self.count() <= 1:
            event.ignore()
            return
        start_index = self._pending_index if self._debounce_timer.isActive() else self.currentIndex()
        delta = event.angleDelta().y()
        if delta > 0:
            new_index = (start_index - 1 + self.count()) % self.count()
        elif delta < 0:
            new_index = (start_index + 1) % self.count()
        else:
            return
        if new_index != start_index:
            self._pending_index = new_index
            if 0 <= new_index < len(self._items):
                self._text = self._items[new_index]
            self._debounce_timer.start()
            self.update()
            event.accept()

    def setFlyoutOpen(self, is_open: bool):
        if is_open:
            self._flyout_open_timestamp = time.time()
            logger.debug(f"ScrollableComboBox: setFlyoutOpen(True). Time: {self._flyout_open_timestamp}")
        else:
            duration = 0.0
            if self._flyout_open_timestamp > 0:
                duration = time.time() - self._flyout_open_timestamp
            logger.debug(f"ScrollableComboBox: setFlyoutOpen(False). Was open for {duration:.4f}s. isVisible={self.isVisible()}")
            self._flyout_open_timestamp = 0.0

        self._flyout_is_open = is_open
        self.update()
