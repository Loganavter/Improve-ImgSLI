import logging
import sys

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.constants import AppConstants
from src.shared_toolkit.ui.managers.theme_manager import ThemeManager

logger = logging.getLogger("ImproveImgSLI")

class _SimpleRow(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, index: int, text: str, is_current: bool, item_height: int, item_font: QFont, parent: QWidget = None):
        super().__init__(parent)
        self.index = index
        self.text = text
        self.is_current = is_current
        self._hovered = False
        self.theme_manager = ThemeManager.get_instance()
        self.setFixedHeight(item_height)
        self.setMouseTracking(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.label = QLabel(text)
        self.label.setFont(item_font)
        layout.addWidget(self.label)
        try:
            self.theme_manager.theme_changed.connect(self._apply_label_style)
        except Exception:
            pass
        self._apply_label_style()

    def _apply_label_style(self):
        tm = self.theme_manager
        text_color_key = "list_item.text.normal"
        font = QFont(self.label.font())
        font.setBold(False)
        self.label.setFont(font)
        self.label.setStyleSheet(f"color: {tm.get_color(text_color_key).name()}; background: transparent;")

    def enterEvent(self, e):
        self._hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit(self.index)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = self.theme_manager
        if self.is_current or self._hovered:
            bg_color = tm.get_color("list_item.background.hover")
        else:
            bg_color = tm.get_color("list_item.background.normal")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        background_rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(background_rect, 5, 5)
        if self.is_current:
            indicator_pen = QPen(tm.get_color("accent"))
            indicator_pen.setWidth(3)
            indicator_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(indicator_pen)
            y1, y2 = self.rect().top() + 7, self.rect().bottom() - 7
            x = self.rect().left() + indicator_pen.width()
            painter.drawLine(x, y1, x, y2)

class SimpleOptionsFlyout(QWidget):
    item_chosen = pyqtSignal(int)
    closed = pyqtSignal()

    SHADOW_RADIUS = 10
    MARGIN = 8
    APPEAR_EXTRA_Y = 6

    def __init__(self, app_ref):
        super().__init__(None)
        self.app_ref = app_ref
        self._theme = ThemeManager.get_instance()
        self._options: list[str] = []
        self._current_index: int = -1
        self._item_height = 36
        self._item_font = QFont(QApplication.font(self))
        self._move_duration_ms = AppConstants.FLYOUT_ANIMATION_DURATION_MS
        self._move_easing = QEasingCurve.Type.OutQuad
        self._drop_offset_px = 80
        self._anim: QPropertyAnimation | None = None

        if sys.platform in ('linux', 'darwin'):
            window_flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        else:
            window_flags = Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint

        self.setWindowFlags(window_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.container_widget = QWidget(self)
        self.container_widget.setObjectName("FlyoutWidget")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(self.SHADOW_RADIUS)
        shadow.setOffset(1, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container_widget.setGraphicsEffect(shadow)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
        self.main_layout.addWidget(self.container_widget)

        self.container_layout = QVBoxLayout(self.container_widget)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(2)

        self.content_widget = QWidget(self.container_widget)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.container_layout.addWidget(self.content_widget)

        self._apply_style()
        self._theme.theme_changed.connect(self._apply_style)
        self.hide()

    def _apply_style(self):
        tm = self._theme
        bg_color = tm.get_color("flyout.background").name(QColor.NameFormat.HexArgb)
        border_color = tm.get_color("flyout.border").name(QColor.NameFormat.HexArgb)
        self.container_widget.setStyleSheet(f"""
            QWidget#FlyoutWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

    def set_row_height(self, h: int): self._item_height = max(28, int(h))
    def set_row_font(self, f: QFont): self._item_font = QFont(f)

    def populate(self, labels: list[str], current_index: int = -1):
        self._options = list(labels)
        self._current_index = current_index if 0 <= current_index < len(self._options) else -1
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if w := item.widget():
                w.deleteLater()
            del item
        for i, text in enumerate(self._options):
            row = _SimpleRow(i, text, i == self._current_index, self._item_height, self._item_font, self.content_widget)
            row.clicked.connect(self._on_row_clicked)
            self.content_layout.addWidget(row)
        self._update_size()

    def _update_size(self):
        num = len(self._options)
        h_content = 50 if num == 0 else (num * self._item_height + max(0, num - 1) * self.content_layout.spacing())
        container_h = h_content + 8
        self.container_widget.setFixedHeight(container_h)
        width = max(self.container_widget.sizeHint().width(), 200)
        self.container_widget.setFixedWidth(width)
        self.setFixedSize(width + self.MARGIN * 2, container_h + self.MARGIN * 2)

    def show_below(self, anchor_widget: QWidget):
        if self._anim: self._anim.stop()

        anchor_width = anchor_widget.width()
        fm = QFontMetrics(self._item_font)
        max_text_width = max((fm.boundingRect(label).width() for label in self._options), default=0)

        content_width = max_text_width + 20 + 8 + 10
        desired_width = max(anchor_width, content_width, 180)

        try:
            anchor_pos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())
            anchor_center_x = anchor_widget.mapToGlobal(anchor_widget.rect().center()).x()
            if hasattr(self, 'windowHandle') and anchor_widget.windowHandle():
                self.windowHandle().setTransientParent(anchor_widget.windowHandle())
        except Exception: return

        self.container_widget.setFixedWidth(desired_width)
        self.setFixedWidth(desired_width + self.MARGIN * 2)
        self.adjustSize()

        total_width, total_height = self.width(), self.height()
        final_y = anchor_pos.y() + self.APPEAR_EXTRA_Y - self.MARGIN
        final_x = int(anchor_center_x - total_width / 2)

        try:
            screen = anchor_widget.screen() or QGuiApplication.screenAt(anchor_pos)
            avail = screen.availableGeometry()
        except Exception: avail = QGuiApplication.primaryScreen().availableGeometry()

        final_x = max(avail.left(), min(final_x, avail.right() - total_width))
        final_y = max(avail.top(), min(final_y, avail.bottom() - total_height))

        start_pos, end_pos = QPoint(final_x, final_y - self._drop_offset_px), QPoint(final_x, final_y)
        self.move(start_pos)
        self.show()

        anim_pos = QPropertyAnimation(self, b"pos", self)
        anim_pos.setDuration(self._move_duration_ms)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(end_pos)
        anim_pos.setEasingCurve(self._move_easing)

        anim_pos.finished.connect(self._on_animation_finished)
        self._anim = anim_pos
        anim_pos.start()

    def _on_animation_finished(self):
        if self._anim:

            anim_obj = self._anim
            self._anim = None
            anim_obj.deleteLater()

    def _on_row_clicked(self, idx: int):
        self.item_chosen.emit(idx)
        self.hide()

    def hideEvent(self, e):
        super().hideEvent(e)

        if self._anim:
            self._anim.stop()

        try:
            self.closed.emit()
        except Exception:
            pass
