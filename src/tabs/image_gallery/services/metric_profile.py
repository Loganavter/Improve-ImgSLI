"""The metric profile — which measured axes apply to a gallery series (P0).

A **profile** is a subset of the fixed metric pool (``metric_scores.SPECS``):
the axes a series is measured and scored on. The pool itself is immutable —
only the *active subset* varies — so the local detectors, the VLM scorecard,
the rank fusion, the card dots and the Quick Look rows all speak ONE
vocabulary (``plan-adaptive-metric-profiles-2026-10-17`` §General model).

Today the profile is exactly the mode mapping (``profile_for_mode``); P1
derives it per context from a salience pre-analysis
(``use_cases/profile_select``) — this module stays the single definition of
"what the pool is" and "which axes a mode implies". P4 adds **named domains**
(``DOMAINS`` / ``DOMAIN_WEIGHTS``): a domain is another *named profile over the
same pool*, chosen manually (the stats-strip chip) or suggested from the
measured spreads (``domain_for_stats``). ``profile_for_domain`` reuses
``profile_for_mode`` for the auto case — the profile type is never forked.

Rule (moved verbatim out of ``rank_fusion`` — single implementation, never a
second axis list):

- untagged axes (absolute local detectors) — every mode;
- ``reference`` axes (one needs a source hub) — ``fidelity`` only;
- ``photo`` axes (the BRISQUE content gate) — ``camera`` only;
- ``EXCLUDED_AXES`` (grouping artefacts, not quality) and non-MEASURED axes
  are never in the pool.

Pure: no Qt, no HTTP, no state. An axis id outside the pool is *dropped*,
never fabricated ("detector-unavailable axes are dropped" — plan §Target
pipeline step 4).
"""

from __future__ import annotations

from dataclasses import dataclass

from tabs.image_gallery.models import MetricKind
from tabs.image_gallery.services.metric_scores import (
    SPECS,
    raw_for,
    score_for,
    spec_for,
)

#: Registry tags that scope an axis to a content situation. Single definition
#: (``rank_fusion`` re-exports the axis/tag rule through this module).
REFERENCE_TAG = "reference"
PHOTO_TAG = "photo"

#: Axis ids that must NEVER be part of a profile or contribute to a rank
#: (grouping artefacts, not quality signals). Re-exported by ``rank_fusion``
#: as ``RANK_EXCLUDED_AXES`` — import, never redefine.
EXCLUDED_AXES: tuple[str, ...] = ("typicality",)

#: The mode ids a profile understands (``models.Mode`` values).
MODES: tuple[str, ...] = ("fidelity", "camera", "batch_synthetic")

#: Where a profile came from. ``heuristic`` = the deterministic derivation
#: (mode mapping ∪ salience, P1); ``vlm`` = a model-chosen subset of the pool
#: (P2). Anything else is coerced to ``heuristic`` (fail-open: a profile is
#: always describable).
PROFILE_SOURCES: tuple[str, ...] = ("heuristic", "vlm")

#: The named domains a metric profile can be pinned to (P4, plan §"Domains
#: beyond the three modes"). A domain is a *named profile over the measured
#: pool* — not a new pool and not a second detector vocabulary. ``auto`` is
#: not a domain: it means "derive it again" (mode mapping ∪ salience), so it is
#: normalized to ``""`` by :func:`domain_id`.
DOMAINS: tuple[str, ...] = ("document", "photo", "synthetic", "mixed")

#: The domain an un-overridden (auto) profile belongs to, per mode. This is the
#: fallback when the measured stats cannot tell the domains apart; it keeps the
#: chip's domain label truthful instead of guessing a domain from noise.
DOMAIN_FOR_MODE: dict[str, str] = {
    "fidelity": "document",
    "camera": "photo",
    "batch_synthetic": "synthetic",
}


def mode_id(mode) -> str:
    """Normalize a ``Mode`` / str / None to one of ``MODES`` (or ``""``)."""
    value = getattr(mode, "value", mode)
    try:
        text = str(value or "").strip().lower()
    except Exception:
        return ""
    return text if text in MODES else ""


def _tags_of(spec) -> set[str]:
    try:
        return {str(t).strip().lower() for t in (spec.tags or ()) if t}
    except Exception:
        return set()


