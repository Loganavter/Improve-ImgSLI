"""Wave-C gate for plan P2 — the VLM profile path, end to end, with no network.

The selector lane (probe + one pinned call + cache) and the wiring lane (stage
`metric_profile` -> worker -> apply-tail) are green alone. This file tests the
**seam between them plus the consumer boundary**, which is where multi-lane work
dies:

- the pin actually prevents a second call for unchanged inputs (a counter, not a
  promise) and an unusable configuration makes no call at all;
- the reply is constrained to the CLOSED pool (an unknown id is dropped, never
  fabricated) and junk / a transport failure degrade to the deterministic
  heuristic — and are NOT pinned;
- the profile that the wiring's apply-tail would store is the axis set the
  consumers resolve (dots, `measured_axes_for`, rank fusion) and the trace names
  `source=vlm`;
- the stage is declared with `requires=("metrics_ready",)` and the settle
  kick/apply pair exists on the controller.

Falsification: this file is red on a selector-only tree (the module-level
`controller._PROFILE_STAGE` and `_run_profile_select_on_settle` do not exist) and
on a tree without the selector (no `choose_profile_sync`) — it is bound to both
sides of the seam. The pin/none-call cases were also checked to fail if the cache
argument is dropped (the second call happens).

No network, no Qt event loop, no GPU: the transport is injected and image
encoding is stubbed (the probe items are fakes, not real files).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery import controller as controller_mod
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryState, Mode, Series
from tabs.image_gallery.services.metric_profile import MEASURED_POOL, profile_for_mode
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.services.rank_fusion import measured_axes_for, rank_series
from tabs.image_gallery.ui.card.dots import metric_dots_for_item
from tabs.image_gallery.use_cases import pipeline_stages
from tabs.image_gallery.use_cases.profile_ai import (
    choose_profile_sync,
    parse_profile_reply,
)
from tabs.image_gallery.use_cases.profile_select import (
    active_profile,
    derive_profile,
    describe,
)

STAGE = "metric_profile"
#: A ``reference`` axis: it is measured *against* a source hub, so it is not
#: applicable to a ``batch_synthetic`` folder (no hub) — the selector's reply
#: must be constrained to the applicable pool axes, never widened with it.
EXTRA = "ssim"


@pytest.fixture(autouse=True)
def _stub_image_encoding(monkeypatch):
    """The probe members are fakes: never read a real image off disk."""
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


def _item(name: str, mtime: int = 1, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), mtime_ns=int(mtime), metrics=dict(metrics))


def _settings(**overrides):
    base = {
        "enabled": True,
        "api_key": "k",
        "base_url": "http://x",
        "model": "m",
        "reasoning_effort": "auto",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _chat(answer) -> dict:
    content = answer if isinstance(answer, str) else json.dumps(answer)
    return {"choices": [{"message": {"content": content}}]}


def _scattered():
    """A decisive spread on sharpness, on ``noise`` AND on the reference axis.

    ``noise`` deliberately ranks the items the OTHER way round, so a profile
    that selects it proves the consumers follow the selection (not the mode
    mapping, which averages sharpness and noise into a tie).
    """
    return [
        _item("a.png", 1, sharpness=0.0, ssim=1.0, noise=1.0),
        _item("b.png", 2, sharpness=400.0, ssim=0.0, noise=0.5),
        _item("c.png", 3, sharpness=200.0, ssim=0.5, noise=0.0),
    ]


class _Transport:
    """Counting fake: ``client_call(base_url, api_key, payload)``."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, base_url, api_key, payload):
        self.calls.append({"base_url": base_url, "api_key": api_key, "payload": payload})
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


def _order(ranks: dict) -> list:
    return [p for p, _r in sorted(ranks.items(), key=lambda kv: (kv[1], kv[0]))]


# --------------------------------------------------------------------------
# one call per unchanged fingerprint; pool-constrained parse; honest fallback
# --------------------------------------------------------------------------


def test_pin_prevents_a_second_call_and_returns_the_same_profile(tmp_path):
    items = _scattered()
    cache = ProfileCache(tmp_path)
    transport = _Transport([_chat({"axes": ["sharpness", "noise"]})])

    first = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=transport
    )
    second = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=transport
    )

    assert len(transport.calls) == 1, "the pin must serve the second run"
    assert first == second and first.source == "vlm"
    # A VLM profile is EXACTLY the pool ids the model chose: it may legitimately
    # be NARROWER than the mode base (dropping an irrelevant axis is the point of
    # the feature). Only the heuristic fallback guarantees the mode base.
    assert set(first.axis_ids) == {"sharpness", "noise"}
    assert set(first.axis_ids) <= set(MEASURED_POOL)

    payload = transport.calls[0]["payload"]
    assert payload.get("response_format") == {"type": "json_object"}
    content = payload["messages"][-1]["content"]
    text = content[0]["text"]
    for axis in MEASURED_POOL:
        assert axis in text, "every pool id is offered (the vocabulary is closed)"
    images = [part for part in content if part.get("type") == "image_url"]
    assert 2 <= len(images) <= len(items), "the probe sends the deviant members as images"


