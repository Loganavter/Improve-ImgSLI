"""Probe selection for the VLM metric-profile selector — plan P2/P3.

Pure, deterministic (no Qt, no HTTP, no state) half of the content-aware
profile: given a folder's items (with the metrics the local proxy pass already
wrote), decide **which** members to send to the model and summarise why.

- :func:`adaptive_k` — how many members to probe: a near-uniform series needs
  only the two extremes, a scattered one needs more. ``K = clamp(2, N,
  2 + round(4 · spread))`` where ``spread`` is the largest per-axis 0–100 score
  spread over 100, so a uniform series probes 2 and a fully scattered one 6.
- :func:`reference_choice` — the source hub when ``reference_path`` resolves to
  a member, else the member farthest from the folder's per-axis median.
- :func:`probe_members` — the K most-deviant members (against the reference
  when there is one, else the median). The reference is *context*, never a
  probe member; each probe image is attached to the salience summary and the
  model picks the applicable axes (``use_cases/profile_ai``).
- :func:`salience_summary` — the compact ``{members, k, axes}`` block sent with
  the images.

Determinism is a hard requirement (plan §Constraints): every function is a pure
function of the metric values and the member set — a permuted input produces an
equal result, and ties break by ``str(path)`` (ascending), so a stable run
never depends on dict/set iteration or list order.

Axis ids in the summary are registry ids: they are the axes a local detector can
also measure, so a model that names one of them lets the app cross-check its
judgement. The summary is *evidence*, never a menu — the selector asks for 3..8
axes in free form and may name axes the pool does not have at all (plan
``plan-gallery-ai-judgement`` §OWNER REVISION 2026-10-22).
"""

from __future__ import annotations

import os

from tabs.image_gallery.services.metric_profile import MEASURED_POOL
from tabs.image_gallery.services.metric_scores import raw_for, score_for, spec_for
from tabs.image_gallery.use_cases.profile_select import salience_axes

#: Baseline probe size — a uniform series sends its two extremes only.
PROBE_BASE_K = 2
#: Spread → extra-probe gain: a fully scattered series adds ``4`` probes.
PROBE_GAIN = 4.0
#: Absolute cap on the probe size (``PROBE_BASE_K + round(PROBE_GAIN·1.0)``).
PROBE_MAX_K = 6
#: Axes kept in the compact salience summary handed to the model.
SALIENCE_TOP_N = 8


def _as_list(items) -> list:
    try:
        return list(items or ())
    except Exception:
        return []


def _path_key(item) -> str:
    try:
        return str(getattr(item, "path", ""))
    except Exception:
        return ""


def _same_path(a, b) -> bool:
    """Path identity that tolerates ``Path`` vs ``str`` and symlinks."""
    try:
        return os.path.realpath(str(a)) == os.path.realpath(str(b))
    except Exception:
        return str(a) == str(b)


def _score_of(item, axis_id: str) -> int | None:
    """The axis' 0–100 quality score for *item*, or None when not measured."""
    spec = spec_for(axis_id)
    if spec is None:
        return None
    try:
        metrics = getattr(item, "metrics", None)
        if not isinstance(metrics, dict) or not metrics:
            return None
        got = raw_for(spec, metrics)
        if got is None:
            return None
        return int(score_for(spec, got[1]))
    except Exception:
        return None


def _resolve_axes(axes) -> tuple[str, ...]:
    """Pool-filtered, de-duplicated axis subset (default: the whole pool)."""
    if axes is None:
        return MEASURED_POOL
    out: list[str] = []
    for axis in axes:
        try:
            axis_id = str(axis)
        except Exception:
            continue
        if axis_id in MEASURED_POOL and axis_id not in out:
            out.append(axis_id)
    return tuple(out)


def _max_spread(items) -> float:
    rows = salience_axes(items)
    return float(rows[0][1]) if rows else 0.0


def adaptive_k(items) -> int:
    """Probe size for *items*: ``2 + round(4·spread)`` clamped to ``[2, N]``.

    ``spread`` is the largest per-axis 0–100 score spread over the series,
    scaled to ``0..1``; a uniform series (spread 0) probes 2, a fully scattered
    one (spread 100) probes :data:`PROBE_MAX_K`. Returns ``len(items)`` when
    fewer than two items exist (nothing to choose between).
    """
    members = _as_list(items)
    n = len(members)
    if n <= 0:
        return 0
    span = max(0.0, min(_max_spread(members), 100.0)) / 100.0
    value = PROBE_BASE_K + int(round(PROBE_GAIN * span))
    value = min(value, PROBE_MAX_K)
    return max(PROBE_BASE_K, min(value, n)) if n >= PROBE_BASE_K else n


