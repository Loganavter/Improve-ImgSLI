"""INVARIANT: the three worker-thread pins refuse a generation a reset dropped.

The reset barrier bumps the owner's epoch tokens, and every LANDING path
compares them — but three writes never pass through a landing path: they go
straight from a worker thread into a store.

===============================  ===========================================
pin                                store
===============================  ===========================================
``jev_client._pin``                ``services.jev_cache`` (Jev rank pins)
the profile pin in ``profile_ai``   ``services.profile_cache`` (VLM answers)
``pairwise_rank``'s ``store.put``   the A/B verdict store (in-memory)
===============================  ===========================================

Measured on the A4 base (``2ceddfc8f``): a reset that lands while the request is
in flight clears the store, and the pin then writes the pre-reset result straight
back — the reset "did nothing" the next pass reads as a hit.

Every test below reproduces that exact window: the reset is triggered from INSIDE
the injected transport/judge, i.e. after the pass snapshotted its lease and before
its write. The AI adapter owns those three stores, so it owns the refusal: the
worker's stale lease raises ``NoProfileYet`` (with the dropped generation in the
message) and the pin is not written. Each test has a control that runs the same
pass WITHOUT the mid-flight reset and asserts the pin DOES land — otherwise a
guard that refuses everything would look green here.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.backends import NoProfileYet
from tabs.image_gallery.backends.ai import BACKEND as AI_BACKEND
from tabs.image_gallery.backends.generation import WorkGeneration
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import jev_cache, jev_client
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.use_cases import pairwise_rank
from tabs.image_gallery.use_cases.cache_reset import clear_metrics_caches
from tabs.image_gallery.use_cases.pairwise_rank import PairwiseVerdictCache, run_pairwise_pass
from tabs.image_gallery.use_cases.profile_ai import choose_profile_sync
from tabs.image_gallery.services.rank_fusion import rank_series


class _Owner:
    """The smallest owner a reset accepts: an empty pool + the optional hooks."""

    def __init__(self, items=()) -> None:
        self.state = SimpleNamespace(items=list(items))
        self._domain_epoch = 0
        self._analysis_epoch = 0

    def clear_metric_profile(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _stub_image_encoding(monkeypatch):
    """The profile probe's members are fakes: never read an image off disk."""
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


def _chat(answer) -> dict:
    content = answer if isinstance(answer, str) else json.dumps(answer)
    return {"choices": [{"message": {"content": content}}]}


def _stale_generation() -> WorkGeneration:
    """A lease that a reset has already dropped (the adapter moved on)."""
    lease = AI_BACKEND.lease()
    AI_BACKEND.reset()
    return lease


# ---------------------------------------------------------------------------
# 0. the refusal itself is the adapter's, and it is typed
# ---------------------------------------------------------------------------


def test_the_owning_adapter_refuses_a_stale_generation_by_type() -> None:
    lease = _stale_generation()
    with pytest.raises(NoProfileYet) as excinfo:
        AI_BACKEND.assert_generation(lease, operation="pin the Jev rank")
    assert "generation" in str(excinfo.value), (
        f"the refusal must name the dropped generation: {excinfo.value}"
    )
    # A live lease passes (non-vacuity: the guard is not refusing everything).
    AI_BACKEND.assert_generation(AI_BACKEND.lease(), operation="pin the Jev rank")


# ---------------------------------------------------------------------------
# 1. the Jev rank pin (``services.jev_client._pin``)
# ---------------------------------------------------------------------------


def _jev_item(name: str, *, ssim: float, noise: float) -> GalleryItem:
    """A member with two measured axes (Jev refuses a one-number vector)."""
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    item.metrics.update({"ssim": float(ssim), "noise": float(noise)})
    # ``sharpness`` mirrors ``ssim``: the same quality at the axis' own scale.
    item.metrics["sharpness"] = float(ssim) * 400.0
    return item


def _jev_pass(items, cache, *, client):
    return jev_client.rank_series_jev_detailed(
        items,
        mode="fidelity",
        client=client,
        cache=cache,
        domain="algorithms",
    )


def test_the_jev_pin_lands_when_no_reset_races_it(tmp_path, counters) -> None:
    """CONTROL: without the mid-flight reset the pin really is written."""
    items = [_jev_item("a.png", ssim=0.9, noise=0.1), _jev_item("b.png", ssim=0.5, noise=0.1)]
    cache = jev_cache.JevRankCache(tmp_path)
    client = lambda _payload: _chat({"ranking": ["img_1", "img_2"], "score": 0.8})

    outcome = _jev_pass(items, cache, client=client)

    assert outcome.decided, "fixture sanity: the scripted reply is a decisive rank"
    assert len(list(tmp_path.glob("rank_*.json"))) == 1, (
        "control failed: a decisive answer must be pinned"
    )
    assert counters["jev_put"] == 1


def test_the_jev_pin_refuses_a_generation_dropped_by_reset(tmp_path, counters) -> None:
    items = [_jev_item("a.png", ssim=0.9, noise=0.1), _jev_item("b.png", ssim=0.5, noise=0.1)]
    cache = jev_cache.JevRankCache(tmp_path)
    owner = _Owner(items)

    def client(_payload):
        # The reset lands while the request is in flight: exactly the window the
        # barrier's landing checks cannot see (this write has no landing path).
        clear_metrics_caches(owner)
        return _chat({"ranking": ["img_1", "img_2"], "score": 0.8})

    outcome = _jev_pass(items, cache, client=client)

    assert outcome.decided, "the answer is still an answer; only its PIN is stale"
    assert list(tmp_path.glob("rank_*.json")) == [], (
        "a rank measured before the reset was pinned after it — the next pass would "
        "read a pre-reset order out of the store the reset just emptied"
    )
    assert counters["jev_put"] == 0


