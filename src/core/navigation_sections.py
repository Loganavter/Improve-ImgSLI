"""Concrete ``NavigationSection`` implementations for the host shell.

``SessionPickerSection`` navigates the create-cards list in the session
picker page.  ``TabStripSection`` owns the workspace tab bar and delegates
Left/Right to QTabBar's native handling (our event filter never sees those
keys because the tab bar consumes them first).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


class SessionPickerSection:
    """Arrow-key navigation for the session picker create-cards list."""

    def __init__(self, page: QWidget) -> None:
        self._page = page

    def owns(self, widget: QWidget) -> bool:
        return self._page.isAncestorOf(widget) or widget is self._page

    def navigate(self, key: int, widget: QWidget) -> bool:
        cards = self._page._card_entries()
        card_idx = next((i for i, (_, c) in enumerate(cards) if c is widget), None)

        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            if card_idx is None:
                if cards:
                    cards[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
                    return True
            elif card_idx < len(cards) - 1:
                cards[card_idx + 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # Past last card — yield to next section (e.g. recent panel or
            # whatever sits below).
            return False

        if key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            if card_idx is None:
                return False
            if card_idx > 0:
                cards[card_idx - 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # At first card — yield so NavigationManager can hand off to
            # the tab strip (the section above).
            return False

        return False

    def focus_first(self) -> bool:
        cards = self._page._card_entries()
        if cards:
            cards[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        return False

    def focus_last(self) -> bool:
        cards = self._page._card_entries()
        if cards:
            cards[-1][1].setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        return False


class TabStripSection:
    """Arrow-key navigation for the workspace tab strip.

    Left/Right between tabs is handled natively by QTabBar (the event
    filter never sees those keys).  Down yields to the session picker.
    """

    def __init__(self, tab_strip: QWidget) -> None:
        self._tab_strip = tab_strip

    def owns(self, widget: QWidget) -> bool:
        return self._tab_strip.isAncestorOf(widget) or widget is self._tab_strip

    def navigate(self, key: int, widget: QWidget) -> bool:
        # Left/Right are handled by QTabBar itself — don't consume them here.
        # Down/Right past the last tab → yield to next section.
        # Up/Left past the first tab → yield to previous section.
        return False

    def focus_first(self) -> bool:
        self._tab_strip.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def focus_last(self) -> bool:
        self._tab_strip.setFocus(Qt.FocusReason.OtherFocusReason)
        return True
