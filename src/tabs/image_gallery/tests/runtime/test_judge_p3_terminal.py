"""P3 (plan-gallery-ai-judgement) — Jev as the TERMINAL calculator.

Falsification story (each test names the live defect it kills):

- **a** — the per-arrival trigger. N VLM scorecards arriving one by one must
  produce exactly ONE Jev dispatch, at the moment the matrix is COMPLETE, and
  the payload it ranks covers every member. Pre-change ``_on_analysis_ready``
  re-ran the ranker on EVERY arrival through a per-arrival coalescing flush
  (deleted with P3), and the metrics settle dispatched before any scorecard
  existed — a rank was asked for on a 3/6 and then a 5/6 matrix (plan §D1.1,
  live 19:12:19-22).
- **b** — the floor and the band. The code owns the deterministic order; the
  model may reorder ONLY items whose measured quality is indistinguishable
  (|quality - band leader| <= the instrument's noise floor). A model order
  that moves an item across the band boundary is recorded as a CONFLICT and
  the measured order wins (plan §D1.2). Pre-change the model's full order was
  applied as-is whenever it named every alias, so one stochastic sample
  replaced the measurement.
- **c** — a pool the model can extend. A VLM-proposed axis (``producer="vlm"``,
  ``kind=CANDIDATE``) survives parsing and reaches the Jev payload BY NAME with
  its per-variant scores; a proposal with no measurable meaning is refused with
  a recorded reason and never stored (plan §P3-B).
- **d** — the sampling config is part of the analyze cache identity: a k=1
  scorecard and a k=3 one are different measurements and must not share an
  entry (GA4, plan §P3-D).

Network-free: the transport is a stub that answers the vector it is given.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem, Mode, Series
from tabs.image_gallery.services import ai_cache, jev_cache
from tabs.image_gallery.services.ai_client import parse as ai_parse
from tabs.image_gallery.services.ai_settings_store import AiSettings
from tabs.image_gallery.services.jev_client import (
    build_measured_vector,
    rank_series_jev_detailed,
)
from tabs.image_gallery.use_cases import ai_analysis, triage_run
from tabs.image_gallery.use_cases import pipeline_stages as ps


def _ai_item(name: str, **axes) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes=dict(axes)
    )
    return it


def _result(**axes) -> AiAnalysisResult:
    return AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes=dict(axes)
    )


def _series(*items) -> Series:
    return Series(id="series_1", members=list(items))


def _chat(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


# ---------------------------------------------------------------------------
# (a) one terminal Jev call per series, after the matrix is complete
# ---------------------------------------------------------------------------


class _TerminalCtrl:
    """Minimal controller surface for the real settle/delivery/rank path."""

    def __init__(self, items, groups, *, cache_dir) -> None:
        self.state = SimpleNamespace(
            series=list(groups),
            items=list(items),
            mode=Mode.FIDELITY,
            metric_profile=None,
            rank_domain="algorithms",
        )
        self._judgment_domain = "ai"
        self._folder_gen = 0
        self._stage_gate = ps.StageGate()
        self._AI_VISIBLE_CAP = 12
        self._metrics_settled_gen = -1
        self.widget = SimpleNamespace(
            visible_paths=lambda: [],
            refresh_card=lambda it: None,
            refresh_cards=lambda its: None,
            set_ranks_visible=lambda visible: None,
            set_rank_provenance=lambda source=None, domain=None: None,
        )
        #: One entry per ``_run_jev_ranks`` trigger: how many members carried a
        #: score at that instant. ``[6]`` == one trigger, on a complete matrix.
        self.dispatch_sizes: list[int] = []
        self.launches: list[list[str]] = []
        self.payloads: list[dict] = []
        self.client_calls = 0
        self.applied: list[dict[str, int]] = []
        self._cache = jev_cache.JevRankCache(cache_dir)
        self._pending_analyses: list[Path] = []
        self._client = self._reply

    # -- transport ---------------------------------------------------------
    def _reply(self, payload: dict) -> dict:
        self.client_calls += 1
        body = json.loads(payload["messages"][-1]["content"][0]["text"])
        self.payloads.append(body)
        ordered = sorted(
            body["items"],
            key=lambda e: (
                -(sum((e.get("scores") or {}).values()) or 0),
                e["alias"],
            ),
        )
        return _chat({"ranking": [e["alias"] for e in ordered]})

    # -- controller seams bound to this fake -------------------------------
    def _find_item(self, path):
        return GalleryController._find_item(self, path)

    def _is_current_folder_gen(self, gen) -> bool:
        return GalleryController._is_current_folder_gen(self, gen)

    def _refresh_open_quick_look(self) -> None:
        return None

    def _mark_local_pass(self, items, phase) -> None:
        return None

    def _apply_fusion_ranks(self, series, *, mode=None) -> None:
        return None

    def _run_profile_select_on_settle(self) -> None:
        return None

    def _clear_series_priority(self) -> None:
        return None

    def _run_ai_for_visible(self) -> None:
        """Cold matrix: every visible card starts an analysis (no scores yet)."""
        try:
            from tabs.image_gallery.use_cases import analysis_batch
        except Exception:
            analysis_batch = None  # pre-change tree: no batch ledger exists
        for it in list(self.state.items):
            if getattr(it, "analysis", None) is not None:
                continue
            if it.path in self._pending_analyses:
                continue
            self._pending_analyses.append(it.path)
            if analysis_batch is not None:
                analysis_batch.begin(self)

    def _run_jev_on_settle(self) -> None:
        run = getattr(triage_run, "_run_jev_on_settle", None)
        if callable(run):
            run(self)

    def _run_jev_ranks(self) -> None:
        self.dispatch_sizes.append(
            sum(1 for it in self.state.items if getattr(it, "analysis", None) is not None)
        )
        return GalleryController._run_jev_ranks(self)

    def _run_jev_rank_for_series(self, members, *, on_complete=None) -> None:
        snapshot = list(members or ())
        self.launches.append([str(getattr(m, "path", "")) for m in snapshot])
        outcome = rank_series_jev_detailed(
            snapshot,
            mode="fidelity",
            client=self._client,
            cache=self._cache,
            domain="ai",
        )
        if outcome.ranks:
            GalleryController._apply_jev_outcome(self, snapshot, outcome)
            self.applied.append(dict(outcome.ranks))
        if callable(on_complete):
            on_complete(GalleryController._jev_outcome_ok(outcome))


def _deliver(owner: _TerminalCtrl, item: GalleryItem, axes: dict, monkeypatch) -> None:
    """Deliver one analysis the way the worker's ``result`` signal does."""
    monkeypatch.setattr(
        "tabs.image_gallery.controller.save_analysis", lambda *a, **k: None
    )
    ai_analysis._on_analysis_ready(owner, item.path, item.mtime_ns, _result(**axes))


