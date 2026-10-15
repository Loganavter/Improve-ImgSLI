"""Cross-series priority (Jev) — task-gallery-ai-routing-jev-2026-10-09.

Falsification story (what each test would catch):

- a request that leaks a series' file paths / member paths / image bytes or a
  prose instruction (it must be aggregate numbers + opaque aliases only);
- alias/order instability (a payload or priority map that depends on input order
  instead of ``series_id``);
- a decisive routing answer that does not move the priority map, or a
  Noul/low-confidence/errored answer that fabricates one;
- a transport hit twice for an unchanged series list (the pin must serve it);
- an exception escaping the seam into the UI thread.

Network-free: the transport is injected. Pure-python fakes, no Qt.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.services import jev_cache, series_priority
from tabs.image_gallery.services.series_priority import (
    PRIORITY_REASON_EMPTY,
    PRIORITY_REASON_LOW_CONFIDENCE,
    PRIORITY_REASON_NOUL,
    build_priority_request,
    route_series_priority,
    route_series_priority_detailed,
)


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


def _series(sid: str, *items) -> SimpleNamespace:
    return SimpleNamespace(id=sid, members=list(items))


def _chat(decision: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(decision)}}]}


def _camera(name: str, sharp: float, noise: float) -> SimpleNamespace:
    # sharpness/0..400 → %, noise (lower better) via _lower_is_better(1.0).
    return _item(name, sharpness=sharp, noise=noise)


def _groups():
    a = _series("a", _camera("a1.png", 300, 0.10), _camera("a2.png", 150, 0.50))
    b = _series("b", _camera("b1.png", 200, 0.20), _camera("b2.png", 260, 0.15))
    return [a, b]


def _text(payload: dict) -> str:
    return payload["messages"][-1]["content"][0]["text"]


# --------------------------------------------------------------------------
# request: text-only aggregates, json_object, no paths/bytes/prose
# --------------------------------------------------------------------------


def test_request_is_one_user_message_asking_for_json() -> None:
    payload = build_priority_request(_groups(), mode="camera")
    assert payload["model"] == series_priority.JEV_MODEL
    assert [m["role"] for m in payload["messages"]] == ["user"]
    assert payload["response_format"] == {"type": "json_object"}
    vector = json.loads(_text(payload))
    assert set(vector) == {"mode", "series"}


def test_payload_is_aggregate_only_no_paths_no_bytes_no_prose() -> None:
    payload = build_priority_request(_groups(), mode="camera")
    blob = json.dumps(payload)
    for leak in ("/gallery/", "a1.png", "b2.png"):
        assert leak not in blob
    assert "image_url" not in blob and "base64" not in blob and "data:image" not in blob
    low = blob.lower()
    for bad in ("you are", "please", "respond", "compare", "instruction", "choose"):
        assert bad not in low
    for entry in json.loads(_text(payload))["series"]:
        assert entry["alias"].startswith("series_")
        assert "members" in entry
        assert set(entry) <= {
            "alias", "members", "quality_mean", "quality_min", "quality_max", "quality_spread"
        }


def test_aliases_and_payload_are_order_independent_by_series_id() -> None:
    a, b = _groups()
    first = build_priority_request([a, b], mode="camera")
    second = build_priority_request([b, a], mode="camera")
    assert first == second


def test_series_with_fewer_than_two_members_is_not_routed() -> None:
    solo = _series("solo", _camera("s.png", 200, 0.2))
    got = build_priority_request([solo], mode="camera")
    assert json.loads(_text(got))["series"] == []


# --------------------------------------------------------------------------
# decisive answer → priorities; degrade otherwise
# --------------------------------------------------------------------------


def test_decisive_ranking_sets_priorities(tmp_path) -> None:
    a, b = _groups()

    def _client(payload):
        # series_1 = "a", series_2 = "b" (id-sorted) → b needs attention first.
        return _chat({"ranking": ["series_2", "series_1"]})

    outcome = route_series_priority_detailed(
        [a, b], mode="camera", client=_client, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert outcome.decided
    assert outcome.priorities == {"b": 1, "a": 2}


def test_recommended_only_ranks_that_series_first_then_by_id(tmp_path) -> None:
    a, b = _groups()

    def _client(payload):
        return _chat({"recommended": "series_2"})

    priorities = route_series_priority(
        [a, b], mode="camera", client=_client, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert priorities["b"] == 1
    assert sorted(priorities.values()) == [1, 2]


def test_noul_and_low_confidence_degrade(tmp_path) -> None:
    a, b = _groups()
    noul = route_series_priority_detailed(
        [a, b], mode="camera", client=lambda p: _chat({"noul": True}),
        cache=jev_cache.JevRankCache(tmp_path / "n"),
    )
    assert noul.priorities is None and noul.reason == PRIORITY_REASON_NOUL

    low = route_series_priority_detailed(
        [a, b], mode="camera",
        client=lambda p: _chat({"ranking": ["series_1", "series_2"], "score": 0.1}),
        cache=jev_cache.JevRankCache(tmp_path / "l"),
    )
    assert low.priorities is None and low.reason == PRIORITY_REASON_LOW_CONFIDENCE


def test_transport_error_and_empty_degrade_without_raising(tmp_path) -> None:
    a, b = _groups()

    def _boom(payload):
        raise RuntimeError("network exploded")

    err = route_series_priority_detailed(
        [a, b], mode="camera", client=_boom, cache=jev_cache.JevRankCache(tmp_path)
    )
    assert err.priorities is None and "exploded" in (err.reason or "")
    assert route_series_priority(
        [a, b], mode="camera", client=_boom, cache=jev_cache.JevRankCache(tmp_path / "x")
    ) is None

    solo = _series("solo", _camera("s.png", 200, 0.2))
    empty = route_series_priority_detailed(
        [solo], mode="camera", client=_boom, cache=jev_cache.JevRankCache(tmp_path / "e")
    )
    assert empty.priorities is None and empty.reason == PRIORITY_REASON_EMPTY


# --------------------------------------------------------------------------
# pin: a second run of the same series list hits the transport once
# --------------------------------------------------------------------------


def test_second_run_is_served_from_the_pin(tmp_path) -> None:
    a, b = _groups()
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _chat({"ranking": ["series_2", "series_1"]})

    cache = jev_cache.JevRankCache(tmp_path)
    first = route_series_priority([a, b], mode="camera", client=_client, cache=cache)
    second = route_series_priority([a, b], mode="camera", client=_client, cache=cache)
    assert len(calls) == 1
    assert first == second == {"b": 1, "a": 2}
