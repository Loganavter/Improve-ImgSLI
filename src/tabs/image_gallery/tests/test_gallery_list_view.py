"""S2-8: list mode inside GalleryGridView (recent items_view parity).

One view, builders swap: grid cards (bg/cover/text) vs list rows
(thumb/text/meta). Pool never mixes modes; series/selection/marquee are
mode-agnostic (operate on live cards).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QPixmap

from tabs.image_gallery.models import Artifact, GalleryItem, Severity
from tabs.image_gallery.ui.grid_view import VIEW_GRID, VIEW_LIST
from tabs.image_gallery.ui.list.card import (
    LIST_CARD_H,
    LIST_ROW_REGION_IDS,
    _bind_list_row,
    build_gallery_list_card,
    update_gallery_list_card,
)
from tabs.image_gallery.ui.list.regions import (
    _artifacts_text,
    _badges_text,
    _list_meta_rows,
    _list_text_rows,
    _vlm_text,
)
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i + 1)
        for i, n in enumerate(names)
    ]


def _grid_ids(card) -> set[str]:
    try:
        return {r.id for r in card._regions}
    except Exception:
        return set()


def test_view_toggle_swaps_builders(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    gv = w._grid_view
    assert gv._view_mode == VIEW_GRID and gv.grid_columns == 4
    assert _grid_ids(gv.card_for(items[0].path)) == {"bg", "cover", "text"}
    w._on_view_toggled(True)
    assert gv._view_mode == VIEW_LIST and gv.grid_columns == 1
    assert _grid_ids(gv.card_for(items[0].path)) == set(LIST_ROW_REGION_IDS)
    assert gv.card_for(items[0].path).height() > 0
    w._on_view_toggled(False)
    assert gv._view_mode == VIEW_GRID and gv.grid_columns == 4
    assert _grid_ids(gv.card_for(items[0].path)) == {"bg", "cover", "text"}


def test_pool_never_mixes_modes(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    gv = w._grid_view
    for _ in range(3):
        w._on_view_toggled(True)
        w._on_view_toggled(False)
    modes = set()
    for it in items:
        card = gv.card_for(it.path)
        assert card is not None
        modes.add(getattr(card, "_gallery_view_mode", None))
    assert modes == {VIEW_GRID}
    assert all(
        getattr(c, "_gallery_view_mode", None) == VIEW_GRID for c in gv._pool
    ) or not gv._pool


def test_series_survive_mode_switch(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png", "c.png")
    w.rebuild_grid(items)
    w._grid_view.set_series([items[:2]], hub_names=["hub1"], collapsed={})
    assert len(w._grid_view._series_headers) == 2  # series + UNGROUPED tail
    w._on_view_toggled(True)
    gv = w._grid_view
    assert gv._series is not None and len(gv._series) == 1
    assert len(gv._series_headers) == 2
    gv._toggle_collapse(0)
    assert gv._collapsed == {0: True}
    # Cluster hidden — tail card still live.
    assert gv.card_for(items[2].path) is not None


def test_selection_and_click_parity_in_list_mode(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    w._on_view_toggled(True)
    w._render_gallery_selection([str(items[0].path)])
    card = w._grid_view.card_for(items[0].path)
    assert getattr(card, "_gallery_sel_applied", (None,))[0] is True
    got: list = []
    orig = w.show_quick_look
    try:
        w.show_quick_look = lambda p: got.append(str(p))  # type: ignore[method-assign]
        w._on_card_toggle(items[1].path, additive=False)
    finally:
        w.show_quick_look = orig  # type: ignore[method-assign]
    assert got == [str(items[1].path)]


def test_list_row_texts() -> None:
    assert _badges_text(_items("a.png")[0]) == ""
    it = _items("a.png")[0]
    it.is_best = True
    it.rank = 3
    assert _badges_text(it) == "#3 ★"
    crowned = _items("b.png")[0]
    crowned.crown_rank = 2
    assert _badges_text(crowned) == "#2"
    crowned.rank = 5
    assert _badges_text(crowned) == "#2"  # crown wins over rank
    rej = _items("c.png")[0]
    rej.rejected = True
    assert _badges_text(rej) == "✕"
    assert "R" not in _badges_text(it) and "C" not in _badges_text(crowned)
    assert _artifacts_text(_items("d.png")[0]) == "…"
    flagged = _items("e.png")[0]
    flagged.artifacts = {Artifact.BANDING: Severity.FLAGGED, Artifact.HALO: Severity.FLAGGED}
    assert _artifacts_text(flagged) == "Artifacts"
    mild = _items("f.png")[0]
    mild.artifacts = {Artifact.NOISE_AMPLIFICATION: Severity.MILD}
    assert _artifacts_text(mild) == "Minor"
    assert _vlm_text(_items("g.png")[0]) == ""
    tie = _items("h.png")[0]
    tie.vlm_tie_pending = True
    assert _vlm_text(tie) == "tie…"
    done = _items("i.png")[0]
    done.vlm_tie_result = "tie"  # type: ignore[assignment]
    assert _vlm_text(done) == "tie-ok"


def _pixmap() -> QPixmap:
    pm = QPixmap(10, 10)
    pm.fill(0xFF336699)
    assert not pm.isNull()
    return pm


def test_thumb_width_follows_aspect_capped(qtbot) -> None:
    from tabs.image_gallery.ui.list.card import _thumb_width_for

    assert _thumb_width_for(_items("a.png")[0]) == 56.0  # no thumbnail yet
    wide = _items("w.png")[0]
    pm = QPixmap(120, 80)
    pm.fill(0xFF336699)
    wide.thumbnail = pm
    assert _thumb_width_for(wide) == 96.0  # 64 * 1.5
    pano = _items("p.png")[0]
    pp = QPixmap(300, 90)
    pp.fill(0xFF336699)
    pano.thumbnail = pp
    assert _thumb_width_for(pano) == 64 * 21 / 9  # capped at 21:9
    portrait = _items("t.png")[0]
    tp = QPixmap(40, 100)
    tp.fill(0xFF336699)
    portrait.thumbnail = tp
    assert _thumb_width_for(portrait) == 32.0  # 64 * 0.4 clamped to portrait minimum
    card = build_gallery_list_card(wide)
    qtbot.addWidget(card)
    assert card._gallery_row_state["w"] == 96.0
    update_gallery_list_card(card, pano)
    assert card._gallery_row_state["w"] == 64 * 21 / 9


def test_list_thumb_uses_cover(qtbot) -> None:
    it = _items("a.png")[0]
    it.thumbnail = _pixmap()
    card = build_gallery_list_card(it)
    qtbot.addWidget(card)
    assert card.region("thumb").image_fill == "cover"
    it.thumbnail = _pixmap()
    update_gallery_list_card(card, it)
    assert card.region("thumb").image_fill == "cover"


def test_list_title_single_row(qtbot) -> None:
    it = _items("a.png")[0]
    rows = _list_text_rows(it)
    assert len(rows) == 1
    row = rows[0]
    assert row.text == "a.png" and row.weight == "normal" and row.size == 16 and row.marquee is True
    it.rank = 3
    it.is_best = True
    rows = _list_text_rows(it)
    assert len(rows) == 1 and rows[0].text == "a.png #3 ★"
    card = build_gallery_list_card(it)
    qtbot.addWidget(card)
    assert len(card.region("text").rows) == 1


def test_list_meta_single_row() -> None:
    rows = _list_meta_rows(_items("a.png")[0])
    assert len(rows) == 1 and rows[0].text == "…"
    it = _items("b.png")[0]
    it.artifacts = {Artifact.BLOCKING: Severity.FLAGGED}
    it.vlm_tie_pending = True
    rows = _list_meta_rows(it)
    assert len(rows) == 1 and rows[0].text == "Artifacts tie…"


def _capsule_owner(item: GalleryItem) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(items=[item], selected_paths=set()))


def test_chrome_regions_present_and_routed(qtbot) -> None:
    it = _items("a.png")[0]
    card = build_gallery_list_card(it)
    qtbot.addWidget(card)
    card.show()
    owner = _capsule_owner(it)
    card._gallery_owner = owner  # type: ignore[attr-defined]
    _bind_list_row(card, on_activate=lambda *_a: None, on_context_menu=lambda *_a: None)
    for rid in ("act_best", "act_reject", "act_compare", "act_delete"):
        assert card.region(rid) is not None
    # Chrome regions are always visible (no hover-only children anymore).
    assert card.findChild(object, "gallery_row_act_best") is None
    card.regionClicked.emit("act_best")
    assert it.is_best is True
    update_gallery_list_card(card, it)
    assert "#1" in card.region("text").rows[0].text and "★" in card.region("text").rows[0].text
    card.regionClicked.emit("act_reject")
    assert it.rejected is True
    card.regionClicked.emit("act_compare")
    assert it.path in owner.state.selected_paths


def test_chrome_resolves_live_item_per_click(qtbot) -> None:
    # Pool-safety: swapping _gallery_item retargets the same regions.
    first, second = _items("a.png", "b.png")
    card = build_gallery_list_card(first)
    qtbot.addWidget(card)
    owner = SimpleNamespace(state=SimpleNamespace(items=[first, second], selected_paths=set()))
    card._gallery_owner = owner  # type: ignore[attr-defined]
    _bind_list_row(card, on_activate=lambda *_a: None, on_context_menu=lambda *_a: None)
    update_gallery_list_card(card, second)
    card.regionClicked.emit("act_best")
    assert second.is_best is True and first.is_best is False


def test_plate_click_activates_and_delete_removes(qtbot, monkeypatch) -> None:
    from tabs.image_gallery.use_cases import triage as _triage

    it = _items("a.png")[0]
    card = build_gallery_list_card(it)
    qtbot.addWidget(card)
    owner = _capsule_owner(it)
    card._gallery_owner = owner  # type: ignore[attr-defined]
    got: list = []
    _bind_list_row(
        card,
        on_activate=lambda p, additive=False: got.append((str(p), additive)),
        on_context_menu=lambda *_a: None,
    )
    card.regionClicked.emit("text")
    assert got == [(str(it.path), False)]
    removed: list = []
    monkeypatch.setattr(_triage, "remove_from_grid", lambda _o, p: removed.append(str(p)) or True)
    card.regionClicked.emit("act_delete")
    assert removed == [str(it.path)]


def test_overlay_no_hover_wash_rejected_dim_only() -> None:
    """Palette parity: plain rows paint no overlay; rejected rows get the dim."""
    from tabs.image_gallery.ui.list.painters import _list_row_overlay_painter

    class _Recorder:
        def __init__(self) -> None:
            self.ops: list = []

        def __getattr__(self, name: str):
            def _op(*_a, **_k) -> None:
                self.ops.append(name)

            return _op

    it = _items("a.png")[0]
    ctx = SimpleNamespace(widget=SimpleNamespace(_gallery_item=it), rect=SimpleNamespace())
    plain = _Recorder()
    _list_row_overlay_painter(plain, ctx, None)
    assert plain.ops == []
    it.rejected = True
    dimmed = _Recorder()
    _list_row_overlay_painter(dimmed, ctx, None)
    assert "drawRect" in dimmed.ops


def test_view_list_rebind_routes_chrome(qtbot) -> None:
    """VIEW_LIST rebind path: recycled rows stay list-routed (no grid activate)."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    w._on_view_toggled(True)
    gv = w._grid_view
    card = gv.card_for(items[0].path)
    assert card is not None
    owner = SimpleNamespace(state=SimpleNamespace(items=list(items), selected_paths=set()))
    card._gallery_owner = owner  # type: ignore[attr-defined]
    gv._rebind_card(card)
    activated: list = []
    orig = w.show_quick_look
    try:
        w.show_quick_look = lambda p: activated.append(str(p))  # type: ignore[method-assign]
        card.regionClicked.emit("act_best")
    finally:
        w.show_quick_look = orig  # type: ignore[method-assign]
    assert items[0].is_best is True
    assert activated == []