def pool_axis_ids() -> tuple[str, ...]:
    """Every MEASURED axis a profile may select, in registry (report) order.

    Derived from the registry — never a second hand-written list — minus
    ``EXCLUDED_AXES``. This is the *closed vocabulary* the plan freezes: a
    profile is always a subset of it.
    """
    out: list[str] = []
    for spec in SPECS:
        if spec.kind is not MetricKind.MEASURED:
            continue
        if spec.id in EXCLUDED_AXES:
            continue
        out.append(spec.id)
    return tuple(out)


#: Materialized pool (registry order, de-duplicated by construction).
MEASURED_POOL: tuple[str, ...] = pool_axis_ids()

#: The axis weights each domain implies, over the MEASURED pool (P4). Weights
#: are a *relative importance* within a domain — used for (a) the domain's axis
#: subset (every listed axis is in its profile) and (b) the stats-driven
#: domain choice (``domain_for_stats`` = highest weighted mean spread). ``mixed``
#: is the whole pool at one weight: it never wins by affinity directly (see
#: ``MIXED_MARGIN``), it is the answer when no specific domain dominates.
DOMAIN_WEIGHTS: dict[str, dict[str, float]] = {
    "document": {
        "sharpness": 1.0,
        "exposure": 0.9,
        "clipping": 0.8,
        "noise": 0.6,
        "white_balance": 0.7,
        "detail_gain": 0.7,
    },
    "photo": {
        "sharpness": 1.0,
        "exposure": 1.0,
        "clipping": 0.8,
        "noise": 0.9,
        "white_balance": 1.0,
        "aesthetic": 0.6,
        "brisque": 1.0,
        "detail_gain": 0.6,
    },
    # Generative content: the source-relative perceptual axes are where an
    # invented texture / over-smoothing shows up (they drop when no hub exists,
    # exactly like the mode mapping's reference axes).
    "synthetic": {
        "sharpness": 0.6,
        "noise": 0.5,
        "color_accuracy": 0.5,
        "aesthetic": 0.9,
        "lpips": 0.9,
        "dists": 0.9,
        "ssim": 0.8,
        "halo_delta": 0.7,
        "chroma_fringe_delta": 0.6,
    },
    # Broad content: every measured axis equally. Its affinity is never the
    # winner directly (see ``MIXED_MARGIN``) — ``mixed`` is the answer when no
    # specific domain dominates, and its profile is the widest subset.
    "mixed": {axis_id: 1.0 for axis_id in MEASURED_POOL},
}


def axis_spreads(items) -> dict[str, float]:
    """``{axis_id: spread}`` for every pool axis the series can separate.

    ``spread`` is ``max − min`` of the axis' 0–100 quality score over the items
    that carry a raw value; axes with fewer than two measured values are
    omitted (a single value must never invent a signal). Registry (pool) order.
    The ONE spread implementation: the P1 salience pass and the P4 domain
    choice both read it, so they cannot disagree about what "moves".
    """
    try:
        members = list(items or ())
    except Exception:
        members = []
    if len(members) < 2:
        return {}
    out: dict[str, float] = {}
    for axis_id in MEASURED_POOL:
        spec = spec_for(axis_id)
        if spec is None:
            continue
        values: list[int] = []
        for item in members:
            try:
                metrics = getattr(item, "metrics", None)
                if not isinstance(metrics, dict) or not metrics:
                    continue
                got = raw_for(spec, metrics)
                if got is None:
                    continue
                _key, raw = got
                values.append(int(score_for(spec, raw)))
            except Exception:
                continue
        if len(values) >= 2:
            out[axis_id] = float(max(values) - min(values))
    return out


def domain_id(value) -> str:
    """Normalize a domain / str / None to one of ``DOMAINS`` (or ``""``).

    ``""`` is the *auto* marker (also returned for unknown values): the profile
    is derived from the mode/measured stats instead of being pinned.
    """
    text = getattr(value, "value", value)
    try:
        text = str(text or "").strip().lower()
    except Exception:
        return ""
    return text if text in DOMAINS else ""


def domain_for_mode(mode=None) -> str:
    """The domain an un-overridden profile of *mode* belongs to (fallback)."""
    return DOMAIN_FOR_MODE.get(mode_id(mode), "mixed")


