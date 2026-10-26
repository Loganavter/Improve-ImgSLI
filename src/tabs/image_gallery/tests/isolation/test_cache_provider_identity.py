"""INVARIANT I1/I2: a cache identity names the ENDPOINT that produced the entry.

Falsification story (red on the int tip): four gallery caches identified the
configuration by paths+mtimes (+model, where they had one) and were blind to the
endpoint, while the model id stays constant across providers:

* ``services/vlm_cache`` — tie-break / compare-brief keys: paths+mtimes only;
* ``controller._ask_cache_key`` — backend token + model, no ``base_url`` (and no
  effort / profile, both of which change the answer);
* ``use_cases/pairwise_rank.pair_key`` — model + prompt version, no ``base_url``;
* ``services/jev_cache`` / ``services/series_priority`` — the payload carries the
  CONSTANT ``JEV_MODEL``, so only paths+payload; no endpoint.

So pointing the same model id at provider B served provider A's verdict/brief/
answer/order/priority as if B had produced it. Each test below seeds through the
REAL producer (the public save/load API, the real pass, the real key builder),
switches the endpoint with the SAME model id, and asserts a MISS. The last test
holds the other half of the identity: two spellings of one endpoint
(``https://h/v1`` vs ``https://h/v1/``) are the SAME cache identity.

Cache roots are redirected to ``tmp_path`` through the ONE resolver every store
uses (``services.io.project_package.cache_kind_dir``), so a test never reads,
writes or deletes the developer's real cache.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import services.io.project_package as project_package
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import CompareBrief, TieBreakResult
from tabs.image_gallery.services import ai_cache, jev_cache, series_priority, vlm_cache
from tabs.image_gallery.services.ai_cache import analysis_cache_identity
from tabs.image_gallery.services.ai_client.parse import parse_response
from tabs.image_gallery.services.jev_client import rank_series_jev_detailed
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.rank_fusion import rank_series
from tabs.image_gallery.use_cases import pairwise_rank
from tabs.image_gallery.use_cases.pairwise_rank import (
    PairwiseVerdictCache,
    pair_key,
    run_pairwise_pass,
)

#: The SAME model id on two endpoints — the provider switch the keys missed.
MODEL = "vendor/same-model"
ENDPOINT_A = "https://provider-a.example/v1"
ENDPOINT_B = "https://provider-b.example/v1"


@pytest.fixture(autouse=True)
def _isolated_cache_root(tmp_path, monkeypatch):
    """Every gallery store resolves its directory through ``cache_kind_dir``."""

    def _kind(kind: str) -> Path:
        root = tmp_path / "cache" / str(kind)
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr(project_package, "cache_kind_dir", _kind)
    pairwise_rank.DEFAULT_CACHE.clear()
    try:
        yield
    finally:
        pairwise_rank.DEFAULT_CACHE.clear()


# -- doubles ------------------------------------------------------------------


def _tie(a: Path, b: Path) -> TieBreakResult:
    return TieBreakResult(
        winner_path=str(a),
        loser_path=str(b),
        reason="sharper edges",
        confidence=0.9,
        model=MODEL,
        decided_at_iso="2026-01-01T00:00:00+00:00",
    )


def _brief(a: Path, b: Path) -> CompareBrief:
    return CompareBrief(
        pair=(str(a), str(b)),
        summary="same scene, B is cleaner",
        differences=("noise",),
        tags=("noise",),
        model=MODEL,
        created_at_iso="2026-01-01T00:00:00+00:00",
    )


class _AskOwner:
    """The controller's in-memory ask store; the key method reads no other state."""

    def __init__(self) -> None:
        self._ask_cache: dict = {}


def _ask_key(*, base_url: str, effort: str = "auto", profile=None) -> str:
    """The REAL ``GalleryController._ask_cache_key`` for one configuration."""
    scope = SimpleNamespace(kind="series", series_id="series_1", label="Series 1")
    context = {
        "items": [{"path": "/gallery/a.png"}, {"path": "/gallery/b.png"}],
        "mode": "fidelity",
    }
    return GalleryController._ask_cache_key(
        _AskOwner(),
        scope,
        context,
        "Which is sharper?",
        "text",
        MODEL,
        base_url=base_url,
        effort=effort,
        profile=profile,
    )


