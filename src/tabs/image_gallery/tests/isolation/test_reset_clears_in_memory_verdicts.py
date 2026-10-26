"""INVARIANT: "Reset metrics cache" drops the IN-MEMORY VLM/Jev verdicts too.

The disk half is covered next door
(``test_reset_clears_jev_and_vlm_pins``) and is not enough on its own: an open
session paints ``state.tie_breaks`` / ``state.series_priority`` and each item's
``vlm_tie_*`` / ``vlm_brief_*`` fields WITHOUT reading those files again, so a
reset that only unlinks files leaves the stale pinned order and the stale
tie-break/brief on screen until the process restarts — the partial-reset
complaint (owner 2026-10-22: "the action zeroes ALL measured state").

Falsification story (red on ``int/backend-isolation``): ``clear_metrics_caches``
empties the items' metrics/rank fields but never touches the verdict maps or
the VLM fields, so every seeded value below survives the call.

Deliberately a separate module from the disk test: the two halves of the reset
must stay separable, so one red does not mask the other.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import CompareBrief, GalleryState, GalleryItem, TieBreakResult
from tabs.image_gallery.use_cases import pairwise_rank
from tabs.image_gallery.use_cases.cache_reset import clear_metrics_caches


class _Owner:
    """Minimal reset owner with a REAL ``GalleryState`` (the verdict maps live there)."""

    def __init__(self, items) -> None:
        self.state = GalleryState(folder=Path("/gallery"), items=list(items))
        self.profile_clears = 0
        self.priority_clears = 0

    def clear_metric_profile(self) -> None:
        self.profile_clears += 1
        self.state.algorithms_profile = None
        self.state.ai_profile = None

    def _clear_series_priority(self) -> None:
        """The controller's seam: drops the hint AND re-stamps the headers."""
        self.priority_clears += 1
        self.state.series_priority = {}


def _tie(path_a: Path, path_b: Path) -> TieBreakResult:
    return TieBreakResult(
        winner_path=str(path_a),
        loser_path=str(path_b),
        reason="sharper",
        confidence=0.9,
        model="judge-model",
        decided_at_iso="t",
    )


def _brief(path_a: Path, path_b: Path) -> CompareBrief:
    return CompareBrief(
        pair=(str(path_a), str(path_b)),
        summary="same scene, b is cleaner",
        differences=("noise",),
        tags=("noise",),
        model="judge-model",
        created_at_iso="t",
    )


def test_reset_clears_in_memory_verdicts(tmp_path, counters) -> None:
    """The verdict maps are emptied and every per-item VLM field is back to rest."""
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    winner = GalleryItem(path=a, mtime_ns=1)
    loser = GalleryItem(path=b, mtime_ns=2)
    verdict = _tie(a, b)
    brief = _brief(a, b)

    for item in (winner, loser):
        item.vlm_tie_result = verdict
        item.vlm_tie_pending = True
        item.vlm_tie_error = "transport: timeout"
        item.vlm_brief = brief
        item.vlm_brief_status = "ready"
        item.vlm_brief_error = "transport: timeout"
    owner = _Owner([winner, loser])
    owner.state.tie_breaks["series_1"] = verdict
    owner.state.series_priority["series_1"] = 1
    pair = pairwise_rank.pair_key(
        "a", 1, "b", 2, model="judge-model", base_url="https://h/v1"
    )
    pairwise_rank.DEFAULT_CACHE.put(pair, pairwise_rank.PairVerdict("a", "b", "a", "b"))
    assert len(pairwise_rank.DEFAULT_CACHE) == 1, "fixture sanity: one seam verdict"

    summary = clear_metrics_caches(owner)

    assert summary["items"] == 2
    assert owner.state.tie_breaks == {}, (
        "the in-memory VLM verdict map survived the reset: "
        f"{owner.state.tie_breaks!r}"
    )
    assert owner.state.series_priority == {}, (
        "the in-memory Jev series-priority hint survived the reset: "
        f"{owner.state.series_priority!r}"
    )
    for item in (winner, loser):
        assert item.vlm_tie_result is None
        assert item.vlm_tie_pending is False
        assert item.vlm_tie_error is None
        assert item.vlm_brief is None
        # The dataclass default, not a "pending"/"error" leftover: after a reset
        # nothing is measuring, so the card must not show a VLM spinner/error.
        assert item.vlm_brief_status == "none"
        assert item.vlm_brief_error is None
    assert len(pairwise_rank.DEFAULT_CACHE) == 0, (
        "the process-wide pairwise verdict store survived the reset"
    )
    assert summary["pairwise_verdicts"] == 1
    assert owner.profile_clears == 1
    # The header attention marker is painted from the hint, so the reset must
    # go through the controller's seam (which re-stamps the headers), not just
    # empty the dict.
    assert owner.priority_clears == 1
