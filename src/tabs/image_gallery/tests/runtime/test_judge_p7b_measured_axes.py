"""P7-B — the named axes are MEASURED, CARRIED and COMPARED.

P7-A let the judge NAME 3..8 axes in free form (``MetricProfile.axis_entries``),
but the chain stopped there: the scorecard parser dropped a free axis' number,
the Jev vector carried only registry numbers, the ranker saw no meaning or
direction, and the noise floor was the constant 20 even when k draws had measured
the instrument's own spread.

Falsification story (what each test would catch, and why it is red before):

- **(a)** a free axis the judge named SURVIVES the scorecard parse and reaches
  the Jev vector BY NAME with its number. Red before: ``_parse_axes`` filtered
  every key outside ``metric_scores.SCORECARD_AXIS_IDS``, so the judge named the
  axis and the parser silently threw its number away.
- **(b)** the payload describes every axis with a MEANING and a DIRECTION, and a
  free axis whose definition says "0 = none" is ``lower-is-better`` even though
  the default is "higher is better". Red before: the system prompt said only
  "measured quality scores" and the vector carried bare numbers, so the live
  ranker wrote *"Noise higher = better? ... likely quality, higher better"*
  (owner log, 2026-10-21) — it guessed.
- **(c)** a vector carrying ONE axis is REFUSED with a named reason and no
  transport call. Red before: one number was ranked and the ranker guessed.
- **(d)** the noise floor is the MEASURED within-item spread when the k draws
  carry it, and the constant only for a single draw — asserted on a fixture where
  the measured spread is small (2) and the constant is 20. Red before:
  ``axis_noise_floor`` returned 20 unconditionally.
- **(e)** the analyze cache identity HITS for the same axis set and MISSES for a
  different one, and a HIT keeps the free axis' number and its draws. Red before:
  the free axis' number was not stored at all.

Red-before evidence was produced on a pre-change scratch copy of ``HEAD``
(``git archive HEAD``) — see ``DONE.md``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.models import (
    AXIS_DIRECTIONS,
    AiAnalysisResult,
    AiAxisProposal,
)
from tabs.image_gallery.services.ai_cache import (
    AI_CACHE_VERSION,
    analysis_cache_identity,
    load_cached_analysis,
    save_analysis,
)
from tabs.image_gallery.services.ai_client import parse_response
from tabs.image_gallery.services.ai_client.parse import merge_samples
from tabs.image_gallery.services.axis_choice import parse_axis_choices
from tabs.image_gallery.services.jev_client import (
    JEV_REASON_ONE_AXIS,
    JEV_REJECT_ONE_AXIS,
    build_measured_vector,
    build_rank_request,
    rank_series_jev_detailed,
)
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.quality_read import axis_noise_floor

FREE = AiAxisProposal(
    name="jpeg_noise",
    definition="8x8 block edges and mosquito noise; 0 = none visible, 100 = heavy",
    scale="0-100",
    direction="higher-is-better",
)
#: A definition that flips the owner default ("higher is better unless the
#: definition says otherwise"): 0 is the good end.
LOWER_FREE = "banding_rings"
LOWER_DEFINITION = "banding rings; 0 = none, 100 = heavy"


def _profile(*entries, axis_ids=("sharpness",)) -> MetricProfile:
    return MetricProfile(
        axis_ids=axis_ids,
        mode="camera",
        source="vlm",
        axis_entries=tuple(entries),
    )


def _chat(obj: dict) -> dict:
    import json

    return {"choices": [{"message": {"content": json.dumps(obj)}}]}


def _item(name: str, axes: dict | None = None, **kwargs) -> SimpleNamespace:
    analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes=dict(axes or {}),
        **kwargs,
    )
    return SimpleNamespace(path=Path(f"/gallery/{name}"), analysis=analysis)


# ---------------------------------------------------------------------------
# (a) a judge-named free axis survives the parse and lands in the vector
# ---------------------------------------------------------------------------


def test_a_judge_named_axis_survives_the_parse_and_reaches_the_vector():
    profile = _profile(FREE)
    raw = _chat(
        {
            "axes": {
                "sharpness": 80,
                FREE.name: 73,
                "not_asked_for": 55,  # neither registry nor judge-named: dropped
            }
        }
    )

    result = parse_response(raw, model="m", profile=profile)

    assert result.axes[FREE.name] == 73, (
        "the judge named this axis and the scorecard answered it — the parser "
        "must keep the number instead of dropping it as unknown"
    )
    assert "not_asked_for" not in result.axes, "a name nobody asked for is never kept"
    assert [e.name for e in result.axis_entries] == [FREE.name], (
        "the scorecard carries the judge's set, so a cache HIT can validate it"
    )

    items = [
        _item("a.png", result.axes),
        _item("b.png", {"sharpness": 40, FREE.name: 21}),
    ]
    vector = build_measured_vector(items, mode="camera", domain="ai", profile=profile)
    by_alias = {entry["alias"]: entry["scores"] for entry in vector["items"]}
    assert by_alias["img_1"][FREE.name] == 73
    assert by_alias["img_2"][FREE.name] == 21


def test_without_the_profile_a_free_axis_is_still_dropped():
    """The guard against over-widening: the set must come from the judge."""
    raw = _chat({"axes": {"sharpness": 80, FREE.name: 73}})

    result = parse_response(raw, model="m")

    assert result.axes == {"sharpness": 80}
    assert result.axis_entries == ()


# ---------------------------------------------------------------------------
# (b) the payload carries a MEANING and a DIRECTION for every axis
# ---------------------------------------------------------------------------


def test_every_payload_axis_carries_a_meaning_and_a_direction():
    # Construct the lower-is-better axis through the REAL parser so its direction
    # is derived from the definition (not the dataclass default).
    choices = parse_axis_choices(
        [
            {
                "name": LOWER_FREE,
                "definition": LOWER_DEFINITION,
                "scale": "0-100",
            }
        ]
    )
    lower = choices.entries[0]
    assert lower.direction == "lower-is-better", "the definition says 0 is the good end"

    profile = _profile(FREE, lower)
    items = [
        _item("a.png", {"sharpness": 90, FREE.name: 70, LOWER_FREE: 10}),
        _item("b.png", {"sharpness": 40, FREE.name: 30, LOWER_FREE: 40}),
    ]
    vector = build_measured_vector(items, mode="camera", domain="ai", profile=profile)

    described = {entry["name"]: entry for entry in vector["axes"]}
    assert set(described) == {"sharpness", FREE.name, LOWER_FREE}
    for name, entry in described.items():
        assert entry["definition"], f"{name} carries no meaning"
        assert entry["scale"] == "0-100"
        assert entry["direction"] in AXIS_DIRECTIONS

    assert described[FREE.name]["definition"] == FREE.definition
    assert described[FREE.name]["direction"] == "higher-is-better"
    assert described[LOWER_FREE]["direction"] == "lower-is-better", (
        "the direction must follow the definition, never the default"
    )
    assert described["sharpness"]["direction"] == "higher-is-better"

    # The output contract states the rule the payload relies on.
    system = build_rank_request(
        items, mode="camera", domain="ai", profile=profile
    )["messages"][0]["content"]
    assert "QUALITY axis" in system and "unless its direction says otherwise" in system
    assert "higher-is-better" in system and "lower-is-better" in system


def test_a_proposed_axis_also_carries_its_direction():
    proposal = AiAxisProposal(
        name="halation",
        definition="red glow around highlights; 0 = none, 100 = heavy",
        scale="0-100",
        score=70,
        direction="lower-is-better",
    )
    items = [
        _item("a.png", {"sharpness": 80}, axis_proposals=(proposal,)),
        _item("b.png", {"sharpness": 60}),
    ]
    vector = build_measured_vector(items, mode="camera", domain="ai")
    proposed = {entry["name"]: entry for entry in vector["proposed_axes"]}
    assert proposed["halation"]["direction"] == "lower-is-better"


# ---------------------------------------------------------------------------
# (c) one axis is refused, never ranked
# ---------------------------------------------------------------------------


def test_a_one_axis_vector_is_refused_with_a_named_reason_and_no_call():
    items = [_item("a.png", {"sharpness": 80}), _item("b.png", {"sharpness": 40})]
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _chat({"choice": "img_1", "score": 0.9})

    outcome = rank_series_jev_detailed(
        items, mode="camera", client=_client, domain="ai"
    )

    assert outcome.ranks is None, "a single number cannot order the variants"
    assert outcome.reason == JEV_REASON_ONE_AXIS
    assert JEV_REJECT_ONE_AXIS in outcome.reason, "the reason names its code"
    assert calls == [], "the refuser must not ask the ranker to guess"


def test_two_axes_are_still_ranked():
    """Contrast: the gate must not over-reach."""
    items = [
        _item("a.png", {"sharpness": 80, "noise": 90}),
        _item("b.png", {"sharpness": 40, "noise": 50}),
    ]
    outcome = rank_series_jev_detailed(
        items,
        mode="camera",
        client=lambda payload: _chat({"choice": "img_1", "score": 0.9}),
        domain="ai",
    )
    assert outcome.decided, outcome.reason


# ---------------------------------------------------------------------------
# (d) the floor is the MEASURED within-item spread when the draws carry it
# ---------------------------------------------------------------------------


def _draw(**axes) -> AiAnalysisResult:
    return AiAnalysisResult(description="", tags=(), model="m", analyzed_at_iso="t", axes=dict(axes))


def test_the_floor_reads_the_measured_within_item_spread_not_the_constant():
    merged = merge_samples(
        [
            _draw(sharpness=70, noise=50),
            _draw(sharpness=73, noise=52),
            _draw(sharpness=72, noise=51),
        ]
    )
    assert merged.axis_samples, "the k draws are carried on the merged result"
    assert merged.axes == {"sharpness": 72, "noise": 51}  # median

    measured = axis_noise_floor("ai", samples=[merged])
    fallback = axis_noise_floor("ai")
    assert measured == 3.0, "the widest per-axis draw-to-draw movement (70→73)"
    assert fallback == 20.0, "a single draw keeps the constant"
    assert measured != fallback


def test_a_small_measured_floor_keeps_an_axis_the_constant_would_suppress():
    """The two paths DIFFER where it matters: what the ranker is shown."""
    # sharpness moves 10 (real at a measured floor of 2, inside the constant
    # 20); noise moves 30 (discriminating under BOTH floors, so suppression has
    # something to keep and the rules are actually exercised).
    draws_a = ({"sharpness": 59, "noise": 60}, {"sharpness": 61, "noise": 60})
    draws_b = ({"sharpness": 69, "noise": 90}, {"sharpness": 71, "noise": 90})
    measured_items = [
        _item("a.png", {"sharpness": 60, "noise": 60}, axis_samples=draws_a),
        _item("b.png", {"sharpness": 70, "noise": 90}, axis_samples=draws_b),
    ]
    constant_items = [
        _item("a.png", {"sharpness": 60, "noise": 60}),
        _item("b.png", {"sharpness": 70, "noise": 90}),
    ]

    measured = build_measured_vector(measured_items, mode="camera", domain="ai")
    constant = build_measured_vector(constant_items, mode="camera", domain="ai")
    measured_scores = {e["alias"]: e["scores"] for e in measured["items"]}
    constant_scores = {e["alias"]: e["scores"] for e in constant["items"]}

    assert "sharpness" in measured_scores["img_1"], (
        "a 10-point between-variant spread is real when the instrument moves 2"
    )
    assert "sharpness" not in constant_scores["img_1"], (
        "the same 10-point spread sits inside the constant 20-point floor"
    )


# ---------------------------------------------------------------------------
# (e) the cache identity: same axis set HITS, a different one MISSES
# ---------------------------------------------------------------------------


def test_the_cache_identity_hits_the_same_axis_set_and_misses_another(tmp_path, monkeypatch):
    from tabs.image_gallery.services import ai_cache

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    same = _profile(FREE)
    same_again = _profile(
        AiAxisProposal(
            name=FREE.name, definition=FREE.definition, direction="higher-is-better"
        )
    )
    other = _profile(
        AiAxisProposal(name="comet_tails", definition="streaks; 0 = none, 100 = heavy")
    )

    identity = analysis_cache_identity(None, mode="camera", profile=same)
    assert identity == analysis_cache_identity(None, mode="camera", profile=same_again)
    other_identity = analysis_cache_identity(None, mode="camera", profile=other)
    assert identity != other_identity

    path = Path("/gallery/frame.png")
    result = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes={"sharpness": 80, FREE.name: 73},
        axis_entries=(FREE,),
        axis_samples=({"sharpness": 79, FREE.name: 72}, {"sharpness": 81, FREE.name: 74}),
    )
    save_analysis(path, 7, result, identity)

    hit = load_cached_analysis(path, 7, identity)
    assert hit is not None
    assert hit.axes[FREE.name] == 73, "a HIT keeps the free axis' number"
    assert hit.axis_samples, "a HIT keeps the draws the floor reads"
    assert load_cached_analysis(path, 7, other_identity) is None, (
        "a different axis set asked a different question"
    )
    assert AI_CACHE_VERSION >= 3