# ---------------------------------------------------------------------------
# 2. the VLM metric-profile pin (``use_cases.profile_ai._pin``)
# ---------------------------------------------------------------------------


def _probe_item(name: str, mtime: int, **metrics):
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"), mtime_ns=int(mtime), metrics=dict(metrics)
    )


def _scattered():
    """A decisive spread, so the probe picks real members to ask about."""
    return [
        _probe_item("a.png", 1, sharpness=0.0, ssim=1.0, noise=1.0),
        _probe_item("b.png", 2, sharpness=400.0, ssim=0.0, noise=0.5),
        _probe_item("c.png", 3, sharpness=200.0, ssim=0.5, noise=0.0),
    ]


def _settings():
    return SimpleNamespace(
        enabled=True,
        api_key="k",
        base_url="http://x",
        model="m",
        reasoning_effort="auto",
    )


_AXES = {"axes": ["sharpness", "noise", "exposure", "clipping", "white_balance"]}


def test_the_profile_pin_lands_when_no_reset_races_it(tmp_path, counters) -> None:
    """CONTROL: the same pass with no mid-flight reset pins the answer."""
    cache = ProfileCache(tmp_path)
    transport = lambda _base_url, _api_key, _payload: _chat(_AXES)

    profile = choose_profile_sync(
        _scattered(), mode="camera", settings=_settings(), cache=cache, client_call=transport
    )

    assert profile is not None and profile.source == "vlm"
    assert counters["profile_put"] == 1
    assert list(tmp_path.glob("profile_*.json")), "control failed: nothing pinned"


def test_the_profile_pin_refuses_a_generation_dropped_by_reset(tmp_path, counters) -> None:
    cache = ProfileCache(tmp_path)
    owner = _Owner(_scattered())

    def transport(_base_url, _api_key, _payload):
        # A metrics reset while the paid call is in flight emptied the profile
        # store; the pin must not put the pre-reset axis set back into it.
        clear_metrics_caches(owner)
        return _chat(_AXES)

    profile = choose_profile_sync(
        _scattered(), mode="camera", settings=_settings(), cache=cache, client_call=transport
    )

    assert profile is not None, "the selector still returns its answer to the caller"
    assert counters["profile_put"] == 0, (
        "a profile resolved before the reset was pinned after it — the next pass "
        "would serve a pre-reset axis set out of the emptied store"
    )
    assert list(tmp_path.glob("profile_*.json")) == []


# ---------------------------------------------------------------------------
# 3. the A/B verdict pin (``use_cases.pairwise_rank``'s ``store.put``)
# ---------------------------------------------------------------------------


def _pair_item(name: str, quality: float):
    record = SimpleNamespace(axis="sharpness", status="ok", value=float(quality))
    return SimpleNamespace(
        path=Path("/gallery") / name,
        mtime_ns=1,
        analysis_records=(record,),
        metrics={},
    )


def _pair_row():
    return SimpleNamespace(
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


class _Judge:
    """Scripted judge: answers ``A``, and optionally fires a side effect first."""

    def __init__(self, *, during_first_call=None) -> None:
        self.during_first_call = during_first_call
        self.calls = 0

    def edge_of(self, _content, _path=None) -> int:
        return 1024

    def __call__(self, item_a, item_b):
        self.calls += 1
        if self.calls == 1 and self.during_first_call is not None:
            self.during_first_call()
        return "A"


def _pairwise_pass(judge, cache, *, owner=None):
    items = [_pair_item(f"{name}.png", 80) for name in "abc"]
    row = _pair_row()
    owner = owner or SimpleNamespace(_ai_settings_store=SimpleNamespace(load=lambda: row))
    return run_pairwise_pass(
        owner,
        items,
        pointwise_ranks=rank_series(items),
        settings=row,
        judge=judge,
        cache=cache,
    )


def test_the_ab_verdicts_are_pinned_when_no_reset_races_the_pass(counters) -> None:
    """CONTROL: six resolved verdicts (three pairs, both orders) are stored."""
    cache = PairwiseVerdictCache()

    result = _pairwise_pass(_Judge(), cache)

    assert result.applied is True, "fixture sanity: the scripted judge decides every pair"
    assert len(cache) == 3, "control failed: one entry per unordered pair"


def test_the_ab_verdicts_refuse_a_generation_dropped_by_reset(counters) -> None:
    cache = PairwiseVerdictCache()
    owner = SimpleNamespace(
        _ai_settings_store=SimpleNamespace(load=_pair_row),
        _folder_gen=0,
        _domain_epoch=0,
        _analysis_epoch=0,
        state=SimpleNamespace(items=[]),
    )
    judge = _Judge(during_first_call=lambda: clear_metrics_caches(owner))

    result = _pairwise_pass(judge, cache, owner=owner)

    assert judge.calls > 0, "fixture sanity: the pass really spent a call"
    assert result.order_paths, "the order is still derived; only its PIN is stale"
    assert len(cache) == 0, (
        "an A/B verdict measured before the reset was pinned after it — the store "
        "the reset emptied now serves a pre-reset comparison"
    )


def test_the_pin_guard_reads_the_owning_adapters_generation(counters) -> None:
    """The three pins share ONE check: the AI adapter's, not a local counter."""
    lease = AI_BACKEND.lease()
    AI_BACKEND.reset()
    from tabs.image_gallery.backends.generation import generation_is_current

    assert generation_is_current(lease, operation="pin the A/B verdict") is False
    assert generation_is_current(AI_BACKEND.lease(), operation="pin the A/B verdict") is True
