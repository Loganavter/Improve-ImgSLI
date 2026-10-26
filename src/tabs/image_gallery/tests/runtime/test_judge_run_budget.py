"""Judge run states and caps its cost (board 2026-10-24).

Four behaviours under test, each with a falsification story:

(a) ESTIMATE FIRST, then a hard CALL ceiling — the pass stops on the last whole
    card that fits and leaves the refused cards on a continue list. Fails if the
    estimate is emitted after the first reservation, if the ceiling is not
    enforced, or if a refused card is touched (it must stay analyzable).
(b) provider concurrency comes from the setting, never ``os.cpu_count()``, and
    the provider admission gate is exactly that wide. Fails if the width is
    derived from the CPU count or the semaphore is unbounded.
(c) a simulated ``AiRateLimitError(retry_after=...)`` pauses the WHOLE queue —
    a second worker's send must not fire while paused — and resuming re-queues
    the parked card (no card is lost, none is marked ERROR).
(d) the estimator formula for ``k`` in {1, 2, 3, 5} and ``N`` in {1, 12, 30},
    including the provider's tile rule on the WIRE edge.
(e) the continue affordance exists exactly after a ceiling stop and is absent
    when ``judge_run_call_ceiling == 0``.

Runs offscreen; no network, no window (the controller double never starts a
real worker). The double's state carries a real, AI-tagged axis set because
the AI backend has no local fallback since R6: an axis-less context is
refused by name instead of being judged on borrowed detector axes.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AnalysisStatus, GalleryItem
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_client import AiRateLimitError
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.use_cases import ai_analysis
from tabs.image_gallery.use_cases import judge_budget
from tabs.image_gallery.use_cases import scheduler
from tabs.image_gallery.use_cases.action_context import (
    ORIGIN_ACTION,
    context_for_paths,
)
from core.log_names import APP_LOGGER_NAME


# -- doubles ------------------------------------------------------------------


#: The judge's OWN axis set (owner rule 2026-10-26, invariant I1): the AI
#: backend never borrows the local mode mapping, so every AI action carries a
#: real, AI-tagged profile — and a 0-axis call is refused by name
#: (``REFUSAL_NO_PROFILE``). The budget/ceiling ledger is only reached for
#: cards that can actually be judged, hence the fixture's slot.
_AI_PROFILE = MetricProfile(
    axis_ids=("sharpness", "noise"), mode="camera", source="vlm"
)


class _Text:
    """Stand-in for the toolbar's activity text (``scanning_label``)."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.tooltips: list[str] = []

    def setText(self, text) -> None:  # noqa: N802 (Qt name)
        self.texts.append(str(text))

    def setToolTip(self, text) -> None:  # noqa: N802 (Qt name)
        self.tooltips.append(str(text))

    def show(self) -> None:
        pass


class _Toolbar:
    def __init__(self) -> None:
        self.scanning_label = _Text()

    def set_triage_done(self) -> None:
        pass


class _Widget:
    def __init__(self) -> None:
        self.toolbar = _Toolbar()

    def refresh_card(self, item) -> None:
        pass

    def refresh_cards(self, items) -> None:
        pass

    def set_ranks_visible(self, flag) -> None:
        pass


def _item(name: str) -> GalleryItem:
    return GalleryItem(path=Path("/gallery") / name, mtime_ns=1)


