"""Keyboard navigation for the CSD title bar.

The title bar contains menu triggers (File/Help), undo/redo buttons, and
window controls (minimize/maximize/close).  Left/Right moves between
visible focusable buttons.  Down yields to the section below (tab strip /
session picker).  Up is consumed — nothing above the title bar.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger("ImproveImgSLI")


def _title_bar_focusable_buttons(title_bar: QWidget) -> list[QWidget]:
    """Collect visible, StrongFocus children of the title bar in layout order.

    Only includes widgets whose parent chain goes through *title_bar*
    (``findChildren`` is recursive but we double-check to avoid false matches
    from reparented or overlay widgets).
    """
    buttons: list[QWidget] = []
    for child in title_bar.findChildren(QWidget):
        if (
            child.isVisible()
            and child.focusPolicy() == Qt.FocusPolicy.StrongFocus
            and title_bar.isAncestorOf(child)
        ):
            buttons.append(child)
    return buttons


class TitleBarNavigationSection:
    """Arrow-key navigation for the CSD title bar.

    Left/Right moves between focusable buttons.
    Down yields to the tab strip (the section below).
    Up is consumed — nothing above the title bar.
    """

    def __init__(self, title_bar: QWidget) -> None:
        self._title_bar = title_bar

    def owns(self, widget: QWidget) -> bool:
        if widget is self._title_bar:
            return True
        # Walk the parent chain — isAncestorOf can fail for widgets added
        # to layouts that reparent through zone hosts.
        w = widget
        chain = []
        while w is not None:
            chain.append(type(w).__name__)
            if w is self._title_bar:
                logger.debug(
                    "[nav-titlebar] owns(%s) → True  chain=%s",
                    type(widget).__name__,
                    " → ".join(chain),
                )
                return True
            w = w.parentWidget()
        logger.debug(
            "[nav-titlebar] owns(%s) → False chain=%s",
            type(widget).__name__,
            " → ".join(chain),
        )
        return False

    def navigate(self, key: int, widget: QWidget) -> bool:
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            buttons = _title_bar_focusable_buttons(self._title_bar)
            idx = next((i for i, b in enumerate(buttons) if b is widget), None)
            if idx is None:
                if buttons:
                    buttons[0].setFocus(Qt.FocusReason.OtherFocusReason)
                    return True
                return True
            step = -1 if key == Qt.Key.Key_Left else 1
            target = idx + step
            if 0 <= target < len(buttons):
                buttons[target].setFocus(Qt.FocusReason.OtherFocusReason)
                logger.debug(
                    "[nav-titlebar] %s btn[%d] → btn[%d] (%s)",
                    "Right" if step > 0 else "Left",
                    idx,
                    target,
                    type(buttons[target]).__name__,
                )
                return True
            logger.debug(
                "[nav-titlebar] %s at boundary btn[%d/%d] — consumed",
                "Right" if step > 0 else "Left",
                idx,
                len(buttons),
            )
            return True
        if key == Qt.Key.Key_Down:
            logger.debug("[nav-titlebar] Down → yield to tab strip")
            return False
        if key == Qt.Key.Key_Up:
            logger.debug("[nav-titlebar] Up — consumed (topmost section)")
            return True
        return True

    def focus_first(self) -> bool:
        buttons = _title_bar_focusable_buttons(self._title_bar)
        if buttons:
            logger.debug(
                "[nav-titlebar] focus_first → %s (of %d)",
                type(buttons[0]).__name__,
                len(buttons),
            )
            buttons[0].setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        logger.debug("[nav-titlebar] focus_first → False (no buttons)")
        return False

    def focus_last(self) -> bool:
        buttons = _title_bar_focusable_buttons(self._title_bar)
        if buttons:
            btn = buttons[-1]
            logger.debug(
                "[nav-titlebar] focus_last pre-setFocus: btn=%s policy=%s "
                "visible=%s acceptsFocus=%s geom=%s parent=%s",
                type(btn).__name__,
                btn.focusPolicy().name,
                btn.isVisible(),
                btn.acceptsFocus(),
                btn.geometry().getRect(),
                type(btn.parentWidget()).__name__,
            )
            btn.setFocus(Qt.FocusReason.OtherFocusReason)
            actual = QApplication.focusWidget()
            if actual is not btn:
                # setFocus redirected — try focusing the title bar itself
                logger.debug(
                    "[nav-titlebar] focus_last: setFocus redirected to %s, "
                    "trying title bar directly",
                    type(actual).__name__ if actual else None,
                )
                self._title_bar.setFocus(Qt.FocusReason.OtherFocusReason)
                actual = QApplication.focusWidget()
            logger.debug(
                "[nav-titlebar] focus_last post-setFocus: actual=%s hasFocus=%s "
                "owner_check=%s",
                type(actual).__name__ if actual else None,
                btn.hasFocus(),
                self.owns(actual) if actual else None,
            )
            return True
        logger.debug("[nav-titlebar] focus_last → False (no buttons)")
        return False
