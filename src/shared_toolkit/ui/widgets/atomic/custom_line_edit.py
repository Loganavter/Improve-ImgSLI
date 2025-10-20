from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PyQt6.QtWidgets import QLineEdit

from src.shared_toolkit.ui.managers.theme_manager import ThemeManager

from ..helpers.underline_painter import UnderlineConfig, draw_bottom_underline

class CustomLineEdit(QLineEdit):
    RADIUS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setProperty("custom-line-edit", True)

        self.setProperty("class", "primary")
        self.theme_manager = ThemeManager.get_instance()
        try:
            self.theme_manager.theme_changed.connect(self.update)
        except Exception:
            pass

    def _style_prefix(self) -> str:
        btn_class = str(self.property("class") or "")
        return "button.primary" if btn_class == "primary" else "button.default"

    def resizeEvent(self, e):

        super().resizeEvent(e)

    def focusInEvent(self, event):
        """Обработка получения фокуса для обновления внешнего вида"""
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        """Обработка потери фокуса для обновления внешнего вида"""
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = self.rect()

            thin = QColor(self.theme_manager.get_color("input.border.thin"))
            alpha = max(8, int(thin.alpha() * 0.66))
            thin.setAlpha(alpha)
            pen = QPen(thin)
            pen.setWidthF(0.66)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)

            radius = self.RADIUS
            rr = QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.drawRoundedRect(rr, radius, radius)

            if self.hasFocus():
                underline_config = UnderlineConfig(
                    color=self.theme_manager.get_color("accent"),
                    alpha=255,
                    thickness=1.0
                )
            else:
                underline_config = UnderlineConfig(alpha=120, thickness=1.0)

            draw_bottom_underline(painter, r, self.theme_manager, underline_config)

            painter.end()
        except Exception:
            pass
