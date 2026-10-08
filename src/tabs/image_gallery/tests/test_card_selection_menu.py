"""Gallery card context menu: selection section (ex-HUD) + per-card actions.

Right-click on a card opens a standard toolkit ``ContextMenu`` under the
cursor. Selection actions (Analyze / Find similar)
appear as a titled section only when a non-empty selection exists.
Deselect is Esc, never a menu entry. Compare actions were removed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.ui.card.context_menu import (
    _selection_count,
    _selection_label,
    popup_gallery_card_context_menu,
)


def _owner(selected: set[Path], mode=None) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(selected_paths=set(selected), mode=mode),
    )


def test_selection_label() -> None:
    assert _selection_label(None, 0) == "No selection"
    assert _selection_label(None, 1) == "1 selected"
    assert _selection_label(None, 2) == "2 selected"


def test_selection_count_empty() -> None:
    assert _selection_count(_owner(set())) == 0
    assert _selection_count(_owner({Path("/a.png"), Path("/b.png")})) == 2
    assert _selection_count(SimpleNamespace()) == 0


def _capture_menu(monkeypatch):
    """Capture menu entries + on_triggered without showing UI.

    Primary path is ``ui.context_menu.manager.open_context_menu_entries``
    (popup surface); the direct-``ContextMenu`` fallback is patched too.
    """
    import sli_ui_toolkit.widgets as _w
    import ui.context_menu.manager as _mgr

    captured: dict = {}

    class _FakeMenu:
        def __init__(self, parent, *, entries=(), on_triggered=None, **kwargs):
            captured["entries"] = tuple(entries)
            captured["on_triggered"] = on_triggered

        def popup_at(self, pos):
            captured["popup_at"] = pos

        def show(self):
            captured["shown"] = True

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        captured["key"] = key
        captured["source_widget"] = source_widget
        return _FakeMenu(source_widget, entries=entries, on_triggered=on_triggered)

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    monkeypatch.setattr(_w, "ContextMenu", _FakeMenu)
    return captured


def _action_ids(entries) -> list[str]:
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    ids: list[str] = []
    for e in entries:
        if isinstance(e, ContextMenuSection):
            ids.extend(a.action_id for a in e.entries)
        elif isinstance(e, ContextMenuAction):
            ids.append(e.action_id)
    return ids


def test_menu_with_selection_has_selection_section(monkeypatch) -> None:
    captured = _capture_menu(monkeypatch)
    owner = _owner({Path("/a.png"), Path("/b.png")})
    card = SimpleNamespace()
    popup_gallery_card_context_menu(
        card, owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    ids = _action_ids(captured["entries"])
    assert "gallery.selection.analyze" in ids
    assert "gallery.selection.find_similar" in ids
    assert "gallery.selection.compare" not in ids
    # No deselect entry — Esc owns that; menus act ON the set.
    assert "gallery.selection.clear" not in ids
    # Per-card actions still present — Compare removed from this menu.
    assert "gallery.make_best" in ids
    assert "gallery.reject" in ids
    assert "gallery.compare" not in ids


def test_menu_without_selection_has_no_selection_section(monkeypatch) -> None:
    captured = _capture_menu(monkeypatch)
    owner = _owner(set())
    card = SimpleNamespace()
    popup_gallery_card_context_menu(
        card, owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    ids = _action_ids(captured["entries"])
    assert not [i for i in ids if i.startswith("gallery.selection.")]
    assert "gallery.make_best" in ids
    assert "gallery.compare" not in ids


def test_make_source_available_in_every_mode(monkeypatch) -> None:
    """'Make source' shows regardless of mode (camera included), labelled so."""
    from tabs.image_gallery.models import Mode

    for mode in (None, Mode.CAMERA, Mode.FIDELITY, Mode.BATCH_SYNTHETIC):
        captured = _capture_menu(monkeypatch)
        owner = _owner({Path("/a.png")}, mode=mode)
        popup_gallery_card_context_menu(
            SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=1,
        )
        ids = _action_ids(captured["entries"])
        assert "gallery.set_as_source" in ids, mode
        assert _action_text(captured["entries"], "gallery.set_as_source") == "Make source"


def test_selection_callbacks_fire(monkeypatch) -> None:
    captured = _capture_menu(monkeypatch)
    fired: list[str] = []
    owner = _owner({Path("/a.png")})
    card = SimpleNamespace()
    popup_gallery_card_context_menu(
        card,
        owner,
        Path("/a.png"),
        global_pos=None,
        selection_count=1,
        on_carry=lambda: fired.append("carry"),
        on_analyze=lambda: fired.append("analyze"),
        on_find_similar=lambda: fired.append("find"),
    )
    trig = captured["on_triggered"]
    trig("gallery.selection.analyze", None)
    trig("gallery.selection.find_similar", None)
    assert fired == ["analyze", "find"]
def _owner_with_items(selected, items, order=None):
    st = SimpleNamespace(selected_paths=set(selected), items=list(items))
    if order is not None:
        st.selected_order = list(order)
    return SimpleNamespace(state=st)


def _triage_item(p, rejected=False):
    return SimpleNamespace(path=Path(p), rejected=rejected, triage_rejected=rejected)


def test_group_reject_sets_all_selected(monkeypatch) -> None:
    """Clicked-inside-selection Reject hits every selected card, uniformly."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_items(
        {Path("/a.png"), Path("/b.png")},
        [_triage_item("/a.png"), _triage_item("/b.png")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    captured["on_triggered"]("gallery.reject", None)
    flags = {str(it.path): it.rejected for it in owner.state.items}
    assert flags == {"/a.png": True, "/b.png": True}


def test_group_reject_unrejects_when_all_rejected(monkeypatch) -> None:
    """All-rejected + Reject → all unrejected (uniform, not per-item flip)."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_items(
        {Path("/a.png"), Path("/b.png")},
        [_triage_item("/a.png", True), _triage_item("/b.png", True)],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    captured["on_triggered"]("gallery.reject", None)
    flags = {str(it.path): it.rejected for it in owner.state.items}
    assert flags == {"/a.png": False, "/b.png": False}


def test_click_outside_selection_acts_single(monkeypatch) -> None:
    """Right-click outside the set touches only the clicked card."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_items(
        {Path("/a.png"), Path("/b.png")},
        [_triage_item("/a.png"), _triage_item("/b.png"), _triage_item("/c.png")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/c.png"), global_pos=None, selection_count=2,
    )
    captured["on_triggered"]("gallery.reject", None)
    flags = {str(it.path): it.rejected for it in owner.state.items}
    assert flags == {"/a.png": False, "/b.png": False, "/c.png": True}


def test_group_remove_uses_batch(monkeypatch) -> None:
    """Remove with selection → remove_paths_from_grid; single → remove_from_grid."""
    from tabs.image_gallery.use_cases import triage as _triage

    captured = _capture_menu(monkeypatch)
    calls: list = []
    monkeypatch.setattr(
        _triage, "remove_paths_from_grid",
        lambda o, ps: calls.append(("batch", sorted(str(p) for p in ps))) or 2,
    )
    monkeypatch.setattr(
        _triage, "remove_from_grid",
        lambda o, p: calls.append(("single", str(p))) or True,
    )
    owner = _owner({Path("/a.png"), Path("/b.png")})
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    captured["on_triggered"]("gallery.remove", None)
    assert calls == [("batch", ["/a.png", "/b.png"])]

    calls.clear()
    owner = _owner(set())
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    captured["on_triggered"]("gallery.remove", None)
    assert calls == [("single", "/a.png")]


def test_group_make_best_loops_selection(monkeypatch) -> None:
    """Make best with selection → per-target call each (own-series best)."""
    from tabs.image_gallery.use_cases import triage as _triage

    captured = _capture_menu(monkeypatch)
    calls: list = []
    monkeypatch.setattr(
        _triage, "make_best", lambda o, p: calls.append(str(p)) or True
    )
    owner = _owner({Path("/a.png"), Path("/b.png")})
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    captured["on_triggered"]("gallery.make_best", None)
    assert sorted(calls) == ["/a.png", "/b.png"]


def _action_text(entries, action_id: str) -> str:
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    for e in entries:
        items = e.entries if isinstance(e, ContextMenuSection) else (e,)
        for a in items:
            if isinstance(a, ContextMenuAction) and a.action_id == action_id:
                return a.text
    raise AssertionError(f"{action_id} entry missing")


def test_reject_label_tracks_state(monkeypatch) -> None:
    """All targets rejected → Unreject; else (incl. mixed) → Reject."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_items(
        {Path("/a.png"), Path("/b.png")},
        [_triage_item("/a.png", True), _triage_item("/b.png", True)],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    assert _action_text(captured["entries"], "gallery.reject") == "↩ Unreject"

    owner = _owner_with_items(
        {Path("/a.png"), Path("/b.png")},
        [_triage_item("/a.png", True), _triage_item("/b.png")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    assert _action_text(captured["entries"], "gallery.reject") == "✕ Reject"

    owner = _owner_with_items(set(), [_triage_item("/a.png", True)])
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    assert _action_text(captured["entries"], "gallery.reject") == "↩ Unreject"

    owner = _owner_with_items(set(), [_triage_item("/a.png")])
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    assert _action_text(captured["entries"], "gallery.reject") == "✕ Reject"


def test_remove_action_calls_remove_from_grid(monkeypatch) -> None:
    """Ex-delete-badge: 'Remove from view' removes the card, file stays."""
    from tabs.image_gallery.use_cases import triage as _triage

    captured = _capture_menu(monkeypatch)
    removed: list[str] = []
    monkeypatch.setattr(
        _triage, "remove_from_grid", lambda o, p: removed.append(str(p)) or True
    )
    owner = _owner(set())
    card = SimpleNamespace()
    popup_gallery_card_context_menu(
        card, owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    trig = captured["on_triggered"]
    trig("gallery.remove", None)
    assert removed == ["/a.png"]
def test_remove_action_has_icon(monkeypatch) -> None:
    """Remove-from-view must render the list-mode trash icon with danger styling."""
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    captured = _capture_menu(monkeypatch)
    owner = _owner(set())
    popup_gallery_card_context_menu(
        card=SimpleNamespace(), owner=owner, path=Path("/a.png"),
        global_pos=None, selection_count=0,
    )
    for e in captured["entries"]:
        items = e.entries if isinstance(e, ContextMenuSection) else (e,)
        for a in items:
            if isinstance(a, ContextMenuAction) and a.action_id == "gallery.remove":
                assert a.text == "Remove from view"
                assert a.icon == "delete", "list-mode trash parity"
                assert a.danger is True
                return
    raise AssertionError("gallery.remove entry missing")


def _hover_card():
    return SimpleNamespace(
        _hover_blue_bar=False,
        _gallery_item=SimpleNamespace(path=Path("/a.png")),
        update=lambda: None,
        setShowUnderline=lambda _v: None,
    )


def _leave_event():
    from PySide6.QtCore import QEvent

    return SimpleNamespace(type=lambda: QEvent.Type.Leave)


def _hover_filter_for(card):
    from tabs.image_gallery.ui.card.hover import _CardHoverFilter

    filt = _CardHoverFilter.__new__(_CardHoverFilter)
    filt._card = card
    filt._owner = None
    return filt


def test_leave_keeps_hover_while_menu_open() -> None:
    """Popup steals the mouse (card gets Leave) — underline must stay."""
    card = _hover_card()
    card._hover_blue_bar = True
    card._gallery_open_menu = SimpleNamespace(isVisible=lambda: True)
    filt = _hover_filter_for(card)
    filt.eventFilter(card, _leave_event())
    assert card._hover_blue_bar is True


def test_leave_hides_after_menu_closed_and_cleans_ref() -> None:
    """Stale menu refs are dropped and the normal hide path resumes."""
    card = _hover_card()
    card._hover_blue_bar = True
    card._gallery_open_menu = SimpleNamespace(isVisible=lambda: False)
    filt = _hover_filter_for(card)
    filt.eventFilter(card, _leave_event())
    assert card._hover_blue_bar is False
    assert getattr(card, "_gallery_open_menu", None) is None


def test_track_open_menu_hide_clears_bar() -> None:
    """aboutToHide clears the ref and always drops the bar (no cursor poll).

    Regression: the old hide path re-derived hover from ``QCursor.pos()``,
    which lies on Wayland at ``aboutToHide`` — the bar came back on after
    *any* menu close (stuck-ON). Real hover is re-established by Qt's own
    Enter/Leave once the popup is gone.
    """
    from tabs.image_gallery.ui.card.menu_track import track_open_menu as _track_open_menu

    card = _hover_card()
    slots: list = []

    class _FakeSignal:
        def connect(self, slot):
            slots.append(slot)

    menu = SimpleNamespace(isVisible=lambda: True, aboutToHide=_FakeSignal())
    _track_open_menu(card, menu)
    assert getattr(card, "_gallery_open_menu", None) is menu
    assert card._hover_blue_bar is True  # forced on while menu open
    assert len(slots) == 1

    card._hover_blue_bar = True
    slots[0]()
    assert getattr(card, "_gallery_open_menu", None) is None
    assert card._hover_blue_bar is False


def test_card_menu_has_no_sort_view_sections(monkeypatch) -> None:
    """Sort by / View live in the empty-canvas menu (FM background menu),
    never in the per-card menu."""
    captured = _capture_menu(monkeypatch)
    owner = _owner(set())
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    ids = _action_ids(captured["entries"])
    assert "gallery.sort_by" not in ids
    assert "gallery.view" not in ids


def _submenu(entry_id: str, entries):
    from sli_ui_toolkit.widgets import ContextMenuAction

    for e in entries:
        if isinstance(e, ContextMenuAction) and e.action_id == entry_id:
            return e
    raise AssertionError(f"submenu {entry_id} not found")


def test_empty_menu_sort_view_present_and_checked(monkeypatch) -> None:
    import ui.context_menu.manager as _mgr
    from tabs.image_gallery.ui.card.sort_view_menu import popup_empty_context_menu

    captured: dict = {}

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        return SimpleNamespace()

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    fired: list = []
    popup_empty_context_menu(
        SimpleNamespace(), None, None, 1, lambda i: fired.append(("sort", i)),
        True, lambda b: fired.append(("view", b)),
    )
    sort_menu = _submenu("gallery.sort_by", captured["entries"])
    assert [a.action_id for a in sort_menu.children] == [
        "gallery.sort.rank", "gallery.sort.name", "gallery.sort.date", "gallery.sort.quality",
    ]
    assert [a.checked for a in sort_menu.children] == [False, True, False, False]
    view_menu = _submenu("gallery.view", captured["entries"])
    assert [(a.action_id, a.checked) for a in view_menu.children] == [
        ("gallery.view.grid", False), ("gallery.view.list", True),
    ]
    captured["on_triggered"]("gallery.sort.date", 2)
    captured["on_triggered"]("gallery.view.list", True)
    assert fired == [("sort", 2), ("view", True)]


def test_empty_host_right_press_opens_background_menu(qtbot) -> None:
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.wait(50)
    fired: list = []
    view.configure(on_empty_context_menu=lambda gp: fired.append(gp))
    host = view.items_host
    empty = QPoint(host.width() - 30, host.height() - 30)
    assert host.childAt(empty) is None
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(empty), QPointF(host.mapToGlobal(empty)),
        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert view.eventFilter(host, press) is True
    assert len(fired) == 1


def test_menu_has_ungroup_entry(monkeypatch) -> None:
    """Explicit path to UNGROUPED when no tail section exists to drop onto."""
    captured = _capture_menu(monkeypatch)
    owner = _owner({Path("/a.png")})
    card = SimpleNamespace()
    popup_gallery_card_context_menu(
        card, owner, Path("/a.png"), global_pos=None, selection_count=1,
    )
    assert "gallery.ungroup" in _action_ids(captured["entries"])


def test_ungroup_moves_whole_selection_to_none(monkeypatch) -> None:
    from tabs.image_gallery.ui.card import context_actions as _actions

    calls: list = []
    owner = SimpleNamespace(
        state=SimpleNamespace(
            selected_paths={Path("/a.png"), Path("/b.png")},
            selected_order=[Path("/b.png"), Path("/a.png")],
        ),
        move_paths_to_series=lambda ps, sid: calls.append((list(ps), sid)) or 2,
    )
    assert _actions._ctx_ungroup(owner, Path("/a.png")) == 2
    assert calls == [([Path("/b.png"), Path("/a.png")], None)]


def test_ungroup_without_controller_is_noop() -> None:
    from tabs.image_gallery.ui.card import context_actions as _actions

    owner = _owner({Path("/a.png")})
    assert _actions._ctx_ungroup(owner, Path("/a.png")) == 0


def test_card_menu_parent_is_card_not_window(qapp, monkeypatch) -> None:
    """Regression (inv-2026-10-06 ql-rhi-menu-first): the popup must be
    parented to the CARD, never the top-level window. A ``Qt.Popup`` whose
    QWidget parent is the MainWindow breaks Wayland compositing for the whole
    window (in-window translucency -> black, fresh QRhiWidget mint fails).
    MC parents to its canvas, IC to its flyout; gallery must parent to the card.
    """
    from PySide6.QtWidgets import QWidget

    captured = _capture_menu(monkeypatch)
    window = QWidget()
    card = QWidget(window)
    try:
        owner = _owner(set())
        popup_gallery_card_context_menu(card, owner, Path("/a.png"), global_pos=None)
        assert captured.get("source_widget") is card
        assert captured.get("source_widget") is not card.window()
    finally:
        window.close()