def _pair_item(name: str, quality: float):
    record = SimpleNamespace(axis="sharpness", status="ok", value=float(quality))
    return SimpleNamespace(
        path=Path("/gallery") / name,
        mtime_ns=1,
        analysis_records=(record,),
        metrics={},
    )


def _pair_settings(base_url: str):
    return SimpleNamespace(
        enabled=True,
        api_key="k",
        model=MODEL,
        base_url=base_url,
        sample_count=1,
        judge_run_call_ceiling=0,
        vlm_max_edge_px=1024,
        pairwise_enabled=True,
        pairwise_top_n=5,
        pairwise_near_tie_threshold=10.0,
    )


class _CountingJudge:
    """Scripted pairwise judge: every call is a spend, ``edge_of`` fixes the key."""

    def __init__(self, answer: str = "A", edge: int = 1024) -> None:
        self.answer = answer
        self.edge = edge
        self.calls = 0

    def edge_of(self, _content: str, _path=None) -> int:
        return self.edge

    def __call__(self, _item_a, _item_b):
        self.calls += 1
        return self.answer


def _run_pairwise(settings, judge, cache):
    owner = SimpleNamespace(
        _ai_settings_store=SimpleNamespace(load=lambda: settings), _folder_gen=0
    )
    items = [_pair_item(f"{name}.png", 80) for name in "abc"]
    return run_pairwise_pass(
        owner,
        items,
        pointwise_ranks=rank_series(items),
        settings=settings,
        judge=judge,
        cache=cache,
    )


def _jev_item(name: str, ssim: float, noise: float = 0.10):
    item = SimpleNamespace(path=Path(f"/gallery/{name}"), mtime_ns=1, metrics={})
    item.metrics.update({"ssim": ssim, "noise": noise, "sharpness": ssim * 400.0})
    return item


def _jev_chat(decision: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(decision)}}]}


def _priority_profile():
    """The AI backend's axis set the priority payload aggregates over (A3).

    ``services.series_priority`` takes the profile as an argument and refuses
    without one (no local aggregate may enter the AI payload), so the pin test
    states the axis set it routes. The items carry no scorecard, so the payload
    has no aggregates — the pin identity is about the endpoint + the series ids,
    which is exactly what this test asserts.
    """
    return MetricProfile(
        mode="camera",
        source="vlm",
        axis_entries=(
            SimpleNamespace(
                name="halation",
                definition="glow at bright edges",
                scale="0-100",
                direction="lower-is-better",
            ),
        ),
    )


def _priority_series():
    def _camera(name: str, sharp: float, noise: float):
        return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics={
            "sharpness": sharp, "noise": noise,
        })

    return [
        SimpleNamespace(id="a", members=[_camera("a1.png", 300, 0.10), _camera("a2.png", 150, 0.50)]),
        SimpleNamespace(id="b", members=[_camera("b1.png", 200, 0.20), _camera("b2.png", 260, 0.15)]),
    ]


# -- 1. VLM tie-break ---------------------------------------------------------


def test_vlm_tie_break_is_a_miss_on_another_endpoint(tmp_path) -> None:
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    vlm_cache.save_tie_break(a, 1, b, 2, _tie(a, b), model=MODEL, base_url=ENDPOINT_A)

    hit = vlm_cache.load_cached_tie_break(
        a, 1, b, 2, model=MODEL, base_url=ENDPOINT_A
    )
    assert hit is not None and hit.reason == "sharper edges"
    assert vlm_cache.load_cached_tie_break(
        a, 1, b, 2, model=MODEL, base_url=ENDPOINT_B
    ) is None, "provider B was served provider A's tie-break"
    assert vlm_cache.load_cached_tie_break(
        a, 1, b, 2, model="vendor/other-model", base_url=ENDPOINT_A
    ) is None, "another model was served this model's tie-break"


# -- 2. VLM compare brief -----------------------------------------------------


def test_vlm_compare_brief_is_a_miss_on_another_endpoint(tmp_path) -> None:
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    vlm_cache.save_brief(a, 1, b, 2, _brief(a, b), model=MODEL, base_url=ENDPOINT_A)

    hit = vlm_cache.load_cached_brief(a, 1, b, 2, model=MODEL, base_url=ENDPOINT_A)
    assert hit is not None and hit.summary == "same scene, B is cleaner"
    assert vlm_cache.load_cached_brief(
        a, 1, b, 2, model=MODEL, base_url=ENDPOINT_B
    ) is None, "provider B was served provider A's compare brief"


# -- 3. Ask AI in-memory answers ---------------------------------------------


