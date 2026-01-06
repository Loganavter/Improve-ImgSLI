from PyQt6.QtCore import QRect, QRectF, QSize, Qt, QTimer, QPoint, QPointF
import time
import logging
import traceback
from typing import List
from PyQt6.QtGui import QColor, QGuiApplication, QPainterPath, QRegion, QPainter, QPen, QBrush, QFont, QFontMetrics, QPolygon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QListView,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from core.layout_cache import LayoutCache

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S.%f'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def _debug_log(msg: str, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

class ComboBoxItemDelegate(QStyledItemDelegate):
    def __init__(self, tm: ThemeManager):
        super().__init__()
        self._tm = tm
        self._border_radius = 7

    def paint(self, painter, option, index):

        is_dark = self._tm.is_dark()

        original_state = option.state
        hover_bg = self._tm.get_color("list_item.background.hover")
        selected_bg = self._tm.get_color("list_item.background.hover")

        is_hover = option.state & QStyle.StateFlag.State_MouseOver
        is_selected = option.state & QStyle.StateFlag.State_Selected

        if is_hover or is_selected:

            rect = QRectF(option.rect.adjusted(1, 1, -1, -1))
            path = QPainterPath()
            path.addRoundedRect(rect, self._border_radius - 1, self._border_radius - 1)

            painter.setRenderHint(painter.RenderHint.Antialiasing)
            painter.fillPath(path, hover_bg if is_hover else selected_bg)

            if is_selected:
                option.state &= ~QStyle.StateFlag.State_Selected

        super().paint(painter, option, index)

        option.state = original_state

