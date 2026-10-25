"""Pairwise ordering of a near-tie top set (board: pointwise cannot order them).

Five behaviours, each with a falsification story:

(a) POSITION BIAS is caught by the swap: a scripted judge that always answers
    "A wins" in BOTH orders produces a TIE for every pair (a one-order pass
    would have crowned whichever image was presented first).
(b) a DECIDED series spends zero calls: the pointwise spread across the top set
    exceeds the declared threshold, so the whole pairwise pass is skipped and
    the pointwise order stands.
(c) the pass is COUNTED: at most ``N x (N-1)`` calls (each unordered pair asked
    in both orders), zero for a decided series, and zero on a cache hit.
(d) the cache key is the UNORDERED pair of content keys plus model, prompt
    version and BOTH wire edges: ``(A,B)`` and ``(B,A)`` share ONE entry, two
    different pairs never share a verdict, and a different model/version/edge
    is a different question.
(e) an INCOMPLETE comparison set never produces an order: a single unanswered
    presentation keeps the pointwise order intact and marks the pass in the
    trace as ``judge_pairwise.incomplete ... order_kept=pointwise``.

Plus the integration contract: ``rank_series(pairwise_order=...)`` is the
opt-in rank source (callers that do not pass it keep today's ordering), and the
pointwise quality numbers survive the pairwise order untouched.

Runs offscreen; no network, no window (the judge is a scripted callable). The
wiring section drives the pass through its PRODUCTION entry points — the
explicit domain switch and the terminal-rank tail of a settled judge run
(``analysis_batch.dispatch_terminal_rank``) — never only by calling
``start_pairwise_refinement`` directly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import Series
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettings, AiSettingsStore
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.profile_judged import scorecard_axis_ids
from tabs.image_gallery.services.rank_fusion import item_quality, rank_series
from tabs.image_gallery.use_cases import ai_analysis
from tabs.image_gallery.use_cases import analysis_batch
from tabs.image_gallery.use_cases import judge_budget
from tabs.image_gallery.use_cases.pairwise_rank import (
    ANSWER_FIRST,
    PairwiseVerdictCache,
    content_key,
    member_qualities,
    pair_key,
    pairwise_calls_bound,
    precheck,
    profile_axis_numbers,
    run_pairwise_pass,
)


# -- doubles ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_verdict_cache():
    """The live path uses the PROCESS-WIDE cache; tests must not inherit it."""
    from tabs.image_gallery.use_cases import pairwise_rank

    pairwise_rank.DEFAULT_CACHE.clear()
    yield
    pairwise_rank.DEFAULT_CACHE.clear()



def _item(name: str, quality: float):
    """One gallery item whose pointwise quality is exactly *quality*."""
    record = SimpleNamespace(axis="sharpness", status="ok", value=float(quality))
    return SimpleNamespace(
        path=Path("/gallery") / name,
        mtime_ns=1,
        analysis_records=(record,),
        metrics={},
    )


def _settings(**overrides):
    base = dict(
        enabled=True,
        api_key="k",
        model="model-x",
        base_url="http://provider.invalid",
        sample_count=1,
        judge_run_call_ceiling=0,
        vlm_max_edge_px=1024,
        pairwise_enabled=True,
        pairwise_top_n=5,
        pairwise_near_tie_threshold=10.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _owner(row):
    owner = SimpleNamespace(
        _ai_settings_store=SimpleNamespace(load=lambda: row), _folder_gen=0
    )
    return owner


class _ScriptedJudge:
    """Deterministic judge that records every presentation it was asked."""

    def __init__(self, answer, *, edge: int = 1024) -> None:
        self.answer = answer
        self.edge = edge
        self.calls = 0
        self.presentations: list[tuple[str, str]] = []

    def edge_of(self, _content: str, _path=None) -> int:
        return self.edge

    def __call__(self, item_a, item_b):
        self.calls += 1
        self.presentations.append(
            (Path(item_a.path).name, Path(item_b.path).name)
        )
        if callable(self.answer):
            return self.answer(item_a, item_b)
        return self.answer


def _pass(items, judge, *, row=None, owner=None, cache=None, **kwargs):
    row = row or _settings()
    owner = owner or _owner(row)
    ranks = rank_series(items)
    return run_pairwise_pass(
        owner,
        items,
        pointwise_ranks=ranks,
        settings=row,
        judge=judge,
        cache=cache if cache is not None else PairwiseVerdictCache(),
        **kwargs,
    )


# -- (a) the swap catches position bias ---------------------------------------


def test_always_a_judge_ends_in_a_tie_not_a_crown() -> None:
    items = [_item(f"{name}.png", 80) for name in "abcde"]
    judge = _ScriptedJudge("A")
    result = _pass(items, judge)

    assert result.applied is True
    assert len(result.verdicts) == 10
    assert all(v.forward == ANSWER_FIRST for v in result.verdicts)
    assert all(v.reverse == ANSWER_FIRST for v in result.verdicts)
    assert all(v.agree is False for v in result.verdicts), "a swap disagreement is a TIE"
    assert all(v.winner is None for v in result.verdicts)
    assert result.ties == 10
    # Every pair really was asked in both orders.
    assert len(judge.presentations) == 20
    assert result.order_paths == tuple(sorted(str(it.path) for it in items))


# -- (b) a decided series spends nothing --------------------------------------


def test_decided_series_skips_the_pass_with_zero_calls() -> None:
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (95, 70, 50, 30, 10))]
    judge = _ScriptedJudge(lambda a, b: (_ for _ in ()).throw(AssertionError("called")))
    cache = PairwiseVerdictCache()
    result = _pass(items, judge, cache=cache)

    assert result.reason == "decided"
    assert result.applied is False
    assert judge.calls == 0
    assert len(cache) == 0
    pointwise = rank_series(items)
    assert rank_series(items, pairwise_order=result.order_paths) == pointwise


# -- (c) the call bound -------------------------------------------------------


def test_call_count_is_bounded_by_n_times_n_minus_one() -> None:
    # Near-tie: the top-set spread (4 points) is inside the 10-point threshold.
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]
    quality = {Path(it.path).name: item_quality(it) for it in items}

    def better(a, b):
        return "A" if quality[Path(a.path).name] >= quality[Path(b.path).name] else "B"

    judge = _ScriptedJudge(better)
    cache = PairwiseVerdictCache()
    result = _pass(items, judge, cache=cache)

    assert result.applied is True
    assert result.calls_bound == pairwise_calls_bound(5) == 20
    assert result.calls == 20
    assert result.calls <= 5 * (5 - 1)
    assert judge.calls == 20
    assert result.order_paths == tuple(str(it.path) for it in items)  # decisive, agreed

    # A second pass over the SAME verdicts spends zero calls and zero budget.
    again = _pass(items, judge, cache=cache)
    assert again.applied is True
    assert again.calls == 0
    assert again.cached == 10
    assert judge.calls == 20  # unchanged

    # And a decided series still spends nothing, with a fresh cache.
    decided = [_item(f"d{name}.png", q) for name, q in zip("abcde", (95, 70, 50, 30, 10))]
    fresh = _ScriptedJudge(better)
    fresh_cache = PairwiseVerdictCache()
    skipped = _pass(decided, fresh, cache=fresh_cache)
    assert skipped.reason == "decided" and fresh.calls == 0 and len(fresh_cache) == 0


def test_ceiling_refusal_spends_nothing_and_keeps_the_pointwise_order() -> None:
    items = [_item(f"{name}.png", 80) for name in "abcde"]
    row = _settings(judge_run_call_ceiling=4)  # the pass needs 20
    owner = _owner(row)
    judge = _ScriptedJudge("A")
    result = _pass(items, judge, row=row, owner=owner)

    assert result.applied is False and result.reason == "ceiling"
    assert judge.calls == 0
    assert owner._judge_run.calls == 0, "a refused pass must not consume the ceiling"
    assert rank_series(items, pairwise_order=result.order_paths) == rank_series(items)


# -- (d) the cache key --------------------------------------------------------


def test_cache_key_is_the_unordered_pair_plus_model_version_and_both_edges() -> None:
    ab = pair_key("A:1", 1024, "B:2", 2048, model="m", prompt_version=1)
    ba = pair_key("B:2", 2048, "A:1", 1024, model="m", prompt_version=1)
    assert ab == ba, "(A,B) and (B,A) must share ONE unordered entry"

    assert pair_key("A:1", 1024, "C:3", 2048, model="m", prompt_version=1) != ab
    assert pair_key("A:1", 1024, "B:2", 2048, model="other", prompt_version=1) != ab
    assert pair_key("A:1", 1024, "B:2", 2048, model="m", prompt_version=2) != ab
    assert pair_key("A:1", 512, "B:2", 2048, model="m", prompt_version=1) != ab
    assert pair_key("A:1", 1024, "B:2", 4096, model="m", prompt_version=1) != ab

    items = [_item(f"{name}.png", 80) for name in "abcde"]
    cache = PairwiseVerdictCache()
    _pass(items, _ScriptedJudge("B"), cache=cache)
    assert len(cache) == 10, "10 unordered pairs, never 20 ordered ones"
    # Content identity is the file (path + mtime), not the quality number...
    assert content_key(items[0]) == content_key(_item("a.png", 81))
    # ...and an edited file is a different identity (the verdict is not reused).
    edited = SimpleNamespace(path=Path("/gallery/a.png"), mtime_ns=2, metrics={})
    assert content_key(edited) != content_key(items[0])


# -- (e) no order from an incomplete comparison set ---------------------------


def test_incomplete_set_keeps_the_pointwise_order_and_is_traced(
    monkeypatch, caplog
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]

    def flaky(a, b):
        # Two presentations never answer (the same pair asked twice): the set
        # stays incomplete and no order may be produced from it.
        return None if Path(a.path).name == "c.png" else "A"

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        result = _pass(items, _ScriptedJudge(flaky))
    assert result.applied is False
    assert result.reason == "incomplete"
    assert result.order_paths == ()
    assert any(not verdict.resolved for verdict in result.verdicts)

    pointwise = rank_series(items)
    assert rank_series(items, pairwise_order=result.order_paths) == pointwise

    lines = [record.getMessage() for record in caplog.records]
    incomplete = [ln for ln in lines if "judge_pairwise.incomplete" in ln]
    assert incomplete, "the trace must mark the incomplete pass"
    assert any("order_kept=pointwise" in ln for ln in incomplete)


# -- the integration seam -----------------------------------------------------


def test_pairwise_order_is_an_opt_in_rank_source_with_visible_numbers() -> None:
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]
    row = _settings(pairwise_top_n=2)
    result = _pass(items, _ScriptedJudge("A"), row=row)

    # Two pairs of the top-2: every pair is a swap disagreement -> tie, but the
    # comparison set is complete, so a (path-ordered) pairwise order exists.
    assert result.applied is True
    assert len(result.members) == 2
    assert result.calls == 2
    top_two = [str(member.path) for member in result.members]
    assert set(result.order_paths) == set(top_two)

    default = rank_series(items)
    pw = rank_series(items, pairwise_order=result.order_paths)
    assert set(pw) == set(default), "the pairwise order never drops a member"
    assert sorted(pw.values()) == [1, 2, 3, 4, 5]
    # The pairwise order decides the top set; the rest keeps the pointwise order.
    assert tuple(p for p, _r in sorted(pw.items(), key=lambda kv: kv[1])[:2]) == result.order_paths
    rest_default = [p for p, r in sorted(default.items(), key=lambda kv: kv[1]) if p not in top_two]
    rest_pw = [p for p, r in sorted(pw.items(), key=lambda kv: kv[1]) if p not in top_two]
    assert rest_pw == rest_default

    # The NUMBERS stay: same quality per item, exposed next to the pairwise order.
    assert [q for _p, q in result.pointwise] == [
        item_quality(it) for it in items[:2]
    ]
    assert {p: q for p, q in result.pointwise} == {
        str(it.path): item_quality(it) for it in items[:2]
    }

    # Opt-in by construction: without the parameter, today's order is untouched.
    assert rank_series(items) == default


# -- settings: declared defaults + clamps -------------------------------------


def test_pairwise_settings_have_declared_defaults_and_clamps(monkeypatch) -> None:
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_pairwise")
    from PySide6.QtCore import QSettings

    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_pairwise")

    store = AiSettingsStore()
    row = store.load()
    # OFF by default: this wave ships no settings row for the flag, so a
    # default-on pass would be an unreachable, unstated spend.
    assert row.pairwise_enabled is False
    assert AiSettings().pairwise_enabled is False
    assert row.pairwise_top_n == 5
    assert row.pairwise_near_tie_threshold == 10.0
    assert AiSettings().pairwise_top_n == 5

    store.save_field("pairwise_top_n", 99)
    store.save_field("pairwise_near_tie_threshold", 500)
    store.save_field("pairwise_enabled", "yes")
    row = store.load()
    assert row.pairwise_top_n == store_module.PAIRWISE_TOP_N_MAX == 8
    assert row.pairwise_near_tie_threshold == store_module.PAIRWISE_NEAR_TIE_THRESHOLD_MAX
    # An explicit opt-in is persisted (not clamped away)...
    assert row.pairwise_enabled is True
    # ...and turning it back off persists too.
    store.save_field("pairwise_enabled", False)
    assert store.load().pairwise_enabled is False

    store.save_field("pairwise_top_n", 0)
    store.save_field("pairwise_near_tie_threshold", -4)
    row = store.load()
    assert row.pairwise_top_n == store_module.PAIRWISE_TOP_N_MIN == 2
    assert row.pairwise_near_tie_threshold == 0.0
    settings.remove("image_gallery_ai_test_pairwise")


def test_generated_pairwise_prompt_is_a_separate_variant() -> None:
    from tabs.image_gallery.services.ai_client.parse import parse_pairwise_verdict
    from tabs.image_gallery.services.ai_client.prompt import (
        PAIRWISE_PROMPT_VERSION,
        PROMPT_TEMPLATE,
        build_pairwise_prompt,
        build_prompt,
    )

    pairwise = build_pairwise_prompt()
    assert PAIRWISE_PROMPT_VERSION == 1
    assert "WINNER: A|B|TIE" in pairwise
    assert pairwise != PROMPT_TEMPLATE
    # The pointwise prompt is untouched by the pairwise variant.
    assert build_prompt() != pairwise
    assert "A/B" not in build_prompt()

    assert parse_pairwise_verdict("WINNER: A") == "A"
    assert parse_pairwise_verdict("Winner: b\n") == "B"
    assert parse_pairwise_verdict('{"winner": "tie"}') == "TIE"
    assert parse_pairwise_verdict("WINNER: TIE") == "TIE"
    assert parse_pairwise_verdict("I think A looks sharper") is None
    assert parse_pairwise_verdict("") is None
    assert parse_pairwise_verdict(None) is None


# -- the WIRING: the pass is reachable, off the GUI thread, fail-open --------
#
# Falsification stories (each assertion fails without the wiring):
# (f) flag OFF (the shipped default): no worker is scheduled and no judge call
#     is attempted — fails if the pass runs, or if the trace is emitted per
#     series instead of once per run;
# (g) flag ON + a near-tie series: the APPLIED ranks come from the pairwise
#     order (the view is re-ordered through ``_apply_fusion_ranks``), and the
#     pointwise numbers are still readable — fails if the result is computed and
#     dropped, or if the numbers are replaced by the order;
# (h) a ceiling refusal admits zero pairwise calls and keeps the pointwise
#     order — fails if the reservation is bypassed or the pass partially spends;
# (i) a judge that raises keeps the pointwise order and marks no card failed —
#     fails if a pairwise failure leaks into the analysis results;
# (j) the run's ONE call counter counts pointwise + admitted pairwise calls —
#     fails if the pass opens a second counter or double-counts.


class _WiringWidget:
    """Bare widget surface the rank primitive touches."""

    def __init__(self) -> None:
        self.refreshed: list = []
        self.ranks_visible: list = []

    def refresh_card(self, item) -> None:
        self.refreshed.append(item)

    def refresh_cards(self, items) -> None:
        self.refreshed.extend(items)

    def set_ranks_visible(self, flag) -> None:
        self.ranks_visible.append(flag)

    def set_rank_provenance(self, _src, **_kwargs) -> None:
        pass


def _wired_owner(items, **settings_overrides):
    """Controller double with the REAL rank primitive and no real pool.

    ``_pool_start`` only records the worker, so a test drives the pass itself
    (``worker.run()``) — the GUI thread is never blocked in the test, exactly
    as in the app.
    """
    ctl = GalleryController.__new__(GalleryController)
    ctl.state = SimpleNamespace(
        items=list(items),
        series=[Series(id="s0", members=list(items))],
        mode="camera",
        metric_profile=None,
    )
    ctl.widget = _WiringWidget()
    ctl._folder_gen = 0
    ctl._judgment_domain = "algorithms"
    ctl._domain_epoch = 0
    ctl._metrics_settled_gen = 0
    ctl._tr = lambda key, default: default
    row = _settings(**settings_overrides)
    ctl._ai_settings_store = SimpleNamespace(load=lambda: row)
    ctl._settings_row = row
    ctl.launched: list = []
    ctl._pool_start = lambda worker, priority: ctl.launched.append(worker)
    ctl._tracked = lambda fn: fn
    ctl._sched_lock = None
    ctl._sched_pending = 0
    ctl._sched_active = 0
    ctl._sched_peak = 0
    ctl._AI_VISIBLE_CAP = 4
    # The Algorithms-domain terminal ranker: a NO-OP that only records, exactly
    # like the real ``_run_jev_ranks`` (it refuses off the AI domain). The
    # pairwise tail hangs off the same trigger, so this must still be called.
    ctl.jev_calls = 0

    def _run_jev_ranks() -> None:
        ctl.jev_calls += 1

    ctl._run_jev_ranks = _run_jev_ranks
    return ctl


def _ranks(items) -> dict:
    return {str(it.path): (it.rank, it.rank_source) for it in items}


def _boom(*_args, **_kwargs):
    raise AssertionError("the pairwise judge must not be called")


def _trace_lines(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def test_wiring_with_flag_off_makes_zero_calls_and_keeps_the_pointwise_ranks(
    monkeypatch, caplog
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]
    owner = _wired_owner(items, pairwise_enabled=False)
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)

    judge = _ScriptedJudge(_boom)
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert ai_analysis.start_pairwise_refinement(owner, judge=judge) is False
        # A second call in the SAME run must not repeat the line.
        assert ai_analysis.start_pairwise_refinement(owner, judge=judge) is False

    assert owner.launched == [], "the off flag must not schedule a worker"
    assert judge.calls == 0, "the off flag must not spend a judge call"
    assert _ranks(items) == before, "the pointwise ranks must be untouched"
    disabled = [
        line for line in _trace_lines(caplog) if "judge_pairwise.skip reason=disabled" in line
    ]
    assert len(disabled) == 1, disabled


def test_wiring_flag_on_near_tie_applies_the_pairwise_order(monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner._apply_fusion_ranks(owner.state.series)
    pointwise = _ranks(items)
    assert (items[0].rank, items[1].rank) == (1, 2), pointwise

    # b.png wins whichever side it is shown on: both presentations agree, so
    # the pair resolves and the pairwise order puts b before a.
    judge = _ScriptedJudge(
        lambda a, b: "A" if Path(a.path).name == "b.png" else "B"
    )
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert ai_analysis.start_pairwise_refinement(owner, judge=judge) is True
        assert len(owner.launched) == 1, "one pass per series"
        owner.launched[0].run()  # the pool would run this off the GUI thread

    assert judge.calls == 2, "one unordered pair, asked in both orders"
    assert items[1].rank == 1, "the pairwise order must decide the top set"
    assert items[0].rank == 2
    assert [items[2].rank, items[3].rank, items[4].rank] == [3, 4, 5]
    assert all(it.rank_source == "fusion" for it in items)
    # Ranks only: the pointwise NUMBERS stay readable next to the order.
    assert [item_quality(it) for it in items] == [80, 79, 78, 77, 76]
    lines = _trace_lines(caplog)
    assert any("judge_pairwise.apply" in line for line in lines), lines


def test_wiring_ceiling_refusal_spends_nothing_and_keeps_the_pointwise_order(
    monkeypatch, caplog
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]
    # The pass needs 2 calls (top_n=2); the run may spend 1.
    owner = _wired_owner(
        items, pairwise_enabled=True, pairwise_top_n=2, judge_run_call_ceiling=1
    )
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)

    judge = _ScriptedJudge("A")
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert ai_analysis.start_pairwise_refinement(owner, judge=judge) is True
        owner.launched[0].run()

    assert judge.calls == 0, "a refused reservation must admit zero calls"
    assert owner._judge_run.calls == 0, "a refusal must not consume the ceiling"
    assert _ranks(items) == before
    budget = [
        line for line in _trace_lines(caplog) if "judge_pairwise.skip reason=budget" in line
    ]
    assert budget, "the refusal must be traced with reason=budget"


def test_wiring_error_path_keeps_pointwise_and_marks_no_card_failed(
    monkeypatch, caplog
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)

    judge = _ScriptedJudge(_boom)  # every presentation raises
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert ai_analysis.start_pairwise_refinement(owner, judge=judge) is True
        owner.launched[0].run()

    assert judge.calls == 2, "the failure reached the judge, it was not skipped"
    assert _ranks(items) == before, "a pairwise failure keeps the pointwise order"
    assert not any(hasattr(it, "analysis_error") for it in items), "no card error"
    assert not any(hasattr(it, "analysis_status") for it in items), "no card mutation"
    lines = _trace_lines(caplog)
    errors = [line for line in lines if "judge_pairwise.skip reason=error" in line]
    assert errors, lines
    assert "exc=" in errors[0]


def test_wiring_counts_pointwise_and_pairwise_calls_in_the_one_ledger(
    monkeypatch,
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]
    owner = _wired_owner(
        items,
        pairwise_enabled=True,
        pairwise_top_n=2,
        judge_run_call_ceiling=100,
        sample_count=1,
    )
    row = owner._settings_row
    # The pointwise pass: one call per card, reserved on the GUI thread.
    judge_budget.begin_judge_run(owner, len(items), settings=row)
    for it in items:
        assert judge_budget._reserve_judge_call(owner, it, settings=row) is True
    pointwise_calls = owner._judge_run.calls
    assert pointwise_calls == 5

    owner._apply_fusion_ranks(owner.state.series)
    judge = _ScriptedJudge(lambda a, b: "A" if Path(a.path).name == "b.png" else "B")
    assert ai_analysis.start_pairwise_refinement(owner, judge=judge) is True
    owner.launched[0].run()

    admitted = judge.calls
    assert admitted == 2, "top_n=2 is ONE pair in both orders"
    # ONE counter: pointwise reservations + admitted pairwise calls, no second
    # ledger and no double count.
    assert owner._judge_run.calls == pointwise_calls + admitted == 7


def test_wiring_free_gates_decide_before_a_worker_exists(monkeypatch, caplog) -> None:
    """A decided / too-small series spends nothing and never occupies a slot."""
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    judge = _ScriptedJudge(_boom)

    decided_items = [
        _item(f"d{name}.png", q) for name, q in zip("abcde", (95, 70, 50, 30, 10))
    ]
    decided = _wired_owner(decided_items, pairwise_enabled=True)
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert ai_analysis.start_pairwise_refinement(decided, judge=judge) is False
    assert decided.launched == [], "a decided series must not schedule a worker"
    assert judge.calls == 0
    assert any(
        "judge_pairwise.skip reason=decided" in line for line in _trace_lines(caplog)
    )

    caplog.clear()
    solo = _wired_owner([_item("solo.png", 80)], pairwise_enabled=True)
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert ai_analysis.start_pairwise_refinement(solo, judge=judge) is False
    assert solo.launched == [], "a one-member series must not schedule a worker"
    assert any(
        "judge_pairwise.skip reason=too_small" in line for line in _trace_lines(caplog)
    )


def test_wiring_keeps_each_series_pairwise_order_across_applies(monkeypatch) -> None:
    """Two near-tie series: the second apply must not drop the first's order."""
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcd", (80, 79, 78, 77))]
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner.state.series = [
        Series(id="s0", members=items[:2]),
        Series(id="s1", members=items[2:]),
    ]
    owner._apply_fusion_ranks(owner.state.series)
    assert [it.rank for it in items] == [1, 2, 1, 2]

    def judge(a, b):
        pair = {Path(a.path).name, Path(b.path).name}
        # Each series' SECOND-by-pointwise item wins, so the pairwise order is
        # the opposite of the pointwise one in both groups.
        if pair & {"a.png", "b.png"}:
            return "A" if Path(a.path).name == "b.png" else "B"
        return "A" if Path(a.path).name == "d.png" else "B"

    assert ai_analysis.start_pairwise_refinement(
        owner, judge=_ScriptedJudge(judge)
    ) is True
    assert len(owner.launched) == 2, "one pass per near-tie series"
    for worker in owner.launched:
        worker.run()

    assert [it.rank for it in items] == [2, 1, 2, 1], "both series keep their order"


