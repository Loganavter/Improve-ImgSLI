"""W0 — axis kinds (plan-gallery-two-domain-axes).

Adds ``MetricKind`` + ``MetricSpec.kind``/``tags`` with no change to measured
scoring. Guards: the three kinds exist; every registry axis is MEASURED today;
``measured_scores`` emits numbers only (identity/shape unchanged).
"""

from __future__ import annotations

from tabs.image_gallery.models import JUDGMENT_DOMAINS, MetricKind
from tabs.image_gallery.services.metric_scores import (
    SPECS,
    measured_scores,
    score_for,
    spec_for,
)


def test_metric_kind_has_exactly_three_members():
    assert {k.value for k in MetricKind} == {"measured", "candidate", "judgment"}


def test_judgment_domains_are_algorithms_and_ai():
    assert JUDGMENT_DOMAINS == ("algorithms", "ai")


def test_every_registry_axis_is_measured_today():
    assert SPECS, "registry must not be empty"
    assert all(spec.kind is MetricKind.MEASURED for spec in SPECS)


def test_measured_scores_shape_and_values_come_from_the_registry():
    metrics = {"sharpness": 200.0, "ssim": 0.9, "delta_e": 2.0}
    out = measured_scores(metrics)
    assert out, "expected some measured axes"
    ids = {t[0] for t in out}
    assert {"sharpness", "ssim", "color_accuracy"} <= ids
    for mid, label, raw, score in out:
        spec = spec_for(mid)
        assert spec is not None
        assert label == spec.label
        assert score == score_for(spec, raw)
        assert spec.kind is MetricKind.MEASURED


def test_measured_scores_never_emits_non_measured_axes():
    out = measured_scores({"sharpness": 100.0})
    assert all(spec_for(mid).kind is MetricKind.MEASURED for mid, *_ in out)