class _ComboPopupFlyout(QWidget):
    def __init__(self, tm: ThemeManager, parent=None):
        super().__init__(parent)
        self._tm = tm
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.container = QWidget(self)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 100))

        self._shadow.setEnabled(False)
        self.container.setGraphicsEffect(self._shadow)

        self._outer_margin = 0
        self._content_layout = QVBoxLayout(self)
        self._content_layout.setContentsMargins(self._outer_margin, self._outer_margin, self._outer_margin, self._outer_margin)
        self._content_layout.setSpacing(0)
        self._content_layout.addWidget(self.container)

        self._container_layout = QVBoxLayout(self.container)

        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(0)

        self.view = QListView(self.container)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setFrameShadow(QFrame.Shadow.Plain)
        self.view.setMouseTracking(True)

        self.view.setViewMode(QListView.ViewMode.ListMode)
        self.view.setFlow(QListView.Flow.TopToBottom)
        self.view.setWrapping(False)
        self.view.setUniformItemSizes(True)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setSpacing(0)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.view.setViewportMargins(0, 0, 0, 0)
        self.view.setContentsMargins(0, 0, 0, 0)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionRectVisible(False)
        self.view.setWordWrap(False)
        self.view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.view.setAlternatingRowColors(False)

        self.view.setItemDelegate(ComboBoxItemDelegate(self._tm))
        self.scroll_area = OverlayScrollArea(self.container)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_area.setWidgetResizable(True)

        self.scroll_area.setViewportMargins(0, 0, 0, 0)
        self.scroll_area.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.view)
        self._container_layout.addWidget(self.scroll_area)

        self._apply_style()

        self._on_close = None
        self._signals_connected = False
        self._current_combo = None
        self._ignore_clicks_until = 0

    def _apply_style(self):

        bg_color = self._tm.get_color("flyout.background").name(QColor.NameFormat.HexArgb)
        border_color = self._tm.get_color("flyout.border").name(QColor.NameFormat.HexArgb)
        self.container.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

        is_dark = self._tm.is_dark()
        text_color = self._tm.get_color("dialog.text").name(QColor.NameFormat.HexArgb)
        accent = self._tm.get_color("accent")
        selected_bg_str = accent.name(QColor.NameFormat.HexArgb)
        selected_text = "#FFFFFFFF" if is_dark else self._tm.get_color("dialog.text").name(QColor.NameFormat.HexArgb)

        self.view.setStyleSheet(
            "QListView {"
            "  background: transparent;"
            "  border: none;"
            f"  color: {text_color};"
            "  padding: 0px; show-decoration-selected: 1;"
            "  outline: 0;"
            "}"
            "QListView::viewport { background: transparent; }"
            "QListView::item {"
            "  padding: 6px 12px;"
            "  margin: 0px;"
            "  min-height: 28px;"
            "  text-align: center;"
            "}"
            f"QListView::item:selected {{ background-color: transparent; color: {selected_text}; }}"
        )

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _update_clip_mask(self):
        try:
            r = self.container.rect()
            if not r.isEmpty():
                path = QPainterPath()
                path.addRoundedRect(r.adjusted(1, 1, -1, -1), 7, 7)
                region = QRegion(path.toFillPolygon().toPolygon())

                self.view.viewport().setMask(region)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self._update_clip_mask()
        except Exception:
            pass

    def set_on_close(self, cb):
        self._on_close = cb

    def closeEvent(self, event):
        super().closeEvent(event)
        if callable(self._on_close):
            try:
                self._on_close()
            except Exception:
                pass

    def show_for_combo(self, combo: 'FluentComboBox'):

        self._current_combo = combo
        self.view.setModel(combo.model())
        try:
            current = combo.currentIndex()
            if current >= 0:

                self.view.setCurrentIndex(combo.model().index(current, 0))

                self.view.clearSelection()
        except Exception:
            pass

        if not self._signals_connected:
            try:
                self.view.clicked.connect(self._on_item_clicked_proxy)
                self.view.activated.connect(self._on_item_clicked_proxy)
                self._signals_connected = True
            except Exception:
                pass

        try:
            hint_row_h = self.view.sizeHintForRow(0)
            row_h = hint_row_h if (combo.count() > 0 and hint_row_h > 0) else 28
        except Exception:
            row_h = 28
        max_visible = min(12, max(5, combo.maxVisibleItems()))
        target_rows = min(combo.count(), max_visible)
        target_content_h = max(28, row_h) * target_rows

        container_h = target_content_h
        self.container.setFixedHeight(container_h)

        try:
            total_content_h = max(28, row_h) * combo.count()
        except Exception:
            total_content_h = max(28, row_h)
        self.view.setMinimumHeight(total_content_h)

        target_w = combo.width()
        self.container.setFixedWidth(target_w)
        self.setFixedSize(QSize(target_w + self._outer_margin * 2, container_h + self._outer_margin * 2))

        try:
            self._update_clip_mask()
        except Exception:
            pass

        try:
            self.scroll_area._update_scrollbar_visibility()
        except Exception:
            pass

        combo_rect = combo.rect()
        anchor_center = combo.mapToGlobal(combo_rect.center())

        screen = QGuiApplication.screenAt(anchor_center) or QApplication.primaryScreen()
        avail = (screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry())

        current_index = current if current >= 0 else 0

        if combo.count() > max_visible:

            ideal_y = int(anchor_center.y() - self.height() / 2)
        else:

            selected_item_offset_y = current_index * row_h
            ideal_y = int(anchor_center.y() - selected_item_offset_y - row_h / 2)

        ideal_x = int(combo.mapToGlobal(combo_rect.topLeft()).x())

        final_x = max(avail.left(), min(ideal_x, avail.right() - self.width()))

        if combo.count() <= max_visible:

            final_y = min(ideal_y, avail.bottom() - self.height())
        else:
            final_y = max(avail.top(), min(ideal_y, avail.bottom() - self.height()))

        end_rect = QRect(final_x, final_y, self.width(), self.height())

        self._ignore_clicks_until = time.time() + 0.15

        self.show()
        self.raise_()
        self.setGeometry(end_rect)

        if combo.count() > max_visible and current_index >= 0:
            try:

                scrollbar = self.scroll_area.verticalScrollBar()
                visible_height = self.scroll_area.height()
                target_value = current_index * row_h - visible_height // 2 + row_h // 2
                target_value = max(0, min(target_value, scrollbar.maximum()))
                scrollbar.setValue(target_value)
            except Exception:
                pass

        try:
            self.scroll_area._position_scrollbar()
            self.scroll_area._update_scrollbar_visibility()
        except Exception:
            pass

    def keyPressEvent(self, event):

        if event.key() == Qt.Key.Key_Escape:

            QTimer.singleShot(0, self.hide)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self.view.currentIndex()
            if idx.isValid():
                self._on_item_clicked_proxy(idx)
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_item_clicked_proxy(self, idx):

        if time.time() < self._ignore_clicks_until:
            return

        try:
            if self._current_combo is not None:
                self._current_combo.setCurrentIndex(idx.row())
        except Exception:
            pass

        QTimer.singleShot(0, self.hide)

