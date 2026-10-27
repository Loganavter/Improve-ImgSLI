"""INVARIANT: the AI domain has no profile-free door, and provenance names WHO DID.

Owner rule (2026-10-27): "we must not decide what is measurable and what is not
… if the app said it needs such metrics, we draw them, period." The AI domain
must be able to say, per axis, WHERE the number came from — and must never
receive the local axis SET merely because no profile was passed.

Three defects, one seam each (``task free-axes-w4``):

(a) ``rank_fusion.measured_axes_for(profile=None)`` fell through to
    ``backends.algorithms.axes_for_mode`` — the LOCAL 8-axis camera set — for any
    caller, including the AI domain. ``NoProfileYet`` only guarded an EMPTY
    profile, so the pairwise refinement
    (``use_cases.ai_analysis.start_pairwise_refinement``) could compute a
    "pointwise" order from detector numbers and the Quick Look rows could render
    the detector set on a judge report. The resolver now refuses a ``profile=None``
    call that DECLARES the AI domain (``domain="ai"``); the local (Algorithms)
    callers keep the mode mapping byte for byte.

(b) ``analysis.read`` stamped a judge-produced number on a POOL axis
    ``measured-locally``, because ``profile_judged.axis_provenance`` answered
    "who CAN measure this axis here" (a detector can produce ``sharpness``
    everywhere) instead of "who DID". Rows then printed the plain registry label
    as if the detector had spoken. The record now carries the producer's own
    answer: a ``vlm`` number is ``measured-by-judge`` even on a registry axis; a
    detector number stays ``measured-locally``. (The dot COLOUR stopped carrying
    provenance on 2026-10-27 — it codes the score band; the instrument lives in
    the label/record, see ``tests/runtime/test_judge_dot_band_colors.py``.)

(c) ``pairwise_rank.profile_axis_numbers`` read ``"algorithms"`` first, then
    ``"ai"``, so on a judged series a registry axis' near-tie number came from
    the detector even when the judge had scored it. It now reads the domain the
    profile belongs to (or the one the caller names), never algorithms-first —
    and ``member_qualities`` never takes the local ``item_quality`` fast path on
    an AI-domain profile.

Falsification story (all three were RED at ``583e499ff`` — see ``DONE.md``):

- (a) base: ``measured_axes_for`` had no ``domain`` at all; ``measured_axes_for(
  "camera")`` answered the 8 local camera axes, which is what every AI caller
  without a profile got.
- (b) base: ``read_axes(item, domain="ai", axes=("sharpness",), profile=judge)``
  returned ``provenance="measured-locally"`` for a value the scorecard wrote,
  and ``metric_dots_for_item`` painted the #2e7d32 good-band colour.
- (c) base: ``profile_axis_numbers`` answered ``{"sharpness": 55.0}`` (the
  detector score of raw 220) where the judge had written 91.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.analysis.read import read_axes
from tabs.image_gallery.backends import NoProfileYet
from tabs.image_gallery.backends.composition import backend
from tabs.image_gallery.models import AiAnalysisResult, AiAxisProposal, GalleryItem, Mode
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.profile_judged import (
    PROVENANCE_JUDGE,
    PROVENANCE_LOCAL,
    provenance_label,
    scorecard_axis_ids,
)
from tabs.image_gallery.services.rank_fusion import measured_axes_for, rank_series
from tabs.image_gallery.use_cases.pairwise_rank import (
    member_qualities,
    profile_axis_numbers,
)

JUDGE_AXIS = "halation"

#: The camera mode mapping — the local 8-axis set this wave must stop handing to
#: the AI domain.
LOCAL_CAMERA_AXES = (
    "sharpness",
    "exposure",
    "clipping",
    "noise",
    "white_balance",
    "detail_gain",
    "aesthetic",
    "brisque",
)


# -- fixtures -----------------------------------------------------------------


def _judge_profile(*, axis_ids=("sharpness",), entries=()) -> MetricProfile:
    """The AI slot's own profile: a judge answer (``source="vlm"``) → AI domain."""
    return MetricProfile(
        axis_ids=tuple(axis_ids),
        mode="camera",
        source="vlm",
        axis_entries=tuple(entries),
    )


def _judge_free_profile() -> MetricProfile:
    return _judge_profile(
        axis_ids=(),
        entries=(
            AiAxisProposal(
                name=JUDGE_AXIS,
                definition="glow around bright edges; 0 = none, 100 = heavy",
                scale="0-100",
                direction="lower-is-better",
            ),
        ),
    )