# -- the TERMINAL-RANK trigger: a settled judge run refines its own order -----
#
# Board 2026-10-25: the pass had exactly ONE production caller — the manual
# domain switch — so a series that had just been judged kept its pointwise
# order until the user flipped the domain and back (measured live: a completed
# run, ledger ``{pointwise: 4, pairwise: 0}``, not one ``judge_pairwise.*``
# line). The tail now hangs off ``analysis_batch.dispatch_terminal_rank`` — the
# ONE "the matrix has settled" trigger — and runs AFTER the pointwise order is
# applied and OUTSIDE ``_apply_fusion_ranks`` (that primitive is how this very
# pass applies its result, so a trigger inside it would re-enter itself).
#
# Falsification stories (each assertion fails with the wiring absent):
# (k) a settled run with the flag ON starts exactly ONE pass and its order is
#     APPLIED (the ranks flip) — at the base commit the terminal path schedules
#     nothing, so ``launched`` stays empty and the pointwise order stands;
# (l) a second trigger while the pass is in flight starts none, and a re-run
#     over the same verdicts spends ZERO judge calls;
# (m) the flag OFF keeps the ``skip reason=disabled`` line (ONE per run) and
#     builds no client — before the wiring that line did not exist on this path;
# (n) a folder switch during the pass discards the late result and does not
#     block the new folder's pass;
# (o) a wide-spread (decided) series traces ``skip reason=decided`` and spends
#     nothing;
# (p) an unusable AI row is the ERROR form of the trace, schedules no worker and
#     keeps the pointwise order (fail open, never a card error);
# (q) an INCOMPLETE matrix (``analysis_batch.pending()`` non-zero) starts
#     neither the ranker nor the pass.


