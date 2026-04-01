from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QGuiApplication, QPainter
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from shared_toolkit.ui.managers.flyout_manager import FlyoutManager
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.overlay_layer import get_overlay_layer
from shared_toolkit.ui.widgets.helpers import draw_rounded_shadow

class BaseFlyout(QWidget):
    SHADOW_RADIUS = 8
    CONTENT_RADIUS = 8

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay_layer = get_overlay_layer(parent)
        if self.overlay_layer is not None:
            self.overlay_layer.attach(self)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )

        self.container = QWidget(self)
        self.container.setObjectName("FlyoutContainer")
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._main_layout.addWidget(self.container)

        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(4)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_base_style)
        self._apply_base_style()

        self.flyout_manager = FlyoutManager.get_instance()
        self.flyout_manager.register_flyout(self)

    def _apply_base_style(self):
        self.container.style().unpolish(self.container)
        self.container.style().polish(self.container)
        self.container.update()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        draw_rounded_shadow(
            painter,
            self.container.geometry(),
            steps=self.SHADOW_RADIUS,
            radius=self.CONTENT_RADIUS,
        )
        painter.end()

    def show_aligned(self, anchor_widget: QWidget, position="top", offset=5):
        visual_offset = offset - self.SHADOW_RADIUS

        self.flyout_manager.request_show(self)

        if self.container.layout():
            self.container.layout().invalidate()
            self.container.layout().activate()
            self.container.updateGeometry()
        self.adjustSize()
        if self.overlay_layer is not None:
            rect = self.overlay_layer.place_rect_relative_to_anchor(
                anchor_widget,
                self.size(),
                position=position,
                offset=visual_offset,
            )
            self.setGeometry(rect)
        else:
            anchor_pos = anchor_widget.mapToGlobal(QPoint(0, 0))
            anchor_w = anchor_widget.width()
            anchor_h = anchor_widget.height()

            my_w = self.width()
            my_h = self.height()

            target_x = anchor_pos.x() + (anchor_w - my_w) // 2
            target_y = anchor_pos.y()

            if position == "top":
                target_y = anchor_pos.y() - my_h - visual_offset
            elif position == "bottom":
                target_y = anchor_pos.y() + anchor_h + visual_offset

            screen = QGuiApplication.screenAt(anchor_pos)
            if screen:
                geo = screen.availableGeometry()
                target_x = max(geo.left(), target_x)
                target_x = min(geo.right() - my_w, target_x)
                if target_y < geo.top() and position == "top":
                    target_y = anchor_pos.y() + anchor_h + visual_offset

            self.move(target_x, target_y)
        self.show()
        self.raise_()

    def contains_global(self, global_pos) -> bool:
        if not self.isVisible():
            return False
        if self.overlay_layer is not None:
            return self.overlay_layer.contains_global(self, global_pos)
        return self.rect().contains(self.mapFromGlobal(global_pos))

    def hide(self):
        self.flyout_manager.request_hide(self)
        super().hide()

        if self.parent() and self.parent().window():
            self.parent().window().activateWindow()
            self.parent().window().setFocus()