def test_refresh_in_list_mode(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png")
    w.rebuild_grid(items)
    w._on_view_toggled(True)
    items[0].rank = 7
    w.refresh_card(items[0])
    card = w._grid_view.card_for(items[0].path)
    assert card is not None
    assert "a.png" in card.toolTip()
    assert LIST_CARD_H == 64


def test_switch_state_survives_rebuild(qtbot) -> None:
    """List mode survives a pool rebuild (new cards use ui/list rows)."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    w._on_view_toggled(True)
    assert w._view_mode is True
    grown = list(items) + _items("c.png")
    w.rebuild_grid(grown)
    gv = w._grid_view
    assert w._view_mode is True
    assert gv._view_mode == VIEW_LIST and gv.grid_columns == 1
    fresh = gv.card_for(grown[2].path)
    assert fresh is not None
    assert _grid_ids(fresh) == set(LIST_ROW_REGION_IDS)
    w._on_view_toggled(False)
    w.rebuild_grid(grown)
    assert gv._view_mode == VIEW_GRID and gv.grid_columns == 4
    assert _grid_ids(gv.card_for(grown[2].path)) == {"bg", "cover", "text"}


def test_toolbar_switch_drives_widget_rows(qtbot) -> None:
    """End-to-end: toolbar segments -> viewToggled -> widget list rows."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    got: list[bool] = []
    w.toolbar.viewToggled.connect(got.append)
    w.toolbar._apply_view(True)  # type: ignore[attr-defined]
    assert got == [True]
    gv = w._grid_view
    assert w._view_mode is True and gv._view_mode == VIEW_LIST
    assert _grid_ids(gv.card_for(items[0].path)) == set(LIST_ROW_REGION_IDS)
    assert gv.card_for(items[0].path).region("thumb").image_fill == "cover"
    w.toolbar._apply_view(False)  # type: ignore[attr-defined]
    assert got == [True, False]
    assert w._view_mode is False and gv._view_mode == VIEW_GRID
    assert _grid_ids(gv.card_for(items[0].path)) == {"bg", "cover", "text"}


def test_marquee_hit_test_in_list_mode(qtbot) -> None:
    """Marquee band sees list rows through the same card_for map."""
    from tabs.image_gallery.ui import marquee as _marquee

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    items = _items("a.png", "b.png", "c.png")
    w.rebuild_grid(items)
    w._on_view_toggled(True)
    gv = w._grid_view
    assert gv._view_mode == VIEW_LIST
    host = gv.items_host
    full = host.rect()
    assert full.height() > 0
    hits = _marquee.paths_for_rect(gv, full)
    assert {str(p) for p in hits} == {str(it.path) for it in items}