def test_n_arrivals_produce_one_jev_call_on_the_complete_matrix(tmp_path, monkeypatch):
    items = [GalleryItem(path=Path(f"/gallery/img_{i}.png"), mtime_ns=0) for i in range(1, 7)]
    ctrl = _TerminalCtrl(items, [_series(*items)], cache_dir=tmp_path)
    scores = [90, 80, 70, 60, 50, 40]

    # The measured-metrics pass settles BEFORE any scorecard exists (the VLM
    # work is started by the same settle): no rank may be asked for yet.
    triage_run._settle_metrics_pass(ctrl, items)
    assert ctrl.launches == [], "a rank was dispatched on a 0/6 matrix"

    for item, score in zip(items, scores):
        _deliver(ctrl, item, {"ssim": score}, monkeypatch)
        if item is not items[-1]:
            assert ctrl.launches == [], (
                f"a Jev rank was dispatched before the matrix was complete "
                f"({items.index(item) + 1} of {len(items)} scored)"
            )

    assert ctrl.dispatch_sizes == [6], (
        f"exactly one terminal dispatch, on the complete matrix; got "
        f"{ctrl.dispatch_sizes}"
    )
    assert ctrl.client_calls == 1, "one Jev call per series, not one per arrival"
    assert ctrl.launches == [[str(it.path) for it in items]]
    payload_aliases = {entry["alias"] for entry in ctrl.payloads[0]["items"]}
    assert payload_aliases == {f"img_{i}" for i in range(1, 7)}, (
        "the single payload must cover every member of the series"
    )
    assert sorted(ctrl.applied[-1].values()) == [1, 2, 3, 4, 5, 6]


