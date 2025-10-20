from typing import Optional

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QIcon
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.shared_toolkit.ui.managers.theme_manager import ThemeManager
from src.shared_toolkit.ui.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)

class CustomButton(QWidget):
    clicked = pyqtSignal()

    RADIUS = 6

    def __init__(self, icon: Optional[QIcon], text: str = "", parent: QWidget = None):
        super().__init__(parent)

        self.setObjectName("CustomButton")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._override_bg_color: Optional[QColor] = None

        self.theme_manager = ThemeManager.get_instance()

        self._icon = icon
        self._icon_size = QSize(16, 16)

        layout = QHBoxLayout(self)
        layout.setSpacing(6)
        self._layout = layout

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._rebuild_layout()
        self.setProperty("class", "custom-button")
        self.setProperty("state", "normal")

        self.theme_manager.theme_changed.connect(self._on_theme_changed)

        self._on_theme_changed()

    def _on_theme_changed(self):
        if self._icon:

            pixmap = self._icon.pixmap(self._icon_size, QIcon.Mode.Normal, QIcon.State.Off)
            self.icon_label.setPixmap(pixmap)

        prefix = self._style_prefix()
        text_color_key = f"{prefix}.text" if "primary" in prefix else "dialog.text"
        text_color = self.theme_manager.get_color(text_color_key)

        self.text_label.setStyleSheet(
            f"color: {text_color.name()}; background: transparent;"
        )

        self.update()

    def _clear_layout(self):

        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                self._layout.removeWidget(w)

    def _free_widget_width(self):

        try:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
        except Exception:
            pass

    def _apply_sizing_mode(self, icon_only: bool):
        if icon_only:
            self.setFixedSize(33, 33)
        else:

            self.setMinimumHeight(33)
            self._free_widget_width()

    def _rebuild_layout(self):
        has_icon = self._icon is not None
        has_text = bool(self.text_label.text())

        self._clear_layout()

        if has_icon and has_text:

            self._apply_sizing_mode(icon_only=False)
            self._icon_size = QSize(16, 16)
            self.icon_label.show()
            self.text_label.show()
            self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            self._layout.setContentsMargins(10, 5, 10, 5)
            self._layout.addStretch(1)
            self._layout.addWidget(self.icon_label)
            self._layout.addWidget(self.text_label)
            self._layout.addStretch(1)
        elif has_icon:

            self._apply_sizing_mode(icon_only=True)
            self._icon_size = QSize(20, 20)
            self.text_label.hide()
            self.icon_label.show()
            self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.addWidget(self.icon_label)
        else:

            self._apply_sizing_mode(icon_only=False)
            self.icon_label.hide()
            self.text_label.show()
            self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            self._layout.setContentsMargins(15, 5, 15, 5)
            self._layout.addStretch(1)
            self._layout.addWidget(self.text_label)
            self._layout.addStretch(1)

    def set_override_bg_color(self, color: Optional[QColor]):
        if self._override_bg_color != color:
            self._override_bg_color = color
            self.update()

    def setText(self, text):
        self.text_label.setText(text)

        self._rebuild_layout()
        self._on_theme_changed()
        self.text_label.update()
        self.updateGeometry()

    def setIcon(self, icon: Optional[QIcon]):
        self._icon = icon
        self._rebuild_layout()
        self._on_theme_changed()

    def text(self):
        return self.text_label.text()

    def _style_prefix(self) -> str:
        btn_class = str(self.property("class") or "")
        return "button.primary" if "primary" in btn_class else "button.default"

    def enterEvent(self, event):
        if not self.isEnabled():
            return
        self.setProperty("state", "hover")
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.isEnabled():
            return
        self.setProperty("state", "normal")
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if not self.isEnabled():
            return
        self.setProperty("state", "pressed")
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setProperty(
            "state", "hover" if self.rect().contains(event.pos()) else "normal"
        )
        self.update()
        if not self.isEnabled():
            return
        if (
            self.rect().contains(event.pos())
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.isEnabled():

            rectf = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

            border_color = self.theme_manager.get_color("dialog.border")
            fill_color = QColor(border_color)
            fill_color.setAlpha(40)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill_color))
            painter.drawRoundedRect(rectf, self.RADIUS, self.RADIUS)

            text_color = self.theme_manager.get_color("dialog.text")
            disabled_text_color = QColor(text_color)
            disabled_text_color.setAlpha(120)

            painter.setPen(disabled_text_color)
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, self.text_label.text()
            )
            return

        state = str(self.property("state") or "normal")

        if self._override_bg_color is not None:
            bg = self._override_bg_color
        else:
            prefix = self._style_prefix()
            if state == "hover":
                bg_key = f"{prefix}.background.hover"
            elif state == "pressed":
                bg_key = f"{prefix}.background.pressed"
            else:
                bg_key = f"{prefix}.background"
            bg = QColor(self.theme_manager.get_color(bg_key))

        rectf = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rectf, self.RADIUS, self.RADIUS)

        prefix = self._style_prefix()
        border_color = QColor(self.theme_manager.get_color(f"{prefix}.border"))

        pen_border = QPen(border_color)
        pen_border.setWidthF(1.0)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, self.RADIUS, self.RADIUS)

        draw_bottom_underline(
            painter, self.rect(), self.theme_manager, UnderlineConfig(alpha=255)
        )
