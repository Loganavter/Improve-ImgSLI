"""Concrete ``NavigationSection`` implementations for the host shell.

``SessionPickerSection`` navigates the create-cards list in the session
picker page.  ``TabStripSection`` owns the workspace tab bar and delegates
Left/Right to ``_AdaptiveTabBar``'s native handling (our event filter never
sees those keys because the tab bar consumes them first).  ``ToolbarRowsSection``
is a generic Up/Down-between-rows section reused by workspace tabs whose
content is one or more horizontal toolbar strips (image_compare, multi_compare).
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("ImproveImgSLI")


class SessionPickerSection:
    """Arrow-key navigation for the session picker create-cards list.

    Down past the last card hands off to the recent panel (if visible).
    Up past the first card hands off to the tab strip.
    Left/Right are consumed (single-column list).
    """

    def __init__(self, page: QWidget) -> None:
        self._page = page

    def owns(self, widget: QWidget) -> bool:
        if widget is self._page:
            return True
        # Shelf (RecentProjectsPanel) has its own event filter for internal
        # navigation — don't claim shelf widgets so their events pass through.
        if self._is_in_recent(widget):
            return False
        # Walk the parent chain — isAncestorOf misses intermediate
        # QWidget wrappers.
        p = widget
        while p is not None:
            if p is self._page:
                return True
            p = p.parentWidget()
        return False

    def _is_in_recent(self, widget: QWidget) -> bool:
        recent = getattr(self._page, "_recent_panel", None)
        if recent is None or not recent.isVisible():
            return False
        return recent.isAncestorOf(widget) or widget is recent

    def navigate(self, key: int, widget: QWidget) -> bool:
        cards = self._page._card_entries()
        card_idx = next((i for i, (_, c) in enumerate(cards) if c is widget), None)

        logger.debug(
            "[nav-card] navigate key=%s widget=%s card_idx=%s cards=%d",
            key, type(widget).__name__, card_idx, len(cards),
        )

        if key == Qt.Key.Key_Down:
            if card_idx is None:
                if cards:
                    logger.debug(
                        "[nav-card] Down from non-card → first card (%s)",
                        type(cards[0][1]).__name__,
                    )
                    cards[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
                    return True
            elif card_idx < len(cards) - 1:
                logger.debug(
                    "[nav-card] Down card[%d] → card[%d]", card_idx, card_idx + 1
                )
                cards[card_idx + 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # Past last card — try to hand off to recent shelf.
            recent = getattr(self._page, "_recent_panel", None)
            if recent is not None and recent.isVisible():
                if recent.focus_header_control(True):
                    logger.debug("[nav-card] Down past last card → shelf header")
                    return True
                if recent.focus_recent_item(True):
                    logger.debug("[nav-card] Down past last card → first recent item")
                    return True
            # No recent panel — yield to next section.
            logger.debug("[nav-card] Down past last card → yield (no shelf)")
            return False

        if key == Qt.Key.Key_Up:
            if card_idx is None:
                logger.debug("[nav-card] Up from non-card → yield")
                return False
            if card_idx > 0:
                logger.debug(
                    "[nav-card] Up card[%d] → card[%d]", card_idx, card_idx - 1
                )
                cards[card_idx - 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # At first card — yield so NavigationManager can hand off to
            # the tab strip (the section above).
            logger.debug("[nav-card] Up from first card → yield to tab strip")
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

    Left/Right between tabs is handled natively by ``_AdaptiveTabBar``
    (the event filter never sees those keys because the tab bar consumes
    them first).  Down yields to the session picker.
    """

    def __init__(self, tab_strip: QWidget) -> None:
        self._tab_strip = tab_strip

    def owns(self, widget: QWidget) -> bool:
        if widget is self._tab_strip:
            return True
        p = widget
        while p is not None:
            if p is self._tab_strip:
                return True
            p = p.parentWidget()
        return False

    def navigate(self, key: int, widget: QWidget) -> bool:
        logger.debug(
            "[nav-tab] navigate key=%s widget=%s",
            key, type(widget).__name__,
        )
        # Left/Right are handled by _AdaptiveTabBar itself — don't consume
        # them here.  Down yields to the session picker below.
        # Up yields so NavigationManager can hand off to the title bar.
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


