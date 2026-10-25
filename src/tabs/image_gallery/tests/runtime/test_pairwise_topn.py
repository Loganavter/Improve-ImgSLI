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

Runs offscreen; no network, no window (the judge is a scripted callable).
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
from tabs.image_gallery.services.rank_fusion import item_quality, rank_series
from tabs.image_gallery.use_cases import ai_analysis
from tabs.image_gallery.use_cases import judge_budget
from tabs.image_gallery.use_cases.pairwise_rank import (
    ANSWER_FIRST,
    PairwiseVerdictCache,
    content_key,
    pair_key,
    pairwise_calls_bound,
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
