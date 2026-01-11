from typing import Optional, Union
from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QIcon, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)
from ui.icon_manager import AppIcon, get_app_icon

class CustomButton(QWidget):
    clicked = pyqtSignal()
    RADIUS = 2

    def __init__(self, icon: Optional[Union[QIcon, AppIcon]], text: str = "", parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("CustomButton")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._override_bg_color: Optional[QColor] = None
        self.theme_manager = ThemeManager.get_instance()
        self._icon = icon
        self._app_icon: Optional[AppIcon] = icon if isinstance(icon, AppIcon) else None
        self._icon_size = QSize(16, 16)

        self._is_footer = False
        self._bottom_extension_factor = 0.0

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

    def set_footer_mode(self, is_footer: bool):
        self._is_footer = is_footer
        self.RADIUS = 8 if is_footer else 2
        self.update()

    def set_bottom_extension(self, factor: float):
        self._bottom_extension_factor = factor
        self.update()

    def _update_icon_pixmap(self):
        if self._icon:
            if self._app_icon is not None:
                icon = get_app_icon(self._app_icon)
            else:
                icon = self._icon
            pixmap = icon.pixmap(self._icon_size, QIcon.Mode.Normal, QIcon.State.Off)
            self.icon_label.setPixmap(pixmap)

    def _on_theme_changed(self):
        self._update_icon_pixmap()
        prefix = self._style_prefix()
        text_color_key = f"{prefix}.text" if "primary" in prefix else "dialog.text"
        text_color = self.theme_manager.get_color(text_color_key)
        self.text_label.setStyleSheet(f"color: {text_color.name()}; background: transparent;")
        self.update()

    def _clear_layout(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if w := item.widget(): self._layout.removeWidget(w)

    def _free_widget_width(self):
        self.setMinimumWidth(0); self.setMaximumWidth(16777215)

    def _apply_sizing_mode(self, icon_only: bool):
        if icon_only: self.setFixedSize(33, 33)
        else: self.setMinimumHeight(33); self._free_widget_width()

    def _rebuild_layout(self):
        self._clear_layout()
        has_icon = self._icon is not None
        has_text = bool(self.text_label.text())

        if has_icon and has_text:
            self._apply_sizing_mode(False)
            self._icon_size = QSize(16, 16)
            self.icon_label.show(); self.text_label.show()
            self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            self._layout.setContentsMargins(10, 5, 10, 5)
            self._layout.addStretch(1); self._layout.addWidget(self.icon_label)
            self._layout.addWidget(self.text_label); self._layout.addStretch(1)
        elif has_icon:
            self._apply_sizing_mode(True)
            self._icon_size = QSize(20, 20)
            self.text_label.hide(); self.icon_label.show()
            self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.addWidget(self.icon_label)
        else:
            self._apply_sizing_mode(False)
            self.icon_label.hide(); self.text_label.show()
            self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            self._layout.setContentsMargins(15, 5, 15, 5)
            self._layout.addStretch(1); self._layout.addWidget(self.text_label); self._layout.addStretch(1)

    def set_override_bg_color(self, color: Optional[QColor]):
        self._override_bg_color = color; self.update()

    def setText(self, text):
        self.text_label.setText(text); self._rebuild_layout(); self.updateGeometry()

    def setIcon(self, icon: Optional[Union[QIcon, AppIcon]]):
        self._icon = icon
        self._app_icon = icon if isinstance(icon, AppIcon) else None
        self._rebuild_layout()
        self._update_icon_pixmap()

    def text(self): return self.text_label.text()

    def _style_prefix(self) -> str:
        return "button.primary" if "primary" in str(self.property("class") or "") else "button.dialog.default"

    def enterEvent(self, e):
        if self.isEnabled(): self.setProperty("state", "hover"); self.update()
        super().enterEvent(e)
    def leaveEvent(self, e):
        if self.isEnabled(): self.setProperty("state", "normal"); self.update()
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        if self.isEnabled(): self.setProperty("state", "pressed"); self.update()
        super().mousePressEvent(e)
    def mouseReleaseEvent(self, e):
        self.setProperty("state", "hover" if self.rect().contains(e.pos()) else "normal"); self.update()
        if self.isEnabled() and self.rect().contains(e.pos()) and e.button() == Qt.MouseButton.LeftButton: self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        state = str(self.property("state") or "normal")
        if not self.isEnabled():
            bg = QColor(self.theme_manager.get_color("dialog.border"))
            bg.setAlpha(40)
        elif self._override_bg_color:
            bg = self._override_bg_color
        else:
            prefix = self._style_prefix()
            key = f"{prefix}.background.pressed" if state=="pressed" else (f"{prefix}.background.hover" if state=="hover" else f"{prefix}.background")
            bg = QColor(self.theme_manager.get_color(key))

        rect = QRectF(self.rect())

        if self._bottom_extension_factor > 0:
            painter.setClipping(False)
            extension = rect.height() * self._bottom_extension_factor
            rect.setHeight(rect.height() + extension)

        rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)

        path = QPainterPath()
        if self._is_footer:

            path.moveTo(rect.left(), rect.top())
            path.lineTo(rect.right(), rect.top())
            path.arcTo(rect.right() - 2*self.RADIUS, rect.bottom() - 2*self.RADIUS, 2*self.RADIUS, 2*self.RADIUS, 0, -90)
            path.arcTo(rect.left(), rect.bottom() - 2*self.RADIUS, 2*self.RADIUS, 2*self.RADIUS, 270, -90)
            path.closeSubpath()
        else:

            path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)

        if self.isEnabled():
            prefix = self._style_prefix()
            border_color = QColor(self.theme_manager.get_color(f"{prefix}.border"))
            painter.setPen(QPen(border_color, 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

            if not self._is_footer:
                draw_bottom_underline(
                    painter, rect.toRect(), self.theme_manager,
                    UnderlineConfig(alpha=40, thickness=1.0, vertical_offset=0.0, arc_radius=self.RADIUS)
                )