def _install_client(monkeypatch, judge):
    """Point the PRODUCTION client build at *judge* (no network, no settings)."""
    from tabs.image_gallery.use_cases import pairwise_rank

    monkeypatch.setattr(
        pairwise_rank,
        "build_client_judge",
        lambda _row, **_kwargs: judge,
    )
    return judge


def _b_wins(a, _b) -> str:
    """``b.png`` wins whichever side it is presented on (a decisive verdict)."""
    return "A" if Path(a.path).name == "b.png" else "B"


def _near_tie_items():
    return [_item(f"{name}.png", q) for name, q in zip("abcde", (80, 79, 78, 77, 76))]


def _new_folder(owner) -> int:
    """The folder switch as the app performs it (gen bump + unsettled settle)."""
    owner._folder_gen += 1
    owner._metrics_settled_gen = -1
    return owner._folder_gen


def test_terminal_rank_starts_the_pass_and_applies_its_order(monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _near_tie_items()
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner._apply_fusion_ranks(owner.state.series)
    assert (items[0].rank, items[1].rank) == (1, 2), "pointwise decides the top set first"

    judge = _install_client(monkeypatch, _ScriptedJudge(_b_wins))
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert analysis_batch.dispatch_terminal_rank(owner) is True
        assert owner.jev_calls == 1, "the terminal path still ran the (no-op) ranker"
        assert len(owner.launched) == 1, "the settled run starts exactly ONE pass"
        owner.launched[0].run()  # the pool would run this off the GUI thread

    assert judge.calls == 2, "one unordered pair, asked in both orders"
    assert (items[1].rank, items[0].rank) == (1, 2), "the pairwise order decided the top set"
    assert [items[2].rank, items[3].rank, items[4].rank] == [3, 4, 5]
    assert all(it.rank_source == "fusion" for it in items)
    # Ranks only: the pointwise NUMBERS survive next to the applied order.
    assert [item_quality(it) for it in items] == [80, 79, 78, 77, 76]
    assert any("judge_pairwise.apply" in line for line in _trace_lines(caplog))


def test_terminal_rank_is_single_flight_and_a_cached_rerun_spends_nothing(
    monkeypatch,
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _near_tie_items()
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner._apply_fusion_ranks(owner.state.series)
    judge = _install_client(monkeypatch, _ScriptedJudge(_b_wins))

    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert len(owner.launched) == 1
    # A second settle/arrival of the SAME generation must not spawn a second
    # pass while the first one is in flight.
    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert len(owner.launched) == 1, "one pass per (folder generation, series) in flight"

    owner.launched[0].run()
    assert judge.calls == 2
    assert (items[1].rank, items[0].rank) == (1, 2)

    # Once it reported, a later trigger may re-derive the SAME order from the
    # verdict cache: applied again, zero new calls.
    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert len(owner.launched) == 2, "a settled re-run is allowed, and is free"
    owner.launched[1].run()
    assert judge.calls == 2, "a cache hit must spend ZERO judge calls"
    assert (items[1].rank, items[0].rank) == (1, 2), "the cached order is re-applied"


def test_terminal_rank_with_the_flag_off_traces_disabled_once(monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _near_tie_items()
    owner = _wired_owner(items, pairwise_enabled=False)
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)

    def _no_client(_row, **_kwargs):
        raise AssertionError("the disabled flag must not build a client")

    from tabs.image_gallery.use_cases import pairwise_rank

    monkeypatch.setattr(pairwise_rank, "build_client_judge", _no_client)

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        # Every arrival lands here, so the line must be per RUN, not per trigger.
        assert analysis_batch.dispatch_terminal_rank(owner) is True
        assert analysis_batch.dispatch_terminal_rank(owner) is True

    assert owner.launched == [], "the off flag must not schedule a worker"
    assert owner.jev_calls == 2, "the ranker still ran; only the pass is off"
    assert _ranks(items) == before, "the pointwise ranks must be untouched"
    disabled = [
        line for line in _trace_lines(caplog) if "judge_pairwise.skip reason=disabled" in line
    ]
    assert len(disabled) == 1, disabled


def test_terminal_rank_folder_switch_discards_the_late_result(monkeypatch) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _near_tie_items()
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)
    judge = _install_client(monkeypatch, _ScriptedJudge(_b_wins))

    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert len(owner.launched) == 1

    _new_folder(owner)  # the user opens another folder while the pass runs
    owner.launched[0].run()  # ...and the pass reports into the new world
    assert _ranks(items) == before, "no cross-folder order may be applied"

    # The stale pass must not block the new folder's own pass.
    owner._metrics_settled_gen = owner._folder_gen
    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert len(owner.launched) == 2, "a new generation gets its own pass"
    owner.launched[1].run()
    assert (items[1].rank, items[0].rank) == (1, 2), "the new folder's order applies"


def test_terminal_rank_decided_series_spends_nothing(monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = [_item(f"{name}.png", q) for name, q in zip("abcde", (95, 70, 50, 30, 10))]
    owner = _wired_owner(items, pairwise_enabled=True)
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)

    judge = _install_client(monkeypatch, _ScriptedJudge(_boom))
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert analysis_batch.dispatch_terminal_rank(owner) is True

    assert owner.launched == [], "a decided series must not occupy a pool slot"
    assert judge.calls == 0, "a decided series must not spend a call"
    assert _ranks(items) == before
    assert any(
        "judge_pairwise.skip reason=decided" in line for line in _trace_lines(caplog)
    )


def test_terminal_rank_fails_open_when_no_provider_is_configured(monkeypatch, caplog) -> None:
    """An unusable AI row is the ERROR form of the trace, never a rank change."""
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _near_tie_items()
    owner = _wired_owner(items, pairwise_enabled=True)
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)
    _install_client(monkeypatch, None)  # the row names no usable provider

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert analysis_batch.dispatch_terminal_rank(owner) is True

    assert owner.launched == [], "an unavailable provider must not occupy a pool slot"
    assert _ranks(items) == before, "the pointwise order stands"
    errors = [line for line in _trace_lines(caplog) if "judge_pairwise.skip reason=error" in line]
    assert errors and "ProviderUnavailable" in errors[0], errors


