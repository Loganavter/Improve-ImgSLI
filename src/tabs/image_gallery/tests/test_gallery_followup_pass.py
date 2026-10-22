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
