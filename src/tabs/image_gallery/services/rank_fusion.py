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

Which axes are "applicable" is NOT decided here: it is the **metric profile**
(``services/metric_profile``) — the mode base plus the salience-derived subset
that ``use_cases/profile_select`` stores on the state (plan P1). This module
delegates (``measured_axes_for``) so ranking, the AI scorecard, the card dots
and the Jev vector read ONE axis set.

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
- **Salience** (plan-gallery-ai-judgement P2 / invariant M3): a series is ranked
  only on axes that *separate* it. ``axis_salience`` measures each axis' spread
  across the series' vectors and marks it ``inside-noise`` when the spread sits
  within the producing instrument's own noise floor (``DETECTOR_NOISE_FLOOR`` for
  the deterministic detectors this module aggregates, ``AXIS_NOISE_FLOOR`` for a
  stochastic judge); such an axis carries no weight here and no score in the Jev
  vector. One rule for both paths (``_inside_noise_axes``), never a second axis
  list — the axis set still comes from ``measured_axes_for``.
- Deterministic: no timestamps, no dict-iteration order, no arrival order;
  ties break by ``str(item.path)``, idempotent under input permutation.
"""

from __future__ import annotations

from tabs.image_gallery.services.metric_profile import (
    EXCLUDED_AXES,
    judged_axis_entries,
    mode_id,
    profile_for_mode,
)
from tabs.image_gallery.services.metric_scores import (
    raw_for,
    score_for,
    spec_for,
)

#: Bump when the fusion semantics change (consumers may pin a cached rank).
#: v1 = the plain mean of applicable measured axes; v2 adds the worst-axis cap;
#: v3 drops the axes whose series spread is inside the judge's noise floor.
RANK_FUSION_VERSION = 3

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

#: The **stochastic** judge's noise floor, in 0–100 score points: the smallest
#: per-axis spread across a series that is distinguishable from a model's own
#: sampling noise. Deliberately the same one-decisive-step the rest of the
#: gallery uses (``RANK_WORST_AXIS_SLACK`` here) and *above* the movement the
#: live VLM showed between two samples of the SAME picture (12–23 points,
#: plan-gallery-ai-judgement J5) — larger than the 2–6-point differences it was
#: asked to rank. So an axis whose spread sits inside this cannot order these
#: variants, and must not pretend to. ONE resolver reads it —
#: ``quality_read.axis_noise_floor("ai")`` — for the VLM scorecard rows/vector
#: and for the offer's floor when the spreads come from the AI domain.
AXIS_NOISE_FLOOR: float = 20.0

#: The **deterministic** detectors' noise floor: same pixels always produce the
#: same number, so the only indistinguishability at a detector is integer
#: quantization — a 0-or-1-point spread. Using the model floor here would drop
#: real differences between two variants the user is comparing (a 5-point
#: sharpness gap is a measurement, not noise). Used for the local-aggregate
#: fusion (``rank_series``) and the Algorithms-domain Jev vector.
DETECTOR_NOISE_FLOOR: float = 1.0

#: ``axis_salience`` verdict vocabulary (plan §Interface — the values are part of
#: the contract: surfaces render the reason from the verdict, never from a second
#: measurement).
DISCRIMINATING = "discriminating"
INSIDE_NOISE = "inside-noise"
SALIENCE_VERDICTS: tuple[str, str] = (DISCRIMINATING, INSIDE_NOISE)

#: Normalized mode id (``services/metric_profile.mode_id`` — single definition,
#: shared with the profile).
_mode_id = mode_id


def measured_axes_for(mode=None, *, profile=None) -> tuple[str, ...]:
    """MEASURED registry axis ids of *profile* / *mode* (registry order).

    ``profile`` (any object with ``.axis_ids``, canonically
    ``metric_profile.MetricProfile``) wins when given — that is how the
    salience-derived subset (plan P1) reaches the rank, the prompt and the
    dots. Without it the mode-implied profile applies
    (``metric_profile.profile_for_mode``): untagged axes everywhere,
    ``reference`` axes in ``fidelity`` only, ``photo`` axes in ``camera``
    only; ``RANK_EXCLUDED_AXES`` and non-MEASURED axes never. An
    unknown/empty *mode* yields the mode-independent (untagged) set.

    The axes the JUDGE named (``profile.axis_entries``) are deliberately NOT
    returned (plan-gallery-ai-judgement P7-A): this resolver is the REGISTRY
    half — the ids a local detector can produce — and the rows/fusion read it to
    show and weight measured numbers. The judge's own axes have no local
    producer; they are read through ``judged_axis_entries`` and labeled
    ``measured-by-judge`` (``metric_profile.axis_provenance``). A profile with
    judge entries and no registry id therefore falls back to the mode mapping
    here (fail-open: the local pipeline always has an axis set), while the
    scorecard prompt asks exactly the judge's axes.
    """
    if profile is not None:
        try:
            axes = tuple(str(a) for a in (profile.axis_ids or ()))
        except Exception:
            axes = ()
        if axes:
            return axes
    return profile_for_mode(mode).axis_ids


def axis_salience(vectors, *, noise_floor) -> dict[str, str]:
    """``{axis: "discriminating" | "inside-noise"}`` for one series.

    ``vectors`` is one ``{axis: 0..100 score}`` mapping per member of the series —
    the shape the fusion builds (:func:`_axis_vector`), the Jev measured vector
    carries (``items[*].scores``) and the Quick Look rows read. For each axis the
    spread is ``max − min`` over the members that carry a value; a spread
    ``<= noise_floor`` is **inside** the instrument's own noise, so that axis
    cannot separate these variants: it must carry no rank weight (``rank_series``
    / ``build_measured_vector``) and must be rendered with that reason instead of
    a bare number (plan-gallery-ai-judgement M3).

    An axis carried by fewer than two members has no measured spread and reports
    ``discriminating``: "cannot be shown to move" is not "does not move", and
    suppressing a real measurement on no evidence is the same lie as fabricating
    one. An unusable *noise_floor* degrades to the stochastic floor (the widest
    one, i.e. fail-open toward measuring). Pure and deterministic (order of
    ``vectors`` is irrelevant; the result is keyed by axis, never by member).
    """
    try:
        floor = float(noise_floor)
    except (TypeError, ValueError):
        floor = AXIS_NOISE_FLOOR
    values: dict[str, list[float]] = {}
    try:
        members = list(vectors or ())
    except Exception:
        members = []
    for vector in members:
        try:
            pairs = dict(vector or {}).items()
        except Exception:
            continue
        for axis, value in pairs:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number != number:  # NaN: not a measurement
                continue
            values.setdefault(str(axis), []).append(number)
    out: dict[str, str] = {}
    for axis, numbers in values.items():
        if len(numbers) < 2:
            out[axis] = DISCRIMINATING
            continue
        out[axis] = (
            INSIDE_NOISE if (max(numbers) - min(numbers)) <= floor else DISCRIMINATING
        )
    return out


def _inside_noise_axes(verdicts) -> frozenset[str]:
    """Axes to suppress as rank weight — or none when nothing separates at all.

    One rule for the fusion and the Jev vector (never two). The exception is
    deliberate: a series whose *every* measured axis is inside the noise floor
    would otherwise have no aggregate and no rank vector, and the order would
    silently degrade to ``str(path)`` (alphabetical) — a fabricated authority
    instead of a measured one. There, suppressing nothing keeps the order
    measured (a tie is still a measurement), while the rows and the vector keep
    saying the axes do not separate the series.
    """
    try:
        inside = {
            str(axis) for axis, verdict in dict(verdicts or {}).items()
            if str(verdict) == INSIDE_NOISE
        }
    except Exception:
        return frozenset()
    if not inside:
        return frozenset()
    try:
        total = len(dict(verdicts or {}))
    except Exception:
        total = 0
    if total and len(inside) >= total:
        return frozenset()
    return frozenset(inside)


def _axis_vector(item, axes) -> dict[str, float]:
    """``{axis: 0..100}`` the item actually carries for *axes* (never fabricated).

    The item's engine record answers for the axes it covers (``status="ok"``,
    ``_record_scores``); when it covers none, the legacy raw ``item.metrics``
    path answers. This is the ONE per-member vector: :func:`item_quality`
    aggregates it and :func:`axis_salience` measures its spread, so "what an axis
    says about this member" has a single definition.
    """
    vector: dict[str, float] = {}
    records = _record_scores(item)
    for axis_id in axes:
        value = records.get(axis_id)
        if value is not None:
            vector[axis_id] = float(value)
    if vector:
        return vector
    metrics = getattr(item, "metrics", None)
    if not isinstance(metrics, dict) or not metrics:
        return {}
    for axis_id in axes:
        spec = spec_for(axis_id)
        if spec is None:
            continue
        got = raw_for(spec, metrics)
        if got is None:
            continue
        _key, raw = got
        vector[axis_id] = float(score_for(spec, raw))
    return vector


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


def item_quality(item, *, mode=None, profile=None, excluded_axes=()) -> float | None:
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

    ``excluded_axes`` is the series' salience verdict (``_inside_noise_axes``):
    those axes carry no weight because they cannot separate these variants.
    Suppression never *erases* a reading — an item whose every value sits on an
    excluded axis keeps them (otherwise it would be re-labelled "unmeasured" and
    dropped out of the order for a reason that is about weights, not scores).

    Applicability is the metric profile (``profile`` when given, else the mode
    mapping — see ``measured_axes_for``). Missing axes are excluded (never
    treated as 0/100) and ``RANK_EXCLUDED_AXES`` is never consulted.
    Deterministic; never fabricates.
    """
    axes = measured_axes_for(mode, profile=profile)
    weights = RANK_AXIS_WEIGHTS.get(_mode_id(mode), {})
    try:
        skip = frozenset(str(axis) for axis in (excluded_axes or ()))
    except Exception:
        skip = frozenset()
    vector = _axis_vector(item, axes)
    if skip:
        kept = {axis: value for axis, value in vector.items() if axis not in skip}
        if kept:
            vector = kept
    weighted: list[tuple[float, float]] = []
    for axis_id, value in vector.items():
        weight = float(weights.get(axis_id, 1.0))
        if weight <= 0.0:
            continue  # a zero/negative weight removes the axis from the aggregate
        weighted.append((value, weight))
    if not weighted:
        return None
    total = sum(weight for _score, weight in weighted)
    mean = sum(score * weight for score, weight in weighted) / total
    worst = min(score for score, _weight in weighted)
    return min(mean, worst + RANK_WORST_AXIS_SLACK)


