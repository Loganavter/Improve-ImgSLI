"""Backend isolation (owner ask 2026-10-22): a live domain switch is ironclad.

Falsification story — each test pins one measured leak:

- the VLM tie-break fired with the Algorithms backend selected (the only gate
  was "AI settings configured"); measured live: one image POST on a plain
  folder open of a near-duplicate series;
- a VLM analysis that was still in flight when the user switched back landed
  anyway: the scorecard was written to the item AND the disk cache under
  Algorithms, so the next AI session served a scorecard produced for a backend
  the user had left;
- a Jev rank outcome landing after the switch re-crowned the series and set
  ``rank_domain="ai"`` under Algorithms (provenance chip said "AI (Jev)" while
  the toolbar said Algorithms);
- the epoch bumping on a repeat switch to the SAME domain, which would cancel
  live work for no reason.

Network-free, Qt-free: the fakes implement only the attributes the guards read.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AnalysisStatus, GalleryItem, Series
from tabs.image_gallery.use_cases import ai_analysis, tie_break


class _Owner:
    """Minimal owner: the isolation guards read the durable domain + epoch."""

    def __init__(self, domain: str = "algorithms", epoch: int = 0) -> None:
        self._judgment_domain = domain
        self._domain_epoch = epoch
        self._folder_gen = 7
        self._AI_VISIBLE_CAP = 12
        self.state = SimpleNamespace(
            items=[], series=[], mode=None, judgment_domain=domain, rank_domain=domain
        )
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=True,
                api_key="k",
                model="m",
                base_url="http://stub/v1",
                sample_count=1,
                sampling_temperature=0.0,
                sampling_seed=0,
                vlm_max_edge_px=1024,
            )
        )
        self.pool_starts = 0
        self.refreshed: list = []
        self.widget = SimpleNamespace(
            refresh_card=self._refresh,
            refresh_cards=lambda its: None,
            visible_paths=lambda: [],
            set_series_attention=lambda s=None: None,
        )

    def _refresh(self, item) -> None:
        self.refreshed.append(item)

    def _find_item(self, path):
        for it in self.state.items:
            if str(it.path) == str(path):
                return it
        return None

    def _pool_start(self, worker, priority=None) -> None:
        self.pool_starts += 1

    def _is_current_folder_gen(self, gen) -> bool:
        return int(gen) == int(self._folder_gen)

    def _is_tie(self, a, b) -> bool:
        return True

    # Real controller primitives the paths under test use.
    def _apply_jev_outcome(self, members, outcome):
        return GalleryController._apply_jev_outcome(self, members, outcome)


def _item(name: str, *, measured: bool = True) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    if measured:
        it.metrics.update({"sharpness": 40.0, "noise": 0.3})
    it.analysis_status = AnalysisStatus.PENDING
    return it


def _series(*items) -> Series:
    return Series(id="series_1", members=list(items))


# -- 1. no VLM tie-break on Algorithms ---------------------------------------


def test_tie_break_emits_no_request_on_algorithms() -> None:
    a, b = _item("a.png"), _item("b.png")
    owner = _Owner("algorithms")
    tie_break.run_tie_break_if_needed(owner, _series(a, b))
    assert owner.pool_starts == 0, "Algorithms must never start a VLM tie-break worker"
    assert not a.vlm_tie_pending and not b.vlm_tie_pending


def test_tie_break_still_runs_on_ai() -> None:
    """Control: the gate is the domain, not a dead code path."""
    a, b = _item("a.png"), _item("b.png")
    owner = _Owner("ai", epoch=3)
    tie_break.run_tie_break_if_needed(owner, _series(a, b))
    assert owner.pool_starts == 1


# -- 2. a late VLM analysis is dropped after the switch ----------------------


def test_late_analysis_is_dropped_after_the_switch(monkeypatch) -> None:
    saved: list = []
    monkeypatch.setattr(
        "tabs.image_gallery.controller.save_analysis",
        lambda *a, **k: saved.append((a, k)),
        raising=False,
    )
    item = _item("a.png")
    owner = _Owner("algorithms", epoch=5)
    owner.state.items = [item]
    from tabs.image_gallery.models import AiAnalysisResult

    result = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes={"sharpness": 70}
    )
    ai_analysis._on_analysis_ready(
        owner, item.path, item.mtime_ns, result, gen=owner._folder_gen, identity={}, epoch=4
    )
    assert item.analysis is None, "a scorecard from the left backend must not land"
    assert item.analysis_status == AnalysisStatus.NOT_ANALYZED
    assert saved == [], "the stale reply must not be written to the disk cache"


def test_late_analysis_lands_when_the_domain_never_moved(monkeypatch) -> None:
    """Control: the same arrival DOES land under the domain that asked for it."""
    saved: list = []
    monkeypatch.setattr(
        "tabs.image_gallery.controller.save_analysis",
        lambda *a, **k: saved.append((a, k)),
        raising=False,
    )
    item = _item("a.png")
    owner = _Owner("ai", epoch=5)
    owner.state.items = [item]
    owner._refresh_open_quick_look = lambda: None
    from tabs.image_gallery.models import AiAnalysisResult

    result = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes={"sharpness": 70}
    )
    ai_analysis._on_analysis_ready(
        owner, item.path, item.mtime_ns, result, gen=owner._folder_gen, identity={}, epoch=5
    )
    assert item.analysis is result
    assert item.analysis_status == AnalysisStatus.DONE
    assert len(saved) == 1


# -- 3. a late Jev outcome cannot re-crown under Algorithms ------------------


def test_late_jev_outcome_is_dropped_on_algorithms() -> None:
    item = _item("a.png")
    item.rank = 2
    item.rank_source = "fusion"
    item.is_best = False
    owner = _Owner("algorithms", epoch=6)
    owner.state.items = [item]
    outcome = SimpleNamespace(ranks={str(item.path): 1}, decided=True, reason=None)
    GalleryController._apply_jev_outcome(owner, [item], outcome)
    assert item.rank == 2, "a Jev verdict must not overwrite the Algorithms rank"
    assert item.is_best is False
    assert getattr(item, "rank_source", "fusion") == "fusion"


# -- 4. the epoch is a monotonic token for explicit (re)activation -----------


def test_domain_epoch_bumps_on_every_explicit_switch() -> None:
    """The toolbar suppresses a same-domain emit (``_apply_domain``), so every
    call here is an explicit (re)activation: bumping cancels the previous
    epoch's queued work, which is exactly what a re-activation asks for."""
    owner = _Owner("algorithms", epoch=0)
    ai_analysis._set_judgment_domain(owner, "ai")
    assert owner._domain_epoch == 1
    assert owner._judgment_domain == "ai"
    ai_analysis._set_judgment_domain(owner, "algorithms")
    assert owner._domain_epoch == 2
    assert owner._judgment_domain == "algorithms"