class ToolbarRowsSection:
    """Up/Down between toolbar rows, Left/Right between buttons in a row.

    ``NavigationManager`` leaves Left/Right to native widget handling by
    default (QTabBar, QSpinBox, ...) — this section opts back in via
    ``extra_keys`` so arrow navigation is symmetric: Down/Up cross rows,
    Left/Right move within the current row's focusable buttons, skipping
    disabled/hidden ones by construction (``_focusable`` already filters
    them out, so stepping to index ± 1 in that list can never land on one).

    A tab's canvas/sliders are deliberately never covered by ``rows_provider``
    — those already bind arrows to pan/value-adjustment when focused, and
    claiming them here would steal that behavior (see image_compare's
    ``canvas/interaction.py`` and slider Find Action wiring).
    """

    def __init__(
        self,
        rows_provider: Callable[[], list[QWidget | None]],
        *,
        tag: str = "toolbar-rows",
    ) -> None:
        self._rows_provider = rows_provider
        self._tag = tag

    def _rows(self) -> list[QWidget]:
        return [r for r in self._rows_provider() if r is not None and r.isVisible()]

    def _row_of(self, widget: QWidget) -> QWidget | None:
        for row in self._rows():
            if row is widget or row.isAncestorOf(widget):
                return row
        return None

    def owns(self, widget: QWidget) -> bool:
        return self._row_of(widget) is not None

    @staticmethod
    def _focusable(row: QWidget) -> list[QWidget]:
        return [
            c for c in row.findChildren(QWidget)
            if (
                c.focusPolicy() == Qt.FocusPolicy.StrongFocus
                and c.isVisible() and c.isEnabled()
            )
        ]

    def _focus_first_in(self, row: QWidget) -> bool:
        items = self._focusable(row)
        if not items:
            return False
        items[0].setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def _focus_near_in(self, row: QWidget, reference: QWidget) -> bool:
        """Like ``_focus_first_in``, but land on the item horizontally
        closest to ``reference`` on screen, instead of always the first.

        This is the standard 2D directional-navigation rule (tvOS Focus
        Engine, Windows XYFocus, W3C CSS Spatial Navigation, Netflix's TV
        UI): moving Down/Up focuses the nearest candidate in that
        direction rather than a fixed index, so focus lands roughly
        under/above where the user actually was.
        """
        items = self._focusable(row)
        if not items:
            return False
        ref_x = reference.mapToGlobal(reference.rect().center()).x()
        target = min(
            items,
            key=lambda w: abs(w.mapToGlobal(w.rect().center()).x() - ref_x),
        )
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def navigate(self, key: int, widget: QWidget) -> bool:
        rows = self._rows()
        row = self._row_of(widget)
        if row is None or row not in rows:
            return False
        idx = rows.index(row)
        logger.debug(
            "[nav-%s] navigate key=%s widget=%s row_idx=%d/%d",
            self._tag, key, type(widget).__name__, idx, len(rows),
        )
        if key == Qt.Key.Key_Down:
            if idx < len(rows) - 1:
                return self._focus_near_in(rows[idx + 1], widget)
            # Last row — yield (e.g. canvas/no further row below).
            return False
        if key == Qt.Key.Key_Up:
            if idx > 0:
                return self._focus_near_in(rows[idx - 1], widget)
            # First row — yield so NavigationManager can hand off upward
            # (title bar / tab strip).
            return False
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            items = self._focusable(row)
            if widget not in items:
                return False
            cur = items.index(widget)
            step = 1 if key == Qt.Key.Key_Right else -1
            target = cur + step
            if 0 <= target < len(items):
                items[target].setFocus(Qt.FocusReason.OtherFocusReason)
            # Row edge: consume anyway (don't fall through to native
            # handling, which does nothing for a plain Button) rather than
            # wrap into an adjacent row — Up/Down already own row transitions.
            return True
        return False

    def focus_first(self) -> bool:
        rows = self._rows()
        return bool(rows) and self._focus_first_in(rows[0])

    def focus_last(self) -> bool:
        rows = self._rows()
        return bool(rows) and self._focus_first_in(rows[-1])

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})