def test_a_cached_matrix_is_ranked_once_by_the_settle_itself(tmp_path, monkeypatch):
    """No analysis is in flight (all cached): the settle is the terminal trigger."""
    items = [_ai_item(f"img_{i}.png", ssim=s) for i, s in enumerate([90, 80, 70, 60], 1)]
    ctrl = _TerminalCtrl(items, [_series(*items)], cache_dir=tmp_path)
    ctrl._run_ai_for_visible = lambda: None  # type: ignore[method-assign]
    triage_run._settle_metrics_pass(ctrl, items)
    assert ctrl.dispatch_sizes == [4]
    assert ctrl.client_calls == 1
    triage_run._settle_metrics_pass(ctrl, items)
    assert ctrl.client_calls == 1, "a second settle over the same matrix is a no-op"


# ---------------------------------------------------------------------------
# (b) the floor and the band — the model decides only inside the noise floor
# ---------------------------------------------------------------------------


def _band_items() -> list[GalleryItem]:
    """Absolute qualities 90 / 40..60 — one clear leader, one tight band."""
    return _ai_item("img_1.png", ssim=90), *[
        _ai_item(f"img_{i}.png", ssim=s)
        for i, s in enumerate((40, 45, 50, 55, 60), start=2)
    ]


def test_model_reordering_beyond_the_band_is_a_visible_conflict(tmp_path):
    items = _band_items()
    paths = [str(it.path) for it in items]

    def _client(payload):
        # The worst variant promoted to the top: 40 vs the 90 leader is far
        # outside the AI domain's 20-point noise floor.
        return _chat({"ranking": ["img_2", "img_1", "img_3", "img_4", "img_5", "img_6"]})

    outcome = rank_series_jev_detailed(
        items,
        mode="fidelity",
        client=_client,
        cache=jev_cache.JevRankCache(tmp_path),
        domain="ai",
    )
    assert outcome.decided, outcome.reason
    assert outcome.ranks[paths[0]] == 1, (
        "the measured leader must keep rank 1 — an out-of-band move is refused"
    )
    assert getattr(outcome, "conflict", ""), (
        "an out-of-band reorder must be recorded as a conflict, not applied silently"
    )
    sources = getattr(outcome, "sources", None)
    assert sources is not None, "the applied order must record which source decided it"
    assert sources[f"{paths[0]}>{paths[1]}"] == "measured", (
        f"the leader/outsider pair is decided by the measurement; got {sources}"
    )


def test_model_reordering_inside_the_band_is_applied_with_its_source(tmp_path):
    items = _band_items()
    paths = [str(it.path) for it in items]

    def _client(payload):
        # img_2 (40) moved above img_6 (60): both sit in the leader-2 band, so
        # this is the model's call inside the noise floor, not a conflict.
        return _chat({"ranking": ["img_1", "img_2", "img_6", "img_5", "img_4", "img_3"]})

    outcome = rank_series_jev_detailed(
        items,
        mode="fidelity",
        client=_client,
        cache=jev_cache.JevRankCache(tmp_path),
        domain="ai",
    )
    assert outcome.decided, outcome.reason
    assert not getattr(outcome, "conflict", ""), (
        f"an in-band reorder is not a conflict; got {getattr(outcome, 'conflict', '')}"
    )
    assert outcome.ranks[paths[0]] == 1
    sources = getattr(outcome, "sources", None) or {}
    assert sources.get(f"{paths[0]}>{paths[1]}") == "measured"
    in_band = [pair for pair, src in sources.items() if src.startswith("model")]
    assert in_band, f"the in-band pair must record a model source; got {sources}"


