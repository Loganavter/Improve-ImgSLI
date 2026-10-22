"""Follow-up wave (owner report 2026-10-22, second pass).

Pins four behaviours:

1. **Sort applies on load, not only on a combo change.** A fresh folder/list was
   rendered in clustering order until the user re-picked the sort
   (owner: "он никак не сортирует, пока не запустить вручную сменой типа
   сортировки"). ``set_triage`` now re-applies the toolbar's CURRENT sort.
2. **The provenance marker answers "who analyzed this card".** ``AI`` when a
   VLM scorecard is present, ``ALG`` when only local detectors ran, nothing when
   neither — one decision (``analysis.read.analysis_source``) and one painter
   (``ui.card.provenance``) shared by grid and list.
3. **The triage commit hydrates the AI cache before the local Stage-2 pass** —
   the first moment the mode+profile identity is real, so a known image's
   cached read paints in milliseconds instead of after the detector pass
   (measured: ~30 s for 6 large images before the cache appeared).
4. **The useless "Axis set — mode default" row is gone** from the quick-look
   metrics report.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap

from tabs.image_gallery.models import AiAnalysisResult, GalleryItem
from tabs.image_gallery.ui.widget_parts import view_prefs
from tabs.image_gallery.widget import ImageGalleryWidget


def _item(name: str, *, rank: int = 0, analysis: bool = False, metrics: bool = True) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=rank + 1)
    it.rank = rank
    if metrics:
        it.metrics.update({"sharpness": 40.0, "noise": 0.3})
    if analysis:
        it.analysis = AiAnalysisResult(
            description="", tags=(), model="m", analyzed_at_iso="t", axes={"sharpness": 70}
        )
    return it


# -- 1. sort applies on load -------------------------------------------------


def test_set_triage_applies_the_current_sort(qtbot, monkeypatch) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = [_item("c.png", rank=3), _item("a.png", rank=1), _item("b.png", rank=2)]
    w._items = list(items)
    # The toolbar's CURRENT sort is Name — set through the real combo state.
    w.toolbar.set_sort_index(1)  # Sort: Name
    assert "name" in view_prefs.current_sort_text(w).lower()

    w.set_triage([items], "camera", None)

    names = [Path(it.path).name for it in w._items]
    assert names == ["a.png", "b.png", "c.png"], f"load ignored the selected sort: {names}"
    # Members inside the cluster are ordered the same way.
    assert [Path(it.path).name for it in w._series[0]] == ["a.png", "b.png", "c.png"]


def test_set_triage_keeps_the_rank_sort_by_default(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = [_item("c.png", rank=3), _item("a.png", rank=1), _item("b.png", rank=2)]
    w._items = list(items)
    assert int(w.toolbar.sort_index) == 0  # Sort: Rank
    w.set_triage([items], "camera", None)
    ranks = [it.rank for it in w._items]
    assert ranks == [1, 2, 3], ranks


# -- 2. provenance marker ----------------------------------------------------


def test_analysis_source_decides_ai_local_or_nothing() -> None:
    from tabs.image_gallery.analysis.read import analysis_source

    assert analysis_source(_item("ai.png", analysis=True)) == "ai"
    assert analysis_source(_item("local.png")) == "local"
    assert analysis_source(_item("none.png", metrics=False)) == ""


def test_marker_text_uses_the_short_tokens() -> None:
    from tabs.image_gallery.ui.card.provenance import marker_text

    assert marker_text(_item("ai.png", analysis=True)) == "AI"
    assert marker_text(_item("local.png")) == "ALG"
    assert marker_text(_item("none.png", metrics=False)) == ""
    def ru(key, default):
        return {"image_gallery.card.source_ai": "ИИ"}.get(key, default)

    assert marker_text(_item("ai.png", analysis=True), translate=ru) == "ИИ"


def test_the_marker_actually_paints(qapp) -> None:
    from PySide6.QtGui import QColor, QPainter

    from tabs.image_gallery.ui.card.provenance import paint_source_marker

    item = _item("ai.png", analysis=True)
    canvas = QPixmap(120, 80)
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    try:
        paint_source_marker(painter, canvas.rect().toRectF(), item)
    finally:
        painter.end()
    img = canvas.toImage()
    pixels = {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height())}
    assert len(pixels) > 1, "the marker painted nothing"


# -- 3. the triage commit hydrates before the local pass ---------------------


def test_the_triage_commit_hydrates_the_cache_before_stage_two() -> None:
    from tabs.image_gallery.use_cases import proxy_pass

    order: list[str] = []

    class _Owner:
        def __init__(self) -> None:
            self.state = SimpleNamespace(
                items=[SimpleNamespace(path=Path("/gallery/a.png"))],
                series=[],
                source_path=None,
                mode="camera",
                triage_state=None,
            )
            self._series_overrides = {}

        def _restore_singletons(self, items, overrides, pre_ids, series, prev):
            return series

        def refresh_metric_profile(self):
            order.append("profile")

        def _hydrate_ai_cache(self, items):
            order.append("hydrate")
            return 1

        def _apply_fusion_ranks(self, series, *, mode=None):
            order.append("rank")

        def _emit_triage_finished(self, state):
            order.append("finished")

        def _refresh_rank_provenance(self):
            return None

    owner = _Owner()
    proxy_pass._commit_triage_series(owner, [[owner.state.items[0]]], None, "camera")
    assert order[:2] == ["profile", "hydrate"], order
    assert "finished" in order


# -- 4. the axis-set row is gone --------------------------------------------


def test_the_quick_look_report_has_no_axis_set_row() -> None:
    source = Path(
        "src/tabs/image_gallery/ui/quick_look/metrics/rows.py"
    ).read_text(encoding="utf-8")
    assert "profile_axis_set" not in source
    assert "profile_mode_fallback" not in source


# -- dots follow the analysis lifecycle, not a fixed axis count --------------


def test_the_placeholder_dots_disappear_when_the_analysis_ends() -> None:
    """Owner: "Analyzing" disappeared but the 8 dots stayed — they read as eight
    criteria that never finish. The placeholder set is now an in-progress
    affordance: it appears when the item is queued/analyzing and is gone the
    moment the item is done (unless axes were actually measured)."""
    from tabs.image_gallery.models import ActivityPhase
    from tabs.image_gallery.services.activity import set_activity
    from tabs.image_gallery.ui.card.dots import metric_dots_for_item

    item = _item("lifecycle.png", metrics=False)
    assert metric_dots_for_item(item, mode="camera")[1] == (), "idle card keeps a placeholder"

    set_activity(item, ActivityPhase.QUEUED, "local")
    _colors, infos = metric_dots_for_item(item, mode="camera")
    assert len(infos) == 8, f"a queued card must show the waiting affordance, got {infos}"

    set_activity(item, ActivityPhase.ANALYZING, "local")
    assert len(metric_dots_for_item(item, mode="camera")[1]) == 8

    set_activity(item, ActivityPhase.DONE, "local")
    assert metric_dots_for_item(item, mode="camera")[1] == (), (
        "the placeholder outlived the analysis (the reported 8 stuck dots)"
    )


# -- the marker never covers the preview -------------------------------------


def test_both_surfaces_draw_the_marker_in_the_text_region(qapp, monkeypatch) -> None:
    """Grid card and list row must pass their TEXT region, not the cover/thumb.

    Owner 2026-10-22: the first marker was a pill inside the preview — it
    covered the image while the strip under the filename was empty.
    """
    from PySide6.QtGui import QImage, QPainter

    from tabs.image_gallery.ui.card import build_gallery_card
    from tabs.image_gallery.ui.card import provenance as prov
    from tabs.image_gallery.ui.card.painters import _gallery_card_overlay_painter
    from tabs.image_gallery.ui.list.card import build_gallery_list_card
    from tabs.image_gallery.ui.list.painters import _list_row_overlay_painter

    captured: list = []

    def _capture(painter, box, item, **kwargs):
        captured.append(box)

    monkeypatch.setattr(prov, "paint_source_marker", _capture)

    item = _item("ai.png", analysis=True)
    card = build_gallery_card(item, parent=None, mode="camera")
    card.resize(250, 170)

    class _Ctx:
        widget = card
        rect = card.rect().toRectF()

    image = QImage(250, 170, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:
        _gallery_card_overlay_painter(painter, _Ctx(), None)
    finally:
        painter.end()

    text = card.region_rect("text")
    assert captured, "the grid card drew no marker"
    box = captured[0]
    assert box.top() >= float(text.top()) - 1.0, (
        f"the marker sits above the text zone (over the preview): {box} vs {text}"
    )

    from PySide6.QtCore import QRectF

    captured.clear()
    row = build_gallery_list_card(item, mode="camera", domain="algorithms", profile=None)
    row.resize(640, 64)

    class _RowCtx:
        widget = row
        rect = QRectF(0, 0, 640, 64)

    image2 = QImage(640, 64, QImage.Format.Format_ARGB32_Premultiplied)
    painter2 = QPainter(image2)
    try:
        _list_row_overlay_painter(painter2, _RowCtx(), None)
    finally:
        painter2.end()
    text_row = row.region_rect("text")
    assert captured, "the list row drew no marker"
    assert captured[0].top() >= float(text_row.top()) - 1.0, captured[0]


# -- the sort is a LIVE order; a switch never spends a request -------------


def test_resort_after_a_rank_change_reorders_the_grid(qtbot) -> None:
    """With "Sort: Rank" the grid must follow the numbers a ranker writes."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = [_item("a.png", rank=3), _item("b.png", rank=1), _item("c.png", rank=2)]
    w._items = list(items)
    w.set_triage([items], "camera", None)
    assert [Path(it.path).name for it in w._items] == ["b.png", "c.png", "a.png"]

    # A ranker (Jev) rewrites the numbers: a.png becomes the winner.
    items[0].rank, items[1].rank, items[2].rank = 1, 2, 3
    view_prefs.resort_after_rank_change(w)

    assert [Path(it.path).name for it in w._items] == ["a.png", "b.png", "c.png"], (
        "the grid kept the pre-rank order after the ranks changed"
    )