def _item(name: str, *, axes: dict | None = None, **metrics) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics = dict(metrics)
    if axes is not None:
        item.analysis = AiAnalysisResult(
            description="",
            tags=(),
            model="judge-model",
            analyzed_at_iso="t",
            axes=dict(axes),
        )
    return item


def _judged_pool_item(name: str = "pool.png") -> GalleryItem:
    """A card the judge scored on a POOL axis — with a DIFFERENT detector number.

    raw 220 maps to 55 % (``metric_scores._sharpness``: raw/400), so a surface
    that shows 91 shows the judge's number and a surface that shows 55 shows the
    detector's — the two instruments can never be mistaken for each other.
    """
    return _item(name, axes={"sharpness": 91}, sharpness=220.0)


# -- (a) no profile-free door for the AI domain -------------------------------


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda: measured_axes_for("camera", domain="ai"),
            id="measured_axes_for",
        ),
        pytest.param(
            lambda: scorecard_axis_ids("camera", domain="ai"),
            id="scorecard_axis_ids",
        ),
        pytest.param(
            lambda: rank_series(
                [_item("a.png", sharpness=220.0), _item("b.png", sharpness=100.0)],
                mode="camera",
                domain="ai",
            ),
            id="rank_series",
        ),
    ],
)
def test_the_ai_domain_refuses_a_missing_profile_instead_of_the_local_axes(call):
    """``profile=None`` in the AI domain is a typed refusal, never the mode map."""
    with pytest.raises(NoProfileYet) as excinfo:
        call()

    assert "ai" in str(excinfo.value), (
        "the refusal must name the AI backend, not a generic error: "
        f"{excinfo.value}"
    )


def test_the_local_door_is_unchanged_and_a_real_ai_profile_still_answers():
    """Non-vacuity: the refusal is about the AI domain, not about ``None``."""
    local = measured_axes_for("camera")
    assert local == backend("algorithms").axes_for_mode("camera")
    assert local == LOCAL_CAMERA_AXES, (
        "the Algorithms door must keep the mode mapping exactly as today"
    )
    # Declaring the local domain explicitly is the same answer.
    assert measured_axes_for("camera", domain="algorithms") == local
    # A real profile still answers its own axes on the AI domain.
    assert measured_axes_for("camera", profile=_judge_profile(), domain="ai") == (
        "sharpness",
    )
    assert measured_axes_for(
        "camera", profile=_judge_free_profile(), domain="ai"
    ) == (JUDGE_AXIS,)


# -- (b) provenance says WHO measured the number ------------------------------


def test_a_judge_scored_pool_axis_is_measured_by_the_judge_not_the_detector():
    item = _judged_pool_item()
    profile = _judge_profile()

    record = read_axes(item, domain="ai", axes=("sharpness",), profile=profile)[0]

    assert (record.producer, record.value) == ("vlm", 91.0)
    assert record.provenance == PROVENANCE_JUDGE, (
        "a number the scorecard wrote is the judge's, even on a registry axis; "
        "stamping it measured-locally is the provenance lie this wave removes"
    )
    assert provenance_label(record.provenance) == "measured by the judge"

    # The SAME axis, read from the detector, is still the detector's number.
    local = read_axes(
        item, domain="algorithms", axes=("sharpness",), profile=profile
    )[0]
    assert local.provenance == PROVENANCE_LOCAL
    assert local.value == 55.0, "the detector's own number is untouched"
    assert provenance_label(local.provenance) == "measured locally"


def test_the_judge_dot_on_a_pool_axis_paints_its_score_band():
    """A judge number paints its BAND (the colour codes the score, 2026-10-27).

    The provenance this file is about is a RECORD fact: it shows in the row and
    in the dot tooltip, never in the dot colour — so the 91 the judge scored on
    ``sharpness`` paints the same ``clean`` green a detector's 91 would.
    """
    from tabs.image_gallery.ui.card.dots import (
        _BAND_SEVERITY,
        _severity_color,
        metric_dots_for_item,
    )
    from tabs.image_gallery.services.metric_scores import score_band

    item = _judged_pool_item()
    profile = _judge_profile()

    colors, infos = metric_dots_for_item(
        item, mode=Mode.CAMERA, domain="ai", profile=profile
    )

    assert [score for _label, score in infos] == [91], infos
    expected = _severity_color(_BAND_SEVERITY[score_band(91)]).name()
    assert [color.name() for color in colors] == [expected], (
        "a judge-scored pool axis did not paint the colour of its score band "
        f"({expected}): {[c.name() for c in colors]}"
    )


