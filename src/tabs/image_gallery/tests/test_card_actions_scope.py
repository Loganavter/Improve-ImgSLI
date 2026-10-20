"""Regression: the card menu's Analyze applies to the WHOLE resolved scope.

Bug (2026-10-20): six cards were selected and "Analyze" produced a scorecard
for exactly one of them (the RGB variant). The menu wiring always passes an
``on_analyze`` callback, and that closure still did
``next(iter(state.selected_paths))`` — set iteration order picked one member.
The context-menu popup's selection-first loop was therefore unreachable.

Scope of this file: the entry point only. Whether analysis actually runs is
covered by the analysis/worker tests.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.ui.widget_parts.card_actions import analyze_menu_targets


def _owner(paths, order=None):
    calls: list[Path] = []
    state = SimpleNamespace(
        selected_paths=set(paths),
        selected_order=list(order if order is not None else paths),
    )
    owner = SimpleNamespace(state=state, analyze_item_by_path=lambda p: calls.append(p))
    return owner, calls


def test_menu_analyze_covers_the_whole_selection(tmp_path):
    paths = [Path(tmp_path / f"variant_{i}.png") for i in range(6)]

    owner, calls = _owner(paths)

    applied = analyze_menu_targets(owner, paths[4])

    assert applied == 6
    assert set(calls) == set(paths), "a selection Analyze must not pick one arbitrary card"
    assert len(calls) == len(set(calls)), "each target is analyzed once"


def test_menu_analyze_targets_the_clicked_card_outside_the_selection(tmp_path):
    selected = [Path(tmp_path / "a.png"), Path(tmp_path / "b.png")]
    clicked = Path(tmp_path / "outside.png")
    owner, calls = _owner(selected)

    applied = analyze_menu_targets(owner, clicked)

    assert applied == 1
    assert calls == [clicked], "file-manager rule: an unselected card acts on itself"


def test_menu_analyze_with_empty_selection_uses_the_clicked_card(tmp_path):
    clicked = Path(tmp_path / "only.png")
    owner, calls = _owner([])

    applied = analyze_menu_targets(owner, clicked)

    assert applied == 1
    assert calls == [clicked]


def test_menu_analyze_isolates_a_failing_item(tmp_path):
    paths = [Path(tmp_path / f"{i}.png") for i in range(3)]
    calls: list[Path] = []

    def _flaky(p):
        if p == paths[1]:
            raise RuntimeError("one bad card must not stop the rest")
        calls.append(p)

    state = SimpleNamespace(selected_paths=set(paths), selected_order=list(paths))
    owner = SimpleNamespace(state=state, analyze_item_by_path=_flaky)

    applied = analyze_menu_targets(owner, paths[0])

    assert applied == 2
    assert set(calls) == {paths[0], paths[2]}


def test_menu_analyze_without_an_analyzer_is_a_noop(tmp_path):
    owner = SimpleNamespace(state=SimpleNamespace(selected_paths={Path(tmp_path / "a.png")}))

    assert analyze_menu_targets(owner, Path(tmp_path / "a.png")) == 0


def test_menu_wiring_no_longer_picks_one_member():
    """Guard the exact regression: the legacy single-member closure must be gone
    and the menu must route through the scope helper."""
    import inspect

    import tabs.image_gallery.ui.widget_parts.card_actions as module

    src = inspect.getsource(module)
    assert "next(iter(sel))" not in src, (
        "the card menu analyzed one arbitrary member of a selection again"
    )
    assert "analyze_menu_targets(_ctx_owner()" in src, (
        "the menu must route Analyze through analyze_menu_targets"
    )
