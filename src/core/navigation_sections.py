"""Concrete ``NavigationSection`` implementations for the host shell.

``SessionPickerSection`` navigates the create-cards list in the session
picker page.  ``TabStripSection`` owns the workspace tab bar and delegates
Left/Right to ``_AdaptiveTabBar``'s native handling (our event filter never
sees those keys because the tab bar consumes them first).

The generic row-navigation section used by workspace tabs
(``ToolbarRowsSection``) has no app-specific logic and lives in
sli-ui-toolkit instead — import it from ``sli_ui_toolkit.managers``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import widget_label

logger = logging.getLogger("ImproveImgSLI")


def _focus_reason() -> Qt.FocusReason:
    try:
        from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

        if not NavigationManager.get_instance().last_input_was_keyboard():
            return Qt.FocusReason.MouseFocusReason
    except Exception:
        pass
    return Qt.FocusReason.OtherFocusReason


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
            key, widget_label(widget), card_idx, len(cards),
        )

        if key == Qt.Key.Key_Down:
            if card_idx is None:
                if cards:
                    logger.debug(
                        "[nav-card] Down from non-card → first card (%s)",
                        widget_label(cards[0][1]),
                    )
                    cards[0][1].setFocus(_focus_reason())
                    return True
            elif card_idx < len(cards) - 1:
                logger.debug(
                    "[nav-card] Down card[%d] → card[%d]", card_idx, card_idx + 1
                )
                cards[card_idx + 1][1].setFocus(_focus_reason())
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
                cards[card_idx - 1][1].setFocus(_focus_reason())
                return True
            # At first card — yield so NavigationManager can hand off to
            # the tab strip (the section above).
            logger.debug("[nav-card] Up from first card → yield to tab strip")
            return False

        # Left/Right: single-column list, nothing horizontal to navigate.
        return True

    def focus_first(self, ref_x: float | None = None) -> bool:
        # Single-column list: x doesn't distinguish anything, ref_x unused.
        cards = self._page._card_entries()
        if cards:
            cards[0][1].setFocus(_focus_reason())
            return True
        return False

    def focus_last(self, ref_x: float | None = None) -> bool:
        cards = self._page._card_entries()
        if cards:
            cards[-1][1].setFocus(_focus_reason())
            return True
        return False

    def focus_nearest(self, pos) -> bool:
        """Land on the nearest focusable widget to *pos* within the page.

        Uses owner-local coordinates (``mapTo``) for reliable comparison
        regardless of window state.  Searches all focusable descendants
        but excludes container widgets that themselves contain focusable
        children (scroll areas, panels — not navigation targets).
        """
        local_pos = self._page.mapFromGlobal(pos)
        local_y = local_pos.y()
        all_focusable = set()
        for w in self._page.findChildren(QWidget):
            if (
                w.focusPolicy() != Qt.FocusPolicy.NoFocus
                and w.isVisible()
                and w.isEnabled()
            ):
                all_focusable.add(w)
        candidates = []
        for w in all_focusable:
            children_focusable = any(
                c in all_focusable
                for c in w.findChildren(QWidget)
                if c is not w
            )
            if not children_focusable:
                candidates.append(w)
        if not candidates:
            return False
        best = min(
            candidates,
            key=lambda w: abs(
                w.mapTo(self._page, w.rect().center()).y() - local_y
            ),
        )
        best.setFocus(_focus_reason())
        return True


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
            key, widget_label(widget),
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
            add_btn.setFocus(_focus_reason())
            return True
        self._tab_strip.setFocus(_focus_reason())
        return True

    def _focus_tab_bar(self, ref_x: float | None) -> bool:
        # Land on the actual tab bar (not the wrapper strip) so its own
        # Left/Right/Home/End handling (_AdaptiveTabBar.keyPressEvent)
        # becomes reachable. setFocus() on ClickFocus still works for an
        # explicit call -- only Tab-key traversal / click-to-focus
        # semantics are affected.
        tab_bar = getattr(self._tab_strip, "tab_bar", None)
        if tab_bar is None:
            return False
        if ref_x is not None:
            count = len(getattr(tab_bar, "_tabs", None) or [])
            if count:
                from PySide6.QtCore import QPoint

                local_x = tab_bar.mapFromGlobal(QPoint(int(ref_x), 0)).x()
                idx = tab_bar.tabAt(QPoint(int(local_x), tab_bar.height() // 2))
                if idx < 0:
                    idx = 0 if local_x < 0 else count - 1
                tab_bar.setCurrentIndex(idx)
        tab_bar.setFocus(_focus_reason())
        return True

    def _focus_nearest(self, ref_x: float) -> bool:
        # Coordinate-aware cross-section entry: whichever real control
        # (tab bar vs. add button) sits closer to ref_x on screen, instead
        # of always jumping to one fixed end regardless of where the user
        # actually was.
        tab_bar = getattr(self._tab_strip, "tab_bar", None)
        add_btn = getattr(self._tab_strip, "add_button", None)
        add_visible = add_btn is not None and add_btn.isVisible()
        if tab_bar is None:
            return self._focus_add_button() if add_visible else False
        if not add_visible:
            return self._focus_tab_bar(ref_x)
        tab_bar_x = tab_bar.mapToGlobal(tab_bar.rect().center()).x()
        add_x = add_btn.mapToGlobal(add_btn.rect().center()).x()
        if abs(add_x - ref_x) < abs(tab_bar_x - ref_x):
            return self._focus_add_button()
        return self._focus_tab_bar(ref_x)

    def focus_first(self, ref_x: float | None = None) -> bool:
        # Entering from above (title bar, Down).
        if ref_x is not None:
            return self._focus_nearest(ref_x)
        return self._focus_tab_bar(None) or self._focus_add_button()

    def focus_last(self, ref_x: float | None = None) -> bool:
        # Entering from below (session picker, Up).
        if ref_x is not None:
            return self._focus_nearest(ref_x)
        return self._focus_add_button()


