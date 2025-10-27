from PyQt6.QtCore import QRect, QRectF, QSize, Qt, QTimer
import time
from PyQt6.QtGui import QColor, QGuiApplication, QPainterPath, QRegion
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea

class ComboBoxItemDelegate(QStyledItemDelegate):
    """Custom delegate to paint item backgrounds with rounded corners clipping."""
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
    """Lightweight flyout popup with animated expand, themed via ThemeManager."""
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
            "  padding: 6px 10px;"
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
        """Clip children (hover/selection) to rounded corners of the container."""
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
    """
    A QFluent-like ComboBox with:
    - Themed popup list (flyout-like) using ThemeManager palette
    - Geometry expand animation (no windowOpacity; compatible with plugins)
    - Rounded corners and consistent padding
    Designed to drop-in replace QComboBox in dialogs/settings.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = ThemeManager.get_instance()
        self._open_anim = None
        self._fade_anim = None

        view = QListView(self)
        view.setMouseTracking(True)

        view.setViewMode(QListView.ViewMode.ListMode)
        view.setFlow(QListView.Flow.TopToBottom)
        view.setWrapping(False)
        view.setUniformItemSizes(True)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setSpacing(0)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setSelectionRectVisible(False)
        view.setWordWrap(False)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        view.setAlternatingRowColors(False)
        self.setView(view)
        self._flyout = None

        self.setMaxVisibleItems(12)
        self.setMinimumContentsLength(0)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.setEditable(False)

        self._apply_theme_styles()
        self._theme.theme_changed.connect(self._apply_theme_styles)

    def _apply_theme_styles(self):
        is_dark = self._theme.is_dark()

        bg = self._theme.get_color("dialog.input.background").name(QColor.NameFormat.HexArgb)
        text = self._theme.get_color("dialog.text").name(QColor.NameFormat.HexArgb)
        border = self._theme.get_color("dialog.border").name(QColor.NameFormat.HexArgb)

        flyout_bg = self._theme.get_color("flyout.background").name(QColor.NameFormat.HexArgb)
        flyout_border = self._theme.get_color("flyout.border").name(QColor.NameFormat.HexArgb)

        accent = self._theme.get_color("accent")

        hover_bg = QColor(accent)
        hover_bg.setAlpha(30 if not is_dark else 45)
        hover_bg_str = hover_bg.name(QColor.NameFormat.HexArgb)

        selected_bg_str = accent.name(QColor.NameFormat.HexArgb)
        selected_text = "#ffffff" if is_dark else "#000000"

        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px 28px 6px 10px;
                outline: 0;
            }}
            QComboBox:hover {{
                border: 1px solid {self._tint_border(border, is_dark)};
            }}
            QComboBox:focus {{
                border: 1px solid {selected_bg_str};
            }}
            QComboBox[flyoutOpen="true"]::drop-down {{
                width: 0px;
            }}
            QComboBox[flyoutOpen="true"]::down-arrow {{
                width: 0px;
                height: 0px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            /* Keep default arrow from style. If you want a custom icon, add QSS with image url here. */
            QComboBox::down-arrow {{
                  /* image: url();  // optional custom chevron */
              }}
        """)

        view = self.view()
        if view:
            try:
                view.setFrameShape(QFrame.Shape.NoFrame)
                view.setFrameShadow(QFrame.Shadow.Plain)
            except Exception:
                pass
            view.setStyleSheet(f"""
                QListView {{
                    background-color: transparent;
                    color: {text};
                    border: none;
                    padding: 0px;
                    show-decoration-selected: 1;
                    outline: 0;
                }}
                QListView::viewport {{
                    background-color: transparent;
                }}
                QListView::item {{
                    padding: 6px 10px;
                    margin: 0px;
                    text-align: center;
                }}
                QListView::item:hover {{
                    background-color: {hover_bg_str};
                }}
                QListView::item:selected {{
                    background-color: {selected_bg_str};
                    color: {selected_text};
                }}
            """)

            view.style().unpolish(view)
            view.style().polish(view)
            view.update()

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def showPopup(self):

        if self._flyout is None:
            self._flyout = _ComboPopupFlyout(self._theme)
            self._theme.theme_changed.connect(self._flyout._apply_style)
            self._flyout.set_on_close(lambda: self.setProperty("flyoutOpen", False))

        self._apply_theme_styles()

        self._flyout.view.setFont(self.font())
        self.setProperty("flyoutOpen", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        QTimer.singleShot(0, lambda: self._flyout.show_for_combo(self))

    def hidePopup(self):

        if self._flyout and self._flyout.isVisible():
            try:

                QTimer.singleShot(0, self._flyout.hide)
            except Exception:
                pass
        self.setProperty("flyoutOpen", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _animate_open_popup(self):

        pass

    @staticmethod
    def _tint_border(border_hex: str, is_dark: bool) -> str:
        """
        Slightly tints the border color for hover using simple heuristic.
        Accepts #AARRGGBB or #RRGGBB and returns #AARRGGBB.
        """
        qcol = QColor(border_hex)
        if is_dark:

            qcol = qcol.lighter(115)
        else:

            qcol = qcol.darker(115)

        if qcol.alpha() == 255:
            qcol.setAlpha(220)
        return qcol.name(QColor.NameFormat.HexArgb)

if __name__ == "__main__":
    import sys

    from PyQt6.QtWidgets import QApplication as QApp
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    app = QApp(sys.argv)

    tm = ThemeManager.get_instance()

    tm.register_palettes(
        light_palette={
            "dialog.input.background": "#FFFFFFFF",
            "dialog.text": "#FF202020",
            "dialog.border": "#1A000000",
            "flyout.background": "#FFFFFFFF",
            "flyout.border": "#1A000000",
            "accent": "#FF1677FF",
        },
        dark_palette={
            "dialog.input.background": "#FF2B2B2B",
            "dialog.text": "#FFEDEDED",
            "dialog.border": "#33FFFFFF",
            "flyout.background": "#FF2B2B2B",
            "flyout.border": "#33FFFFFF",
            "accent": "#FF3AA3FF",
        },
    )
    tm.set_theme("dark", app)

    w = QWidget()
    lay = QVBoxLayout(w)

    c1 = FluentComboBox()
    c1.addItem("Auto", userData="auto")
    c1.addItem("Light", userData="light")
    c1.addItem("Dark", userData="dark")

    c2 = FluentComboBox()
    for fam in ["Source Sans 3", "Inter", "Roboto", "System UI", "JetBrains Mono"]:
        c2.addItem(fam, userData=fam)

    lay.addWidget(c1)
    lay.addWidget(c2)

    w.resize(360, 160)
    w.show()

    sys.exit(app.exec())