def test_alias_tail_never_decides_an_out_of_band_position(tmp_path):
    """A short reply cannot promote an outsider: the measured block wins."""
    items = _band_items()
    paths = [str(it.path) for it in items]

    outcome = rank_series_jev_detailed(
        items,
        mode="fidelity",
        client=lambda payload: _chat({"ranking": ["img_2"]}),
        cache=jev_cache.JevRankCache(tmp_path),
        domain="ai",
    )
    assert outcome.decided, outcome.reason
    assert outcome.ranks[paths[0]] == 1, "a single-alias reply named the worst variant"
    assert sorted(outcome.ranks.values()) == [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# (c) a pool the model can extend
# ---------------------------------------------------------------------------

_GOOD_PROPOSAL = {
    "name": "halation",
    "definition": "Red glow bleeding around bright highlights, 0 = none, 100 = heavy",
    "scale": "0-100",
    "score": 72,
}
_MEANINGLESS_PROPOSAL = {
    "name": "vibes",
    "definition": "",
    "scale": "0-100",
    "score": 50,
}


def test_a_proposed_axis_survives_the_parser_and_reaches_the_jev_payload() -> None:
    raw = _chat(
        {
            "axes": {"ssim": 80},
            "axis_proposals": [_GOOD_PROPOSAL, _MEANINGLESS_PROPOSAL],
        }
    )
    result = ai_parse.parse_response(raw, model="m")

    assert [p.name for p in result.axis_proposals] == ["halation"], (
        "the measurable proposal must be kept as a first-class axis"
    )
    assert result.axis_proposals[0].score == 72
    assert result.axis_proposals[0].definition
    refused = dict(result.axis_proposal_refusals)
    assert "vibes" in refused, "a meaningless proposal must be recorded, never stored"
    assert refused["vibes"], "the refusal must carry a reason"

    items = [
        _ai_item("img_1.png", ssim=90),
        _ai_item("img_2.png", ssim=40),
    ]
    import dataclasses

    items[0].analysis = dataclasses.replace(
        items[0].analysis, axis_proposals=result.axis_proposals
    )
    items[1].analysis = dataclasses.replace(
        items[1].analysis,
        axis_proposals=tuple(
            type(p)(name=p.name, definition=p.definition, scale=p.scale, score=30)
            for p in result.axis_proposals
        ),
    )
    vector = build_measured_vector(items, mode="fidelity", domain="ai")
    proposed = {entry["name"]: entry for entry in vector.get("proposed_axes", ())}
    assert "halation" in proposed, (
        f"the proposal must reach the ranker by name; vector={vector}"
    )
    assert proposed["halation"]["scores"] == {"img_1": 72, "img_2": 30}
    assert proposed["halation"]["scale"] == "0-100"


def test_a_duplicate_of_a_pool_axis_is_refused_with_a_reason() -> None:
    raw = _chat(
        {
            "axes": {"sharpness": 70},
            "axis_proposals": [
                {
                    "name": "Sharpness",
                    "definition": "How crisp the edges are",
                    "scale": "0-100",
                    "score": 70,
                }
            ],
        }
    )
    result = ai_parse.parse_response(raw, model="m")
    assert result.axis_proposals == ()
    reason = dict(result.axis_proposal_refusals).get("sharpness")
    assert reason, "a duplicate of a pool axis must be refused with a reason"


# ---------------------------------------------------------------------------
# (d) sampling config + schema version inside the analyze cache identity
# ---------------------------------------------------------------------------


def _settings() -> AiSettings:
    return AiSettings(
        enabled=True,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-not-a-real-key",
        model="model/A",
        reasoning_effort="auto",
        sample_count=1,
    )


def test_the_identity_changes_with_the_sampling_config(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "ai_cache"
    cache.mkdir()
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: cache)
    path, mtime = Path("/gallery/a.png"), 7
    one = ai_cache.analysis_cache_identity(_settings(), mode="camera", k=1)
    three = ai_cache.analysis_cache_identity(_settings(), mode="camera", k=3)
    assert one != three, "a k=1 sample and a k=3 median must not share an entry"
    assert one["k"] == "1" and three["k"] == "3"
    assert "temperature" in one and "seed" in one

    ai_cache.save_analysis(path, mtime, _result(ssim=80), one)
    assert ai_cache.load_cached_analysis(path, mtime, one) is not None
    assert ai_cache.load_cached_analysis(path, mtime, three) is None, (
        "the sampling config must MISS the other config's scorecard"
    )


def test_the_declared_k_setting_is_the_default_one() -> None:
    """k defaults to 1 — the owner never set a cost ceiling (no silent k=3)."""
    assert _settings().sample_count == 1
    identity = ai_cache.analysis_cache_identity(_settings(), mode="camera")
    assert identity["k"] == "1"


def test_the_prompt_does_not_echo_the_numbers_the_model_must_judge() -> None:
    """P3-E: no local number for an axis the model is asked to score."""
    from tabs.image_gallery.services.ai_client.prompt import build_prompt

    text = build_prompt(
        "fidelity",
        profile=("ssim", "sharpness"),
        measured_block="- Source match: 0.91 (quality 91%)\n- Sharpness: 1.2 (quality 55%)",
    )
    assert "LOCAL MEASUREMENTS" not in text, (
        "the local numbers for the judged axes are an echo, not a judgement: " + text
    )
