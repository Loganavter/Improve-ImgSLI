"""The series-derived metric profile — the OFFER (plan-gallery-ai-judgement P5).

P0 gave the profile a name (``services/metric_profile.MetricProfile``) and a
single read seam (``rank_fusion.measured_axes_for``). P1 made the profile
content-aware (``salience_axes`` over the local metrics). P5 closes the offer
side: **the axis set the model is ASKED about comes from the series**.

Before P5 the stored profile was "the mode base ∪ the salient axes", so the
camera base was always part of the offer and the model was asked for white
balance, aesthetic and brisque on a series of ONE picture, where those axes are
constant by construction (the owner's complaint: "why
white balance, why aesthetics — the composition is identical everywhere").
The derivation now delegates to ``metric_profile.profile_for_series``:

    offer = the pool axes whose spread in THIS series clears the local
            instrument's noise floor (+ source-relative axes when a source
            exists), else the mode mapping as the LAST fallback

One offer per **series**, never per image — every member of a batch is asked
about the same axes, because an order over variants is only comparable when one
instrument measured all of them on the same axes (M1).

Deliberately NOT here: the reference/hub deviation and the probe-member ranking
(K most-deviant members) — those live in ``use_cases.profile_probe``. The floor
number is not picked here either: ``quality_read.axis_noise_floor(domain)`` is
the ONE resolver, and the spread itself comes from
``metric_profile.axis_spreads`` (never re-measured).

Pure: no Qt, no HTTP, no I/O, no state mutation. ``active_profile`` only
*reads*; the producer (``controller``) decides when to derive and store.
"""

from __future__ import annotations

import logging