def _settings(**overrides):
    base = dict(
        enabled=True,
        api_key="k",
        model="m",
        base_url="http://h",
        sample_count=1,
        judge_run_call_ceiling=0,
        judge_concurrency=3,
        vlm_max_edge_px=1024,
        sampling_temperature=0.0,
        sampling_seed=0,
        reasoning_effort="auto",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _owner(items, **settings_overrides):
    """A storeless controller double that binds the REAL analyze path."""
    ctl = GalleryController.__new__(GalleryController)
    # ``mode`` + a REAL owned AI profile: ``context_for_paths`` snapshots the
    # active profile of THIS action's backend (``profile_select.active_profile``
    # → the AI adapter's slot), which is what makes the run judge anything at
    # all under the 5..8 / no-0-axis rule.
    ctl.state = SimpleNamespace(
        items=list(items), mode="camera", ai_profile=_AI_PROFILE
    )
    ctl.widget = _Widget()
    ctl._folder_gen = 0
    ctl._judgment_domain = "ai"
    ctl._domain_epoch = 0
    ctl._tr = lambda key, default: default
    row = _settings(**settings_overrides)
    ctl._ai_settings_store = SimpleNamespace(load=lambda: row)
    # No real pool: a scheduled worker would be a real network call.
    ctl._pool_start = lambda worker, priority: None
    ctl._activity_bridge = None
    return ctl


# -- (a) estimate first, then the ceiling -------------------------------------


def test_counted_pass_states_the_estimate_first_and_stops_at_the_ceiling() -> None:
    items = [_item(f"{i}.png") for i in range(5)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=2)

    ctx = context_for_paths(owner, [it.path for it in items], origin=ORIGIN_ACTION)
    owner.analyze(ctx)

    run = owner._judge_run
    assert run.calls == 2          # the two cards that fit
    assert run.stopped is True
    assert run.skipped == [it.path for it in items[2:]]
    # The card the ceiling refused is NOT an error and NOT in flight: it stays
    # analyzable for the continue affordance.
    assert all(it.analysis_status == AnalysisStatus.PENDING for it in items[:2])
    assert all(it.analysis_status == AnalysisStatus.NOT_ANALYZED for it in items[2:])

    # User-visible text: the ESTIMATE is the first thing written, the stop last.
    texts = owner.widget.toolbar.scanning_label.texts
    assert texts, "the run stated nothing in the activity text"
    assert texts[0].startswith("AI judge: up to 5 × 1 = 5 calls")
    assert "estimate" in texts[0]
    assert len(texts) == 2 and "ceiling" not in texts[0].lower()
    assert "2-call limit" in texts[1]
    # The tooltip carries the SAME full sentence (the row elides the paint, so
    # the ceiling mention is only reachable here).
    assert owner.widget.toolbar.scanning_label.tooltips == texts


def test_ceiling_stop_trace_line_is_exact(monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{i}.png") for i in range(3)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=1)

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        ctx = context_for_paths(owner, [it.path for it in items], origin=ORIGIN_ACTION)
        owner.analyze(ctx)

    lines = [rec.getMessage() for rec in caplog.records]
    stops = [ln for ln in lines if "judge run stop" in ln]
    assert stops == ["[ai] judge run stop: ceiling 1 calls"]
    estimate_at = next(i for i, ln in enumerate(lines) if "judge run start" in ln)
    stop_at = next(i for i, ln in enumerate(lines) if "judge run stop" in ln)
    assert estimate_at < stop_at, "the estimate must be stated before the stop"


def test_ceiling_never_overshoots_when_a_card_costs_k_calls() -> None:
    items = [_item(f"{i}.png") for i in range(4)]
    # k = 3: two cards cost 6 calls, a third would cost 9 > 7.
    owner = _owner(items, sample_count=3, judge_run_call_ceiling=7)

    ctx = context_for_paths(owner, [it.path for it in items], origin=ORIGIN_ACTION)
    owner.analyze(ctx)

    assert owner._judge_run.calls == 6
    assert owner._judge_run.stopped is True
    assert owner._judge_run.calls <= 7
    assert owner._judge_run.skipped == [it.path for it in items[2:]]


# -- (e) the continue affordance ----------------------------------------------


def test_continue_affordance_after_a_ceiling_stop_reopens_the_run() -> None:
    items = [_item(f"{i}.png") for i in range(5)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=2)

    ctx = context_for_paths(owner, [it.path for it in items], origin=ORIGIN_ACTION)
    owner.analyze(ctx)
    assert owner.judge_run_continue_available is True

    assert owner.continue_judge_run() is True
    # The continuation starts a FRESH window over the parked cards: 2 more fit,
    # the remaining one is parked again (the ceiling is not silently lifted).
    assert [it.analysis_status for it in items[2:4]] == [
        AnalysisStatus.PENDING,
        AnalysisStatus.PENDING,
    ]
    assert owner._judge_run.skipped == [items[4].path]
    assert owner.judge_run_continue_available is True


def test_no_continue_affordance_without_a_ceiling() -> None:
    items = [_item(f"{i}.png") for i in range(3)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=0)

    ctx = context_for_paths(owner, [it.path for it in items], origin=ORIGIN_ACTION)
    owner.analyze(ctx)

    assert owner._judge_run.stopped is False
    assert owner.judge_run_continue_available is False
    assert owner.continue_judge_run() is False
    assert all(it.analysis_status == AnalysisStatus.PENDING for it in items)


# -- (d) the estimator --------------------------------------------------------


@pytest.mark.parametrize("k", [1, 2, 3, 5])
@pytest.mark.parametrize("n", [1, 12, 30])
def test_estimate_formula(n: int, k: int) -> None:
    est = judge_budget.estimate_judge_run(n, k, wire_edge=1024)

    assert est.cards == n
    assert est.k == k
    assert est.calls_max == n * k
    # Provider image-token rule at a 1024-px wire edge: 2x2 tiles of 512 px,
    # 85 tokens each + the 170-token base, plus the prompt/answer envelope.
    image_tokens = 170 + 4 * 85
    per_call = image_tokens + judge_budget._PROMPT_TOKENS_MAX + judge_budget._ANSWER_TOKENS_MAX
    assert est.tokens_max == n * k * per_call


def test_estimate_is_an_upper_bound_on_the_wire_edge() -> None:
    small = judge_budget.estimate_judge_run(1, 1, wire_edge=512)
    large = judge_budget.estimate_judge_run(1, 1, wire_edge=2048)
    assert large.tokens_max > small.tokens_max
    # edge 0 = "send the original bytes": unbounded, so the estimator assumes
    # the largest declared downscale choice instead of claiming zero cost.
    assert judge_budget.estimate_judge_run(1, 1, wire_edge=0).tokens_max == large.tokens_max
    # A run of zero cards costs nothing (a fully cached pass).
    assert judge_budget.estimate_judge_run(0, 3, wire_edge=1024).calls_max == 0


# -- (b) provider-aware concurrency -------------------------------------------


def test_judge_concurrency_comes_from_the_setting_not_the_cpu_count(monkeypatch) -> None:
    from tabs.image_gallery.controller import _GALLERY_SCHED_MIN_THREADS

    monkeypatch.setattr(os, "cpu_count", lambda: 64)
    monkeypatch.setattr(
        AiSettingsStore, "load", lambda self: _settings(judge_concurrency=2)
    )
    scheduler.reset_judge_concurrency_cache()
    scheduler.reset_provider_slots()
    try:
        assert scheduler.judge_concurrency() == 2
        # The pool is shared with thumbnail decodes, so it keeps the decode
        # floor; the PROVIDER width (what reaches the API) is the setting.
        assert scheduler._scheduler_thread_count() == max(
            _GALLERY_SCHED_MIN_THREADS, 2
        )
        with scheduler.ai_provider_slot():
            assert scheduler._AI_SLOTS_WIDTH == 2
    finally:
        scheduler.reset_judge_concurrency_cache()
        scheduler.reset_provider_slots()


def test_provider_slot_caps_in_flight_requests(monkeypatch) -> None:
    monkeypatch.setattr(
        AiSettingsStore, "load", lambda self: _settings(judge_concurrency=2)
    )
    scheduler.reset_judge_concurrency_cache()
    scheduler.reset_provider_slots()
    live = 0
    peak = 0
    lock = threading.Lock()

    def _work() -> None:
        nonlocal live, peak
        with scheduler.ai_provider_slot():
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.02)
            with lock:
                live -= 1

    try:
        threads = [threading.Thread(target=_work) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        assert peak == 2, f"provider width was {peak}, expected the configured 2"
    finally:
        scheduler.reset_judge_concurrency_cache()
        scheduler.reset_provider_slots()


def test_settings_clamp_both_new_fields(monkeypatch) -> None:
    group = "image_gallery_ai_judge_budget_test"
    monkeypatch.setattr(store_module, "_QS_GROUP", group)
    qsettings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    qsettings.remove(group)
    store = AiSettingsStore()
    try:
        assert store.load().judge_concurrency == 3
        assert store.load().judge_run_call_ceiling == 0

        store.save_field("judge_concurrency", 99)
        store.save_field("judge_run_call_ceiling", -5)
        loaded = store.load()
        assert loaded.judge_concurrency == 8
        assert loaded.judge_run_call_ceiling == 0

        store.save_field("judge_concurrency", 0)
        store.save_field("judge_run_call_ceiling", 12)
        loaded = store.load()
        assert loaded.judge_concurrency == 1
        assert loaded.judge_run_call_ceiling == 12
    finally:
        qsettings.remove(group)


# -- (c) run-level 429 --------------------------------------------------------


def test_rate_limit_pauses_the_queue_then_resumes_without_losing_cards(monkeypatch) -> None:
    items = [_item("a.png"), _item("b.png")]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=0)
    judge_budget.begin_judge_run(owner, len(items))

    # Card A hits a 429: it is parked, not failed, and the queue pauses.
    error = AiRateLimitError("HTTP 429", retry_after="5")
    ai_analysis._on_analysis_error(
        owner, items[0].path, (AiRateLimitError, error, None), 0
    )
    assert scheduler.ai_queue_paused(owner) is True
    assert owner._ai_queue_retry == [items[0].path]
    assert items[0].analysis_status != AnalysisStatus.ERROR
    assert items[0].analysis_error is None

    sent: list[str] = []
    monkeypatch.setattr(
        ai_analysis, "analyze_image_sync", lambda path, **kw: sent.append(str(path))
    )
    # Card B's worker is already on a pool thread: it must NOT fire while the
    # run is paused (one request's retries cannot keep the others going).
    worker = threading.Thread(
        target=ai_analysis._send_if_current,
        args=(owner, ai_analysis.domain_epoch(owner), items[1].path),
    )
    worker.start()
    time.sleep(0.2)
    assert sent == [], "a send went out while the run-level pause was armed"

    scheduler.resume_ai_queue(owner)
    worker.join(5)
    assert not worker.is_alive()
    assert sent == [str(items[1].path)]
    assert scheduler.ai_queue_paused(owner) is False
    # Resume re-queued the parked card through the ORDINARY path: it is
    # analyzable again (no card lost) with no error message.
    assert items[0].analysis_status == AnalysisStatus.PENDING
    assert owner._ai_queue_retry == []


def test_rate_limit_gives_up_after_the_retry_budget(monkeypatch) -> None:
    items = [_item("a.png")]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=0)
    judge_budget.begin_judge_run(owner, 1)

    monkeypatch.setattr(scheduler, "pause_ai_queue", lambda *a, **k: None)
    for _ in range(judge_budget._AI_RATE_LIMIT_MAX_RETRIES):
        error = AiRateLimitError("HTTP 429", retry_after="1")
        ai_analysis._on_analysis_error(
            owner, items[0].path, (AiRateLimitError, error, None), 0
        )
        assert items[0].analysis_status != AnalysisStatus.ERROR

    # The budget is spent: the next 429 is reported like any other failure.
    error = AiRateLimitError("HTTP 429", retry_after="1")
    ai_analysis._on_analysis_error(
        owner, items[0].path, (AiRateLimitError, error, None), 0
    )
    assert items[0].analysis_status == AnalysisStatus.ERROR
    assert items[0].analysis_error


