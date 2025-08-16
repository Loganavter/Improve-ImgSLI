from PyQt6.QtCore import Qt, QRectF, QPointF, QRect
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QRegion
from PyQt6.QtWidgets import QLineEdit

from core.theme import ThemeManager
from ..helpers.underline_painter import draw_bottom_underline, UnderlineConfig

class CustomLineEdit(QLineEdit):
    RADIUS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        try:
            w, h = self.width(), self.height()
            if w <= 0 or h <= 0:
                self.clearMask()
            else:
                radius = float(self.RADIUS)
                path = QPainterPath()

                rectf = QRectF(-1.0, 0.0, float(w + 1), float(h))
                path.addRoundedRect(rectf, radius, radius)
                region = QRegion(path.toFillPolygon().toPolygon())
                self.setMask(region)
        except Exception:
            pass
        super().resizeEvent(e)

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

            draw_bottom_underline(painter, r, self.theme_manager, UnderlineConfig(alpha=120, thickness=1.0))

            painter.end()
        except Exception:
            pass
