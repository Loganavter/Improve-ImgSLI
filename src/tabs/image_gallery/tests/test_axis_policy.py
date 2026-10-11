"""W1 — open-vocabulary axis relevance + flag-for-review (two-domain-axes)."""

from __future__ import annotations

from tabs.image_gallery.models import MetricKind
from tabs.image_gallery.services import axis_policy
from tabs.image_gallery.services.axis_policy import (
    FLAG_FOR_REVIEW,
    degrade_unknown,
    normalize_tag,
    relevant_axes,
)
from tabs.image_gallery.services.metric_scores import SPECS

ALL_IDS = {s.id for s in SPECS}


def test_normalize_tag_unifies_separators():
    assert normalize_tag(" Cel-Noise ") == "cel noise"
    assert normalize_tag("over_smoothing") == "over smoothing"


def test_relevant_axes_never_drops_a_measured_axis():
    for tags in ((), ("reference",), ("photo",), ("zzz-unknown",)):
        got = relevant_axes(tags, kind=MetricKind.MEASURED)
        assert set(got) == ALL_IDS, tags


def test_relevant_axes_orders_matches_first():
    got = relevant_axes(("reference",))
    # ssim is reference-tagged → surfaced before an untagged axis
    assert got.index("ssim") < got.index("sharpness")


def test_degrade_unknown_flags_unknown_observations_without_a_number():
    assert degrade_unknown("cel noise") == FLAG_FOR_REVIEW
    assert degrade_unknown("hallucinated extra hand") == FLAG_FOR_REVIEW


def test_degrade_unknown_maps_known_observations_to_axis_ids():
    assert degrade_unknown("ssim") == "ssim"
    assert degrade_unknown("source match") == "ssim"
    assert degrade_unknown("brisque") == "brisque"


def test_no_closed_operation_or_content_enumeration_in_policy():
    src = open(axis_policy.__file__, encoding="utf-8").read().lower()
    for banned in ("inpaint", "content_class", "content_types", "operations ="):
        assert banned not in src
