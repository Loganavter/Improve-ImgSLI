"""Hydrate and reset repaint what they changed (owner report, third pass).

Two measured staleness symptoms, one family: data changed without a repaint.

* "Если сбросить кэш, сделать quick look, выйти из него — на карточке снова
  появляется бейджик АЛГ/ИИ." The AI-cache hydrate (open, triage commit, settle)
  fills ``item.analysis`` but never refreshes the cards — the marker/dots appear
  only when some unrelated event repaints the card (opening quick look does).
* "Кэш сброшен, нумерации нет, а метрики остались." The OPEN quick-look report
  keeps its own row set; the reset re-stamped the cards but never rebuilt the
  panel, so it still showed the pre-reset numbers.

Both fixes are the same seam: a change to the DERIVED state must repaint the
surfaces that derive it (cards) and rebuild the panel that caches it.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.use_cases import ai_analysis, cache_reset


class _Widget:
    def __init__(self) -> None:
        self.refreshed_batches: list = []
        self.refreshed_single: list = []

    def refresh_cards(self, items) -> None:
        self.refreshed_batches.append(list(items))

    def refresh_card(self, item) -> None:
        self.refreshed_single.append(item)


class _Owner:
    def __init__(self, items) -> None:
        self.state = SimpleNamespace(items=list(items), mode="camera", metric_profile=None)
        self.widget = _Widget()
        self._judgment_domain = "algorithms"
        self.ql_refreshes = 0

    def _refresh_open_quick_look(self) -> None:
        self.ql_refreshes += 1


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    it.metrics.update(metrics)
    return it


# -- hydrate repaints what it filled -----------------------------------------


def test_a_hydrated_item_is_repainted_immediately(monkeypatch) -> None:
    """The AI marker/dots must not wait for an unrelated repaint (QL open)."""
    item = _item("a.png")
    owner = _Owner([item])

    monkeypatch.setattr(
        ai_analysis,
        "analysis_identity_for",
        lambda owner, ctx=None: {},
    )
    monkeypatch.setattr(
        "tabs.image_gallery.services.ai_cache.hydrate_item",
        lambda it, identity: True,
    )

    filled = ai_analysis._hydrate_ai_cache(owner, [item])

    assert filled == 1
    assert owner.widget.refreshed_batches == [[item]], (
        "the hydrated card was not repainted (the marker/dots stayed pre-hydration"
    )
    assert owner.ql_refreshes == 1, "the open quick-look report was not rebuilt"


def test_a_hydrate_that_fills_nothing_repaints_nothing(monkeypatch) -> None:
    item = _item("a.png")
    owner = _Owner([item])
    monkeypatch.setattr(ai_analysis, "analysis_identity_for", lambda owner, ctx=None: {})
    monkeypatch.setattr(
        "tabs.image_gallery.services.ai_cache.hydrate_item",
        lambda it, identity: False,
    )
    assert ai_analysis._hydrate_ai_cache(owner, [item]) == 0
    assert owner.widget.refreshed_batches == []
    assert owner.ql_refreshes == 0


# -- reset rebuilds the open report ------------------------------------------


def test_the_reset_rebuilds_the_open_quick_look_report() -> None:
    item = _item("a.png", sharpness=300.0, noise=0.2)
    owner = _Owner([item])

    summary = cache_reset.clear_metrics_caches(owner, paths=[item.path])

    assert summary["items"] == 1
    assert owner.ql_refreshes == 1, (
        "the open report kept its pre-reset rows (the reported 'metrics stayed')"
    )
    assert owner.widget.refreshed_batches, "the cleared card was not repainted"
    assert item.metrics == {}, "the measured metrics must be gone"
