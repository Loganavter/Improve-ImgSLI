from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QLineEdit

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import (
    UnderlineConfig,
    apply_editable_text_behavior,
    draw_bottom_underline,
)

class CustomLineEdit(QLineEdit):
    RADIUS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("custom-line-edit", True)
        self.setProperty("class", "primary")
        apply_editable_text_behavior(self)
        self.theme_manager = ThemeManager.get_instance()
        try:
            self.theme_manager.theme_changed.connect(self.update)
        except Exception:
            pass

    def _style_prefix(self) -> str:
        btn_class = str(self.property("class") or "")
        return "button.primary" if btn_class == "primary" else "button.default"

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.update)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        QTimer.singleShot(0, self.update)

    def paintEvent(self, event):
        rect = self.rect()
        radius = self.RADIUS
        rounded_rect = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = self.theme_manager.get_color("dialog.input.background")
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rounded_rect, radius, radius)
        painter.end()

        super().paintEvent(event)

        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            thin = QColor(self.theme_manager.get_color("input.border.thin"))
            alpha = max(8, int(thin.alpha() * 0.66))
            thin.setAlpha(alpha)
            pen = QPen(thin)
            pen.setWidthF(0.66)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rounded_rect, radius, radius)

            if self.hasFocus():
                underline_config = UnderlineConfig(
                    color=self.theme_manager.get_color("accent"),
                    alpha=120,
                    thickness=1.5,
                    arc_radius=3.0,
                )
            else:
                underline_config = UnderlineConfig(
                    alpha=60,
                    thickness=1.0,
                    arc_radius=3.0,
                )

            draw_bottom_underline(painter, rect, self.theme_manager, underline_config)
            painter.end()
        except Exception:
            pass
