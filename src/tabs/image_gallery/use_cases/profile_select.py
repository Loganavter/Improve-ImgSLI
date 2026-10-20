"""Salience-derived metric profiles — plan P1 (``plan-adaptive-metric-profiles-2026-10-17``).

P0 gave the profile a name (``services/metric_profile.MetricProfile``) and a
single read seam (``rank_fusion.measured_axes_for``). P1 makes the profile
**content-aware**, still without any network call:

    profile = mode base ∪ {axes whose salience in THIS series exceeds a floor}

*Salience* is local and deterministic, read from the metrics the local proxy
pass already wrote into ``item.metrics``: the **spread** (``max − min``) of
the axis' 0–100 quality score across the items that carry a raw value. An
axis carried by fewer than two items has no spread and is omitted — a single
value must never invent a signal.

Only axes from the immutable pool can be added (``MEASURED_POOL``) — a
detector-less or unknown id is dropped, never fabricated. The mode base is
always kept, so a folder with no usable signals reproduces today's behaviour
exactly (fail-open, plan §Fallback).

Deliberately NOT here: the reference/hub deviation and the probe-member
ranking (K most-deviant members). When the hub is one of the compared items
its deviation is bounded by the spread above, so as a *threshold* signal it
is redundant; choosing the reference is plan **P3** ("adaptive K + reference
choice"), where it selects probe members — not axes.

Pure: no Qt, no HTTP, no I/O, no state mutation. ``active_profile`` only
*reads*; the producer (``controller``) decides when to derive and store.

P1 is deliberately per **folder** (like ``state.mode``); per-series contexts
and the VLM selector are P2/P3.
"""

from __future__ import annotations

import logging

from tabs.image_gallery.services.metric_profile import (
    MEASURED_POOL,
    MetricProfile,
    axis_spreads,
    format_profile,
    profile_for_mode,
)

logger = logging.getLogger("ImproveImgSLI")

#: Score spread (0–100 quality points) at which an axis counts as *salient*.
#: 20 = the same "one decisive step in the score space" the fusion already
#: uses for its worst-axis cap (``rank_fusion.RANK_WORST_AXIS_SLACK``), and
#: below the 30-point width of a ``metric_scores.score_band`` — an axis that
#: cannot move an item across a band is not worth a slot in the profile.
DEFAULT_SPREAD_FLOOR: float = 20.0


def salience_axes(items) -> tuple[tuple[str, float], ...]:
    """``(axis_id, spread)`` for every pool axis the series can separate.

    ``spread`` is ``max − min`` of the axis' 0–100 score over the items that
    carry a raw value; axes with fewer than two measured values are omitted.
    Ordered by spread descending, ties in registry (pool) order — a stable
    sort over a pool-ordered build, so the result is deterministic and
    independent of input order and dict iteration.

    The measurement itself lives in ``metric_profile.axis_spreads`` (ONE
    implementation: the P4 domain choice reads the same numbers).
    """
    spreads = axis_spreads(items)
    out = [(axis_id, spreads[axis_id]) for axis_id in MEASURED_POOL if axis_id in spreads]
    # Stable sort: descending spread, ties stay in registry (pool) order.
    out.sort(key=lambda pair: -pair[1])
    return tuple(out)


def derive_profile(
    items,
    *,
    mode=None,
    spread_floor: float = DEFAULT_SPREAD_FLOOR,
) -> MetricProfile:
    """The heuristic profile for *items*: the mode base plus salient axes.

    Pure function of (metric values, mode, floor) — the same inputs always
    produce an equal ``MetricProfile`` (plan §Acceptance). The mode base is
    always included, so nothing that worked before disappears.
    """
    base = profile_for_mode(mode)
    try:
        floor = float(spread_floor)
    except Exception:
        floor = DEFAULT_SPREAD_FLOOR
    salient = tuple(
        axis_id for axis_id, value in salience_axes(items) if value >= floor
    )
    return MetricProfile(
        axis_ids=tuple(base.axis_ids) + salient,
        mode=base.mode,
        source="heuristic",
        salient_axes=salient,
    )


def derive_for_state(state, *, spread_floor: float = DEFAULT_SPREAD_FLOOR) -> MetricProfile:
    """Heuristic profile for a ``GalleryState``-like object (never raises).

    Reads the folder's items and its mode. Any missing attribute degrades to
    the mode mapping — the pipeline always gets a usable axis set.
    """
    try:
        return derive_profile(
            getattr(state, "items", None),
            mode=getattr(state, "mode", None),
            spread_floor=spread_floor,
        )
    except Exception:
        logger.debug("metric profile derivation failed", exc_info=True)
        try:
            return profile_for_mode(getattr(state, "mode", None))
        except Exception:
            return profile_for_mode(None)


def active_profile(state=None, *, mode=None) -> MetricProfile:
    """The profile the UI/analysis must use — the stored one, else the mode base.

    The producer (``controller``) stores the derived profile on the state when
    the folder's mode/metrics settle; consumers call this single accessor, so
    the dots, the AI scorecard, the Jev vector and the rank cannot disagree.
    Without a stored profile this is exactly the pre-P1 mode mapping
    (fail-open) — direct callers that only hold a ``mode`` keep working
    unchanged.
    """
    try:
        cached = getattr(state, "metric_profile", None) if state is not None else None
        if isinstance(cached, MetricProfile) and cached.axis_ids:
            return cached
    except Exception:
        pass
    try:
        if mode is None and state is not None:
            mode = getattr(state, "mode", None)
        return profile_for_mode(mode)
    except Exception:
        return profile_for_mode(None)


def describe(state=None, *, mode=None) -> str:
    """``format_profile(active_profile(...))`` — one line for the log/trace."""
    return format_profile(active_profile(state, mode=mode))


__all__ = [
    "DEFAULT_SPREAD_FLOOR",
    "active_profile",
    "derive_for_state",
    "derive_profile",
    "describe",
    "salience_axes",
]