def test_terminal_rank_keeps_the_settle_gate_before_the_pass(monkeypatch) -> None:
    """An incomplete matrix starts neither the ranker nor the refinement.

    The "is the batch over" refusal is ``analysis_batch.pending()``'s job (the
    existing model for this trigger); here it is pinned for the NEW tail too:
    refining a top set derived from a half-arrived matrix would compare the
    wrong members and spend calls on an order that will change again.
    """
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _near_tie_items()
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner._apply_fusion_ranks(owner.state.series)
    judge = _install_client(monkeypatch, _ScriptedJudge(_boom))

    owner._ai_batch_gen = owner._folder_gen
    owner._ai_batch_pending = 1  # one analysis of this generation still in flight
    assert analysis_batch.dispatch_terminal_rank(owner) is False
    assert owner.jev_calls == 0, "the ranker waits for the complete matrix"
    assert owner.launched == [], "the pass waits for the complete matrix"
    assert judge.calls == 0

    analysis_batch.end(owner)  # the last analysis reports -> the matrix settled
    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert len(owner.launched) == 1, "the settled batch starts the one pass"


def test_terminal_rank_refuses_in_the_ai_domain_and_runs_after_a_switch(
    monkeypatch,
) -> None:
    """The AI domain owns the displayed order — the pass must not spend there.

    The pass refines the POINTWISE (fusion) order. Under ``ai`` the rank on
    screen is Jev's (``rank_source="jev"`` items are locked in
    ``_apply_fusion_ranks``), so refining the fusion order would spend up to
    N x (N-1) judge calls on an order the user cannot see. This fails if the
    ``_epoch_is_current(..., domain="algorithms")`` gate is dropped from
    ``dispatch_pairwise_refinement`` — the absence assertion alone would pass
    for any reason, the switch pair is what pins the gate.
    """
    items = _near_tie_items()
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner._apply_fusion_ranks(owner.state.series)
    before = _ranks(items)
    owner._judgment_domain = "ai"

    built: list = []
    judge = _ScriptedJudge(_b_wins)
    from tabs.image_gallery.use_cases import pairwise_rank

    monkeypatch.setattr(
        pairwise_rank,
        "build_client_judge",
        lambda row, **_kwargs: (built.append(row), judge)[1],
    )

    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert built == [], "the AI domain must not even build a judge client"
    assert owner.launched == [], "no pass may start while Jev owns the order"
    assert judge.calls == 0, "no call spent on an order nobody sees"
    assert _ranks(items) == before, "the pointwise order is left untouched"

    # Back in the Algorithms domain the SAME settled generation does refine:
    # the pair of assertions proves the domain gate, not a missing trigger.
    owner._judgment_domain = "algorithms"
    assert analysis_batch.dispatch_terminal_rank(owner) is True
    assert len(owner.launched) == 1, "one pass once the pointwise order owns the view"
    owner.launched[0].run()
    assert judge.calls == 2, "one unordered pair, asked in both orders"
    assert (items[1].rank, items[0].rank) == (1, 2), "the pairwise order applied"


