"""Deterministic rank fusion over the MEASURED gallery axes (plan R0).

Replaces the HSV-centroid "typicality" order with an explicit, measured
decision: an item's quality is the mean of the quality scores of every
applicable MEASURED axis (``metric_scores``), and a series is ranked by
``(-quality, str(path))`` with unmeasured items sorted last by path.

Pure: no Qt, no HTTP, no PIL — numbers in, ranks out. The module reads the
registry (``spec_for`` / ``raw_for`` / ``score_for``); it never re-derives
thresholds and never fabricates a value for a missing axis. When an item
carries engine records (``item.analysis_records``, engine-on only — the
default since P9a), those already-scored 0–100 values are the answer and the
registry is consulted only on the legacy branch (``_record_scores``).

Which axes are "applicable" is NOT decided here any more: it is the
**metric profile** (``services/metric_profile``) — the mode mapping today,
the salience-derived subset per plan P1 (``plan-adaptive-metric-profiles-
2026-10-17``). This module delegates (``measured_axes_for``) so ranking, the
AI scorecard, the card dots and the Jev vector read ONE axis set.

Design rules (see ``plan-gallery-rank-backends-2026-10-15`` §Seam):

- Only ``MetricKind.MEASURED`` axes contribute; ``RANK_EXCLUDED_AXES`` never
  does (``typicality`` is a grouping artefact, not a quality signal).
- An axis with no raw value (and no engine record) is *excluded* from the mean
  — never counted as 0/100. An item with no measured axis is *unranked*
  (``None``) and sorts after every measured item.
- The aggregate is a **weighted** mean (``RANK_AXIS_WEIGHTS``; neutral ``1.0``
  by default), then capped by the weakest participating axis
  (``RANK_WORST_AXIS_SLACK``): a single catastrophic axis cannot be averaged
  away by otherwise-strong ones.
- Deterministic: no timestamps, no dict-iteration order, no arrival order;
  ties break by ``str(item.path)``, idempotent under input permutation.
"""

from __future__ import annotations

from tabs.image_gallery.services.metric_profile import (
    EXCLUDED_AXES,
    mode_id,
    profile_for_mode,
)
from tabs.image_gallery.services.metric_scores import (
    raw_for,
    score_for,
    spec_for,
)

#: Bump when the fusion semantics change (consumers may pin a cached rank).
#: v1 = the plain mean of applicable measured axes; v2 adds the worst-axis cap.
RANK_FUSION_VERSION = 2

#: Axis ids that must NEVER contribute to a rank (grouping artefacts, not
#: quality). Single definition for the whole tree — import, never redefine.
RANK_EXCLUDED_AXES = EXCLUDED_AXES

#: Worst-axis cap: the aggregate may not exceed the item's single weakest
#: measured axis by more than this margin, so one catastrophic axis (e.g. total
#: clipping) cannot be averaged away by otherwise-strong axes. A deterministic
#: rule that needs no real-series calibration.
RANK_WORST_AXIS_SLACK = 20.0

#: Per-mode axis weights for the fusion mean: ``{mode: {axis_id: weight}}``.
#: A missing mode or axis is weight ``1.0`` (neutral), so an empty table
#: reproduces the unweighted baseline exactly. A weight ``<= 0`` removes that
#: axis from the aggregate (mean AND cap). The mechanism lives here so that
#: real-series calibration is a *data* edit, not a code change — the plan
#: (§Open questions) deliberately does not invent weights before that
#: measurement.
RANK_AXIS_WEIGHTS: dict[str, dict[str, float]] = {}

#: Normalized mode id (``services/metric_profile.mode_id`` — single definition,
#: shared with the profile).
_mode_id = mode_id


def measured_axes_for(mode=None, *, profile=None) -> tuple[str, ...]:
    """MEASURED axis ids applicable to *profile* / *mode* (registry order).

    ``profile`` (any object with ``.axis_ids``, canonically
    ``metric_profile.MetricProfile``) wins when given — that is how the
    salience-derived subset (plan P1) reaches the rank, the prompt and the
    dots. Without it the mode-implied profile applies
    (``metric_profile.profile_for_mode``): untagged axes everywhere,
    ``reference`` axes in ``fidelity`` only, ``photo`` axes in ``camera``
    only; ``RANK_EXCLUDED_AXES`` and non-MEASURED axes never. An
    unknown/empty *mode* yields the mode-independent (untagged) set.
    """
    if profile is not None:
        try:
            axes = tuple(str(a) for a in (profile.axis_ids or ()))
        except Exception:
            axes = ()
        if axes:
            return axes
    return profile_for_mode(mode).axis_ids


def _records_of(item) -> tuple:
    """The item's engine records as a tuple (``()`` when it has none)."""
    try:
        return tuple(getattr(item, "analysis_records", ()) or ())
    except Exception:
        return ()


def _record_axes(item) -> frozenset[str]:
    """Axis ids the item has a record for, whatever its status (``gap`` included).

    ``axis_spreads`` needs "a record exists and says no number" to be different
    from "no record at all": the first excludes the item from that axis' spread,
    the second may still use the legacy raw path.
    """
    return frozenset(
        axis
        for axis in (
            str(getattr(record, "axis", "") or "") for record in _records_of(item)
        )
        if axis
    )


