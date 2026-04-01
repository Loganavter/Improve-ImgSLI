from PyQt6.QtCore import QPointF

from shared_toolkit.ui.widgets.composite.unified_flyout.common import FlyoutMode, logger

class _UnifiedFlyoutDragDropMixin:
    def can_accept_drop(self, payload: dict) -> bool:
        return self.isVisible()

    def _panel_under_global_pos(self, global_pos: QPointF):
        local_pos = self.container_widget.mapFromGlobal(global_pos.toPoint())
        if self.mode == FlyoutMode.DOUBLE:
            if self.panel_left.geometry().contains(local_pos):
                return self.panel_left
            if self.panel_right.geometry().contains(local_pos):
                return self.panel_right
            return None
        return (
            self.panel_left
            if self.panel_left.isVisible()
            else (self.panel_right if self.panel_right.isVisible() else None)
        )

    def update_drop_indicator(self, global_pos: QPointF):
        panel = self._panel_under_global_pos(global_pos)
        if panel is None:
            self.clear_drop_indicator()
            return

        other = self.panel_right if panel is self.panel_left else self.panel_left
        try:
            panel.update_drop_indicator(global_pos)
            other.clear_drop_indicator()
        except Exception as e:
            logger.exception(f"[UnifiedFlyout] exception in update_drop_indicator: {e}")

    def clear_drop_indicator(self):
        self.panel_left.clear_drop_indicator()
        self.panel_right.clear_drop_indicator()

    def handle_drop(self, payload: dict, global_pos: QPointF):
        panel = self._panel_under_global_pos(global_pos)
        if panel:
            panel.handle_drop(payload, global_pos)