def _affinity(weights: dict[str, float], spreads: dict[str, float]) -> float:
    """Weighted mean spread of a domain's axes (0 when nothing moved)."""
    total = 0.0
    for weight in weights.values():
        try:
            total += float(weight)
        except Exception:
            continue
    if total <= 0:
        return 0.0
    weighted = 0.0
    for axis_id, weight in weights.items():
        try:
            weighted += float(weight) * float(spreads.get(axis_id, 0.0) or 0.0)
        except Exception:
            continue
    return weighted / total


#: Relative affinity margin that still counts as a tie. When the two best
#: specific domains are within this fraction of each other, the stats support
#: several domains about equally → ``mixed`` (broad content), not a coin flip
#: decided by table order.
MIXED_MARGIN: float = 0.15


def domain_for_stats(items=None, *, mode=None, spreads=None) -> str:
    """Pick the named domain the measured stats point at (never raises).

    Each domain's affinity is the weighted mean of its axes' 0–100 spreads
    (``axis_spreads``) — a domain wins when *its* characteristic axes are the
    ones that actually separate the series. When the two best domains are
    within ``MIXED_MARGIN`` of each other the signal is not specific to either,
    so the answer is ``mixed`` (broad content) instead of a table-order coin
    flip. No measured spread at all → the mode's domain (``domain_for_mode``),
    so the label is always answerable (fail-open).
    """
    if spreads is None:
        try:
            spreads = axis_spreads(items)
        except Exception:
            spreads = {}
    try:
        spread_map = {str(k): float(v) for k, v in dict(spreads).items()}
    except Exception:
        spread_map = {}
    ranked: list[tuple[str, float]] = []
    # Fixed DOMAINS order (most specific first) → deterministic tie order.
    for domain in DOMAINS:
        if domain == "mixed":
            continue
        ranked.append((domain, _affinity(DOMAIN_WEIGHTS.get(domain, {}), spread_map)))
    if not ranked:
        return domain_for_mode(mode)
    best_domain, best_score = ranked[0]
    second_score = 0.0
    for domain, score in ranked[1:]:
        if score > best_score:
            second_score = best_score
            best_domain, best_score = domain, score
        elif score > second_score:
            second_score = score
    if best_score <= 0.0:
        return domain_for_mode(mode)
    if second_score > 0.0 and second_score >= best_score * (1.0 - MIXED_MARGIN):
        return "mixed"
    return best_domain



@dataclass(frozen=True, eq=True)
class MetricProfile:
    """The axes a series is measured/scored on — a subset of ``MEASURED_POOL``.

    ``axis_ids`` is always pool-filtered, de-duplicated and in **registry
    order** (the dots, the report rows and the fusion mean are
    position-stable; the order carries no ranking intent). ``salient_axes``
    records which axes the salience pass *added* on top of the mode base, for
    the trace — it is a subset of ``axis_ids``. ``source`` explains the
    decision (``heuristic`` | ``vlm``); ``mode`` is the normalized mode id;
    ``domain`` is the explicit named domain this profile was pinned to (P4),
    or ``""`` when it came from the mode/auto derivation.

    Hashable and comparable, so a cached profile is trivially equal to a
    freshly derived one (determinism check).
    """

    axis_ids: tuple[str, ...] = ()
    mode: str = ""
    source: str = "heuristic"
    salient_axes: tuple[str, ...] = ()
    domain: str = ""

    def __post_init__(self) -> None:
        wanted = set()
        try:
            wanted = {str(a) for a in (self.axis_ids or ())}
        except Exception:
            wanted = set()
        ordered = tuple(a for a in MEASURED_POOL if a in wanted)
        try:
            salient = {str(a) for a in (self.salient_axes or ())}
        except Exception:
            salient = set()
        salient_ordered = tuple(a for a in ordered if a in salient)
        source = str(self.source or "").strip().lower()
        object.__setattr__(self, "axis_ids", ordered)
        object.__setattr__(self, "salient_axes", salient_ordered)
        object.__setattr__(self, "mode", mode_id(self.mode))
        object.__setattr__(self, "domain", domain_id(self.domain))
        object.__setattr__(
            self, "source", source if source in PROFILE_SOURCES else "heuristic"
        )

    def __bool__(self) -> bool:
        return bool(self.axis_ids)

    def __iter__(self):
        return iter(self.axis_ids)

    def __len__(self) -> int:
        return len(self.axis_ids)

    def __contains__(self, axis_id) -> bool:
        try:
            return str(axis_id) in self.axis_ids
        except Exception:
            return False