# -- MEASURED = the ACTIVE profile's own axes, in BOTH judgment stores --------
#
# Board 2026-10-25 (live, real provider, 3-image folder): the trigger FIRED —
# the terminal-rank tail re-entered after a 9-call judge run AND after switching
# back to the Algorithms domain — but the pass could not start:
# ``judge_pairwise.skip reason=too_small top_n=3 members=3 measured=0``, logged
# BOTH before and after the judge run, so it was not a settle race.
#
# Diagnostic answer (printed by the first test below; recorded in the task's
# DONE.md): a judge run writes its numbers to ``item.analysis.axes`` under the
# axes the metric profile ASKED for — which on such a folder is the profile's
# JUDGE half (free-form names like ``texture_fidelity``). ``PairMember.quality``
# came from ``rank_fusion.item_quality``, whose axis resolver
# (``measured_axes_for``) is the REGISTRY half on purpose (a judge name has no
# local producer) and whose per-member vector reads only
# ``analysis_records``/``item.metrics``. Nothing on those two paths names a
# judged axis, so every member's quality was None → measured=0 → too_small → the
# pass never spent a call.
#
# Falsification stories:
# (r) a judged card reads its numbers through the profile's axes
#     (``profile_axis_numbers``) and its quality through the set-level read
#     (``member_qualities``) — fails if the fixture is not the judged shape
#     (e.g. it also carried a detector record, so the pass could open for the
#     wrong reason);
# (s) judge-named axes ALONE open the gate: a near-tie judged set gets past
#     too_small and the A/B pass really runs (2 calls, both orders) — at the
#     base commit the same fixture answers too_small with zero calls;
# (t) a WIDE judged spread is ``decided`` with ``spread=`` in the trace, not
#     too_small — the gate still spends nothing when the order is already clear;
# (u) a judged card with nothing scored anywhere still blocks the set with
#     ``unmeasured`` — the honest read never fabricates a number;
# (v) the production terminal-rank trigger schedules the pass on a judged
#     series (scripted owner, no network), so the fix reaches the live path.

