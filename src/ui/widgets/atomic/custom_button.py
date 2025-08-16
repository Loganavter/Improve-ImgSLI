from PyQt6.QtCore import QSize, pyqtSignal, Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from ui.icon_manager import get_icon, AppIcon
from core.theme import ThemeManager
from ..helpers.underline_painter import draw_bottom_underline, UnderlineConfig

class CustomButton(QWidget):
    clicked = pyqtSignal()

    RADIUS = 6

    def __init__(self, icon: AppIcon, text: str = "", parent: QWidget = None):
        super().__init__(parent)

        self.setObjectName("CustomButton")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(33)

        self._icon = icon
        self._icon_size = QSize(16, 16)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(6)

        layout.addStretch(1)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.icon_label.setPixmap(get_icon(self._icon).pixmap(self._icon_size))

        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch(1)

        self.setProperty("state", "normal")
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self):

        self.icon_label.setPixmap(get_icon(self._icon).pixmap(self._icon_size))
        self.update()

    def setText(self, text):
        self.text_label.setText(text)

    def _style_prefix(self) -> str:

        btn_class = str(self.property("class") or "")
        return "button.primary" if btn_class == "primary" else "button.default"

    def enterEvent(self, event):
        self.setProperty("state", "hover")
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("state", "normal")
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.setProperty("state", "pressed")
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setProperty("state", "hover" if self.rect().contains(event.pos()) else "normal")
        self.update()
        if self.rect().contains(event.pos()) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        state = str(self.property("state") or "normal")
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

        thin = QColor(self.theme_manager.get_color("input.border.thin"))
        is_primary = (str(self.property("class") or "") == "primary")
        alpha_factor = 0.66 if is_primary else 0.33
        alpha = max(8, int(thin.alpha() * alpha_factor))
        thin.setAlpha(alpha)
        pen_border = QPen(thin)
        pen_border.setWidthF(0.66)
        pen_border.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, self.RADIUS, self.RADIUS)

        draw_bottom_underline(painter, self.rect(), self.theme_manager, UnderlineConfig(alpha=255))
