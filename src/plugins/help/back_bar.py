"""Back / breadcrumb bar for hierarchical help."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager

from ui.theming import resolve_theme_color
from sli_ui_toolkit.ui.widgets.helpers import unregister_hover_widget
from sli_ui_toolkit.widgets import Button, Label

# Button sizeHint pads text with +24px; crumbs only need a hair of inset.
_CRUMB_PAD_X = 4
_CRUMB_H = 28


def _dispose_hover_widget(widget: QWidget) -> None:
    try:
        unregister_hover_widget(widget)
    except Exception:
        pass
    widget.hide()
    widget.setParent(None)
    widget.deleteLater()


def _crumb_button(title: str, *, bold: bool, parent: QWidget) -> Button:
    """Same ghost Button chrome for every segment; bold via ``sliBold`` paint flag."""
    btn = Button(
        text=title,
        variant="ghost",
        size=(0, _CRUMB_H),
        content_padding=(_CRUMB_PAD_X, 0, _CRUMB_PAD_X, 0),
        parent=parent,
    )
    # setFont(bold) is cleared by Qt polish / theme; TextContent honors sliBold.
    btn.setProperty("sliBold", bool(bold))
    if bold:
        font = btn.font()
        font.setBold(True)
        btn.setFont(font)
    width = QFontMetrics(btn.font()).horizontalAdvance(title) + _CRUMB_PAD_X * 2
    if bold:
        # Width must account for bold metrics even if polish later clears setFont.
        bold_font = QFont(btn.font())
        bold_font.setBold(True)
        width = QFontMetrics(bold_font).horizontalAdvance(title) + _CRUMB_PAD_X * 2
    btn.setFixedSize(max(width, 1), _CRUMB_H)
    return btn


class HelpBackBar(QWidget):
    """Full-width ``←`` + breadcrumb chrome above sidebar and content."""

    backRequested = Signal()
    segmentActivated = Signal(str)  # node_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpBackBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 6, 8, 7)
        self._layout.setSpacing(6)

        self._back = Button(
            text="←",
            variant="ghost",
            size=(36, 28),
            parent=self,
        )
        self._back.clicked.connect(self.backRequested.emit)
        self._layout.addWidget(self._back, 0)

        self._crumbs_host = QWidget(self)
        self._crumbs_layout = QHBoxLayout(self._crumbs_host)
        self._crumbs_layout.setContentsMargins(0, 0, 0, 0)
        self._crumbs_layout.setSpacing(0)
        self._layout.addWidget(self._crumbs_host, 1)
        self._layout.addStretch(0)

        self.set_breadcrumb(())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        tm = ThemeManager.get_instance()
        color = resolve_theme_color(tm, "separator.color")
        if color is None or not color.isValid():
            color = resolve_theme_color(tm, "dialog.border")
        if color is not None and color.isValid():
            y = self.height() - 1
            painter.setPen(QPen(color, 1))
            painter.drawLine(0, y, self.width(), y)
        painter.end()

    def set_can_go_back(self, enabled: bool) -> None:
        self._back.setEnabled(bool(enabled))
        self.setVisible(True)

    def set_breadcrumb(self, crumbs: tuple[tuple[str, str], ...]) -> None:
        while self._crumbs_layout.count():
            item = self._crumbs_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                _dispose_hover_widget(w)

        if not crumbs:
            self._back.setEnabled(False)
            return

        for index, (node_id, title) in enumerate(crumbs):
            if index > 0:
                sep = Label("/", pixel_size=12, parent=self._crumbs_host)
                sep.setSizePolicy(
                    QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
                )
                sep.setContentsMargins(0, 0, 0, 0)
                self._crumbs_layout.addWidget(
                    sep, 0, Qt.AlignmentFlag.AlignVCenter
                )
            is_current = index == len(crumbs) - 1
            btn = _crumb_button(
                title, bold=is_current, parent=self._crumbs_host
            )
            if not is_current:
                btn.clicked.connect(
                    lambda _checked=False, nid=node_id: self.segmentActivated.emit(
                        nid
                    )
                )
            self._crumbs_layout.addWidget(btn)
        self._crumbs_layout.addStretch(1)
        self._back.setEnabled(len(crumbs) > 1)