def test_ask_answer_is_a_miss_on_another_endpoint() -> None:
    owner = _AskOwner()
    key_a = _ask_key(base_url=ENDPOINT_A)
    owner._ask_cache[key_a] = "answer from A"

    assert owner._ask_cache.get(_ask_key(base_url=ENDPOINT_A)) == "answer from A"
    assert _ask_key(base_url=ENDPOINT_B) not in owner._ask_cache, (
        "provider B was served provider A's ask answer"
    )


def test_ask_identity_also_names_the_effort_and_the_profile() -> None:
    profile = SimpleNamespace(
        axis_ids=("sharpness", "noise"), source="vlm", mode="fidelity"
    )
    base = _ask_key(base_url=ENDPOINT_A, effort="auto", profile=profile)
    assert _ask_key(base_url=ENDPOINT_A, effort="high", profile=profile) != base
    other = SimpleNamespace(
        axis_ids=("sharpness", "noise", "composition"), source="vlm", mode="fidelity"
    )
    assert _ask_key(base_url=ENDPOINT_A, effort="auto", profile=other) != base


# -- 4. Pairwise verdicts -----------------------------------------------------


def test_pairwise_verdict_is_a_miss_on_another_endpoint() -> None:
    cache = PairwiseVerdictCache()
    judge = _CountingJudge("A")

    first = _run_pairwise(_pair_settings(ENDPOINT_A), judge, cache)
    assert first.applied is True and judge.calls == 6

    again = _run_pairwise(_pair_settings(ENDPOINT_A), judge, cache)
    assert again.applied is True and judge.calls == 6, "the same provider must HIT"
    assert again.cached == 3

    switched = _run_pairwise(_pair_settings(ENDPOINT_B), judge, cache)
    assert switched.applied is True
    assert judge.calls == 12, "provider B reused provider A's pairwise verdicts"
    assert switched.cached == 0


def test_pairwise_default_cache_can_be_dropped() -> None:
    """The reset seam W4's ``cache_reset`` must call (it owns that file)."""
    key = pair_key(
        "A:1", 1024, "B:2", 1024, model=MODEL, base_url=ENDPOINT_A
    )
    pairwise_rank.DEFAULT_CACHE.put(
        key, pairwise_rank.PairVerdict("A:1", "B:2", "first", "second")
    )
    assert len(pairwise_rank.DEFAULT_CACHE) == 1

    assert pairwise_rank.clear_default_cache() == 1
    assert len(pairwise_rank.DEFAULT_CACHE) == 0


# -- 5. Jev rank + series priority -------------------------------------------


def test_jev_rank_pin_is_a_miss_on_another_endpoint(tmp_path) -> None:
    items = [_jev_item("a.png", 0.90), _jev_item("b.png", 0.50), _jev_item("c.png", 0.70)]
    cache_dir = tmp_path / "jev"
    cache_dir.mkdir()
    cache = jev_cache.JevRankCache(cache_dir)
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _jev_chat({"choice": "img_2", "score": 0.9})

    first = rank_series_jev_detailed(
        items, mode="fidelity", client=_client, cache=cache, base_url=ENDPOINT_A
    )
    assert first.decided and len(calls) == 1

    again = rank_series_jev_detailed(
        items, mode="fidelity", client=_client, cache=cache, base_url=ENDPOINT_A
    )
    assert again.decided and again.cached is True and len(calls) == 1

    switched = rank_series_jev_detailed(
        items, mode="fidelity", client=_client, cache=cache, base_url=ENDPOINT_B
    )
    assert switched.decided and switched.cached is False
    assert len(calls) == 2, "provider B was served provider A's pinned Jev rank"


def test_series_priority_pin_is_a_miss_on_another_endpoint(tmp_path) -> None:
    series = _priority_series()
    cache_dir = tmp_path / "priority"
    cache_dir.mkdir()
    cache = jev_cache.JevRankCache(cache_dir)
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _jev_chat({"ranking": ["series_2", "series_1"]})

    profile = _priority_profile()
    first = series_priority.route_series_priority_detailed(
        series,
        mode="camera",
        client=_client,
        cache=cache,
        base_url=ENDPOINT_A,
        profile=profile,
    )
    assert first.decided and len(calls) == 1

    again = series_priority.route_series_priority_detailed(
        series,
        mode="camera",
        client=_client,
        cache=cache,
        base_url=ENDPOINT_A,
        profile=profile,
    )
    assert again.cached is True and len(calls) == 1

    switched = series_priority.route_series_priority_detailed(
        series,
        mode="camera",
        client=_client,
        cache=cache,
        base_url=ENDPOINT_B,
        profile=profile,
    )
    assert switched.decided and switched.cached is False
    assert len(calls) == 2, "provider B was served provider A's priority pin"


