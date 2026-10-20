"""Per-axis provenance read path — the ONE place "whose numbers" is decided.

Why this module exists (``plan-gallery-analysis-engine-2026-10-20`` §Invariants
I1/I6, defect B6): the read seam used to swap a whole dict per judgment domain,
so "whose number is this" was inferred from a controller field and a missing
axis simply vanished from the dict. Here every axis is a record — value,
producer, status, reason — and a missing axis is a ``gap`` with a human reason
and ``value=None``. ``AxisValue`` itself refuses a gap that carries a value, so
filling a gap from the other domain (or from a neighbouring axis) is
unrepresentable rather than merely discouraged.

The reader is a thin adapter over the existing primitives, never a second
source of numbers:

- the AI domain's values come from ``quality_read.ai_axis_scores`` (the VLM
  scorecard on ``item.analysis``);
- the Algorithms domain's values come from ``quality_read.detector_axis_scores``
  (the local detectors on ``item.metrics``, via ``metric_scores``);
- artifact severities delegate to ``quality_read.domain_artifact_severities``
  (the defect→artifact mapping is not duplicated here).

``backend`` stays ``None`` until the catalog is wired into the producers (W5): a
``BackendRef`` invented at read time would attribute a model that never ran.
"""

from __future__ import annotations

from typing import Iterable

from engine.analysis.contracts import AxisValue

from tabs.image_gallery.services.quality_read import (
    AI_DOMAIN,
    ai_axis_scores,
    detector_axis_scores,
    domain_artifact_severities,
    normalize_domain,
)

#: Producer id of the model-authored scorecard. Registered by W5; the id is
#: part of the record now so a surface never has to infer it from the domain.
AI_PRODUCER = "vlm"
#: Producer id of the local detectors (``metric_scores.SPECS``).
LOCAL_PRODUCER = "local"

#: Gap reasons, one per *cause* rather than one per surface: "the model has not
#: seen this image" and "the model skipped this axis" are different answers to
#: the user's "why is this empty?".
NOT_ANALYZED_REASON = "not analyzed by the model yet"
AXIS_UNSCORED_REASON = "the model did not score this axis"
NOT_MEASURED_REASON = "no local detector has measured this image yet"
AXIS_UNMEASURED_REASON = "no local detector reports this axis"


def _ai_values(item) -> dict[str, float]:
    """The VLM's per-axis scores for *item* (``{}`` when it has none)."""
    return {str(axis): float(score) for axis, score in ai_axis_scores(item).items()}


def _local_values(item) -> dict[str, float]:
    """The local detectors' per-axis scores for *item* (``{}`` when none)."""
    return {
        str(axis): float(score)
        for axis, score in detector_axis_scores(item).items()
    }


def _ai_gap_reason(item) -> str:
    return (
        NOT_ANALYZED_REASON
        if getattr(item, "analysis", None) is None
        else AXIS_UNSCORED_REASON
    )


def _local_gap_reason(item) -> str:
    metrics = getattr(item, "metrics", None)
    return (
        NOT_MEASURED_REASON
        if not isinstance(metrics, dict) or not metrics
        else AXIS_UNMEASURED_REASON
    )


def read_axes(
    item,
    *,
    domain,
    axes: Iterable[str] | None = None,
) -> tuple[AxisValue, ...]:
    """One ``AxisValue`` per requested axis, read from *domain* only.

    ``axes=None`` means "the axes the source actually reports", in the source's
    own order. A caller that passes ``axes`` (dots/rows pass the active metric
    profile) gets exactly one record per requested axis, in the requested order,
    so a surface can render its whole axis set without a second lookup.

    An axis the domain does not answer becomes ``status="gap"`` with a reason and
    ``value=None``. It is never filled from the other domain and never from a
    neighbour: that substitution is the defect this read path removes.
    """
    dom = normalize_domain(domain)
    if dom == AI_DOMAIN:
        values = _ai_values(item)
        producer = AI_PRODUCER
        gap_reason = _ai_gap_reason(item)
    else:
        values = _local_values(item)
        producer = LOCAL_PRODUCER
        gap_reason = _local_gap_reason(item)

    requested = (
        tuple(str(axis) for axis in axes) if axes is not None else tuple(values)
    )
    records: list[AxisValue] = []
    for axis in requested:
        value = values.get(axis)
        if value is None:
            records.append(
                AxisValue(
                    axis=axis,
                    value=None,
                    producer=producer,
                    status="gap",
                    reason=gap_reason,
                )
            )
            continue
        records.append(AxisValue(axis=axis, value=value, producer=producer))
    return tuple(records)


def read_axis(item, *, axis: str, domain) -> AxisValue:
    """The record of one axis for *domain* (a gap when it has no value)."""
    return read_axes(item, domain=domain, axes=(axis,))[0]


def read_artifact_severities(item, *, domain) -> dict[str, str]:
    """Artifact id → severity for *domain* (delegates the defect mapping)."""
    return domain_artifact_severities(item, domain=domain)


__all__ = [
    "AI_PRODUCER",
    "AXIS_UNMEASURED_REASON",
    "AXIS_UNSCORED_REASON",
    "LOCAL_PRODUCER",
    "NOT_ANALYZED_REASON",
    "NOT_MEASURED_REASON",
    "read_artifact_severities",
    "read_axes",
    "read_axis",
]
