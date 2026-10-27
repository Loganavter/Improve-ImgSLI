"""P2 — no premature "done", honest provenance (``task-analysis-phase-state``).

Measured defect (owner, 2026-10-26): ``proxy_pass`` stamped ``set_triage_done``
when the METRICS phase ended, so the app announced a finished analysis (and
cleared its badge) while the AI tail was still ahead — and the tail then
restarted the badge. The stats-strip chip rendered ``rank_source`` as final, so
the same run read "Алгоритмы" (fusion) and moments later "ИИ (Jev)".

Falsification story (each test names the defect it kills):

- **a** — an in-flight AI tail HOLDS the done announcement ("metrics done, AI
  pending" in the trace) instead of announcing completion and restarting it.
  Red before: the announce site called ``widget.set_triage_done`` directly.
- **b** — the held announcement lands exactly once when the tail goes quiet, and
  the chip switches from the pending value to the ACTUAL ranker. Red before: the
  chip showed ``fusion`` while the AI tail was still running.
- **c** — the phase is derived from facts, not a toggle: an in-flight scorecard
  or rank batch keeps it pending, and the Algorithms domain (no AI tail at all)
  is done immediately.

The widget is a recording double; the phase methods under test are the REAL
controller ones, so "held" is observed as "no done call", not inferred.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem
from tabs.image_gallery.services.ai_settings_store import AiSettings
from tabs.image_gallery.ui.stats_strip import RANK_SOURCE_PENDING, StatsStrip
from tabs.image_gallery.use_cases import proxy_pass
from core.log_names import APP_LOGGER_NAME

SETTINGS = AiSettings(
    enabled=True,
    base_url="https://openrouter.ai/api/v1",
    api_key="sk-not-a-real-secret",
    model="model/A",
    reasoning_effort="auto",
)

GEN = 5


class _Widget:
    """Recording widget double (only the seams the tails touch)."""

    def __init__(self) -> None:
        self.done_calls: list = []
        self.chips: list = []
        self.ranks_visible_calls: list = []

    def set_ranks_visible(self, want) -> None:
        self.ranks_visible_calls.append(bool(want))

    def set_triage(self, *args, **kwargs) -> None:
        return None

    def set_triage_done(self) -> None:
        self.done_calls.append(1)

    def set_rank_provenance(self, source=None, *, domain=None) -> None:
        self.chips.append(source)

    def refresh_card(self, item) -> None:
        return None

    def refresh_cards(self, items) -> None:
        return None

    def visible_paths(self) -> list:
        return []


class _Owner:
    """Qt-free controller double with the REAL phase methods bound."""

    def __init__(self, items, *, domain: str = "ai") -> None:
        self.state = SimpleNamespace(items=list(items), mode="camera", series=[])
        self.widget = _Widget()
        self._judgment_domain = domain
        self._folder_gen = GEN
        self._metrics_settled_gen = -1
        self._profile_settle_pending_gen = None
        self._profile_consumed_gen = None
        self._ai_tail_started_gen = -1
        self._jev_inflight_gen = -1
        self._done_held_gen = -1
        self._ai_batch_gen = GEN
        self._ai_batch_pending = 0
        self._ai_settings_store = SimpleNamespace(load=lambda: SETTINGS)
        self._last_analysis_fingerprint = None
        self.proxy_starts: list = []

    # -- real controller primitives ---------------------------------------
    def _announce_metrics_done(self):
        return GalleryController._announce_metrics_done(self)

    def _maybe_announce_done(self):
        return GalleryController._maybe_announce_done(self)

    def _stamp_triage_done(self):
        return GalleryController._stamp_triage_done(self)

    def _ai_tail_reasons(self):
        return GalleryController._ai_tail_reasons(self)

    def _ai_tail_pending(self):
        return GalleryController._ai_tail_pending(self)

    def _refresh_rank_provenance(self):
        return GalleryController._refresh_rank_provenance(self)

    def _refresh_ranks_visible(self):
        return GalleryController._refresh_ranks_visible(self)

    # -- seams the triage tail touches ------------------------------------
    def _start_proxy_analysis(self, items, source, mode, *, on_done=None):
        self.proxy_starts.append((items, on_done))

    def run_tie_break_if_needed(self, series) -> None:
        return None

    def _mark_local_pass(self, items, phase) -> None:
        return None

    def _apply_fusion_ranks(self, series, *, mode=None, pairwise_order=None) -> None:
        return None

    def _hydrate_ai_cache(self, items, *, ctx=None) -> int:
        return 0


def _item(name: str, *, analyzed: bool = False, rank=None, source=None) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update({"sharpness": 40.0})
    if analyzed:
        item.analysis = AiAnalysisResult(
            description="", tags=(), model="model/A", analyzed_at_iso="t",
            axes={"sharpness": 70},
        )
    if rank is not None:
        item.rank = rank
        item.rank_source = source
    return item


def _run_triage_tail(owner: _Owner) -> None:
    """Drive the REAL ``_apply_triage_result`` (the announce site)."""
    proxy_pass._apply_triage_result(owner, list(owner.state.series), None, "camera")


# ---------------------------------------------------------------------------
# (a) the metrics phase ending does not announce "done"
# ---------------------------------------------------------------------------


def test_an_in_flight_ai_tail_holds_the_done_announcement(monkeypatch, caplog) -> None:
    # The phase trace rides the one AI trace gate the gallery already uses.
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    owner = _Owner([_item("a.png"), _item("b.png")])  # no scorecards yet

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        _run_triage_tail(owner)

    assert owner.widget.done_calls == [], (
        "the app announced a finished analysis while the AI tail was still ahead "
        "(the badge is then restarted — the flicker this phase removes)"
    )
    assert owner._done_held_gen == GEN, "the announcement is HELD, not dropped"
    assert owner.widget.chips and owner.widget.chips[-1] == RANK_SOURCE_PENDING, (
        "the provenance chip must state that the run is still going, not present "
        "the provisional ranker as final"
    )
    assert any(
        "metrics done" in rec.getMessage() and "AI pending" in rec.getMessage()
        for rec in caplog.records
    ), "the hold must be visible in the trace"


def test_the_hold_lands_once_when_the_tail_settles(monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    item = _item("a.png", rank=1, source="jev")  # no scorecard yet: the tail is ahead
    owner = _Owner([item])
    owner.state.series = [SimpleNamespace(members=[item])]
    owner._metrics_settled_gen = GEN

    # Before the settle's AI dispatch: the tail is ahead, so the announce holds.
    owner._ai_tail_started_gen = -1
    _run_triage_tail(owner)
    assert owner.widget.done_calls == [], "still ahead of the AI tail"

    # The scorecard arrived and the settle dispatched its tails; nothing is in
    # flight any more.
    item.analysis = AiAnalysisResult(
        description="", tags=(), model="model/A", analyzed_at_iso="t",
        axes={"sharpness": 70},
    )
    owner._ai_tail_started_gen = GEN
    owner._jev_inflight_gen = -1
    owner._ai_batch_pending = 0

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        owner._maybe_announce_done()

    assert owner.widget.done_calls == [1], "the held done lands exactly once"
    assert owner._done_held_gen == -1, "the hold is consumed, not remembered"
    # The rank badges were blanked while the tail ran (the apply re-evaluates
    # visibility with this very batch in flight). The tail-settle seam must
    # re-evaluate them, or a ranked card keeps no #N/BEST (owner 2026-10-27).
    assert owner.widget.ranks_visible_calls, (
        "the tail-settle seam must re-evaluate rank visibility"
    )
    assert owner.widget.ranks_visible_calls[-1] is True, (
        "with the metrics settled and no tail pending the ranks are FINAL"
    )
    assert owner.widget.chips[-1] == "jev", (
        "once the tail settled, the chip states the ranker that actually ranked "
        "(the AI domain's Jev), not the provisional fusion order"
    )
    assert any(
        "AI tail settled" in rec.getMessage() for rec in caplog.records
    ), "the release is traced with its generation"

    # Idempotent: a second tail-settle must not announce done again.
    owner._maybe_announce_done()
    assert owner.widget.done_calls == [1]


# ---------------------------------------------------------------------------
# (c) the phase is derived from facts
# ---------------------------------------------------------------------------


def test_an_in_flight_scorecard_or_rank_keeps_the_phase_pending() -> None:
    owner = _Owner([_item("a.png", analyzed=True)])
    owner._ai_tail_started_gen = GEN
    owner._done_held_gen = GEN

    owner._ai_batch_pending = 1
    assert owner._ai_tail_pending() is True
    owner._maybe_announce_done()
    assert owner.widget.done_calls == []

    owner._ai_batch_pending = 0
    owner._jev_inflight_gen = GEN
    assert owner._ai_tail_pending() is True
    owner._maybe_announce_done()
    assert owner.widget.done_calls == []

    owner._jev_inflight_gen = -1
    assert owner._ai_tail_pending() is False
    owner._maybe_announce_done()
    assert owner.widget.done_calls == [1]


def test_the_algorithms_domain_is_done_when_its_metrics_settle() -> None:
    """No AI tail exists off the AI domain — the gate must not invent one."""
    owner = _Owner([_item("a.png"), _item("b.png")], domain="algorithms")

    _run_triage_tail(owner)

    assert owner._ai_tail_reasons() == ()
    assert owner.widget.done_calls == [1], "the local pipeline is done at its settle"


def test_a_warm_folder_is_done_immediately() -> None:
    """Every card already carries a scorecard: nothing is ahead of anything."""
    owner = _Owner([_item("a.png", analyzed=True), _item("b.png", analyzed=True)])

    _run_triage_tail(owner)

    assert owner.widget.done_calls == [1]


def test_unconfigured_ai_has_no_tail() -> None:
    owner = _Owner([_item("a.png")])
    owner._ai_settings_store = SimpleNamespace(
        load=lambda: AiSettings(enabled=False)
    )
    _run_triage_tail(owner)
    assert owner.widget.done_calls == [1]


# ---------------------------------------------------------------------------
# the chip's pending value (stats strip)
# ---------------------------------------------------------------------------


def test_the_stats_strip_renders_an_explicit_pending_value(qtbot) -> None:
    strip = StatsStrip()
    qtbot.addWidget(strip)

    strip.set_rank_provenance(RANK_SOURCE_PENDING)
    assert strip.rank_source == RANK_SOURCE_PENDING
    assert strip.rank_provenance_label.text().strip(), "a pending chip is never blank"
    assert "Analyzing" in strip.rank_provenance_label.text(), (
        "the pending state uses the existing activity word (no new catalogue key)"
    )

    # …and it is replaced by the real ranker, never by an empty chip.
    strip.set_rank_provenance("jev")
    assert "AI (Jev)" in strip.rank_provenance_label.text()
    strip.set_rank_provenance(None)
    assert strip.rank_provenance_label.text() == ""


def test_pending_is_not_a_domain_default(qtbot) -> None:
    """A domain fallback can never claim "analyzing" forever."""
    strip = StatsStrip()
    qtbot.addWidget(strip)
    strip.set_rank_provenance(None, domain="ai")
    assert strip.rank_source == "jev"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
