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
    """Arrow-key navigation for the session picker create-cards list.

    Down past the last card hands off to the recent panel (if visible).
    Up past the first card hands off to the tab strip.
    Left/Right are consumed (single-column list).
    """

    def __init__(self, page: QWidget) -> None:
        self._page = page

    def owns(self, widget: QWidget) -> bool:
        return self._page.isAncestorOf(widget) or widget is self._page

    def navigate(self, key: int, widget: QWidget) -> bool:
        cards = self._page._card_entries()
        card_idx = next((i for i, (_, c) in enumerate(cards) if c is widget), None)

        if key == Qt.Key.Key_Down:
            if card_idx is None:
                if cards:
                    cards[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
                    return True
            elif card_idx < len(cards) - 1:
                cards[card_idx + 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # Past last card — try to hand off to recent panel.
            recent = getattr(self._page, "_recent_panel", None)
            if recent is not None and recent.isVisible():
                recent.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # No recent panel — yield to next section.
            return False

        if key == Qt.Key.Key_Up:
            if card_idx is None:
                return False
            if card_idx > 0:
                cards[card_idx - 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # At first card — yield so NavigationManager can hand off to
            # the tab strip (the section above).
            return False

        # Left/Right: single-column list, nothing horizontal to navigate.
        return True

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
        # Down yields to the session picker below.
        # Up — consume: no section above the tab strip.
        if key == Qt.Key.Key_Up:
            return True
        return False

    def _focus_add_button(self) -> bool:
        """Focus the add button — the only focusable widget in the strip
        that accepts programmatic focus (tab_bar has ClickFocus)."""
        add_btn = getattr(self._tab_strip, "add_button", None)
        if add_btn is not None and add_btn.isVisible():
            add_btn.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        self._tab_strip.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def focus_first(self) -> bool:
        return self._focus_add_button()

    def focus_last(self) -> bool:
        return self._focus_add_button()
