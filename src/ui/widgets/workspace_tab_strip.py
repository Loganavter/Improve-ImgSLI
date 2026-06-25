"""Workspace-specific tab strip behavior."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QTabBar

from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
    AdaptiveTabStrip,
    CloseButtonPolicy,
)


class WorkspaceTabStrip(AdaptiveTabStrip):
    """Adaptive tabs with browser-like close interactions.

    Eats mouse presses that land on a tab's close-button slot so QTabBar does
    not activate the tab on press while the close button is being clicked.
    Without this, clicking the X on an inactive tab briefly switches to that
    tab (currentChanged on press) before the close is processed on release,
    flashing the closed tab's page for one frame.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("close_policy", CloseButtonPolicy.ALL)
        super().__init__(*args, **kwargs)
        self.tab_bar.installEventFilter(self)

    def _close_slot_at(self, pos):
        index = self.tab_bar.tabAt(pos)
        if index < 0:
            return None, -1
        slot = self.tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if slot is None or not slot.isVisible():
            return None, -1
        slot_rect = slot.geometry()
        if slot_rect.contains(pos):
            return slot, index
        return None, -1

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.tab_bar:
            if event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.MiddleButton:
                    index = self.tab_bar.tabAt(event.pos())
                    if index >= 0:
                        self.tabCloseRequested.emit(index)
                        event.accept()
                        return True
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                _slot, idx = self._close_slot_at(event.pos())
                if idx >= 0:
                    # Eat the press so QTabBar doesn't activate the tab on
                    # mousePress while the X-button is still being clicked.
                    # The inner close button's own ``clicked`` signal handles
                    # the close on mouseRelease.
                    event.accept()
                    return True
        return super().eventFilter(watched, event)