# -- 6. One endpoint, two spellings = ONE identity ---------------------------

def test_one_endpoint_with_two_spellings_is_one_identity(tmp_path) -> None:
    """The inverse of the tests above: normalization must not SPLIT one backend."""
    a, b = tmp_path / "a.png", tmp_path / "b.png"

    # Stage-3 VLM tie-break + brief: seeded under the plain spelling.
    vlm_cache.save_tie_break(a, 1, b, 2, _tie(a, b), model=MODEL, base_url=ENDPOINT_A)
    vlm_cache.save_brief(a, 1, b, 2, _brief(a, b), model=MODEL, base_url=ENDPOINT_A)
    assert vlm_cache.load_cached_tie_break(
        a, 1, b, 2, model=MODEL, base_url=f"{ENDPOINT_A}/"
    ) is not None
    assert vlm_cache.load_cached_brief(
        a, 1, b, 2, model=MODEL, base_url=f"{ENDPOINT_A}/"
    ) is not None

    # Ask AI key.
    assert _ask_key(base_url=ENDPOINT_A) == _ask_key(base_url=f"{ENDPOINT_A}/")

    # Pairwise key.
    assert pair_key(
        "A:1", 1024, "B:2", 2048, model=MODEL, base_url=ENDPOINT_A
    ) == pair_key(
        "A:1", 1024, "B:2", 2048, model=MODEL, base_url=f"{ENDPOINT_A}/"
    )

    # Jev rank pin.
    items = [_jev_item("a.png", 0.90), _jev_item("b.png", 0.50)]
    payload = {"model": "typesafe/jev-router", "messages": []}
    assert jev_cache.rank_cache_key(
        items, payload, base_url=ENDPOINT_A
    ) == jev_cache.rank_cache_key(items, payload, base_url=f"{ENDPOINT_A}/")

    # Cross-series priority pin.
    series = _priority_series()
    priority_payload = {"model": "typesafe/jev-router", "messages": []}
    assert series_priority.priority_cache_key(
        series, priority_payload, base_url=ENDPOINT_A
    ) == series_priority.priority_cache_key(
        series, priority_payload, base_url=f"{ENDPOINT_A}/"
    )

    # The analyze-scorecard identity uses the SAME normalizer.
    settings = SimpleNamespace(
        model=MODEL, base_url=ENDPOINT_A, reasoning_effort="auto", sample_count=1
    )
    slashed = SimpleNamespace(
        model=MODEL, base_url=f"{ENDPOINT_A}/", reasoning_effort="auto", sample_count=1
    )
    assert analysis_cache_identity(settings) == analysis_cache_identity(slashed)


# -- 7. The fallback model is RECORDED, never keyed --------------------------


def test_the_answer_model_that_actually_served_is_recorded_not_keyed(tmp_path) -> None:
    """OpenRouter's fallback chain may answer with another id (requirement 6).

    The identity must stay on the REQUESTED model (keying the routed id would
    split one configured backend into one entry per route and a re-run could
    never hit), while the entry must say which model really answered.
    """
    raw = {
        "model": "openai/gpt-6-luna",  # the fallback, NOT the requested id
        "choices": [
            {"message": {"content": json.dumps({"axes": {"sharpness": 80}, "reason": "clean"})}}
        ],
    }
    result = parse_response(raw, model=MODEL)
    assert result.model == MODEL, "the requested model must stay the identity model"
    assert result.answered_model == "openai/gpt-6-luna"

    settings = SimpleNamespace(
        model=MODEL, base_url=ENDPOINT_A, reasoning_effort="auto", sample_count=1
    )
    identity = analysis_cache_identity(settings)
    path, mtime = tmp_path / "a.png", 7
    ai_cache.save_analysis(path, mtime, result, identity)

    loaded = ai_cache.load_cached_analysis(path, mtime, identity)
    assert loaded is not None
    assert loaded.model == MODEL
    assert loaded.answered_model == "openai/gpt-6-luna", (
        "a HIT lost the model that actually produced the scorecard"
    )
