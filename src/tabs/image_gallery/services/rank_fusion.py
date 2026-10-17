"""Deterministic rank fusion over the MEASURED gallery axes (plan R0).

Replaces the HSV-centroid "typicality" order with an explicit, measured
decision: an item's quality is the mean of the quality scores of every
applicable MEASURED axis (``metric_scores``), and a series is ranked by
``(-quality, str(path))`` with unmeasured items sorted last by path.

Pure: no Qt, no HTTP, no PIL — numbers in, ranks out. The module reads the
registry (``spec_for`` / ``raw_for`` / ``score_for``); it never re-derives
thresholds and never fabricates a value for a missing axis.

Which axes are "applicable" is NOT decided here any more: it is the
**metric profile** (``services/metric_profile``) — the mode mapping today,
the salience-derived subset per plan P1 (``plan-adaptive-metric-profiles-
2026-10-17``). This module delegates (``measured_axes_for``) so ranking, the
AI scorecard, the card dots and the Jev vector read ONE axis set.

Design rules (see ``plan-gallery-rank-backends-2026-10-15`` §Seam):

- Only ``MetricKind.MEASURED`` axes contribute; ``RANK_EXCLUDED_AXES`` never
  does (``typicality`` is a grouping artefact, not a quality signal).
- An axis with no raw value is *excluded* from the mean — never counted as
  0/100. An item with no measured axis is *unranked* (``None``) and sorts
  after every measured item.
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


def item_quality(item, *, mode=None, profile=None) -> float | None:
    """0..100 aggregate over applicable MEASURED axes; None when nothing measured.

    The **weighted** mean of ``score_for`` over every applicable axis that has a
    raw value in ``item.metrics`` (weights from ``RANK_AXIS_WEIGHTS``, neutral
    ``1.0`` by default; a weight ``<= 0`` drops the axis), then capped by the
    weakest participating axis (``RANK_WORST_AXIS_SLACK``):
    ``min(mean, worst + slack)`` so a single catastrophic axis is not averaged
    away. Applicability is the metric profile (``profile`` when given, else
    the mode mapping — see ``measured_axes_for``). Missing axes are excluded
    (never treated as 0/100) and ``RANK_EXCLUDED_AXES`` is never consulted.
    Deterministic; never fabricates.
    """
    metrics = getattr(item, "metrics", None)
    if not isinstance(metrics, dict) or not metrics:
        return None
    weights = RANK_AXIS_WEIGHTS.get(_mode_id(mode), {})
    weighted: list[tuple[int, float]] = []
    for axis_id in measured_axes_for(mode, profile=profile):
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
