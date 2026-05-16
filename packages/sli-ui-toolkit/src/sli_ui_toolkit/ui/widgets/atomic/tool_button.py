from __future__ import annotations

from PyQt6.QtCore import QEvent, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QToolButton

from sli_ui_toolkit.ui.widgets.style_bridge import update_widget_style

class ToolButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setObjectName("ToolButton")
        self._variant = "default"
        self._density = "normal"
        self._icon_size_px = 22
        self._corner_radius_px = 6

    def setIcon(self, icon: QIcon):  # noqa: N802
        super().setIcon(icon)

    def setIconSize(self, size: QSize):  # noqa: N802
        super().setIconSize(size)

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                super().setIconSize(QSize(self._icon_size_px, self._icon_size_px))
            elif name == "cornerRadiusPx":
                self._corner_radius_px = max(0, int(self.property("cornerRadiusPx") or self._corner_radius_px))
            update_widget_style(self)
        return super().event(event)

    def getVariant(self) -> str:
        return self._variant

    def setVariant(self, variant: str):
        self._variant = str(variant or "default")
        self.setProperty("variant", self._variant)
        update_widget_style(self)

    def getDensity(self) -> str:
        return self._density

    def setDensity(self, density: str):
        self._density = str(density or "normal")
        self.setProperty("density", self._density)
        update_widget_style(self)

    def getIconSizePx(self) -> int:
        return int(self._icon_size_px)

    def setIconSizePx(self, size_px: int):
        size_px = max(1, int(size_px))
        self._icon_size_px = size_px
        self.setProperty("iconSizePx", size_px)
        super().setIconSize(QSize(size_px, size_px))
        update_widget_style(self, update_geometry=True)

    def getCornerRadiusPx(self) -> int:
        return int(self._corner_radius_px)

    def setCornerRadiusPx(self, radius_px: int):
        self._corner_radius_px = max(0, int(radius_px))
        self.setProperty("cornerRadiusPx", self._corner_radius_px)
        update_widget_style(self)