def test_restoring_the_sort_index_reorders_the_current_items(qtbot) -> None:
    """A reopened tab must show the saved order, not "Sort: Name" on a triage grid."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = [_item("c.png", rank=3), _item("a.png", rank=1), _item("b.png", rank=2)]
    w._items = list(items)
    w.rebuild_grid(items)

    w.apply_view_prefs(view_list=False, judgment_domain="algorithms", sort_index=1)

    assert [Path(it.path).name for it in w._items] == ["a.png", "b.png", "c.png"]


def test_the_marker_follows_the_active_domain() -> None:
    """Algorithms mode says ALG even when an AI scorecard still sits on the item."""
    from tabs.image_gallery.ui.card.provenance import marker_text

    analyzed = _item("ai.png", analysis=True)
    assert marker_text(analyzed, domain="ai") == "AI"
    assert marker_text(analyzed, domain="algorithms") == "ALG"
    assert marker_text(_item("none.png", metrics=False), domain="algorithms") == ""


def test_a_domain_switch_is_cache_only() -> None:
    """Switching backends must not spend a request on already-produced metrics."""
    from tabs.image_gallery.use_cases import ai_analysis

    class _Owner:
        def __init__(self) -> None:
            self.state = SimpleNamespace(items=[], mode="camera")
            self._AI_VISIBLE_CAP = 12
            self.hydrated: list = []
            self.analyzed = 0
            self.widget = SimpleNamespace(visible_paths=lambda: [])

        def _hydrate_ai_cache(self, items, **kwargs):
            self.hydrated.append(list(items))
            return len(self.hydrated[-1])

        def analyze(self, ctx):
            self.analyzed += 1

    owner = _Owner()
    items = [_item("a.png"), _item("b.png")]
    owner.state.items = items

    ai_analysis._run_ai_for_visible(owner, cache_only=True)

    assert owner.hydrated and owner.hydrated[0] == items
    assert owner.analyzed == 0, "a switch must not start a live analysis"


def test_fusion_repoints_the_ranks_and_the_provenance_chip() -> None:
    """Switching back to Algorithms must say "Ranked by Algorithms" again.

    The live screenshot kept "Ranked by AI (Jev)" after the switch: fusion did
    re-derive the ranks, but the stats-strip chip was never refreshed.
    """
    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.models import Series

    items = [_item("a.png", rank=2, metrics=False), _item("b.png", rank=1, metrics=False)]
    for it, score in zip(items, (300.0, 260.0)):
        it.metrics["sharpness"] = score
        it.metrics["noise"] = 0.2
        it.rank_source = "jev"
    items[1].is_best = True

    seen: list = []

    class _Owner:
        def __init__(self) -> None:
            self.state = SimpleNamespace(
                series=[Series(id="s", members=list(items))],
                items=list(items),
                mode="camera",
                metric_profile=None,
            )
            self._judgment_domain = "algorithms"
            self._metrics_settled_gen = 5
            self._folder_gen = 5
            self.widget = SimpleNamespace(
                set_rank_provenance=lambda src=None, domain=None: seen.append((src, domain)),
                refresh_cards=lambda its: None,
                refresh_card=lambda it: None,
            )

        def _section_members(self, entry):
            return list(getattr(entry, "members", entry) or [])

    owner = _Owner()
    GalleryController._apply_fusion_ranks(owner, owner.state.series)

    assert all(it.rank_source == "fusion" for it in items), [it.rank_source for it in items]
    assert seen and seen[-1] == ("fusion", "algorithms"), seen


def test_the_marker_receives_the_active_domain_from_both_painters(qapp, monkeypatch) -> None:
    from PySide6.QtGui import QImage, QPainter

    from tabs.image_gallery.ui.card import build_gallery_card
    from tabs.image_gallery.ui.card import provenance as prov
    from tabs.image_gallery.ui.card.painters import _gallery_card_overlay_painter
    from tabs.image_gallery.ui.list.card import build_gallery_list_card
    from tabs.image_gallery.ui.list.painters import _list_row_overlay_painter

    captured: list = []

    def _capture(painter, box, item, **kwargs):
        captured.append(kwargs.get("domain"))

    monkeypatch.setattr(prov, "paint_source_marker", _capture)

    item = _item("ai.png", analysis=True)
    card = build_gallery_card(item, parent=None, mode="camera")
    card._gallery_domain = "algorithms"
    card.resize(250, 170)

    class _Ctx:
        widget = card
        rect = card.rect().toRectF()

    image = QImage(250, 170, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:
        _gallery_card_overlay_painter(painter, _Ctx(), None)
    finally:
        painter.end()
    assert captured and captured[-1] == "algorithms", captured

    captured.clear()
    from PySide6.QtCore import QRectF

    row = build_gallery_list_card(item, mode="camera", domain="algorithms", profile=None)
    row._gallery_domain = "ai"
    row.resize(640, 64)

    class _RowCtx:
        widget = row
        rect = QRectF(0, 0, 640, 64)

    image2 = QImage(640, 64, QImage.Format.Format_ARGB32_Premultiplied)
    painter2 = QPainter(image2)
    try:
        _list_row_overlay_painter(painter2, _RowCtx(), None)
    finally:
        painter2.end()
    assert captured and captured[-1] == "ai", captured


# -- the marker: only after the analysis, and clear of the hover bar --------


def test_the_marker_waits_for_the_analysis_to_finish() -> None:
    """A freshly loaded card must NOT say ALG before the local pass finishes."""
    from tabs.image_gallery.models import ActivityPhase
    from tabs.image_gallery.services.activity import set_activity
    from tabs.image_gallery.ui.card.provenance import marker_text

    item = _item("fresh.png")  # local metrics present (the pass is running)
    set_activity(item, ActivityPhase.QUEUED, "local")
    assert marker_text(item, domain="algorithms") == "", (
        "the card claims a backend while its analysis is still running"
    )

    set_activity(item, ActivityPhase.DONE, "local")
    assert marker_text(item, domain="algorithms") == "ALG"


def test_the_marker_clears_the_hover_underline(qapp) -> None:
    """The caption must sit above the 3px accent bar (owner: invisible on hover)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    from tabs.image_gallery.ui.card.provenance import paint_source_marker

    item = _item("a.png")
    box = QRectF(0, 118, 250, 52)  # the card's text zone at design scale
    canvas = QImage(250, 170, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(0)
    painter = QPainter(canvas)
    try:
        paint_source_marker(painter, box, item, domain="algorithms")
    finally:
        painter.end()

    # The hover bar lives in the bottom 11 px (3px bar at 8 from the bottom).
    band_top = int(box.bottom() - 11)
    ink_in_band = sum(
        1
        for y in range(band_top, canvas.height())
        for x in range(0, 90)
        if canvas.pixelColor(x, y).alpha() > 0
    )
    assert ink_in_band == 0, f"the marker paints over the hover bar ({ink_in_band} px)"
    lit = sum(
        1
        for y in range(int(box.top()), band_top)
        for x in range(0, 90)
        if canvas.pixelColor(x, y).alpha() > 0
    )
    assert lit > 0, "the marker did not paint at all"
