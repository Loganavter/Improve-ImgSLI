"""Context-menu "Group N": pin multi-selection into a brand-new series.

- menu entry appears for ≥2 menu-rule targets, hidden otherwise;
- trigger routes the ordered targets to the controller;
- controller mints a fresh stable id (counter continues, no collisions),
  pins via overrides, regroups in memory and delivers the view — existing
  series untouched, leftovers keep their sections.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QThreadPool

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, GalleryState, Series, TriageState
from tabs.image_gallery.tests.test_triage_view_stability import _make_ctrl, _ScanStub
from tabs.image_gallery.ui.card.context_actions import _ctx_group
from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu


def _img(tmp_path: Path, name: str) -> GalleryItem:
    p = tmp_path / name
    p.write_bytes(b"\x00")
    return GalleryItem(path=p, mtime_ns=p.stat().st_mtime_ns)


def _owner(selected, items=None):
    st = SimpleNamespace(selected_paths=set(selected), items=list(items or []))
    return SimpleNamespace(state=st)


def _pool_item(name: str, series_id=None):
    return SimpleNamespace(path=Path(name), series_id=series_id)


def _owner_with_series(selected, series=(), grid_series=None):
    owner = _owner(selected)
    owner.state.series = list(series)
    if grid_series is not None:
        owner._grid_view = SimpleNamespace(_series=list(grid_series))
    return owner


def _series(id_: str, *names: str):
    members = [SimpleNamespace(path=Path(n)) for n in names]
    return SimpleNamespace(id=id_, members=members)


def _capture_menu(monkeypatch):
    import sli_ui_toolkit.widgets as _w
    import ui.context_menu.manager as _mgr

    captured: dict = {}

    class _FakeMenu:
        def __init__(self, parent, *, entries=(), on_triggered=None, **kwargs):
            captured["entries"] = tuple(entries)
            captured["on_triggered"] = on_triggered

        def popup_at(self, pos):
            captured["popup_at"] = pos

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None, **_kwargs):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
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


def _action_labels(entries) -> dict[str, str]:
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    out: dict[str, str] = {}
    for e in entries:
        acts = e.entries if isinstance(e, ContextMenuSection) else (e,)
        for a in acts:
            if isinstance(a, ContextMenuAction):
                out[a.action_id] = a.text
    return out


def test_menu_shows_group_for_multi_selection(monkeypatch) -> None:
    captured = _capture_menu(monkeypatch)
    owner = _owner({Path("/a.png"), Path("/b.png")})
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    ids = _action_ids(captured["entries"])
    assert "gallery.group" in ids
    assert _action_labels(captured["entries"])["gallery.group"] == "Group"


def test_menu_hides_group_for_whole_series_only(monkeypatch) -> None:
    """Selecting exactly one complete series: Group would be a no-op."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_series(
        {Path("/a.png"), Path("/b.png")},
        series=[_series("series_2", "/a.png", "/b.png")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    ids = _action_ids(captured["entries"])
    assert "gallery.group" not in ids
    assert "gallery.ungroup" in ids


def test_menu_hides_group_for_whole_series_via_grid_mirror(monkeypatch) -> None:
    """Same via the grid-view series mirror (widget-shaped owners)."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_series(
        {Path("/a.png"), Path("/b.png")},
        grid_series=[[SimpleNamespace(path=Path("/a.png")), SimpleNamespace(path=Path("/b.png"))]],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    assert "gallery.group" not in _action_ids(captured["entries"])


def test_menu_shows_group_for_series_subset(monkeypatch) -> None:
    """Two of three series members: regrouping is a real move."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_series(
        {Path("/a.png"), Path("/b.png")},
        series=[_series("series_2", "/a.png", "/b.png", "/c.png")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    assert "gallery.group" in _action_ids(captured["entries"])


def test_menu_shows_group_for_cross_series_pick(monkeypatch) -> None:
    """Members of two series: grouping merges them into a new one."""
    captured = _capture_menu(monkeypatch)
    owner = _owner_with_series(
        {Path("/a.png"), Path("/c.png")},
        series=[
            _series("series_2", "/a.png", "/b.png"),
            _series("series_3", "/c.png", "/d.png"),
        ],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    assert "gallery.group" in _action_ids(captured["entries"])


def test_menu_hides_group_for_single_target(monkeypatch) -> None:
    captured = _capture_menu(monkeypatch)
    owner = _owner({Path("/a.png")})
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=1,
    )
    assert "gallery.group" not in _action_ids(captured["entries"])


def test_menu_hides_group_without_selection(monkeypatch) -> None:
    captured = _capture_menu(monkeypatch)
    owner = _owner(set())
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=0,
    )
    assert "gallery.group" not in _action_ids(captured["entries"])


def test_menu_hides_ungroup_for_all_ungrouped(monkeypatch) -> None:
    """UNGROUPED tail cards: nothing to dissolve, no Ungroup entry."""
    captured = _capture_menu(monkeypatch)
    owner = _owner(
        {Path("/a.png"), Path("/b.png")},
        [_pool_item("/a.png"), _pool_item("/b.png")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    ids = _action_ids(captured["entries"])
    assert "gallery.ungroup" not in ids
    # …but Group is still offered (they can form a new series).
    assert "gallery.group" in ids


def test_menu_shows_ungroup_for_grouped_and_mixed(monkeypatch) -> None:
    captured = _capture_menu(monkeypatch)
    owner = _owner(
        {Path("/a.png"), Path("/b.png")},
        [_pool_item("/a.png", "series_2"), _pool_item("/b.png", "series_2")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    assert "gallery.ungroup" in _action_ids(captured["entries"])

    captured = _capture_menu(monkeypatch)
    owner = _owner(
        {Path("/a.png"), Path("/c.png")},
        [_pool_item("/a.png", "series_2"), _pool_item("/c.png")],
    )
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, Path("/a.png"), global_pos=None, selection_count=2,
    )
    assert "gallery.ungroup" in _action_ids(captured["entries"])


def test_group_trigger_routes_ordered_targets() -> None:
    calls: list = []

    def _group(paths):
        calls.append(list(paths))
        return "series_9"

    owner = _owner({Path("/b.png"), Path("/a.png")})
    owner.move_paths_to_series = lambda paths, sid: 2
    owner.group_paths_as_new_series = _group
    owner.state.selected_order = [Path("/b.png"), Path("/a.png")]
    assert _ctx_group(owner, Path("/b.png")) == "series_9"
    assert calls == [[Path("/b.png"), Path("/a.png")]]


def test_group_needs_two_targets_and_controller() -> None:
    owner = _owner({Path("/a.png")})
    owner.move_paths_to_series = lambda paths, sid: 1
    owner.group_paths_as_new_series = lambda paths: "series_9"
    assert _ctx_group(owner, Path("/a.png")) is None
    # No controller reachable (storeless double): graceful None.
    assert _ctx_group(_owner({Path("/a.png"), Path("/b.png")}), Path("/a.png")) is None


def _grouped_ctrl(tmp_path: Path):
    widget = _ScanStub()
    ctrl = _make_ctrl(widget)
    b1, b2 = _img(tmp_path, "b1.png"), _img(tmp_path, "b2.png")
    b1.series_id, b1.rank = "series_2", 1
    b2.series_id, b2.rank = "series_2", 2
    ctrl.state = GalleryState(
        folder=tmp_path, items=[b1, b2], triage_state=TriageState.DONE
    )
    ctrl.state.series = [Series(id="series_2", members=[b1, b2])]
    ctrl._series_next_id = 2
    return ctrl, widget, (b1, b2)


def _members(entry) -> list:
    if hasattr(entry, "members"):
        return list(entry.members or [])
    return list(entry)


def test_group_ungrouped_pair_mints_fresh_series(tmp_path) -> None:
    ctrl, widget, (b1, b2) = _grouped_ctrl(tmp_path)
    r1, r2 = _img(tmp_path, "r1.png"), _img(tmp_path, "r2.png")
    ctrl.state.items = [b1, b2, r1, r2]
    new_id = ctrl.group_paths_as_new_series([r1.path, r2.path])
    assert new_id == "series_3"
    assert ctrl._series_next_id == 3
    assert [s.id for s in ctrl.state.series] == ["series_2", "series_3"]
    assert _members(ctrl.state.series[0]) == [b1, b2]
    assert sorted(str(m.path) for m in _members(ctrl.state.series[1])) == sorted(
        [str(r1.path), str(r2.path)]
    )
    # View delivered with both sections.
    assert widget.triage_calls, "expected set_triage delivery"
    assert [s.id for s in widget.triage_calls[-1][0]] == ["series_2", "series_3"]


def test_group_across_series_moves_members(tmp_path) -> None:
    """One blue + one red → new series; leftover blue keeps its section."""
    ctrl, _widget, (b1, b2) = _grouped_ctrl(tmp_path)
    r1 = _img(tmp_path, "r1.png")
    ctrl.state.items = [b1, b2, r1]
    new_id = ctrl.group_paths_as_new_series([b1.path, r1.path])
    assert new_id == "series_3"
    by_id = {s.id: _members(s) for s in ctrl.state.series}
    assert sorted(str(m.path) for m in by_id["series_3"]) == sorted(
        [str(b1.path), str(r1.path)]
    )
    assert str(b1.path) not in {str(m.path) for m in by_id["series_2"]}
    assert sorted(str(m.path) for m in by_id["series_2"]) == [str(b2.path)]


def test_group_empty_or_out_of_pool_is_none(tmp_path) -> None:
    ctrl, _widget, _blues = _grouped_ctrl(tmp_path)
    assert ctrl.group_paths_as_new_series([]) is None
    assert ctrl.group_paths_as_new_series([Path("/nope.png")]) is None
    assert [s.id for s in ctrl.state.series] == ["series_2"]


def test_ungroup_down_to_last_member_dissolves_series(tmp_path) -> None:
    """Ungrouping the last remaining member closes the series (no resurrection)."""
    ctrl, _widget, (b1, b2) = _grouped_ctrl(tmp_path)
    assert ctrl.move_paths_to_series([b1.path], None) == 1
    assert [s.id for s in ctrl.state.series] == ["series_2"]
    assert _members(ctrl.state.series[0]) == [b2]
    assert ctrl.move_paths_to_series([b2.path], None) == 1
    assert ctrl.state.series == []
    by_path = {str(it.path): it for it in ctrl.state.items}
    assert by_path[str(b1.path)].series_id is None
    assert by_path[str(b2.path)].series_id is None


def test_ungroup_whole_series_at_once(tmp_path) -> None:
    ctrl, _widget, (b1, b2) = _grouped_ctrl(tmp_path)
    assert ctrl.move_paths_to_series([b1.path, b2.path], None) == 2
    assert ctrl.state.series == []