def _record_scores(item) -> dict[str, float]:
    """``{axis: 0..100 score}`` from the item's engine records (``{}`` if none).

    Only ``status="ok"`` records contribute: a ``gap``/``error`` is "no number"
    (``AxisValue`` forbids a value there), and ``echo``/``stale`` are not an
    independent measurement — ranking either would be the provenance lie
    ``engine/analysis/contracts`` exists to prevent. First record wins per axis,
    exactly like the read path (``analysis/read._engine_by_axis``): the runner
    appends producers in plan order, so an earlier producer's answer must not be
    overwritten by a later one. Values are already scored by the producer, so no
    registry lookup happens here (``spec_for`` is legacy-only).
    """
    out: dict[str, float] = {}
    seen: set[str] = set()
    for record in _records_of(item):
        axis = str(getattr(record, "axis", "") or "")
        if not axis or axis in seen:
            continue
        seen.add(axis)
        if str(getattr(record, "status", "")) != "ok":
            continue
        value = getattr(record, "value", None)
        if value is None:
            continue
        try:
            out[axis] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def item_quality(item, *, mode=None, profile=None) -> float | None:
    """0..100 aggregate over applicable MEASURED axes; None when nothing measured.

    The **weighted** mean over every applicable axis that has a value — an
    engine record (``item.analysis_records``, its 0–100 score used directly)
    when the item has one, else ``score_for`` over the raw ``item.metrics``
    value (weights from ``RANK_AXIS_WEIGHTS``, neutral ``1.0`` by default; a
    weight ``<= 0`` drops the axis), then capped by the weakest participating
    axis (``RANK_WORST_AXIS_SLACK``): ``min(mean, worst + slack)`` so a single
    catastrophic axis is not averaged away.

    Records win for the axes they cover and only for those: when at least one
    applicable axis has an ``ok`` record, the records are the answer and an axis
    without a record is *excluded* — never 0 and never the legacy raw value
    (the engine ran and had nothing, which is a different fact). An item whose
    records cover no applicable axis falls back to the legacy raw path
    unchanged, so an item the engine could not measure (producer failure, no records)
    keeps today's exact numbers.

    Applicability is the metric profile (``profile`` when given, else the mode
    mapping — see ``measured_axes_for``). Missing axes are excluded (never
    treated as 0/100) and ``RANK_EXCLUDED_AXES`` is never consulted.
    Deterministic; never fabricates.
    """
    axes = measured_axes_for(mode, profile=profile)
    weights = RANK_AXIS_WEIGHTS.get(_mode_id(mode), {})
    records = _record_scores(item)
    weighted: list[tuple[float, float]] = []
    from_records = False
    for axis_id in axes:
        value = records.get(axis_id)
        if value is None:
            continue
        from_records = True
        weight = float(weights.get(axis_id, 1.0))
        if weight <= 0.0:
            continue  # a zero/negative weight removes the axis from the aggregate
        weighted.append((value, weight))
    if not from_records:
        metrics = getattr(item, "metrics", None)
        if not isinstance(metrics, dict) or not metrics:
            return None
        for axis_id in axes:
            spec = spec_for(axis_id)
            if spec is None:
                continue
            got = raw_for(spec, metrics)
            if got is None:
                continue
            weight = float(weights.get(axis_id, 1.0))
            if weight <= 0.0:
                continue  # a zero/negative weight removes the axis from the aggregate
            _key, raw = got
            weighted.append((score_for(spec, raw), weight))
    if not weighted:
        return None
    total = sum(weight for _score, weight in weighted)
    mean = sum(score * weight for score, weight in weighted) / total
    worst = min(score for score, _weight in weighted)
    return min(mean, worst + RANK_WORST_AXIS_SLACK)


def rank_series(items, *, mode=None, profile=None) -> dict[str, int]:
    """path -> rank 1..N; measured first by ``(-quality, str(path))``, then
    unmeasured by ``str(path)``. Idempotent under input permutation.

    ``profile`` (metric profile) selects the axes, so the rank can never
    disagree with the dots/prompt about which axes count.
    """
    measured: list[tuple[float, str]] = []
    unmeasured: list[str] = []
    for item in items or ():
        path = str(getattr(item, "path", ""))
        quality = item_quality(item, mode=mode, profile=profile)
        if quality is None:
            unmeasured.append(path)
        else:
            measured.append((quality, path))

    measured.sort(key=lambda pair: (-pair[0], pair[1]))
    unmeasured.sort()

    ranks: dict[str, int] = {}
    rank = 1
    for _quality, path in measured:
        ranks[path] = rank
        rank += 1
    for path in unmeasured:
        ranks[path] = rank
        rank += 1
    return ranks


__all__ = [
    "RANK_AXIS_WEIGHTS",
    "RANK_EXCLUDED_AXES",
    "RANK_FUSION_VERSION",
    "RANK_WORST_AXIS_SLACK",
    "item_quality",
    "measured_axes_for",
    "rank_series",
]
