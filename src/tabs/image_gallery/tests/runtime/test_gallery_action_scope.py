"""Gallery action scope: one target-resolution mechanism for every action.

Regression for the owner report (2026-10-20): context-menu **Analyze** acted
on ONE image of a selected group. Pre-fix that handler did
``next(iter(state.selected_paths))`` — set iteration order, not a scope
decision — so with three selected cards exactly **one arbitrary** path
reached ``analyze_item_by_path``. That red behaviour is asserted here as
"all three" (the pre-fix body fails `test_analyze_applies_to_every_selected_target`
with a call list of length 1; no re-run of the old commit is needed).

Covers the resolver precedence (``use_cases.action_scope``) and the migrated
call sites: popup Analyze, reset-metrics, and the selection read that carry /
keyboard already consume. No app boot: a ``SimpleNamespace`` owner plus the
real popup handler, with the menu-open seam monkeypatched (same seam
``test_card_selection_menu`` uses).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint

from tabs.image_gallery.use_cases import action_scope


def _owner(selected, order=None, items=None, **extra):
    st = SimpleNamespace(
        selected_paths={Path(p) for p in selected},
        selected_order=[Path(p) for p in (order or [])],
        items=list(items or []),
    )
    ns = SimpleNamespace(state=st, **extra)
    return ns


def _capture_menu(monkeypatch):
    """Capture menu entries + on_triggered without showing UI."""
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

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None, **_kwargs):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        return _FakeMenu(source_widget, entries=entries, on_triggered=on_triggered)

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    monkeypatch.setattr(_w, "ContextMenu", _FakeMenu)
    return captured


def _trigger_analyze(monkeypatch, owner, path):
    """Open the real card context menu and run its Analyze action."""
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    captured = _capture_menu(monkeypatch)
    popup_gallery_card_context_menu(
        SimpleNamespace(),
        owner,
        path,
        global_pos=QPoint(0, 0),
        selection_count=len(owner.state.selected_paths),
    )
    captured["on_triggered"]("gallery.selection.analyze", None)
    return captured


def test_analyze_applies_to_every_selected_target(monkeypatch) -> None:
    """RED BEFORE: `next(iter(selected_paths))` analyzed exactly one of three."""
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    analyzed: list[Path] = []
    owner = _owner({a, b, c}, order=[a, b, c])
    owner.analyze_item_by_path = analyzed.append
    _trigger_analyze(monkeypatch, owner, a)
    assert analyzed == [a, b, c]


def test_analyze_respects_selected_order(monkeypatch) -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    analyzed: list[Path] = []
    owner = _owner({a, b, c}, order=[c, a, b])
    owner.analyze_item_by_path = analyzed.append
    _trigger_analyze(monkeypatch, owner, a)
    assert analyzed == [c, a, b]


def test_analyze_on_unselected_card_acts_on_that_card_only(monkeypatch) -> None:
    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    analyzed: list[Path] = []
    owner = _owner({a, b, c}, order=[a, b, c])
    owner.analyze_item_by_path = analyzed.append
    _trigger_analyze(monkeypatch, owner, d)
    assert analyzed == [d]


def test_analyze_callback_precedence_is_kept(monkeypatch) -> None:
    fired: list[str] = []
    analyzed: list[Path] = []
    owner = _owner({Path("/a.png"), Path("/b.png")})
    owner.analyze_item_by_path = analyzed.append
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    captured = _capture_menu(monkeypatch)
    popup_gallery_card_context_menu(
        SimpleNamespace(),
        owner,
        Path("/a.png"),
        global_pos=QPoint(0, 0),
        selection_count=2,
        on_analyze=lambda: fired.append("analyze"),
    )
    captured["on_triggered"]("gallery.selection.analyze", None)
    assert fired == ["analyze"]
    assert analyzed == []


def test_find_similar_uses_the_whole_selection(monkeypatch, caplog) -> None:
    """Find similar is a selection action too — it sees all three, not one."""
    import logging

    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[a, b, c])
    captured = _capture_menu(monkeypatch)
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, a, global_pos=QPoint(0, 0), selection_count=3,
    )
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        captured["on_triggered"]("gallery.selection.find_similar", None)
    assert any("3 selected" in r.getMessage() for r in caplog.records)


def test_analyze_isolates_per_item_failures(monkeypatch) -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    seen: list[Path] = []

    def _fn(path):
        if path == b:
            raise RuntimeError("boom")
        seen.append(path)

    owner = _owner({a, b, c}, order=[a, b, c])
    assert action_scope.apply_to_targets(owner, _fn, card_path=a) == 2
    assert seen == [a, c]


def test_resolve_clicked_outside_selection_is_card_only() -> None:
    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    owner = _owner({a, b, c}, order=[b, a, c])
    assert action_scope.resolve_targets(owner, card_path=d) == [d]


def test_resolve_empty_selection_with_card_path() -> None:
    card = Path("/a.png")
    owner = _owner(set())
    assert action_scope.resolve_targets(owner, card_path=card) == [card]


def test_resolve_empty_selection_falls_back_to_first_item(monkeypatch) -> None:
    monkeypatch.setattr(action_scope, "_focused_path", lambda owner: None)
    first = SimpleNamespace(path=Path("/first.png"))
    second = SimpleNamespace(path=Path("/second.png"))
    owner = _owner(set(), items=[first, second])
    assert action_scope.resolve_targets(owner) == [Path("/first.png")]


def test_resolve_empty_selection_prefers_focused_card() -> None:
    focused = Path("/focused.png")
    first = SimpleNamespace(path=Path("/first.png"))
    owner = _owner(set(), items=[first], focused_path=focused)
    assert action_scope.resolve_targets(owner) == [focused]


def test_resolve_empty_scope_is_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(action_scope, "_focused_path", lambda owner: None)
    owner = SimpleNamespace(state=SimpleNamespace(selected_paths=set()))
    assert action_scope.resolve_targets(owner) == []
    assert action_scope.resolve_targets(owner, card_path=Path("/a.png")) == [Path("/a.png")]


def test_selected_order_is_stable_and_deduped() -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[c, a, b, a, "c"])
    assert action_scope.selected_paths(owner) == [c, a, b]
    assert action_scope.selected_paths(owner) == [c, a, b]
    assert action_scope.resolve_targets(owner, card_path=b) == [c, a, b]


def test_selected_paths_normalizes_strings_and_hides_mirror_types() -> None:
    owner = _owner({"/a.png", "/b.png"}, order=["/b.png", "/a.png"])
    assert action_scope.selected_paths(owner) == [Path("/b.png"), Path("/a.png")]


def test_reset_metrics_receives_all_selected_targets(monkeypatch) -> None:
    """The reset call site passes the whole resolved scope (not `or None`)."""
    from tabs.image_gallery.ui.card import context_actions
    from tabs.image_gallery.use_cases import cache_reset

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    calls: list[dict] = []
    monkeypatch.setattr(
        cache_reset,
        "reset_metrics_caches",
        lambda owner, paths=None, **kw: calls.append({"owner": owner, "paths": paths}),
    )
    owner = _owner({a, b, c}, order=[b, a, c])
    context_actions._ctx_reset_metrics(owner, b)
    assert len(calls) == 1
    assert calls[0]["owner"] is owner
    assert calls[0]["paths"] == [b, a, c]


def test_reset_metrics_empty_scope_keeps_whole_pool_none(monkeypatch) -> None:
    from tabs.image_gallery.ui.card import context_actions
    from tabs.image_gallery.use_cases import cache_reset

    calls: list = []
    monkeypatch.setattr(
        cache_reset,
        "reset_metrics_caches",
        lambda owner, paths=None, **kw: calls.append(paths),
    )
    # Deterministic empty scope: no selection, no card, no focus/first item
    # (the focus fallback reads the process-wide QApplication otherwise).
    monkeypatch.setattr(action_scope, "_focused_path", lambda owner: None)
    monkeypatch.setattr(action_scope, "_first_item_path", lambda owner: None)
    context_actions._ctx_reset_metrics(SimpleNamespace(), None)
    assert calls == [None]


def test_keyboard_current_path_is_the_first_resolved_target(monkeypatch) -> None:
    from tabs.image_gallery.use_cases import triage_ui

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[c, a, b])
    assert triage_ui.current_path(owner) == c


def test_carry_selection_uses_the_same_read() -> None:
    from tabs.image_gallery.use_cases import carry

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[b, c, a])
    assert carry._selected_paths(owner) == [b, c, a]
