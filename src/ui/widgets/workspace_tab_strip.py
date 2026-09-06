"""Workspace-specific tab strip behavior."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QTabBar

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
    AdaptiveTabStrip,
    CloseButtonPolicy,
)
from sli_ui_toolkit.widgets import ThemedWidget
from ui.theming import try_resolve_theme_color


class WorkspaceTabStrip(ThemedWidget, AdaptiveTabStrip):
    """Adaptive tabs with browser-like close interactions.

    Eats mouse presses that land on a tab's close-button slot so
    ``_AdaptiveTabBar`` does not activate the tab on press while the close
    button is being clicked.  Without this, clicking the X on an inactive
    tab briefly switches to that tab (currentChanged on press) before the
    close is processed on release, flashing the closed tab's page for one
    frame.

    The strip paints its own background from the ``button.toggle.background.normal``
    token (QSS retired; the tab bar above it paints the same token).
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("close_policy", CloseButtonPolicy.ALL)
        self._strip_bg_color = QColor()
        super().__init__(*args, **kwargs)
        self._read_strip_color()
        self.tab_bar.installEventFilter(self)

    def _read_strip_color(self) -> None:
        try:
            resolved = try_resolve_theme_color(
                self._theme_manager, "surface.list"
            )
        except Exception:
            resolved = None
        if resolved is not None and resolved.isValid():
            self._strip_bg_color = QColor(resolved)
        else:
            self._strip_bg_color = QColor(self.palette().window().color())

    def on_theme_changed(self) -> None:
        self._read_strip_color()
        super().on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._strip_bg_color)
        painter.end()

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
                    # Eat the press so _AdaptiveTabBar doesn't activate the
                    # tab on mousePress while the X-button is still being
                    # clicked.  The inner close button's own ``clicked``
                    # signal handles the close on mouseRelease.
                    event.accept()
                    return True
        return super().eventFilter(watched, event)


WorkspaceTabStrip.inspect_spec = InspectSpec(
    family="WorkspaceTabStrip",
    state=(
        SpecField("tab_count", lambda w: w.count()),
        SpecField("current_index", lambda w: w.currentIndex()),
    ),
    docs="docs/dev/widgets/workspace_tab_strip.md",
)