def test_unknown_ids_are_dropped_never_fabricated():
    profile = parse_profile_reply(
        json.dumps({"axes": ["sharpness", "not_an_axis", "composition"]}), mode="camera"
    )
    assert profile is not None
    assert profile.axis_ids == ("sharpness",)
    assert profile.source == "vlm"


def test_junk_reply_degrades_to_the_series_offer_and_is_not_pinned(tmp_path):
    items = _scattered()
    cache = ProfileCache(tmp_path)
    transport = _Transport([_chat("I cannot help with that."), _chat("still prose")])

    first = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=transport
    )
    second = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=transport
    )

    assert first.source == "series" and second.source == "series"
    # The fallback is the SERIES OFFER (P5): only the axes this series can
    # separate — sharpness and noise spread; the reference axis needs a source
    # hub, and the mode base's constant axes are not offered.
    assert first == derive_profile(items, mode="camera")
    assert set(first.axis_ids) == {"sharpness", "noise"}
    assert "white_balance" not in first.axis_ids
    assert len(transport.calls) == 2, "a malformed reply must not be pinned (it may retry)"


def test_transport_failure_degrades_to_the_series_offer(tmp_path):
    transport = _Transport([RuntimeError("boom")])
    profile = choose_profile_sync(
        _scattered(), mode="camera", settings=_settings(),
        cache=ProfileCache(tmp_path), client_call=transport,
    )
    assert profile.source == "series"
    assert set(profile.axis_ids) == {"sharpness", "noise"}, (
        "the local spreads still decide the offer when the VLM is out"
    )
    assert EXTRA not in profile.axis_ids, (
        "a reference axis needs a source hub — none here"
    )


def test_ai_unavailable_makes_no_call(tmp_path):
    transport = _Transport([_chat({"axes": ["sharpness"]})])
    for overrides in ({"enabled": False}, {"api_key": ""}, {"model": "", "base_url": ""}):
        transport.calls.clear()
        profile = choose_profile_sync(
            _scattered(), mode="camera", settings=_settings(**overrides),
            cache=ProfileCache(tmp_path), client_call=transport,
        )
        assert profile.source == "series"
        assert transport.calls == [], f"an unusable configuration must not hit the transport: {overrides}"


# --------------------------------------------------------------------------
# the chosen profile IS the axis set the consumers read
# --------------------------------------------------------------------------


def test_the_vlm_profile_reaches_dots_axes_and_the_rank(tmp_path):
    items = _scattered()
    transport = _Transport([_chat({"axes": ["noise", EXTRA]})])
    profile = choose_profile_sync(
        items, mode="batch_synthetic", settings=_settings(),
        cache=ProfileCache(tmp_path), client_call=transport,
    )
    assert profile.source == "vlm"
    # The pick is the SELECTION (a subset of the pool), constrained to the
    # axes this context can measure: the reference axis has no source hub in a
    # synthetic folder, so it is dropped rather than widening the vocabulary.
    assert "noise" in profile.axis_ids
    assert EXTRA not in profile.axis_ids
    assert set(profile.axis_ids) <= set(profile_for_mode("batch_synthetic").axis_ids)

    # This is what the wiring's apply-tail stores; assert the consumers then
    # resolve exactly that set.
    state = GalleryState(
        items=list(items),
        series=[Series(id="s1", members=list(items))],
        mode=Mode.BATCH_SYNTHETIC,
        metric_profile=profile,
    )
    resolved = active_profile(state)
    assert resolved == profile
    assert measured_axes_for(state.mode, profile=resolved) == profile.axis_ids

    _colors, infos = metric_dots_for_item(items[0], mode=state.mode, profile=resolved)
    assert len(infos) == len(profile.axis_ids)

    expected = rank_series(list(items), mode=state.mode, profile=resolved)
    mode_only = rank_series(list(items), mode=state.mode)
    assert expected != mode_only, "the dataset must be discriminating for this to prove anything"

    ctrl = SimpleNamespace(state=state)
    GalleryController._apply_fusion_ranks(ctrl, state.series, mode=state.mode)
    got = {str(i.path): i.rank for i in items}
    assert _order(got) == _order(expected), "the rank must follow the SAME profile the dots read"

    assert "source=vlm" in describe(state)


# --------------------------------------------------------------------------
# the wiring side of the seam
# --------------------------------------------------------------------------


def test_the_stage_is_declared_and_requires_metrics_ready():
    assert controller_mod._PROFILE_STAGE == STAGE
    assert pipeline_stages.stage_requires(STAGE) == ("metrics_ready",)


def test_wiring_exposes_the_settle_kick_and_the_outcome_apply():
    assert callable(GalleryController._run_profile_select_on_settle)
    assert callable(GalleryController._apply_profile_outcome)
