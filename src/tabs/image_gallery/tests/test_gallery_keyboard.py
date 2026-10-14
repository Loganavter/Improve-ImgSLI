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

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

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
    QTest.qWait(20)
    assert gv.focused_card() is target
    QTest.keyClick(target, Qt.Key.Key_Up)
    QTest.qWait(20)
    assert gv.focused_card() is first


def test_home_end_jump_first_last(qtbot) -> None:
    w, gv, items = _shown_widget(qtbot)
    mid = gv.card_for(items[2].path)
    first = gv.card_for(items[0].path)
    last = gv.card_for(items[-1].path)
    assert mid is not None and first is not None and last is not None
    assert gv.focus_card(mid)
    QTest.keyClick(mid, Qt.Key.Key_Home)
    QTest.qWait(20)
    assert gv.focused_card() is first
    QTest.keyClick(first, Qt.Key.Key_End)
    QTest.qWait(20)
    assert gv.focused_card() is last


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
