"""Gallery card context menu: selection section (ex-HUD) + per-card actions.

Right-click on a card opens a standard toolkit ``ContextMenu`` under the
cursor. Selection actions (Clear / Analyze / Find similar / Compare →)
appear as a titled section only when a non-empty selection exists.
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
    assert "gallery.selection.clear" in ids
    assert "gallery.selection.analyze" in ids
    assert "gallery.selection.find_similar" in ids
    assert "gallery.selection.compare" in ids
    # Per-card actions still present.
    assert "gallery.make_best" in ids
    assert "gallery.reject" in ids
    assert "gallery.compare" in ids


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
        on_clear=lambda: fired.append("clear"),
        on_carry=lambda: fired.append("carry"),
        on_analyze=lambda: fired.append("analyze"),
        on_find_similar=lambda: fired.append("find"),
    )
    trig = captured["on_triggered"]
    trig("gallery.selection.clear", None)
    trig("gallery.selection.compare", None)
    trig("gallery.selection.analyze", None)
    trig("gallery.selection.find_similar", None)
    assert fired == ["clear", "carry", "analyze", "find"]
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
    """Delete must render the list-mode trash icon with danger styling."""
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
                assert a.text == "Delete"
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


def test_track_open_menu_restores_hover_on_hide(monkeypatch) -> None:
    """aboutToHide clears the ref and repaints the highlight."""
    from tabs.image_gallery.ui.card.context_menu import _track_open_menu

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
    card._hover_blue_bar = False
    slots[0]()
    assert getattr(card, "_gallery_open_menu", None) is None
    assert card._hover_blue_bar is True
