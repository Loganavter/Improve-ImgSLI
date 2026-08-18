"""App-side keyboard navigation for the CSD title bar.

Generic Left/Right navigation between focusable buttons and focus
management live in the toolkit's ``CustomTitleBar`` (``focus_first_button``,
``focus_last_button``, event filter).  This section handles only
cross-section transitions:

- **Down** yields to the tab strip (the section below).
- **Up** is consumed — nothing above the title bar.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("ImproveImgSLI")


class TitleBarNavigationSection:
    """NavigationSection adapter for the CSD title bar.

    Delegates Left/Right/focus to the toolkit ``CustomTitleBar``;
    only Down/Up cross-section transitions are app-specific.
    """

    def __init__(self, title_bar: QWidget) -> None:
        self._title_bar = title_bar

    def owns(self, widget: QWidget) -> bool:
        if widget is self._title_bar:
            return True
        w = widget
        while w is not None:
            if w is self._title_bar:
                return True
            w = w.parentWidget()
        return False

    def navigate(self, key: int, widget: QWidget) -> bool:
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            return True
        if key == Qt.Key.Key_Down:
            logger.debug("[nav-titlebar] Down → yield to tab strip")
            return False
        if key == Qt.Key.Key_Up:
            logger.debug("[nav-titlebar] Up — consumed (topmost section)")
            return True
        return True

    def focus_first(self) -> bool:
        self._title_bar.setFocus(Qt.FocusReason.OtherFocusReason)
        result = self._title_bar.focus_first_button()
        logger.debug("[nav-titlebar] focus_first → %s", result)
        return True

    def focus_last(self) -> bool:
        self._title_bar.setFocus(Qt.FocusReason.OtherFocusReason)
        result = self._title_bar.focus_last_button()
        logger.debug("[nav-titlebar] focus_last → %s", result)
        return True