JUDGE_AXES = (
    SimpleNamespace(
        name="texture_fidelity",
        definition="how faithfully fine texture and micro-detail are reproduced",
        scale="0-100",
        direction="higher-is-better",
    ),
    SimpleNamespace(
        name="halo_freedom",
        definition="absence of bright or dark halos along high-contrast edges",
        scale="0-100",
        direction="higher-is-better",
    ),
)


def _judge_profile(*, axis_ids=(), entries=JUDGE_AXES) -> MetricProfile:
    """The profile a VLM-derived series carries: judge half, maybe empty registry."""
    return MetricProfile(
        axis_ids=tuple(axis_ids),
        mode="camera",
        source="vlm",
        axis_entries=tuple(entries),
    )


def _judged_item(name: str, **scores):
    """A card a judge run scored: numbers on ``analysis.axes``, no local record."""
    return SimpleNamespace(
        path=Path("/gallery") / name,
        mtime_ns=1,
        analysis=SimpleNamespace(axes=dict(scores)),
        analysis_records=(),
        metrics={},
    )


def test_a_judged_card_is_measured_through_the_profiles_own_axes() -> None:
    """(r) the diagnostic: where a judged card's numbers actually live."""
    profile = _judge_profile()
    card = _judged_item("a.png", texture_fidelity=91, halo_freedom=90)
    axes = scorecard_axis_ids("camera", profile=profile)
    numbers = profile_axis_numbers(card, mode="camera", profile=profile)
    registry = item_quality(card, mode="camera", profile=profile)
    print(
        "\n[diagnostic] profile.axis_entries=%s\n"
        "             scorecard_axis_ids=%s\n"
        "             profile_axis_numbers=%s\n"
        "             rank_fusion.item_quality=%s"
        % (tuple(entry.name for entry in JUDGE_AXES), axes, numbers, registry)
    )

    assert axes == ("texture_fidelity", "halo_freedom"), (
        "the ACTIVE profile's asked set is its judge half when it has no "
        "registry ids — the same set the scorecard prompt asked for"
    )
    assert numbers == {"texture_fidelity": 91.0, "halo_freedom": 90.0}
    assert member_qualities([card], mode="camera", profile=profile) == [90.5]
    # A card with nothing scored on any profile axis is NOT measured: the read
    # never fills a gap (0 or a neighbour axis) to get past the gate.
    blank = SimpleNamespace(path=Path("/gallery") / "z.png", mtime_ns=1, metrics={})
    assert profile_axis_numbers(blank, mode="camera", profile=profile) == {}
    assert member_qualities([blank], mode="camera", profile=profile) == [None]