def profile_for_mode(mode=None) -> MetricProfile:
    """The mode-implied profile (the pre-P1 mapping — today's behaviour).

    The single definition of the mode→axes rule; ``rank_fusion`` delegates
    here so ranking, the AI scorecard, the dots and the Jev vector can never
    disagree about which axes a mode implies. An unknown/empty *mode* yields
    the mode-independent (untagged) set, since no source or photographic
    content can be asserted for it.
    """
    mid = mode_id(mode)
    has_source = mid == "fidelity"
    is_photo = mid == "camera"
    axis_ids: list[str] = []
    for spec in SPECS:
        if spec.kind is not MetricKind.MEASURED:
            continue
        if spec.id in EXCLUDED_AXES:
            continue
        tags = _tags_of(spec)
        if REFERENCE_TAG in tags and not has_source:
            continue
        if PHOTO_TAG in tags and not is_photo:
            continue
        axis_ids.append(spec.id)
    return MetricProfile(axis_ids=tuple(axis_ids), mode=mid, source="heuristic")


def profile_for_domain(domain, pool=None, *, mode=None) -> MetricProfile:
    """The concrete profile of a named domain (P4), over the measured pool.

    Reuses ``profile_for_mode`` for the *auto* case (``""``/``"auto"``/unknown)
    — a domain profile is the same ``MetricProfile`` type, never a fork. The
    domain's axis subset comes from ``DOMAIN_WEIGHTS`` (weights are the domain's
    relative priorities; the profile's axis set is every listed axis) filtered
    to *pool* when given (the plan's "unavailable axes are dropped") and then
    to ``MEASURED_POOL`` + registry order by the value object itself. An empty
    *pool* therefore yields an empty (falsy) profile — consumers fall back to
    the mode mapping, as with any unusable profile.
    """
    dom = domain_id(domain)
    if not dom:
        return profile_for_mode(mode)
    allowed = set(MEASURED_POOL)
    try:
        if pool is not None:
            allowed &= {str(axis) for axis in pool}
    except Exception:
        pass
    axis_ids = tuple(a for a in DOMAIN_WEIGHTS.get(dom, {}) if a in allowed)
    if not axis_ids:
        # Nothing of the domain survives the pool → not a usable profile;
        # consumers fall back to the mode mapping (same rule as any empty
        # profile), and the domain label must not claim otherwise.
        return profile_for_mode(mode)
    return MetricProfile(
        axis_ids=axis_ids,
        mode=mode_id(mode),
        source="heuristic",
        domain=dom,
    )



def format_profile(profile) -> str:
    """One-line profile summary for a log/trace line or the chip tooltip.

    ``"axes=a,b,c source=heuristic mode=camera domain=photo salient=x"`` — so
    an odd or empty measurement set is explained, not silent (plan
    §Observability). ``domain`` and ``salient`` are appended only when set.
    """
    try:
        axes = ",".join(str(a) for a in (getattr(profile, "axis_ids", ()) or ()))
        text = (
            f"axes={axes or '-'} "
            f"source={getattr(profile, 'source', 'heuristic') or 'heuristic'} "
            f"mode={getattr(profile, 'mode', '') or '-'}"
        )
        domain = str(getattr(profile, "domain", "") or "")
        if domain:
            text += f" domain={domain}"
        salient = tuple(getattr(profile, "salient_axes", ()) or ())
        if salient:
            text += " salient=" + ",".join(str(a) for a in salient)
        return text
    except Exception:
        return "axes=- source=heuristic mode=-"


__all__ = [
    "DOMAIN_FOR_MODE",
    "DOMAIN_WEIGHTS",
    "DOMAINS",
    "EXCLUDED_AXES",
    "MEASURED_POOL",
    "MIXED_MARGIN",
    "MODES",
    "PHOTO_TAG",
    "PROFILE_SOURCES",
    "REFERENCE_TAG",
    "MetricProfile",
    "axis_spreads",
    "domain_for_mode",
    "domain_for_stats",
    "domain_id",
    "format_profile",
    "mode_id",
    "pool_axis_ids",
    "profile_for_domain",
    "profile_for_mode",
]