# -- the pairwise bound is part of the estimate (row task-pairwise-default-on)


def test_estimate_prices_the_pairwise_bound_when_armed() -> None:
    """`calls_max` is the WHOLE run bound: pointwise + the refinement.

    Row task-pairwise-default-on states the precondition for defaulting the flag:
    a hidden refinement is how a near-tie folder gets an understated estimate.
    """
    est = judge_budget.estimate_judge_run(10, 3, wire_edge=1024, pairwise_calls_max=20)

    assert est.pointwise_calls_max == 30, "10 cards x 3 draws"
    assert est.pairwise_calls_max == 20, "10 cards x (top_n 3 - 1)"
    assert est.calls_max == 50, "the ceiling must carry both halves"
    plain = judge_budget.estimate_judge_run(10, 3, wire_edge=1024)
    assert plain.pairwise_calls_max == 0 and plain.calls_max == 30
    assert est.tokens_max > plain.tokens_max


def test_pairwise_estimate_bound_is_cards_times_top_n_minus_one() -> None:
    on = SimpleNamespace(pairwise_enabled=True, pairwise_top_n=3)
    off = SimpleNamespace(pairwise_enabled=False, pairwise_top_n=3)
    single = SimpleNamespace(pairwise_enabled=True, pairwise_top_n=1)

    assert judge_budget._pairwise_estimate_bound(10, on) == 20
    assert judge_budget._pairwise_estimate_bound(10, off) == 0, "flag off prices nothing"
    assert judge_budget._pairwise_estimate_bound(10, single) == 0, "one member cannot pair"
    assert judge_budget._pairwise_estimate_bound(1, on) == 0


def test_the_activity_line_names_the_pairwise_half_only_when_armed() -> None:
    owner = _owner(
        [_item("a.png")], pairwise_enabled=True, pairwise_top_n=3, sample_count=3
    )
    judge_budget.begin_judge_run(owner, 10)
    text = owner.widget.toolbar.scanning_label.texts[-1]
    assert "= 30 calls" in text, text
    assert "up to 20 pairwise" in text, text
    # The tooltip carries the same sentence (the line elides in the toolbar).
    assert owner.widget.toolbar.scanning_label.tooltips[-1] == text

    owner_off = _owner([_item("a.png")], sample_count=3)
    judge_budget.begin_judge_run(owner_off, 10)
    plain = owner_off.widget.toolbar.scanning_label.texts[-1]
    assert "pairwise" not in plain.lower(), plain