def _median(values) -> float | None:
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return float(vals[mid])
    return (float(vals[mid - 1]) + float(vals[mid])) / 2.0


def _medians(members, axes) -> dict[str, float]:
    """Per-axis median score over the members that carry a value for it."""
    out: dict[str, float] = {}
    for axis_id in axes:
        values = [s for s in (_score_of(m, axis_id) for m in members) if s is not None]
        med = _median(values)
        if med is not None:
            out[axis_id] = med
    return out


def _deviation(item, *, reference, medians, axes) -> float:
    """Summed ``|score − baseline|`` over *axes* (reference score or median)."""
    total = 0.0
    for axis_id in axes:
        score = _score_of(item, axis_id)
        if score is None:
            continue
        if reference is not None:
            base = _score_of(reference, axis_id)
        else:
            base = medians.get(axis_id)
        if base is None:
            continue
        total += abs(float(score) - float(base))
    return total


def _resolve_reference(members, reference_path):
    if reference_path is None:
        return None
    for item in members:
        if _same_path(getattr(item, "path", None), reference_path):
            return item
    return None


def reference_choice(items, *, reference_path=None, axes=None):
    """The reference item for *items* — the source hub, else farthest-from-median.

    Returns the member whose path resolves to *reference_path* (the source hub)
    when it is one of *items*; otherwise the member with the largest summed
    deviation from the folder's per-axis median over *axes* (default: every
    pool axis carrying a value). Ties break by ``str(path)`` (ascending).
    ``None`` when there are fewer than two items — a lone member cannot be a
    reference for anybody.
    """
    members = _as_list(items)
    if len(members) < 2:
        return None
    hub = _resolve_reference(members, reference_path)
    if hub is not None:
        return hub
    resolved_axes = _resolve_axes(axes)
    medians = _medians(members, resolved_axes)
    best_item = None
    best_key = None
    for item in members:
        deviation = _deviation(item, reference=None, medians=medians, axes=resolved_axes)
        key = (-deviation, _path_key(item))
        if best_key is None or key < best_key:
            best_key, best_item = key, item
    return best_item


def probe_members(items, *, k=None, reference_path=None, axes=None) -> tuple:
    """The ``k`` most-deviant members, ordered by deviation desc, ties by path.

    Deviation is measured against the reference (the source hub named by
    *reference_path*) when it resolves to a member, else against the folder's
    per-axis median — the reference itself is context, never a probe member.
    ``k`` defaults to :func:`adaptive_k`; when the candidate count is at or
    below ``k`` every candidate is returned. Deterministic under input
    permutation.
    """
    members = _as_list(items)
    if not members:
        return ()
    reference = _resolve_reference(members, reference_path)
    candidates = [m for m in members if m is not reference]
    if not candidates:
        return ()
    try:
        size = int(k) if k is not None else adaptive_k(members)
    except Exception:
        size = adaptive_k(members)
    if size < 1:
        size = 1
    resolved_axes = _resolve_axes(axes)
    if reference is not None:
        medians: dict[str, float] = {}
    else:
        medians = _medians(members, resolved_axes)
    scored = [
        (_deviation(item, reference=reference, medians=medians, axes=resolved_axes), _path_key(item), item)
        for item in candidates
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    return tuple(item for _deviation_value, _path, item in scored[:size])


def salience_summary(items, *, axes=None, top_n=SALIENCE_TOP_N) -> dict:
    """Compact ``{members, k, axes}`` block for the probe request.

    ``axes`` is ``[{"id", "spread"}]`` sorted by spread descending, ties in
    registry (pool) order (``profile_select.salience_axes``), truncated to
    *top_n*. ``k`` is the adaptive probe size for the same series.
    """
    members = _as_list(items)
    rows = salience_axes(members)
    if axes is not None:
        allowed = set(_resolve_axes(axes))
        rows = tuple(row for row in rows if row[0] in allowed)
    try:
        limit = int(top_n)
    except Exception:
        limit = SALIENCE_TOP_N
    if limit >= 0:
        rows = rows[:limit]
    return {
        "members": len(members),
        "k": adaptive_k(members),
        "axes": [{"id": axis_id, "spread": float(spread)} for axis_id, spread in rows],
    }


__all__ = [
    "PROBE_BASE_K",
    "PROBE_GAIN",
    "PROBE_MAX_K",
    "SALIENCE_TOP_N",
    "adaptive_k",
    "probe_members",
    "reference_choice",
    "salience_summary",
]
