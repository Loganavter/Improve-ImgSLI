"""R3 — AI-domain ranker: Jev (``typesafe/jev-router``) over the measured vector.

Falsification story (what each test would catch):

- a request that leaks a file path, image bytes or a prose instruction — the
  payload test asserts the serialized body is measured numbers + opaque aliases
  only, sent as ONE user message over the shared ``ai_client.call_sync`` seam;
- a decisive Choice that does not move the rank, or that moves it without
  stamping ``rank_source="jev"``;
- an abstain/low-confidence/errored answer that silently clears the Algorithms
  rank instead of keeping it (and setting no reason);
- a transport that is hit twice for an unchanged series (the pin must serve the
  second pass);
- an exception escaping the client into the UI thread.

Network-free: the transport is injected (and one test monkeypatches the real
``ai_client.call_sync`` seam). No Qt event loop — a lightweight fake controller
calls the real (unbound) controller rank primitives over plain ``GalleryItem``
objects.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, GalleryState, Mode, Series
from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.jev_client import (
    JEV_MIN_CONFIDENCE,
    JEV_MODEL,
    JEV_REASON_LOW_CONFIDENCE,
    JEV_REASON_NOUL,
    JEV_TIMEOUT_S,
    build_rank_request,
    make_client,
    rank_series_jev,
    rank_series_jev_detailed,
)
from tabs.image_gallery.services.rank_fusion import measured_axes_for


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    return it


def _series(*items) -> list[Series]:
    return [Series(id="series_1", members=list(items))]


def _chat(decision: dict) -> dict:
    """A chat/completions envelope whose assistant message is *decision* JSON."""
    return {"choices": [{"message": {"content": json.dumps(decision)}}]}


def _message_text(payload: dict) -> str:
    return payload["messages"][-1]["content"][0]["text"]


class _FakeController:
    """Minimal controller surface for the Jev apply/degrade hook (no Qt)."""

    def __init__(self, items, series=None, mode=Mode.FIDELITY) -> None:
        self.state = GalleryState(
            items=list(items), series=list(series if series is not None else []), mode=mode
        )
        self.refreshed: list = []
        self.ai_ran = False
        self.jev_ran = False
        self.priority_ran = False
        self.priority_cleared = False
        self.widget = SimpleNamespace(
            refresh_card=lambda it: self.refreshed.append(it),
            visible_paths=lambda: [it.path for it in self.state.items],
        )
        self._ai_settings_store = None

    def _find_item(self, path):
        return GalleryController._find_item(self, path)

    def _apply_fusion_ranks(self, series, *, mode=None):
        return GalleryController._apply_fusion_ranks(self, series, mode=mode)

    def _apply_jev_outcome(self, members, outcome):
        return GalleryController._apply_jev_outcome(self, members, outcome)

    def _degrade_jev(self, members, reason):
        return GalleryController._degrade_jev(self, members, reason)

    def activate_judgment_domain(self, domain):
        return GalleryController.activate_judgment_domain(self, domain)

    def _run_ai_for_visible(self):
        self.ai_ran = True

    def _run_jev_ranks(self):
        self.jev_ran = True

    def _run_series_priority(self):
        self.priority_ran = True

    def _clear_series_priority(self):
        self.priority_cleared = True


def _ranks_by_name(items) -> dict:
    return {it.path.name: it.rank for it in items}


# --------------------------------------------------------------------------
# request: chat/completions body, measured vector only, no paths/bytes/prose
# --------------------------------------------------------------------------


def test_rank_request_is_a_single_user_message_chat_body() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    payload = build_rank_request([a, b], mode="fidelity")

    assert payload["model"] == JEV_MODEL
    assert [m["role"] for m in payload["messages"]] == ["user"]  # no system prompt


def test_rank_request_asks_for_a_json_object() -> None:
    """The live reply is unstable in shape without structured output (prose vs
    fenced JSON vs bare object — probe 2026-10-15), so the request pins it."""
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    payload = build_rank_request([a, b], mode="fidelity")
    assert payload["response_format"] == {"type": "json_object"}


def test_payload_is_measured_vector_only_no_paths_no_bytes_no_prose() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    payload = build_rank_request([a, b], mode="fidelity")
    vector = json.loads(_message_text(payload))

    assert set(vector) == {"mode", "items"}
    assert vector["mode"] == "fidelity"

    blob = json.dumps(payload)
    # No file identity of any kind.
    assert "/gallery/" not in blob and "a.png" not in blob and "b.png" not in blob
    # No image bytes / vision envelope.
    assert "image_url" not in blob and "base64" not in blob and "data:image" not in blob
    # No prose instruction.
    low = blob.lower()
    for bad in ("you are", "please", "respond", "compare", "instruction", "choose"):
        assert bad not in low

    axes = set(measured_axes_for("fidelity"))
    for entry in vector["items"]:
        assert set(entry) == {"alias", "scores"}
        assert entry["alias"].startswith("img_")
        assert entry["scores"], "measured items must carry their measured axes"
        for axis_id, score in entry["scores"].items():
            assert axis_id in axes
            assert isinstance(score, int) and 0 <= score <= 100


def test_payload_omits_an_axis_the_item_did_not_measure() -> None:
    a = _item("a.png", ssim=0.90)
    vector = json.loads(_message_text(build_rank_request([a], mode="fidelity")))
    assert "ssim" in vector["items"][0]["scores"]
    assert "noise" not in vector["items"][0]["scores"]  # never fabricated as 0/100


def test_payload_alias_order_is_deterministic_by_path() -> None:
    x = _item("x.png", ssim=0.5)
    a = _item("a.png", ssim=0.5)
    first = build_rank_request([x, a], mode="fidelity")
    second = build_rank_request([a, x], mode="fidelity")
    assert first == second
    assert [e["alias"] for e in json.loads(_message_text(first))["items"]] == [
        "img_1",
        "img_2",
    ]


# --------------------------------------------------------------------------
# decisive answer → ranks + rank_source="jev"
# --------------------------------------------------------------------------


def _decisive_client(choice: str, score: float = 0.9):
    def _client(payload):
        return _chat({"choice": choice, "score": score, "noul": False})

    return _client


def test_decisive_choice_sets_jev_ranks_on_every_item(tmp_path) -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    c = _item("c.png", ssim=0.70, noise=0.10)
    ctrl = _FakeController([a, b, c], _series(a, b, c))
    # Baseline Algorithms (fusion) rank first.
    GalleryController._apply_fusion_ranks(ctrl, ctrl.state.series)
    assert all(it.rank_source == "fusion" for it in (a, b, c))

    cache = jev_cache.JevRankCache(tmp_path)
    # img_1=a.png, img_2=b.png, img_3=c.png (path-sorted aliases).
    outcome = rank_series_jev_detailed(
        [a, b, c], mode="fidelity", client=_decisive_client("img_2"), cache=cache
    )
    assert outcome.decided
    ctrl._apply_jev_outcome([a, b, c], outcome)

    assert b.rank == 1
    assert sorted((a.rank, b.rank, c.rank)) == [1, 2, 3]  # complete 1..N
    assert all(it.rank_source == "jev" for it in (a, b, c))
    assert ctrl.state.rank_domain == "ai"


def test_rank_series_jev_matches_explicit_full_ranking(tmp_path) -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    c = _item("c.png", ssim=0.70, noise=0.10)

    def _client(payload):
        return _chat({"ranking": ["img_3", "img_1", "img_2"], "score": 0.8})

    ranks = rank_series_jev(
        [a, b, c], mode="fidelity", client=_client, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert ranks == {
        str(c.path): 1,
        str(a.path): 2,
        str(b.path): 3,
    }


def test_real_jev_reply_without_a_score_is_still_decisive(tmp_path) -> None:
    """Falsification: the live ``typesafe/jev-router`` reply carries prose + a
    fenced JSON block with ``best``/``ranking`` and **no** ``score`` (probe
    2026-10-15). Reading a missing confidence number as a malformed answer made
    every real AI-domain call silently degrade to the Algorithms rank."""
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    c = _item("c.png", ssim=0.70, noise=0.10)

    content = (
        'Best overall: **img_1**\n\nRanking for `mode: "fidelity"`:\n\n'
        "1. **img_1** ...\n2. **img_3** ...\n3. **img_2** ...\n\n"
        "```json\n"
        '{"mode": "fidelity", "best": "img_1", '
        '"ranking": ["img_1", "img_3", "img_2"], '
        '"composite_scores": {"img_1": 78.2, "img_3": 71.4, "img_2": 49.0}}\n'
        "```"
    )

    def _client(payload):
        return {"choices": [{"message": {"content": content}}]}

    outcome = rank_series_jev_detailed(
        [a, b, c], mode="fidelity", client=_client, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert outcome.decided, outcome.reason
    assert outcome.ranks == {str(a.path): 1, str(c.path): 2, str(b.path): 3}


def test_decision_keyed_recommended_is_decisive(tmp_path) -> None:
    """Observed "Jev Router" JSON shape A (probe 2026-10-15): a bare
    ``recommended`` with no ``ranking``/``best``/``choice`` key still names a
    winner — the tail keeps the deterministic fusion order."""
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    c = _item("c.png", ssim=0.70, noise=0.10)

    def _client(payload):
        return _chat({"recommended": "img_1", "mode": "fidelity", "reason": "best balance"})

    outcome = rank_series_jev_detailed(
        [a, b, c], mode="fidelity", client=_client, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert outcome.decided, outcome.reason
    assert outcome.ranks[str(a.path)] == 1
    assert sorted(outcome.ranks.values()) == [1, 2, 3]  # complete 1..N


def test_ranking_of_alias_objects_is_decisive(tmp_path) -> None:
    """Observed "Jev Router" JSON shape B (probe 2026-10-15): ``ranking`` is a
    list of ``{"alias": ...}`` objects, not bare alias strings."""
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    c = _item("c.png", ssim=0.70, noise=0.10)

    def _client(payload):
        return _chat({
            "mode": "fidelity",
            "best": "img_1",
            "ranking": [
                {"alias": "img_1", "overall": 78.2},
                {"alias": "img_3", "overall": 71.4},
                {"alias": "img_2", "overall": 49.0},
            ],
        })

    ranks = rank_series_jev(
        [a, b, c], mode="fidelity", client=_client, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert ranks == {str(a.path): 1, str(c.path): 2, str(b.path): 3}


def test_present_low_score_still_degrades_even_with_a_ranking(tmp_path) -> None:
    """The confidence gate is not weakened: a *present* sub-threshold score
    degrades even when the reply also carries an explicit ranking."""
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)

    def _client(payload):
        return _chat({"ranking": ["img_1", "img_2"], "score": 0.1})

    outcome = rank_series_jev_detailed(
        [a, b], mode="fidelity", client=_client, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert outcome.ranks is None
    assert outcome.reason == JEV_REASON_LOW_CONFIDENCE


def test_decision_with_neither_ranking_nor_choice_degrades(tmp_path) -> None:
    """A score-free body that names no winner/ordering is still unusable."""
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)

    outcome = rank_series_jev_detailed(
        [a, b],
        mode="fidelity",
        client=lambda p: _chat({"mode": "fidelity", "note": "no decision here"}),
        cache=jev_cache.JevRankCache(tmp_path),
    )
    assert outcome.ranks is None


# --------------------------------------------------------------------------
# indecisive / low confidence → Algorithms rank survives + reason set
# --------------------------------------------------------------------------


def test_noul_keeps_the_fusion_rank_and_sets_a_reason(tmp_path) -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    GalleryController._apply_fusion_ranks(ctrl, ctrl.state.series)
    before = _ranks_by_name((a, b))

    outcome = rank_series_jev_detailed(
        [a, b],
        mode="fidelity",
        client=lambda p: _chat({"noul": True}),
        cache=jev_cache.JevRankCache(tmp_path),
    )
    assert outcome.ranks is None
    assert outcome.reason == JEV_REASON_NOUL
    ctrl._apply_jev_outcome([a, b], outcome)

    assert _ranks_by_name((a, b)) == before  # fusion rank unchanged
    assert all(it.rank_source == "fusion" for it in (a, b))


def test_low_confidence_keeps_the_fusion_rank_and_sets_a_reason(tmp_path) -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    GalleryController._apply_fusion_ranks(ctrl, ctrl.state.series)
    before = _ranks_by_name((a, b))

    score = max(0.0, JEV_MIN_CONFIDENCE - 0.1)
    outcome = rank_series_jev_detailed(
        [a, b],
        mode="fidelity",
        client=lambda p: _chat({"choice": "img_1", "score": score}),
        cache=jev_cache.JevRankCache(tmp_path),
    )
    assert outcome.ranks is None
    assert outcome.reason == JEV_REASON_LOW_CONFIDENCE
    ctrl._apply_jev_outcome([a, b], outcome)

    assert _ranks_by_name((a, b)) == before
    assert all(it.rank_source == "fusion" for it in (a, b))


# --------------------------------------------------------------------------
# transport error → degrade, no exception escapes
# --------------------------------------------------------------------------


def test_transport_exception_degrades_without_raising(tmp_path) -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    GalleryController._apply_fusion_ranks(ctrl, ctrl.state.series)
    before = _ranks_by_name((a, b))

    def _boom(payload):
        raise RuntimeError("network exploded")

    outcome = rank_series_jev_detailed(
        [a, b], mode="fidelity", client=_boom, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert outcome.ranks is None
    assert outcome.reason and "exploded" in outcome.reason
    # The public seam returns None and never re-raises.
    assert rank_series_jev(
        [a, b], mode="fidelity", client=_boom, cache=jev_cache.JevRankCache(tmp_path / "x")
    ) is None

    ctrl._apply_jev_outcome([a, b], outcome)
    assert _ranks_by_name((a, b)) == before
    assert all(it.rank_source == "fusion" for it in (a, b))


# --------------------------------------------------------------------------
# cache/pin: the same series must not hit the transport twice
# --------------------------------------------------------------------------


def test_second_run_of_same_series_hits_the_transport_once(tmp_path) -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    cache = jev_cache.JevRankCache(tmp_path)
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _chat({"choice": "img_2", "score": 0.9})

    first = rank_series_jev([a, b], mode="fidelity", client=_client, cache=cache)
    second = rank_series_jev([a, b], mode="fidelity", client=_client, cache=cache)

    assert len(calls) == 1  # the pin served the second run
    assert first == second
    assert first is not None


def test_abstain_is_pinned_so_a_rerun_is_stable(tmp_path) -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    cache = jev_cache.JevRankCache(tmp_path)
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _chat({"noul": True})

    first = rank_series_jev_detailed([a, b], mode="fidelity", client=_client, cache=cache)
    second = rank_series_jev_detailed([a, b], mode="fidelity", client=_client, cache=cache)
    assert first.ranks is None and second.ranks is None
    assert second.cached is True
    assert len(calls) == 1


def test_cache_key_changes_with_paths_and_mtimes(tmp_path) -> None:
    import copy

    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    payload = build_rank_request([a, b], mode="fidelity")
    key = jev_cache.rank_cache_key([a, b], payload)
    assert key == jev_cache.rank_cache_key([b, a], payload)  # order-independent

    moved = copy.deepcopy([a, b])
    moved[0].mtime_ns = 123456
    assert jev_cache.rank_cache_key(moved, payload) != key

    other = copy.deepcopy([a, b])
    other[0].metrics["ssim"] = 0.10  # payload changes
    assert jev_cache.rank_cache_key(other, build_rank_request(other, mode="fidelity")) != key


# --------------------------------------------------------------------------
# transport seam: reuse ai_client.call_sync (no second client)
# --------------------------------------------------------------------------


def test_make_client_routes_through_ai_client_call_sync(monkeypatch, tmp_path) -> None:
    from tabs.image_gallery.services import ai_client

    captured: dict = {}

    def _fake_call_sync(base_url, api_key, payload, **kwargs):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["payload"] = payload
        return _chat({"choice": "img_2", "score": 0.9})

    monkeypatch.setattr(ai_client, "call_sync", _fake_call_sync)

    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    client = make_client("https://openrouter.ai/api/v1", "sk-test")
    ranks = rank_series_jev(
        [a, b], mode="fidelity", client=client, cache=jev_cache.JevRankCache(tmp_path)
    )

    assert ranks == {str(b.path): 1, str(a.path): 2}
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["payload"]["model"] == JEV_MODEL
    blob = json.dumps(captured["payload"])
    assert "image_url" not in blob and "/gallery/" not in blob


def test_make_client_uses_the_longer_jev_timeout(monkeypatch, tmp_path) -> None:
    """The router's latency is opaque and observed over 30 s (probe 2026-10-15),
    so the Jev transport must not use the 30 s ``call_sync`` default."""
    from tabs.image_gallery.services import ai_client

    captured: dict = {}

    def _fake_call_sync(base_url, api_key, payload, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return _chat({"choice": "img_1", "score": 0.9})

    monkeypatch.setattr(ai_client, "call_sync", _fake_call_sync)
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    rank_series_jev(
        [a, b],
        mode="fidelity",
        client=make_client("https://openrouter.ai/api/v1", "sk-test"),
        cache=jev_cache.JevRankCache(tmp_path),
    )
    assert captured["timeout"] == JEV_TIMEOUT_S
    assert JEV_TIMEOUT_S > 30.0


# --------------------------------------------------------------------------
# controller domain hook
# --------------------------------------------------------------------------


def test_switch_to_ai_sets_rank_domain_and_schedules_jev() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    ctrl.activate_judgment_domain("ai")
    assert ctrl.state.judgment_domain == "ai"
    assert ctrl.state.rank_domain == "ai"
    assert ctrl.ai_ran is True
    assert ctrl.jev_ran is True
    assert ctrl.priority_ran is True


def test_switch_back_to_algorithms_re_derives_the_fusion_rank() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    # Simulate a Jev rank currently displayed on the AI domain.
    b.rank, b.rank_source = 1, "jev"
    a.rank, a.rank_source = 2, "jev"
    ctrl.state.rank_domain = "ai"

    ctrl.activate_judgment_domain("algorithms")
    assert ctrl.state.rank_domain == "algorithms"
    assert ctrl.priority_cleared is True
    # Fusion re-derives: a (better ssim) is #1 again, provenance back to fusion.
    assert a.rank == 1 and a.rank_source == "fusion"
    assert b.rank == 2 and b.rank_source == "fusion"


def test_jev_rank_survives_a_regroup_while_on_the_ai_domain() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    b.rank, b.rank_source = 1, "jev"
    a.rank, a.rank_source = 2, "jev"
    ctrl.state.rank_domain = "ai"

    GalleryController._apply_fusion_ranks(ctrl, ctrl.state.series)
    assert b.rank == 1 and b.rank_source == "jev"
    assert a.rank == 2 and a.rank_source == "jev"


def test_jev_model_is_the_frozen_seam() -> None:
    assert JEV_MODEL == "typesafe/jev-router"
