import time

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter

from shared_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from shared_toolkit.ui.widgets.composite.unified_flyout.common import FlyoutMode
from shared_toolkit.ui.widgets.helpers import draw_rounded_shadow

class _UnifiedFlyoutStyleMixin:
    def _apply_style(self):
        if self.mode == FlyoutMode.DOUBLE:
            self._container_clip.setEnabled(False)
            self.container_widget.setProperty("surfaceRole", "transparent")
            self.panel_left.setProperty("surfaceRole", "panel")
            self.panel_right.setProperty("surfaceRole", "panel")
            self._panel_left_clip.setEnabled(True)
            self._panel_right_clip.setEnabled(True)
        else:
            self._panel_left_clip.setEnabled(False)
            self._panel_right_clip.setEnabled(False)
            self._container_clip.setEnabled(True)
            self.container_widget.setProperty("surfaceRole", "container")
            self.panel_left.setProperty("surfaceRole", "transparent")
            self.panel_right.setProperty("surfaceRole", "transparent")

        for widget in (self.container_widget, self.panel_left, self.panel_right):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _apply_container_geometry(self):
        inner_rect = self.rect().adjusted(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
        )
        if self.container_widget.geometry() != inner_rect:
            self.container_widget.setGeometry(inner_rect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_container_geometry()
        if self.mode != FlyoutMode.DOUBLE:
            self._position_panels_for_single()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        steps = self.SHADOW_RADIUS

        if self.mode == FlyoutMode.DOUBLE:
            offset = self.container_widget.geometry().topLeft()
            for panel in (self.panel_left, self.panel_right):
                if panel.isVisible():
                    panel_rect = QRectF(panel.geometry()).translated(
                        offset.x(), offset.y()
                    )
                    self._draw_shadow(painter, panel_rect, steps)
        else:
            self._draw_shadow(painter, QRectF(self.container_widget.geometry()), steps)
        painter.end()

    def _draw_shadow(self, painter, rect, steps):
        draw_rounded_shadow(painter, rect, steps=steps, radius=8)

    def start_closing_animation(self):
        if not self.isVisible() or self._is_closing:
            return
        self.hide()

    def _on_animation_finished(self):
        if self._anim:
            self._anim.deleteLater()
            self._anim = None

    def hideEvent(self, event):
        closing_mode = self.mode
        if self._anim:
            self._anim.stop()
        PathTooltip.get_instance().hide_tooltip()

        self.last_close_timestamp = time.monotonic()
        self.last_close_mode = closing_mode

        if not self._is_closing:
            self._is_closing = True
            try:
                self.mode = FlyoutMode.HIDDEN
                self.closing_animation_finished.emit()
            finally:
                self._is_closing = False

        super().hideEvent(event)
