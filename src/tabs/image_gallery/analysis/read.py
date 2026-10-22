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

- when the item carries engine records (``item.analysis_records``, written by
  the proxy engine hook — the only path since P9b), those records are the
  answer: an axis without a record is a ``gap`` and is NEVER filled from the
  legacy value — the engine ran and had nothing, which is a different fact from
  "the legacy source has a number" (plan W9);
- otherwise the AI domain's values come from ``quality_read.ai_axis_scores``
  (the VLM scorecard on ``item.analysis``);
- otherwise the Algorithms domain's values come from
  ``quality_read.detector_axis_scores`` (the local detectors on
  ``item.metrics``, via ``metric_scores``);
- artifact severities delegate to ``quality_read.domain_artifact_severities``
  (the defect→artifact mapping is not duplicated here).

Since P7-C the caller may pass the active metric ``profile``: each record then
carries the instrument token the profile's one vocabulary defines
(``measured-locally`` / ``measured-by-judge``), so the axes a model NAMED are
read here like any other axis — same records, same gap reasons — and a surface
can label their provenance without a second axis list.

``backend`` stays ``None`` until the catalog is wired into the producers (W5): a
``BackendRef`` invented at read time would attribute a model that never ran.
"""

from __future__ import annotations

import dataclasses
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

#: Producer id on the gap the reader synthesises when the item HAS engine
#: records but none covers the requested axis. It names the engine, not a
#: backend: no producer ran for that axis, and attributing one that never ran
#: would be the provenance lie ``AxisValue`` exists to prevent.
ENGINE_PRODUCER = "engine"
#: Gap reason for that case — distinct from the legacy per-domain reasons
#: because the cause is different: the engine ran and had nothing for the axis
#: (W9's hard no-fallback rule).
ENGINE_GAP_REASON = "the engine produced no value for this axis"


def _engine_by_axis(item) -> dict[str, AxisValue]:
    """The item's engine records indexed by axis (``{}`` when it has none).

    First record wins: the runner appends each producer in plan order, so a
    duplicate axis keeps the earlier (higher-priority) producer's answer rather
    than letting a later producer silently overwrite it.
    """
    try:
        records = tuple(getattr(item, "analysis_records", ()) or ())
    except Exception:
        return {}
    out: dict[str, AxisValue] = {}
    for record in records:
        axis = str(getattr(record, "axis", "") or "")
        if axis and axis not in out:
            out[axis] = record
    return out


def _engine_records_for_domain(item, domain) -> dict[str, AxisValue]:
    """The engine records that may answer *domain* (empty when none may).

    Records carry their own producer, so the domain no longer decides "whose
    numbers" — but a record still answers only the domain it was produced for:
    a ``vlm`` record answers the AI domain, every other record answers
    Algorithms. Without this split, an engine run of the local policy would
    answer an AI-domain read with detector numbers, which is the substitution
    the whole read path exists to prevent.
    """
    records = _engine_by_axis(item)
    if not records:
        return {}
    if normalize_domain(domain) == AI_DOMAIN:
        return {
            axis: record
            for axis, record in records.items()
            if str(getattr(record, "producer", "")) == AI_PRODUCER
        }
    return {
        axis: record
        for axis, record in records.items()
        if str(getattr(record, "producer", "")) != AI_PRODUCER
    }


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


def _provenance_for(axis: str, *, profile) -> str:
    """The P7-A instrument token for *axis* in *profile* (``""`` = no claim).

    ``services.profile_judged.axis_provenance`` is the ONE definition of the
    two-token vocabulary (``measured-locally`` / ``measured-by-judge``); this
    reader only stamps its answer on the record so a surface never has to
    re-derive it from the axis name (plan-gallery-ai-judgement P7-C: the
    judge's axes reach the ONE read path, with their provenance). No profile
    means the reader cannot say which instrument is authoritative — an empty
    token, never a guess.
    """
    if profile is None:
        return ""
    try:
        from tabs.image_gallery.services.profile_judged import axis_provenance

        return str(axis_provenance(axis, profile=profile) or "")
    except Exception:
        return ""


def _stamped(record: AxisValue, *, axis: str, profile) -> AxisValue:
    """*record* with the reader's provenance token (identity when it cannot say).

    The engine records are frozen and the reader never rewrites a producer's
    value: only the provenance field is added, and only when a profile lets the
    reader name the instrument. Without a profile the record is returned
    verbatim (the engine's own object, provenance intact).
    """
    provenance = _provenance_for(axis, profile=profile)
    if not provenance or str(getattr(record, "provenance", "") or "") == provenance:
        return record
    try:
        return dataclasses.replace(record, provenance=provenance)
    except Exception:
        return record


def read_axes(
    item,
    *,
    domain,
    axes: Iterable[str] | None = None,
    profile=None,
) -> tuple[AxisValue, ...]:
    """One ``AxisValue`` per requested axis, read from *domain* only.

    ``axes=None`` means "the axes the source actually reports", in the source's
    own order. A caller that passes ``axes`` (dots/rows pass the active metric
    profile's full set — registry half plus the axes the judge NAMED) gets
    exactly one record per requested axis, in the requested order, so a surface
    can render its whole axis set without a second lookup.

    ``profile`` (the active ``MetricProfile``) lets the reader stamp each record
    with the P7-A provenance token: ``measured-locally`` for a registry axis a
    detector produces here, ``measured-by-judge`` for an axis the judge named
    (or a registry id this context has no local producer for). That is how the
    judge's own axes arrive on THIS path — as records whose ``axis`` is the
    judge's name and whose ``provenance`` says who measured it — instead of a
    parallel axis list a surface would have to reconcile.

    When the item carries engine records (``analysis_records``, engine-on only
    — the engine is the only path since P9b),
    the records **for this domain** are the source: ``producer="vlm"`` records
    answer the AI domain, every other producer answers Algorithms. A requested
    axis without a record in that domain is a ``gap`` with
    ``ENGINE_GAP_REASON`` — never the legacy value (W9's no-fallback rule), and
    never the other domain's record. A domain with no engine records at all
    falls through to the legacy branch unchanged.

    An axis the source does not answer becomes ``status="gap"`` with a reason
    and ``value=None``. It is never filled from the other domain and never from
    a neighbour: that substitution is the defect this read path removes.
    """
    engine = _engine_records_for_domain(item, domain)
    if engine:
        requested = (
            tuple(str(axis) for axis in axes) if axes is not None else tuple(engine)
        )
        records: list[AxisValue] = []
        for axis in requested:
            record = engine.get(axis)
            if record is None:
                records.append(
                    AxisValue(
                        axis=axis,
                        value=None,
                        producer=ENGINE_PRODUCER,
                        status="gap",
                        reason=ENGINE_GAP_REASON,
                        provenance=_provenance_for(axis, profile=profile),
                    )
                )
                continue
            records.append(_stamped(record, axis=axis, profile=profile))
        return tuple(records)

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
        provenance = _provenance_for(axis, profile=profile)
        value = values.get(axis)
        if value is None:
            records.append(
                AxisValue(
                    axis=axis,
                    value=None,
                    producer=producer,
                    status="gap",
                    reason=gap_reason,
                    provenance=provenance,
                )
            )
            continue
        records.append(
            AxisValue(
                axis=axis, value=value, producer=producer, provenance=provenance
            )
        )
    return tuple(records)


def read_axis(item, *, axis: str, domain, profile=None) -> AxisValue:
    """The record of one axis for *domain* (a gap when it has no value)."""
    return read_axes(item, domain=domain, axes=(axis,), profile=profile)[0]


def read_artifact_severities(item, *, domain) -> dict[str, str]:
    """Artifact id → severity for *domain* (delegates the defect mapping)."""
    return domain_artifact_severities(item, domain=domain)


__all__ = [
    "AI_PRODUCER",
    "AXIS_UNMEASURED_REASON",
    "AXIS_UNSCORED_REASON",
    "ENGINE_GAP_REASON",
    "ENGINE_PRODUCER",
    "LOCAL_PRODUCER",
    "NOT_ANALYZED_REASON",
    "NOT_MEASURED_REASON",
    "read_artifact_severities",
    "read_axes",
    "read_axis",
]

#: ``analysis_source`` tokens — imported instead of literal comparisons so the
#: analysis-engine gate (G10) keeps ONE domain-decision site.
SOURCE_AI = "ai"
SOURCE_LOCAL = "local"


def analysis_source(item) -> str:
    """Who produced this item's report: ``"ai"``, ``"local"`` or ``""``.

    The per-card provenance marker (owner request 2026-10-22): a card can be
    analyzed by the VLM (an ``AiAnalysisResult`` is present) or by the local
    detectors (only ``metrics`` are present). The read path keeps this decision
    here — the UI never reads ``item.metrics``/``item.analysis`` directly
    (``tests/contracts/test_analysis_no_raw_metric_reads.py``).
    """
    try:
        if getattr(item, "analysis", None) is not None:
            return SOURCE_AI
    except Exception:
        pass
    try:
        metrics = getattr(item, "metrics", None)
        if metrics:
            return SOURCE_LOCAL
    except Exception:
        pass
    return ""