def rank_series(items, *, mode=None, profile=None, pairwise_order=None) -> dict[str, int]:
    """path -> rank 1..N; measured first by ``(-quality, str(path))``, then
    unmeasured by ``str(path)``. Idempotent under input permutation.

    ``profile`` (metric profile) selects the axes, so the rank can never
    disagree with the dots/prompt about which axes count. The axes whose spread
    across THIS series is inside the judge's noise carry no weight
    (``axis_salience`` + ``_inside_noise_axes``): the callers get an order built
    only from what actually separates the variants.

    ``pairwise_order`` (opt-in, ``use_cases/pairwise_rank``) is an explicit
    ordering of a SUBSET — the series' near-tie top set, derived from complete
    A/B comparisons. Those paths take ranks 1..k in the given order and every
    other measured item follows in the pointwise order; ``None`` (the default,
    and every existing caller) reproduces today's exact ordering. The pairwise
    order never changes which items are measured, never touches the quality
    numbers, and is ignored for a path this series did not measure — a rank
    source, never a second sort.
    """
    members = list(items or ())
    axes = measured_axes_for(mode, profile=profile)
    verdicts = axis_salience(
        [_axis_vector(member, axes) for member in members],
        noise_floor=DETECTOR_NOISE_FLOOR,
    )
    excluded = _inside_noise_axes(verdicts)
    measured: list[tuple[float, str]] = []
    unmeasured: list[str] = []
    for item in members:
        path = str(getattr(item, "path", ""))
        quality = item_quality(
            item, mode=mode, profile=profile, excluded_axes=excluded
        )
        if quality is None:
            unmeasured.append(path)
        else:
            measured.append((quality, path))

    measured.sort(key=lambda pair: (-pair[0], pair[1]))
    unmeasured.sort()

    if pairwise_order:
        quality_by_path = {path: quality for quality, path in measured}
        reordered: list[tuple[float, str]] = []
        used: set[str] = set()
        for path in pairwise_order:
            key = str(path)
            if key in quality_by_path and key not in used:
                reordered.append((quality_by_path[key], key))
                used.add(key)
        reordered.extend(pair for pair in measured if pair[1] not in used)
        measured = reordered

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
    "AXIS_NOISE_FLOOR",
    "DETECTOR_NOISE_FLOOR",
    "DISCRIMINATING",
    "INSIDE_NOISE",
    "RANK_AXIS_WEIGHTS",
    "RANK_EXCLUDED_AXES",
    "RANK_FUSION_VERSION",
    "RANK_WORST_AXIS_SLACK",
    "SALIENCE_VERDICTS",
    "axis_salience",
    "item_quality",
    "measured_axes_for",
    "rank_series",
]
