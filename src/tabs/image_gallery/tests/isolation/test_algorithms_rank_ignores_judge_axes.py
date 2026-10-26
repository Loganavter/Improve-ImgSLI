"""INVARIANT: each backend ranks on ITS OWN profile's axes — never the other's.

The isolation is carried by the PROFILE, not by deleting the score read. Owner
decision #694 (2026-10-26): the free-form axes the judge names ARE the AI
backend's measurement vocabulary and they rank. So ``rank_fusion`` legitimately
reads ``item.analysis`` — for the AI profile. The Algorithms backend must be
handed an Algorithms profile (``source`` = ``series`` / ``heuristic``, no judge
entries), and then a VLM scorecard cannot move its order.

Falsification story (red before the profile split): one ``state.metric_profile``
slot held the judge's answer, and the fusion call passed it to the Algorithms
ranker. Consequence: two items with byte-identical ``metrics`` stopped tying as
soon as one carried a scorecard — the paid axis changed the Algorithms quality
and rank. The same scorecard MUST move the AI order (that is the non-vacuity
half of this test, and #694's contract).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import AiAnalysisResult, AiAxisProposal, GalleryItem
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.rank_fusion import (
    item_quality,
    measured_axes_for,
    rank_series,
)
from tabs.image_gallery.use_cases.profile_select import active_profile

_JUDGE_AXIS = "halation"


def _local_profile() -> MetricProfile:
    """What the LOCAL derivation produces: registry ids, no judge entries."""
    return MetricProfile(
        axis_ids=("sharpness", "noise"), mode="camera", source="series"
    )


def _judge_profile() -> MetricProfile:
    """What the VLM judge produces: its own free-form axis, no registry ids."""
    return MetricProfile(
        mode="camera",
        source="vlm",
        axis_entries=(
            AiAxisProposal(
                name=_JUDGE_AXIS,
                definition="glow around bright edges",
                scale="0-100",
                score=-1,
            ),
        ),
    )


def _state(**slots) -> SimpleNamespace:
    base = {"mode": "camera", "algorithms_profile": None, "ai_profile": None}
    base.update(slots)
    return SimpleNamespace(**base)


def _item(name: str) -> GalleryItem:
    """Two items with IDENTICAL local measurements (a real near-tie)."""
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update({"sharpness": 200.0, "noise": 0.2})
    return item


def _scorecard(*, axis: str, score: int) -> AiAnalysisResult:
    return AiAnalysisResult(
        description="",
        tags=(),
        model="judge-model",
        analyzed_at_iso="t",
        axes={axis: score},
        axis_proposals=(AiAxisProposal(name=axis, score=score),),
    )


def test_the_two_profiles_carry_different_axis_families() -> None:
    state = _state(
        algorithms_profile=_local_profile(), ai_profile=_judge_profile()
    )
    algo = active_profile(state, domain="algorithms")
    ai = active_profile(state, domain="ai")

    assert _JUDGE_AXIS not in measured_axes_for("camera", profile=algo), (
        "the Algorithms profile must not carry a judge-named axis"
    )
    assert _JUDGE_AXIS in measured_axes_for("camera", profile=ai), (
        "non-vacuity: the judge axis must be rankable in the AI backend"
    )


def test_a_vlm_scorecard_cannot_move_the_algorithms_order() -> None:
    state = _state(algorithms_profile=_local_profile())
    algo = active_profile(state, domain="algorithms")

    a = _item("a.png")
    b = _item("b.png")
    baseline_ranks = rank_series([a, b], profile=algo)
    baseline_quality = [item_quality(item, profile=algo) for item in (a, b)]

    # The AI backend's answer exists on the item, but not in this backend's
    # profile — so it cannot contribute a number.
    b.analysis = _scorecard(axis=_JUDGE_AXIS, score=100)

    assert baseline_quality == [65.0, 65.0], (
        "fixture sanity: identical metrics must produce identical local quality"
    )
    assert [item_quality(item, profile=algo) for item in (a, b)] == baseline_quality, (
        "the Algorithms backend's quality must not read item.analysis"
    )
    assert rank_series([a, b], profile=algo) == baseline_ranks, (
        "a VLM scorecard changed the Algorithms order"
    )


def test_the_same_scorecard_moves_the_ai_order() -> None:
    """Owner #694: judge-named axes rank — for the AI profile.

    This half keeps the test honest: the scorecard above is a real measurement
    that the AI backend must use, not an inert fixture.
    """
    state = _state(ai_profile=_judge_profile())
    ai = active_profile(state, domain="ai")
    assert ai.axis_entries, "the AI slot must carry the judge's axis"

    a = _item("a.png")
    b = _item("b.png")
    b.analysis = _scorecard(axis=_JUDGE_AXIS, score=100)

    ranks = rank_series([a, b], profile=ai)
    assert ranks[str(b.path)] < ranks[str(a.path)], (
        "the judge's axis must order the AI backend's rank: "
        f"ranks={ranks!r}"
    )
    assert item_quality(a, profile=ai) is None, (
        "an item with no judge value for the axis stays unmeasured, never 0"
    )
