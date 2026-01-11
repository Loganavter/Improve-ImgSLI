import sys
import time
import logging

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
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.constants import AppConstants
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.composite.base_flyout import BaseFlyout

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
        self.label.setProperty("class", "option-label")

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

class SimpleOptionsFlyout(BaseFlyout):
    item_chosen = pyqtSignal(int)
    closed = pyqtSignal()

    MARGIN = 8
    APPEAR_EXTRA_Y = 6

    def __init__(self, parent_widget=None):

        super().__init__(parent_widget)
        self.parent_widget = parent_widget
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

        self._main_layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)

        self.content_layout.setSpacing(2)

        self.hide()

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
            row = _SimpleRow(i, text, i == self._current_index, self._item_height, self._item_font, self.container)
            row.clicked.connect(self._on_row_clicked)
            self.content_layout.addWidget(row)

        self._update_size()

    def _update_size(self, match_width: int = 0, exact_match: bool = False):
        num = len(self._options)

        h_content = 50 if num == 0 else (num * self._item_height + max(0, num - 1) * self.content_layout.spacing())
        container_h = h_content + 8

        fm = QFontMetrics(self._item_font)
        max_text_width = 0
        for text in self._options:

            w = fm.horizontalAdvance(text)
            if w > max_text_width:
                max_text_width = w

        final_w = max_text_width + 50

        if exact_match and match_width > 0:

            target_total_width = match_width

            target_container_width = target_total_width - (self.MARGIN * 2) + 17

            if final_w > target_container_width:

                width = final_w
                logger.debug(f"SimpleOptionsFlyout._update_size: Content requires {final_w}px > container {target_container_width}px, "
                           f"using content width (flyout will be wider than button)")
            else:

                width = target_container_width

            actual_total_width = width + self.MARGIN * 2

            if final_w <= target_container_width and actual_total_width != target_total_width:
                logger.warning(f"SimpleOptionsFlyout._update_size: Width mismatch! "
                             f"Expected={target_total_width}, Actual={actual_total_width}, "
                             f"container_width={width}, MARGIN={self.MARGIN}")

            logger.debug(f"SimpleOptionsFlyout._update_size: exact_match=True, match_width={match_width}, "
                        f"target_container_width={target_container_width}, final_w={final_w}, "
                        f"resulting width={width}, total will be={actual_total_width} "
                        f"(target was {target_total_width}, diff={actual_total_width - target_total_width})")
        elif match_width > 0:

            target_container_width = match_width - (self.MARGIN * 2)
            min_container_width = max(180, target_container_width)
            width = max(final_w, min_container_width)
        else:

            width = max(final_w, 180)

        self.container.setFixedSize(width, container_h)
        total_width = width + self.MARGIN * 2

        self.setFixedSize(total_width, container_h + self.MARGIN * 2)

        if exact_match and match_width > 0:
            actual_width = self.width()

            expected_min_width = match_width
            if actual_width < expected_min_width:
                logger.warning(f"SimpleOptionsFlyout._update_size: Width mismatch! "
                             f"Expected min={expected_min_width}, Actual={actual_width}, "
                             f"container_width={width}, total_calculated={total_width}")
            else:
                logger.debug(f"SimpleOptionsFlyout._update_size: Width OK. "
                           f"Expected min={expected_min_width}, Actual={actual_width}, "
                           f"container_width={width}, total_calculated={total_width}")

    def show_below(self, anchor_widget: QWidget, exact_width_match: bool = True):
        self.flyout_manager.request_show(self)

        if self._anim:
            self._anim.stop()
            self._anim = None

        anchor_width = anchor_widget.frameGeometry().width()
        if anchor_width <= 0:

            anchor_width = anchor_widget.geometry().width()
        if anchor_width <= 0:

            anchor_width = anchor_widget.width()

        logger.debug(f"SimpleOptionsFlyout.show_below: anchor_width={anchor_width} "
                    f"(frame={anchor_widget.frameGeometry().width()}, "
                    f"geometry={anchor_widget.geometry().width()}, "
                    f"width={anchor_widget.width()}), exact_width_match={exact_width_match}")

        self._just_opened = True
        self._open_timestamp = time.monotonic()

        self._update_size(match_width=anchor_width, exact_match=exact_width_match)

        anchor_pos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())
        anchor_center_x = anchor_widget.mapToGlobal(anchor_widget.rect().center()).x()

        try:
            if self.windowHandle():
                anchor_window = anchor_widget.window()
                if anchor_window and anchor_window.windowHandle():
                    self.windowHandle().setTransientParent(anchor_window.windowHandle())
        except Exception as e:
            logger.debug(f"SimpleOptionsFlyout: Failed to set transient parent: {e}")

        total_width, total_height = self.width(), self.height()
        final_y = anchor_pos.y() + self.APPEAR_EXTRA_Y - self.MARGIN

        final_x = int(anchor_center_x - total_width / 2) + 2

        try:
            screen = anchor_widget.screen() or QGuiApplication.screenAt(anchor_pos)
            avail = screen.availableGeometry()
        except Exception:
            avail = QGuiApplication.primaryScreen().availableGeometry()

        final_x = max(avail.left(), min(final_x, avail.right() - total_width))
        final_y = max(avail.top(), min(final_y, avail.bottom() - total_height))

        start_pos, end_pos = QPoint(final_x, final_y - self._drop_offset_px), QPoint(final_x, final_y)

        self.move(start_pos)

        if sys.platform not in ('linux', 'darwin'):
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.setVisible(True)
        self.raise_()

        if not self.isVisible():
            logger.warning("SimpleOptionsFlyout: Widget failed to become visible after show()")

            self.show()

        QApplication.processEvents()

        if exact_width_match:
            actual_width_after = self.width()
            if actual_width_after != total_width:
                logger.warning(f"SimpleOptionsFlyout.show_below: Width changed after processEvents! "
                             f"Before={total_width}, After={actual_width_after}, anchor_width={anchor_width}")

                self.setFixedSize(total_width, total_height)

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

        if hasattr(self, '_just_opened'):
            self._just_opened = False
        self.hide()

    def hide(self):

        if hasattr(self, '_just_opened') and getattr(self, '_just_opened', False):
            time_since_open = time.monotonic() - getattr(self, '_open_timestamp', 0)
            logger.debug(f"SimpleOptionsFlyout.hide() called {time_since_open:.3f}s after opening (just_opened={self._just_opened})")
        super().hide()

    def hideEvent(self, e):

        if hasattr(self, '_just_opened') and getattr(self, '_just_opened', False):
            time_since_open = time.monotonic() - getattr(self, '_open_timestamp', 0)

            if time_since_open < 0.3:
                logger.debug(f"SimpleOptionsFlyout.hideEvent: Ignoring hide event - just opened {time_since_open:.3f}s ago")
                e.ignore()
                return

            self._just_opened = False

        super().hideEvent(e)

        if self._anim:
            self._anim.stop()
            self._anim = None

        if hasattr(self, '_just_opened'):
            self._just_opened = False

        try:
            self.closed.emit()
        except Exception:
            pass
