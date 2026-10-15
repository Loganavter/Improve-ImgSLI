"""Keyboard interaction on the gallery tab — grid AND list.

Focus navigation, activation, context-menu key, Home/End and
focus-survives-rebuild. Mirrors the working sibling
``tabs.session_picker.recent.items_view`` (``navigate_focus`` /
``activate_focused_card`` / ``_ensure_index_visible`` + focus-preserving
recycle) — cards keep real Qt focus, the toolkit Button ring is the only
focus model.

Red-before/green-after: before GalleryGridView owned its keyboard, a
focused card was a dead end — arrows fell through to ``triage_ui.handle_key``
(selection only, focus never moved), the context-menu key did nothing, and a
rebuild recycled the pool and dropped the keyboard ring.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(n: int) -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/kbd{i}.png"), mtime_ns=i + 1)
        for i in range(n)
    ]


def _shown_widget(qtbot, n: int = 20):
    """A shown gallery with *n* cards (offscreen focus needs a live window)."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    qtbot.waitExposed(w)
    items = _items(n)
    w.rebuild_grid(items)
    QTest.qWait(20)
    return w, w._grid_view, items


def _shown_widget_with_state(qtbot, n: int = 8):
    """Shown gallery whose ``state`` mirror backs triage key actions.

    Storeless widget (``_owner_for_triage`` → itself) with a minimal
    ``SimpleNamespace`` state so Space/Delete can remove pool members.
    """
    w, gv, items = _shown_widget(qtbot, n)
    w.state = SimpleNamespace(
        items=list(items), selected_paths=set(), selected_order=[]
    )
    return w, gv, items