def test_judge_named_axes_alone_get_past_too_small_and_the_pass_runs() -> None:
    """(s) nothing but judge-named numbers: the pass is scheduled and applies."""
    profile = _judge_profile()
    items = [
        _judged_item("a.png", texture_fidelity=91, halo_freedom=90),
        _judged_item("b.png", texture_fidelity=89, halo_freedom=88),
        _judged_item("c.png", texture_fidelity=88, halo_freedom=87),
    ]
    row = _settings(pairwise_top_n=2, pairwise_near_tie_threshold=10.0)
    ranks = {str(item.path): index for index, item in enumerate(items, start=1)}

    assert (
        precheck(
            _owner(row),
            items,
            pointwise_ranks=ranks,
            settings=row,
            mode="camera",
            profile=profile,
        )
        is None
    ), "a judged near-tie set must be allowed to start a pass"

    judge = _ScriptedJudge(_b_wins)
    result = run_pairwise_pass(
        _owner(row),
        items,
        pointwise_ranks=ranks,
        settings=row,
        mode="camera",
        profile=profile,
        judge=judge,
        cache=PairwiseVerdictCache(),
    )

    assert result.reason != "too_small"
    assert result.applied is True
    assert judge.calls == 2, "one unordered pair, asked in both orders"
    assert [member.quality for member in result.members] == [90.5, 88.5]
    assert result.order_paths == (str(items[1].path), str(items[0].path))