from tabs.image_gallery.services.metric_profile import (
    DOMAIN_AI,
    DOMAIN_ALGORITHMS,
    MEASURED_POOL,
    MetricProfile,
    PROFILE_SOURCE_VLM,
    axis_spreads,
    format_profile,
    mode_id,
    profile_for_mode,
    profile_for_series,
    profile_source_label,
)
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def salience_axes(items) -> tuple[tuple[str, float], ...]:
    """``(axis_id, spread)`` for every pool axis the series can separate.

    ``spread`` is ``max − min`` of the axis' 0–100 score over the items that
    carry the measured value; axes with fewer than two measured values are
    omitted. Ordered by spread descending, ties in registry (pool) order — a
    stable sort over a pool-ordered build, so the result is deterministic and
    independent of input order and dict iteration.

    The measurement itself lives in ``metric_profile.axis_spreads`` over the
    items' metrics — the adaptive-probe summary the VLM selector is shown
    (``use_cases.profile_probe``). The rank's salience (which axis is allowed to
    ORDER these variants, against the producing instrument's noise floor) is
    ``rank_fusion.axis_salience`` over the per-member vectors; the offer
    (``profile_for_series``) decides which axes are asked about at all. Three
    questions, one spread source.
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
    has_reference: bool = False,
    domain=None,
) -> MetricProfile:
    """The series-derived OFFER for *items* (P5) — a pure function of them.

    Reads the ONE spread source (``metric_profile.axis_spreads``) and delegates
    to ``metric_profile.profile_for_series``, so the offer, the floor resolver
    and the eligibility rule (mode tags / a source hub) live in exactly one
    place. *has_reference* says whether the folder has a source hub: without
    one, source-relative axes measure nothing and are not offered.

    The mode mapping is the LAST fallback — used only while the series has no
    discriminating measurement at all, and traced as a fallback by
    ``profile_source_label``. It is never silently merged into the offer: that
    merge is what kept asking the model for constants.
    """
    try:
        spreads = axis_spreads(items)
    except Exception:
        spreads = {}
    return profile_for_series(
        spreads, mode=mode, has_reference=has_reference, domain=domain
    )


def derive_for_state(state, *, domain=None) -> MetricProfile:
    """Series offer for a ``GalleryState``-like object (never raises).

    Reads the folder's items, its mode and whether a source hub exists
    (``state.source_path``). Any missing attribute degrades to the mode mapping
    — the pipeline always gets a usable axis set.
    """
    try:
        mode = getattr(state, "mode", None)
        has_reference = getattr(state, "source_path", None) is not None
        return derive_profile(
            getattr(state, "items", None),
            mode=mode,
            has_reference=has_reference,
            domain=domain,
        )
    except Exception:
        logger.debug("metric profile derivation failed", exc_info=True)
        try:
            return profile_for_mode(getattr(state, "mode", None))
        except Exception:
            return profile_for_mode(None)


def active_profile(
    state=None, *, mode=None, domain: str = DOMAIN_ALGORITHMS
) -> MetricProfile:
    """The profile the UI/analysis must use for *domain* — its own slot, else mode.

    The producer (``controller``) stores the derived offer on
    ``state.algorithms_profile`` and the judge's answer on ``state.ai_profile``;
    consumers call this accessor with the domain they serve, so the dots, the AI
    scorecard, the Jev vector and the rank read the axis set of THEIR backend and
    never the other one's. The read goes through the OWNING ADAPTER (ADR 009 A2:
    ``backends.algorithms`` / ``backends.ai`` own their slot), not through a core
    slot lookup; a foreign-tagged slot is a fail-open fallback here (the UI must
    still paint) and a loud error at the adapter's own seam.

    Without a stored profile for *domain*: the Algorithms accessor returns the
    mode mapping (the LAST local fallback, named as such by ``describe_source``);
    the AI accessor returns an EMPTY judge profile — it never borrows the local
    axis set (owner rule 2026-10-26 / invariant I1).
    """
    try:
        if state is not None:
            from tabs.image_gallery.backends.composition import backend

            cached = backend(str(domain or "").strip().lower()).load_profile(state)
            if isinstance(cached, MetricProfile) and cached:
                # Truthiness, not ``axis_ids``: a VLM answer may name ONLY its own
                # axes (no registry id), and that is a complete profile (P7-A).
                return cached
    except Exception:
        logger.debug(
            "profile slot read failed domain=%s (falling back to the mode mapping)",
            domain,
            exc_info=True,
        )
    if str(domain or "").strip().lower() == DOMAIN_AI:
        # The AI backend has NO mode fallback (invariant I1): the local mode
        # mapping is a locally derived axis set, and letting the judge run on it
        # is exactly the cross-backend borrow this split exists to stop. An
        # empty AI slot is an EMPTY judge profile — the scorecard prompt asks
        # for nothing and the AI path refuses/asks the model; it never silently
        # measures the detectors' axes.
        try:
            if mode is None and state is not None:
                mode = getattr(state, "mode", None)
            return MetricProfile(
                axis_ids=(), mode=mode_id(mode), source=PROFILE_SOURCE_VLM
            )
        except Exception:
            return MetricProfile(source=PROFILE_SOURCE_VLM)
    try:
        if mode is None and state is not None:
            mode = getattr(state, "mode", None)
        return profile_for_mode(mode)
    except Exception:
        return profile_for_mode(None)


def describe(state=None, *, mode=None, domain: str = DOMAIN_ALGORITHMS) -> str:
    """``format_profile(active_profile(...))`` — one line for the log/trace."""
    return format_profile(active_profile(state, mode=mode, domain=domain))


def describe_source(state=None, *, mode=None, domain: str = DOMAIN_ALGORITHMS) -> str:
    """Where the active profile came from: ``series-derived`` / ``judge-vlm`` /
    ``heuristic-<mode> (fallback)`` (P5 precedence, one vocabulary)."""
    return profile_source_label(active_profile(state, mode=mode, domain=domain))


__all__ = [
    "active_profile",
    "derive_for_state",
    "derive_profile",
    "describe",
    "describe_source",
    "salience_axes",
]
