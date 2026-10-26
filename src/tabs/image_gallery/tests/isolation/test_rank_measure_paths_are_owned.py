"""INVARIANT (ADR 009 A3): each backend's measure/rank reads ONLY its artifacts.

A2 put profile, measurement and rank in one adapter module. A3 makes the two
reading operations their own files (``backends/{algorithms,ai}/{measure,rank}.py``)
and pins what each may touch:

* **Algorithms** — the local engine records / ``item.metrics`` over the
  profile's REGISTRY half (``axis_ids``). A judge-named axis has no local
  producer, so it is not measured here and cannot enter the local order: with a
  locally tagged profile that (illegally) carries a judge entry, the local rank
  must be unmoved by the scorecard that carries that axis' number, and the local
  envelope must carry no record for it.
* **Algorithms issues zero POSTs** — measure + rank are pure local reads; the
  isolation counters must stay at zero (a detector pass that reached the VLM
  client would be the "AI work under Algorithms" leak in its most expensive form).
* **AI** — the scorecard half, and a degraded Jev answer is an EMPTY rank: the
  local fusion order is never substituted for the judge's missing one (that is
  the caller's product decision, not the owner of the profile).

Falsification story (red on the A2 base): both adapters measured with
``backends.context.profile_axes`` (registry + judge names) and the Algorithms
rank called ``rank_fusion.rank_series(profile=…)``, which reads the judge half
through ``_judge_scores`` — so a locally tagged profile carrying judge entries
ranked on the VLM scorecard, and the Algorithms measure emitted gap records for
names no local detector can produce.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.backends.ai import BACKEND as AI_BACKEND
from tabs.image_gallery.backends.algorithms import BACKEND as ALGORITHMS_BACKEND
from tabs.image_gallery.backends.composition import backend
from tabs.image_gallery.backends.context import SeriesContext, owned_profile
from tabs.image_gallery.backends.contract import MeasureRequest, RankRequest
from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiAxisProposal,
    GalleryItem,
    GalleryState,
)
from tabs.image_gallery.services.metric_profile import MetricProfile

JUDGE_AXIS = "halation"


def _twin(name: str) -> GalleryItem:
    """Two items with IDENTICAL local measurements (a real near-tie)."""
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update({"sharpness": 200.0, "noise": 0.2})
    return item


def _judge_only_scorecard(score: int) -> AiAnalysisResult:
    return AiAnalysisResult(
        description="",
        tags=(),
        model="judge-model",
        analyzed_at_iso="t",
        axes={JUDGE_AXIS: score},
        axis_proposals=(
            AiAxisProposal(name=JUDGE_AXIS, definition="glow at bright edges", score=score),
        ),
    )


def _owned_locally_tagged_profile_with_a_judge_entry():
    """A profile the Algorithms adapter accepts, carrying a judge entry.

    ``source="series"`` is the local tag (so ``install``/``domain_of`` accept
    it), while ``axis_entries`` is the AI half — the exact shape a leaked
    profile would have. The adapter must still measure and rank the registry
    half only.
    """
    profile = MetricProfile(
        axis_ids=("sharpness",),
        mode="camera",
        source="series",
        axis_entries=(
            AiAxisProposal(
                name=JUDGE_AXIS, definition="glow at bright edges", score=-1
            ),
        ),
    )
    ALGORITHMS_BACKEND.reset()
    ALGORITHMS_BACKEND.install(GalleryState(mode="camera"), profile)
    return profile, owned_profile(ALGORITHMS_BACKEND.descriptor, profile)


def test_the_algorithms_rank_ignores_a_judge_profile() -> None:
    a, b = _twin("a.png"), _twin("b.png")
    profile, owned = _owned_locally_tagged_profile_with_a_judge_entry()

    baseline = ALGORITHMS_BACKEND.rank(
        RankRequest(profile=owned), context=SeriesContext(members=(a, b))
    )
    # The AI backend's measurement exists on the item, but it is not this
    # backend's vocabulary: it cannot contribute a number here.
    b.analysis = _judge_only_scorecard(score=100)
    after = ALGORITHMS_BACKEND.rank(
        RankRequest(profile=owned), context=SeriesContext(members=(a, b))
    )

    assert dict(after.ranks) == dict(baseline.ranks) == {
        str(a.path): 1,
        str(b.path): 2,
    }, "a VLM scorecard moved the Algorithms order"


def test_the_algorithms_measure_ignores_a_judge_profile() -> None:
    a = _twin("a.png")
    a.analysis = _judge_only_scorecard(score=100)
    _profile, owned = _owned_locally_tagged_profile_with_a_judge_entry()

    envelope = ALGORITHMS_BACKEND.measure(
        MeasureRequest(profile=owned), context=SeriesContext(members=(a,))
    )

    assert envelope.backend_id == "algorithms"
    axes = [record.axis for measured in envelope.records for record in measured.records]
    assert axes == ["sharpness"], (
        "the local envelope carried the judge's axis (or dropped the registry "
        f"one): {axes!r}"
    )


def test_the_algorithms_measure_and_rank_issue_zero_posts(counters) -> None:
    a, b = _twin("a.png"), _twin("b.png")
    _profile, owned = _owned_locally_tagged_profile_with_a_judge_entry()

    ALGORITHMS_BACKEND.measure(
        MeasureRequest(profile=owned), context=SeriesContext(members=(a, b))
    )
    ALGORITHMS_BACKEND.rank(
        RankRequest(profile=owned), context=SeriesContext(members=(a, b))
    )

    assert counters["call_sync"] == 0, "the local measure/rank reached the VLM transport"
    assert counters["save_analysis"] == 0
    assert counters["profile_put"] == 0


def test_the_ai_rank_never_substitutes_the_local_order(tmp_path) -> None:
    """A degraded Jev answer is EMPTY, never the Algorithms fusion order."""
    from tabs.image_gallery.services import jev_cache

    a, b = _twin("a.png"), _twin("b.png")
    AI_BACKEND.reset()
    profile = MetricProfile(axis_ids=("sharpness",), mode="camera", source="vlm")
    AI_BACKEND.install(GalleryState(mode="camera"), profile)
    owned = owned_profile(AI_BACKEND.descriptor, profile)

    result = AI_BACKEND.rank(
        RankRequest(profile=owned),
        context=SeriesContext(
            members=(a, b),
            client=lambda _payload: {"choices": [{"message": {"content": "nope"}}]},
            cache=jev_cache.JevRankCache(tmp_path),
        ),
    )

    assert dict(result.ranks) == {}, (
        "the AI backend borrowed a rank it did not measure: " + repr(dict(result.ranks))
    )


def test_the_mode_mapping_belongs_to_the_algorithms_backend_only() -> None:
    """The AI backend has NO mode mapping — that is the whole point of A3."""
    assert hasattr(backend("algorithms"), "axes_for_mode")
    assert not hasattr(backend("ai"), "axes_for_mode")

    mode_axes = backend("algorithms").axes_for_mode("camera")
    assert "sharpness" in mode_axes
    assert backend("algorithms").axes_for_mode("fidelity") != mode_axes, (
        "fixture sanity: a mode change must change the mode-implied axis set"
    )
