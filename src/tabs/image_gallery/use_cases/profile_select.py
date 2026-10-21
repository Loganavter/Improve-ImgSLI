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
    MEASURED_POOL,
    MetricProfile,
    axis_spreads,
    format_profile,
    profile_for_mode,
    profile_for_series,
    profile_source_label,
)

logger = logging.getLogger("ImproveImgSLI")


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


def active_profile(state=None, *, mode=None) -> MetricProfile:
    """The profile the UI/analysis must use — the stored one, else the mode base.

    The producer (``controller``) stores the derived offer on the state when the
    folder's mode/metrics settle; consumers call this single accessor, so the
    dots, the AI scorecard, the Jev vector and the rank cannot disagree.
    Without a stored profile this is exactly the mode mapping (fail-open) — the
    LAST fallback, which ``describe_source`` names as such.
    """
    try:
        cached = getattr(state, "metric_profile", None) if state is not None else None
        if isinstance(cached, MetricProfile) and cached:
            # Truthiness, not ``axis_ids``: a VLM answer may name ONLY its own
            # axes (no registry id), and that is a complete profile (P7-A).
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


def describe_source(state=None, *, mode=None) -> str:
    """Where the active profile came from: ``series-derived`` / ``judge-vlm`` /
    ``heuristic-<mode> (fallback)`` (P5 precedence, one vocabulary)."""
    return profile_source_label(active_profile(state, mode=mode))


__all__ = [
    "active_profile",
    "derive_for_state",
    "derive_profile",
    "describe",
    "describe_source",
    "salience_axes",
]