def test_right_arrow_moves_focus_to_next_card(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    first = gv.card_for(items[0].path)
    second = gv.card_for(items[1].path)
    assert first is not None and second is not None
    assert gv.focus_card(first)
    QTest.keyClick(first, Qt.Key.Key_Right)
    QTest.qWait(20)
    assert gv.focused_card() is second


def test_down_arrow_moves_focus_by_row(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    cols = int(gv.grid_columns)
    assert cols >= 1 and len(items) > cols
    first = gv.card_for(items[0].path)
    target = gv.card_for(items[cols].path)
    assert first is not None and target is not None
    assert gv.focus_card(first)
    QTest.keyClick(first, Qt.Key.Key_Down)
    qtbot.waitUntil(lambda: gv.focused_card() is target, timeout=1000)
    QTest.keyClick(target, Qt.Key.Key_Up)
    qtbot.waitUntil(lambda: gv.focused_card() is first, timeout=1000)


def test_home_end_jump_first_last(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    mid = gv.card_for(items[2].path)
    first = gv.card_for(items[0].path)
    last = gv.card_for(items[-1].path)
    assert mid is not None and first is not None and last is not None
    assert gv.focus_card(mid)
    QTest.keyClick(mid, Qt.Key.Key_Home)
    qtbot.waitUntil(lambda: gv.focused_card() is first, timeout=1000)
    QTest.keyClick(first, Qt.Key.Key_End)
    qtbot.waitUntil(lambda: gv.focused_card() is last, timeout=1000)


def test_arrow_from_widget_bootstraps_first_card(qtbot) -> None:
    """Focus on the tab widget (no card yet): an arrow focuses the first card."""
    w, gv, items = _shown_widget(qtbot)
    w.setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.qWait(10)
    QTest.keyClick(w, Qt.Key.Key_Right)
    QTest.qWait(20)
    assert gv.focused_card() is gv.card_for(items[0].path)


def test_enter_activates_focused_card_quick_look(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    opened: list[str] = []
    w.show_quick_look = lambda p: opened.append(str(p))  # type: ignore[method-assign]
    second = gv.card_for(items[1].path)
    assert second is not None
    assert gv.focus_card(second)
    QTest.keyClick(second, Qt.Key.Key_Return)
    QTest.qWait(20)
    assert opened == [str(items[1].path)]


def test_menu_key_opens_focused_card_menu(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    opened: list[str] = []
    gv._on_context_menu = lambda p: opened.append(str(p))  # type: ignore[method-assign]
    third = gv.card_for(items[2].path)
    assert third is not None
    assert gv.focus_card(third)
    QTest.keyClick(third, Qt.Key.Key_Menu)
    QTest.qWait(20)
    assert opened == [str(items[2].path)]


def test_space_does_not_activate_quick_look(qtbot) -> None:
    """Space stays remove-from-view — the Button must not activate the card."""
    w, gv, items = _shown_widget(qtbot)
    opened: list[str] = []
    w.show_quick_look = lambda p: opened.append(str(p))  # type: ignore[method-assign]
    card = gv.card_for(items[0].path)
    assert card is not None
    assert gv.focus_card(card)
    QTest.keyClick(card, Qt.Key.Key_Space)
    # The toolkit Button defers its click by the ripple duration — wait past
    # it so a swallowed-through activation cannot hide here.
    QTest.qWait(420)
    assert opened == []


def test_focus_survives_rebuild(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    second = gv.card_for(items[1].path)
    assert second is not None
    assert gv.focus_card(second)
    w.rebuild_grid(list(items))
    QTest.qWait(20)
    assert gv.focused_card() is gv.card_for(items[1].path)


def test_arrow_navigation_in_list_mode(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    w._on_view_toggled(True)  # list mode
    QTest.qWait(20)
    assert gv._view_mode == "list"
    first = gv.card_for(items[0].path)
    second = gv.card_for(items[1].path)
    assert first is not None and second is not None
    assert gv.focus_card(first)
    QTest.keyClick(first, Qt.Key.Key_Down)
    QTest.qWait(20)
    assert gv.focused_card() is second
    QTest.keyClick(second, Qt.Key.Key_Up)
    QTest.qWait(20)
    assert gv.focused_card() is first


# ---------------------------------------------------------------------------
# Breakage regressions found in the gallery keyboard recon
# ---------------------------------------------------------------------------


def test_focus_survives_removing_the_focused_card(qtbot) -> None:
    """Space on the focused (selected) card must keep keyboard focus alive.

    Pre-fix the focused card was recycled by the rebuild and the ring dropped
    to the hosting widget: the very next arrow bootstrapped back to card 0
    instead of continuing from where the user was. Mirrors
    ``RecentItemsView._restore_focus_after_recycle`` (nearest live card).
    """
    w, gv, items = _shown_widget_with_state(qtbot, 8)
    target = gv.card_for(items[2].path)
    assert target is not None
    w.state.selected_paths = {items[2].path}
    w.state.selected_order = [items[2].path]
    gv.apply_selection({items[2].path})
    assert gv.focus_card(target)

    QTest.keyClick(target, Qt.Key.Key_Space)
    QTest.qWait(60)

    focused = gv.focused_card()
    assert focused is not None, "keyboard focus was dropped by the rebuild"
    # The neighbour that slid into the freed slot keeps the ring (pool cards are
    # rotated by the rebuild, so compare against the post-rebuild lookup).
    assert focused is gv.card_for(items[3].path)


def test_move_focus_at_top_edge_yields(qtbot) -> None:
    """Up at the topmost header (or first row with no header) and Left on the
    first card must not be consumed ("never yours to keep").

    Pre-fix ``move_focus`` kept focus put but still returned ``True``, so the
    key was swallowed and NavigationManager's trial-dispatch (or any ancestor)
    could never take over.
    """
    w, gv, items = _shown_widget(qtbot, 12)
    first = gv.card_for(items[0].path)
    assert first is not None
    assert gv.focus_card(first)
    assert gv.move_focus(Qt.Key.Key_Left) is False
    assert gv.focused_card() is first
    # First Up reaches the topmost header above row 0; Up from there yields.
    assert gv.move_focus(Qt.Key.Key_Up) is True
    top_hdr = gv.focused_header()
    assert top_hdr is not None
    assert gv.move_focus(Qt.Key.Key_Up) is False
    assert gv.focused_header() is top_hdr

    # Header-less flat grid: Up from the first row yields directly.
    gv.rebuild_grid(items)
    QTest.qWait(20)
    flat_first = gv.card_for(items[0].path)
    assert flat_first is not None
    assert gv.focus_card(flat_first)
    assert gv.move_focus(Qt.Key.Key_Up) is False
    assert gv.focused_card() is flat_first


def test_move_focus_at_bottom_edge_yields(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot, 12)
    last = gv.card_for(items[-1].path)
    assert last is not None
    assert gv.focus_card(last)
    assert gv.move_focus(Qt.Key.Key_Down) is False
    assert gv.focused_card() is last


def test_handle_navigation_key_ignores_edge_arrow(qtbot) -> None:
    """An edge arrow must return False (event.ignore), not be swallowed."""
    w, gv, items = _shown_widget(qtbot, 12)
    first = gv.card_for(items[0].path)
    assert first is not None
    assert gv.focus_card(first)
    # Step onto the topmost header, then Up is at the top edge and must yield.
    assert gv.move_focus(Qt.Key.Key_Up) is True
    ev = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier
    )
    assert gv.handle_navigation_key(ev) is False


class _FakeKeyEvent:
    def __init__(self, key: int) -> None:
        self._key = key
        self.accepted = False

    def type(self):
        return QEvent.Type.KeyPress

    def key(self):
        return self._key

    def accept(self):
        self.accepted = True


def test_edge_up_hands_off_to_toolbar_via_trial_dispatch(qtbot, monkeypatch) -> None:
    """NavigationManager trial-dispatch: an unhandled Up at the top edge must
    hand off to the toolbar section above the grid (not be swallowed)."""
    from sli_ui_toolkit.managers import (
        NavigationManager,
        declare_toolbar_navigation,
    )
    import sli_ui_toolkit.ui.managers.navigation_manager as _nm

    w, gv, items = _shown_widget(qtbot, 12)
    # Container rows (the real ``ImageGalleryTab._toolbar_rows`` shape) so the
    # toolbar section is a live neighbour, not an inert bare-control row.
    declare_toolbar_navigation(
        w, [w.toolbar, w.stats_strip], tag="image-gallery-kbd-test"
    )
    mgr = NavigationManager.get_instance()
    mgr.register(gv, gv.nav_section)
    # eventFilter flips the app-wide input-modality flag; restore it so no
    # later test's freshly-shown widget paints a keyboard ring.
    prev_modality = getattr(mgr, "_last_input_keyboard", False)
    try:
        toolbar_sec = next(s for o, s in mgr._sections if o is w)
        calls: list = []
        monkeypatch.setattr(
            toolbar_sec,
            "focus_last",
            lambda ref_x=None, *, reason: (calls.append(reason) or True),
            raising=False,
        )
        first = gv.card_for(items[0].path)
        assert first is not None
        assert gv.focus_card(first)
        # First Up moves from row 0 card to the topmost header above it.
        assert gv.move_focus(Qt.Key.Key_Up) is True
        top_hdr = gv.focused_header()
        assert top_hdr is not None
        monkeypatch.setattr(
            _nm.QApplication, "focusWidget", staticmethod(lambda: top_hdr)
        )
        handled = mgr.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Up))
        assert handled is True
        assert calls, "edge Up was swallowed instead of handed to the toolbar"
    finally:
        mgr._last_input_keyboard = prev_modality  # type: ignore[attr-defined]
        mgr.unregister(gv)
        mgr.unregister(w)


def test_grid_nav_section_owns_cards_only(qtbot) -> None:
    """The registered grid section claims live cards — never the toolbar/host."""
    w, gv, items = _shown_widget(qtbot, 8)
    sec = gv.nav_section
    first = gv.card_for(items[0].path)
    assert first is not None
    assert sec.owns(first) is True
    assert sec.owns(w) is False
    assert sec.owns(w.toolbar) is False
    assert Qt.Key.Key_Left in sec.extra_keys
    assert Qt.Key.Key_Right in sec.extra_keys
    # navigate() drives the same focus mover; focus_first/last back the
    # cross-section entries.
    assert gv.focus_card(gv.card_for(items[1].path))
    assert sec.navigate(Qt.Key.Key_Right, gv.card_for(items[1].path)) is True
    assert gv.focused_card() is gv.card_for(items[2].path)
    assert sec.focus_last(reason=Qt.FocusReason.OtherFocusReason) is True
    assert gv.focused_card() is gv.card_for(items[-1].path)


def test_tab_registers_grid_section_and_container_rows(qtbot) -> None:
    """``ImageGalleryTab._register_nav_section`` wires BOTH sections and the
    toolbar rows are containers (a bare control is an inert row)."""
    from sli_ui_toolkit.managers import NavigationManager

    from tabs.contract import TabContext
    from tabs.image_gallery.tab import ImageGalleryTab

    tab = ImageGalleryTab()
    parent = QWidget()
    qtbot.addWidget(parent)
    page = tab.create_page(parent, TabContext())
    qtbot.addWidget(page)
    w = tab._widget
    assert w is not None and w._grid_view is not None

    rows = [r for r in tab._toolbar_rows() if r is not None]
    assert w.toolbar in rows
    assert w._filter_edit not in rows
    assert w._pick_button not in rows

    mgr = NavigationManager.get_instance()
    tab._register_nav_section()
    try:
        owners = [o for o, _s in mgr._sections]
        assert w in owners
        assert w._grid_view in owners
    finally:
        mgr.unregister(w._grid_view)
        mgr.unregister(w)


def test_host_keypress_bootstraps_first_card(qtbot) -> None:
    """A bare arrow on the grid host (no card focused yet) enters the grid —
    the OverlayScrollArea viewport would otherwise swallow it."""
    w, gv, items = _shown_widget(qtbot, 12)
    assert gv.focused_card() is None
    QTest.keyClick(gv.items_host, Qt.Key.Key_Right)
    QTest.qWait(20)
    assert gv.focused_card() is gv.card_for(items[0].path)


def test_rebuild_series_restores_focus_reason_not_literal(qtbot) -> None:
    """Series regroup must re-grant focus through the keyboard-aware reason.

    Pre-fix the surgical reconcile used a bare ``setFocus()`` (implicit
    ``OtherFocusReason``), which lights the ring even for mouse-originated
    rebuilds.
    """
    w, gv, items = _shown_widget(qtbot, 8)
    target = gv.card_for(items[4].path)
    assert target is not None
    assert gv.focus_card(target)
    seen: list = []
    orig = gv._focus_reason

    def _spy():
        reason = orig()
        seen.append(reason)
        return reason

    gv._focus_reason = _spy  # type: ignore[method-assign]
    gv.set_series([list(items)], hub_names=[None], collapsed={})
    QTest.qWait(20)
    gv._focus_reason = orig  # type: ignore[method-assign]
    assert seen, "series regroup did not route focus through _focus_reason()"


def test_empty_grid_area_is_owned_and_a_key_reaches_a_card(qtbot) -> None:
    """Clicking the empty zone below the cards must not kill navigation.

    Regression: a click on the grid host realigned the ring onto the scroll
    area, which owned no section — arrows were "reveal-only" and nothing was
    reachable. The grid section now owns the scroll subtree, so a key from
    there reaches a live card.
    """
    from tabs.image_gallery.ui.grid_view import GalleryGridNavSection

    w, gv, items = _shown_widget(qtbot, 6)
    section = GalleryGridNavSection(gv)
    assert section.owns(gv.scroll_area) is True

    gv.scroll_area.setFocus(Qt.FocusReason.MouseFocusReason)
    QTest.qWait(10)
    assert section.navigate(Qt.Key.Key_Down, gv.scroll_area) is True
    assert gv.focused_card() is not None


def test_up_from_first_card_reaches_series_header_and_enter_collapses(qtbot) -> None:
    """Up from the first card of a series block focuses its header Button;
    Enter/Space toggles collapse/expand and keeps focus sane."""
    from sli_ui_toolkit.widgets import Button

    w, gv, items = _shown_widget(qtbot, 8)
    gv.set_series([items[:4], items[4:]], hub_names=["A", "B"], collapsed={})
    QTest.qWait(20)

    hdr0 = gv.findChild(Button, "GallerySeriesHeaderBtn_0")
    first = gv.card_for(items[0].path)
    assert hdr0 is not None and first is not None
    assert gv.focus_card(first)

    # Up from first card of Series 0 -> Series 0 header
    QTest.keyClick(first, Qt.Key.Key_Up)
    QTest.qWait(20)
    assert QApplication.focusWidget() is hdr0
    assert gv.focused_header() is hdr0

    # Up at topmost header yields (False) so NavigationManager can hand off upward
    assert gv.move_focus(Qt.Key.Key_Up) is False
    # Left/Right on a full-width header yield at row edges without wrapping
    assert gv.move_focus(Qt.Key.Key_Left) is False
    assert gv.move_focus(Qt.Key.Key_Right) is False
    assert QApplication.focusWidget() is hdr0

    # Down from Series 0 header -> first card of Series 0
    QTest.keyClick(hdr0, Qt.Key.Key_Down)
    QTest.qWait(20)
    assert gv.focused_card() is first

    # Up back to Series 0 header, then Enter collapses Series 0
    QTest.keyClick(first, Qt.Key.Key_Up)
    QTest.qWait(20)
    assert QApplication.focusWidget() is hdr0
    QTest.keyClick(hdr0, Qt.Key.Key_Return)
    QTest.qWait(20)
    assert gv._collapsed.get(0) is True
    assert gv.card_for(items[0].path) is None
    assert QApplication.focusWidget() is hdr0

    # Space on focused header expands Series 0 back
    QTest.keyClick(hdr0, Qt.Key.Key_Space)
    QTest.qWait(20)
    assert gv._collapsed.get(0) is False
    assert gv.card_for(items[0].path) is not None
    assert QApplication.focusWidget() is hdr0


def test_series_and_ungrouped_tail_header_navigation(qtbot) -> None:
    """Second series header and UNGROUPED tail header are reachable via Up/Down."""
    from sli_ui_toolkit.widgets import Button

    w, gv, items = _shown_widget(qtbot, 6)
    gv.set_series([items[:2], items[2:4]], hub_names=["A", "B"], collapsed={})
    QTest.qWait(20)

    hdr1 = gv.findChild(Button, "GallerySeriesHeaderBtn_1")
    tail_hdr = gv.findChild(Button, "GallerySeriesHeader_ungrouped_btn")
    s1_first = gv.card_for(items[2].path)
    tail_first = gv.card_for(items[4].path)
    assert hdr1 is not None and tail_hdr is not None
    assert s1_first is not None and tail_first is not None

    # Up from first card of Series 1 -> Series 1 header; Down -> back to first card
    assert gv.focus_card(s1_first)
    QTest.keyClick(s1_first, Qt.Key.Key_Up)
    QTest.qWait(20)
    assert QApplication.focusWidget() is hdr1
    QTest.keyClick(hdr1, Qt.Key.Key_Down)
    QTest.qWait(20)
    assert gv.focused_card() is s1_first

    # Up from first card of ungrouped tail -> tail header; Down -> first tail card
    assert gv.focus_card(tail_first)
    QTest.keyClick(tail_first, Qt.Key.Key_Up)
    QTest.qWait(20)
    assert QApplication.focusWidget() is tail_hdr
    QTest.keyClick(tail_hdr, Qt.Key.Key_Down)
    QTest.qWait(20)
    assert gv.focused_card() is tail_first


def _banded_gallery(qtbot):
    """Wide viewport + one series -> left section and UNGROUPED tail side by side."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    qtbot.waitExposed(w)
    items = _items(27)
    w.rebuild_grid(items)
    qtbot.wait(400)  # let the debounced adaptive reflow settle
    gv = w._grid_view
    gv.set_series([items[:25]], hub_names=["HUB-A"], collapsed={})
    QTest.qWait(40)
    assert gv._band_state is not None, "expected a side-by-side banded layout"
    return gv, int(gv._band_state[2])


def test_banded_down_reaches_the_right_band(qtbot) -> None:
    """Side-by-side bands are one vertical strip: Down must not dead-end at
    the left band's bottom row.

    Falsification (pre-repair): block-scoped Up/Down treated every band as a
    closed strip, so ``Down`` at the left band's last row returned ``False``
    and the right band became keyboard-unreachable.
    """
    gv, sep_col = _banded_gallery(qtbot)
    cards = gv._live_cards_in_order()
    assert gv.focus_card(cards[0])

    reached_right = False
    for _ in range(60):
        if gv.move_focus(Qt.Key.Key_Down) is not True:
            break
        card = gv.focused_card()
        if card is None:  # focus parked on a series/tail header — keep walking
            continue
        idx = gv.items_layout.indexOf(card)
        if idx >= 0 and int(gv.items_layout.getItemPosition(idx)[1]) >= sep_col:
            reached_right = True
    assert reached_right, "Down dead-ended at the left band"


def test_banded_up_reaches_the_left_band(qtbot) -> None:
    """Walking Up from the bottom card must climb back through the right band
    into the left one instead of yielding at the band boundary.

    Parity guard, not a falsification test: pre-repair the flat index
    arithmetic happened to cross the boundary too. It pins that the
    block-scoped Up keeps doing so after the band-crossing repair.
    """
    gv, sep_col = _banded_gallery(qtbot)
    cards = gv._live_cards_in_order()
    assert gv.focus_card(cards[-1])

    reached_left = False
    for _ in range(60):
        if gv.move_focus(Qt.Key.Key_Up) is not True:
            break
        card = gv.focused_card()
        if card is None:
            continue
        idx = gv.items_layout.indexOf(card)
        if idx >= 0 and int(gv.items_layout.getItemPosition(idx)[1]) < sep_col:
            reached_left = True
    assert reached_left, "Up dead-ended at the right band"