def test_a_detector_dot_keeps_the_severity_band():
    """Non-vacuity: the Algorithms domain is still painted by band."""
    from tabs.image_gallery.ui.card.dots import _accent_color, metric_dots_for_item

    item = _item("local.png", sharpness=220.0)

    colors, infos = metric_dots_for_item(item, mode=Mode.CAMERA, domain="algorithms")

    assert [score for _label, score in infos] == [55], infos
    assert colors[0].name() != _accent_color().name(), (
        "a detector number must not be painted as the judge's instrument"
    )


# -- (c) the pairwise numbers come from the domain they were asked for --------


def test_pairwise_numbers_on_a_judged_series_read_the_scorecard_not_the_metrics():
    item = _judged_pool_item()
    profile = _judge_profile()

    numbers = profile_axis_numbers(item, mode="camera", profile=profile)

    assert numbers == {"sharpness": 91.0}, (
        "the pairwise payload carried the detector's 55 for an axis the judge "
        f"scored at 91: {numbers}"
    )
    assert member_qualities([item], mode="camera", profile=profile) == [91.0], (
        "member_qualities took the local item_quality fast path on an AI profile"
    )


def test_pairwise_numbers_honour_an_explicit_domain():
    """The asked domain is read, not a fixed algorithms-first order."""
    item = _judged_pool_item()
    profile = _judge_profile()

    assert profile_axis_numbers(
        item, mode="camera", profile=profile, domain="ai"
    ) == {"sharpness": 91.0}
    assert profile_axis_numbers(
        item, mode="camera", profile=profile, domain="algorithms"
    ) == {"sharpness": 55.0}


def test_a_local_profile_still_reads_the_detectors():
    """Non-vacuity: an Algorithms profile is not diverted to the scorecard."""
    item = _judged_pool_item()
    local_profile = MetricProfile(
        axis_ids=("sharpness",), mode="camera", source="series"
    )

    assert profile_axis_numbers(item, mode="camera", profile=local_profile) == {
        "sharpness": 55.0
    }


# -- the production door: the pairwise refinement -----------------------------


class _NoProfileOwner:
    """The AI-domain owner with an EMPTY AI slot and a near-tie local series.

    This is the live shape the recon measured (``ai_analysis.py`` pairwise
    block): the domain says AI, the state has no judge profile, and the members
    still carry detector numbers a profile-free pass could compare.
    """

    _judgment_domain = "ai"
    _folder_gen = 0
    _domain_epoch = 0
    _AI_VISIBLE_CAP = 4

    def __init__(self, items) -> None:
        settings = SimpleNamespace(
            enabled=True,
            api_key="k",
            model="model-x",
            base_url="http://provider.invalid",
            pairwise_enabled=True,
            pairwise_top_n=2,
            pairwise_near_tie_threshold=10.0,
            judge_run_call_ceiling=0,
        )
        series = SimpleNamespace(id="s0", members=list(items))
        self.state = SimpleNamespace(
            mode="camera", ai_profile=None, items=list(items), series=[series]
        )
        self._ai_settings_store = SimpleNamespace(load=lambda: settings)
        self.launched: list = []
        self._pool_start = lambda worker, priority: self.launched.append(worker)
        self._tracked = lambda fn: fn


def test_the_pairwise_pass_is_not_scheduled_without_an_ai_profile():
    """The AI refinement never compares detector numbers (the no-profile door)."""
    from tabs.image_gallery.use_cases import ai_analysis

    # Raw 320/300 -> 80/75: a near-tie the DETECTOR could compare, so a
    # profile-free pass would have spent judge calls on local numbers.
    items = [
        _item("a.png", sharpness=320.0),
        _item("b.png", sharpness=300.0),
    ]
    owner = _NoProfileOwner(items)

    scheduled = ai_analysis.start_pairwise_refinement(owner, judge=lambda a, b: None)

    assert scheduled is False
    assert owner.launched == [], (
        "the pairwise pass was scheduled without an AI profile — it would have "
        "ranked the judge's work on the local mode axes"
    )