class FluentComboBox(QComboBox):

    PADDING_LEFT = 15
    PADDING_RIGHT = 12
    BORDER_RADIUS = 6

    def __init__(self, parent=None, auto_resize_width: bool = True):
        super().__init__(parent)
        self._auto_resize_width = auto_resize_width
        self._fixed_width_cache = None
        self._theme = ThemeManager.get_instance()
        self._flyout = None

        view = QListView(self)
        view.setMouseTracking(True)
        view.setUniformItemSizes(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setView(view)

        self.setMaxVisibleItems(12)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.setEditable(False)

        if self._auto_resize_width:
            size_policy = self.sizePolicy()
            size_policy.setHorizontalPolicy(QSizePolicy.Policy.Minimum)
            self.setSizePolicy(size_policy)

        self._theme.theme_changed.connect(self.update)

    def sizeHint(self) -> QSize:
        if self._fixed_width_cache is not None:
            return QSize(self._fixed_width_cache, super().sizeHint().height())

        if self._auto_resize_width:
            fm = self.fontMetrics()
            max_text_w = 0

            count = self.count()
            if count > 0:
                for i in range(count):
                    w = fm.horizontalAdvance(self.itemText(i))
                    if w > max_text_w:
                        max_text_w = w
            else:
                max_text_w = fm.horizontalAdvance(self.currentText())

            content_width = (
                self.PADDING_LEFT +
                max_text_w +
                self.PADDING_RIGHT
            )

            buffer = 10
            final_w = max(content_width + buffer, 40)

            height = max(33, fm.height() + 14)

            return QSize(final_w, height)

        return super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        rectf = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)

        is_dark = self._theme.is_dark()
        bg_color = self._theme.get_color("dialog.input.background")
        border_color = self._theme.get_color("dialog.border")
        text_color = self._theme.get_color("dialog.text")
        accent_color = self._theme.get_color("accent")

        if not self.isEnabled():
            bg_color = self._theme.get_color("Window")
            text_color.setAlpha(100)
            border_color.setAlpha(100)
        elif self.property("flyoutOpen") is True:

            border_color = accent_color
        elif self.hasFocus():
            border_color = accent_color
        elif self.underMouse():

            border_color = self._tint_color(border_color, is_dark)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rectf, self.BORDER_RADIUS, self.BORDER_RADIUS)

        pen_border = QPen(border_color)
        pen_border.setWidthF(1.0)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, self.BORDER_RADIUS, self.BORDER_RADIUS)

        current_text = self.currentText()
        if current_text:
            painter.setPen(QPen(text_color))
            font = self.font()
            painter.setFont(font)
            fm = QFontMetrics(font)

            text_rect = QRect(
                rect.left() + self.PADDING_LEFT,
                rect.top(),
                rect.width() - self.PADDING_LEFT - self.PADDING_RIGHT,
                rect.height()
            )

            elided_text = fm.elidedText(current_text, Qt.TextElideMode.ElideRight, text_rect.width())

            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_text)

        painter.end()

    @staticmethod
    def _tint_color(color: QColor, is_dark: bool) -> QColor:
        new_c = QColor(color)
        if is_dark:
            new_c = new_c.lighter(120)
        else:
            new_c = new_c.darker(110)
        return new_c

    def _update_minimum_width(self):
        if not self._auto_resize_width:
            return
        sh = self.sizeHint()
        if self.minimumWidth() != sh.width():
            self.setMinimumWidth(sh.width())

    def showPopup(self):
        if self._flyout is None:

            self._flyout = _ComboPopupFlyout(self._theme)
            self._theme.theme_changed.connect(self._flyout._apply_style)
            self._flyout.set_on_close(lambda: (self.setProperty("flyoutOpen", False), self.update()))

        self.setProperty("flyoutOpen", True)
        self.update()

        self._flyout.view.setFont(self.font())
        QTimer.singleShot(0, lambda: self._flyout.show_for_combo(self))

    def hidePopup(self):
        if self._flyout and self._flyout.isVisible():
            QTimer.singleShot(0, self._flyout.hide)
        self.setProperty("flyoutOpen", False)
        self.update()

    def addItem(self, text: str, userData=None):
        super().addItem(text, userData)
        if self._auto_resize_width:
            self._update_minimum_width()

    def addItems(self, texts: List[str]):
        super().addItems(texts)
        if self._auto_resize_width:
            self._update_minimum_width()

    def setModel(self, model):
        super().setModel(model)
        if self._auto_resize_width:
            QTimer.singleShot(0, self._update_minimum_width)

    def showEvent(self, event):
        if self._auto_resize_width:
            self._update_minimum_width()
        super().showEvent(event)

    def setText(self, text: str):

        pass

    def setPrecomputedLayoutKey(self, key: str, current_language: str = "en"):

        width = LayoutCache.get_instance().get_fixed_width(key, current_language)

        if width:
            self._auto_resize_width = False
            self._fixed_width_cache = int(width)

            self.setFixedWidth(width)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            self.updateGeometry()
        else:
            self._auto_resize_width = True
            self._fixed_width_cache = None

            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