def test_a_wide_judged_spread_is_decided_not_too_small(monkeypatch, caplog) -> None:
    """(t) the numbers exist and already separate them: zero calls, decided."""
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    profile = _judge_profile()
    items = [
        _judged_item("a.png", texture_fidelity=95, halo_freedom=94),
        _judged_item("b.png", texture_fidelity=60, halo_freedom=59),
        _judged_item("c.png", texture_fidelity=58, halo_freedom=57),
    ]
    row = _settings(pairwise_top_n=3, pairwise_near_tie_threshold=10.0)
    ranks = {str(item.path): index for index, item in enumerate(items, start=1)}
    judge = _ScriptedJudge(_boom)

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        result = run_pairwise_pass(
            _owner(row),
            items,
            pointwise_ranks=ranks,
            settings=row,
            mode="camera",
            profile=profile,
            judge=judge,
            cache=PairwiseVerdictCache(),
        )

    assert result.reason == "decided"
    assert result.applied is False
    assert judge.calls == 0, "a decided series must not spend a call"
    decided = [
        line for line in _trace_lines(caplog) if "judge_pairwise.skip reason=decided" in line
    ]
    assert decided, _trace_lines(caplog)
    assert "spread=" in decided[0], "the trace must state the judged spread it used"
    assert not any(
        "judge_pairwise.skip reason=too_small" in line for line in _trace_lines(caplog)
    )


def test_a_judged_card_with_nothing_scored_still_blocks_the_set(caplog) -> None:
    """(u) a half-unknown top set is ``unmeasured`` — never a fabricated number."""
    profile = _judge_profile()
    items = [
        _judged_item("a.png", texture_fidelity=91),
        _judged_item("b.png", texture_fidelity=89),
        SimpleNamespace(path=Path("/gallery") / "c.png", mtime_ns=1, metrics={}),
    ]
    row = _settings(pairwise_top_n=3)
    ranks = {str(item.path): index for index, item in enumerate(items, start=1)}
    judge = _ScriptedJudge(_boom)

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        result = run_pairwise_pass(
            _owner(row),
            items,
            pointwise_ranks=ranks,
            settings=row,
            mode="camera",
            profile=profile,
            judge=judge,
            cache=PairwiseVerdictCache(),
        )

    assert result.reason == "unmeasured"
    assert judge.calls == 0
    assert [member.quality for member in result.members] == [91.0, 89.0, None]


def test_terminal_rank_schedules_the_pass_on_a_judged_series(monkeypatch, caplog) -> None:
    """(v) the production trigger reaches the fix: a judged near-tie refines.

    Scope note: this pins the GATE (a pass is scheduled and really spends its
    two calls, and the derived order is handed to the ONE rank primitive). How
    far that order travels is ``rank_series``' half of the seam: it applies a
    pairwise order only to paths it MEASURED, and it decides "measured" through
    ``item_quality`` — the very read the sibling ``rank_fusion`` lane is
    extending to the profile's own axes. Asserting the final ranks here would
    pin another module's limitation, so the trace line is what is asserted.
    """
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    profile = _judge_profile()
    items = [
        _judged_item("a.png", texture_fidelity=91, halo_freedom=90),
        _judged_item("b.png", texture_fidelity=89, halo_freedom=88),
        _judged_item("c.png", texture_fidelity=88, halo_freedom=87),
    ]
    owner = _wired_owner(items, pairwise_enabled=True, pairwise_top_n=2)
    owner.state.metric_profile = profile
    owner._apply_fusion_ranks(owner.state.series)
    judge = _install_client(monkeypatch, _ScriptedJudge(_b_wins))

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        assert analysis_batch.dispatch_terminal_rank(owner) is True
        assert len(owner.launched) == 1, "a judged near-tie series starts ONE pass"
        owner.launched[0].run()

    assert judge.calls == 2, "one unordered pair, asked in both orders"
    lines = _trace_lines(caplog)
    assert any("judge_pairwise.apply" in line for line in lines), lines
    assert not any("judge_pairwise.skip reason=too_small" in line for line in lines), lines

