"""The metric profile — which measured axes apply to a gallery series (P0).

A **profile** is a subset of the fixed metric pool (``metric_scores.SPECS``):
the axes a series is measured and scored on. The pool itself is immutable —
only the *active subset* varies — so the local detectors, the VLM scorecard,
the rank fusion, the card dots and the Quick Look rows all speak ONE
vocabulary (``plan-adaptive-metric-profiles-2026-10-17`` §General model).

The profile the model is ASKED about is derived from the SERIES
(:func:`profile_for_series`, plan-gallery-ai-judgement P5, stored on
``state.metric_profile`` by ``controller.refresh_metric_profile``): the pool
axes whose spread in THIS series the local metrics pass measured above the
instrument's own noise floor. The mode mapping (:func:`profile_for_mode`) is
only the LAST fallback — no discriminating measurement yet — and says so in
the trace (:func:`profile_source_label`); it is never a second axis list.

This module stays the single definition of "what the pool is", "which axes a
mode implies" and "what can be offered for a series".

The named metric domains (a manual "pin" that replaced the derived axis set)
were deleted with the stats-strip chip that selected them (owner decision
2026-10-20, ``plan-gallery-analysis-engine-2026-10-20`` §Product decision):
with no pin there is nothing to label, so the domain table, the stats-driven
domain guess and the domain-profile constructor went with it.

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

#: Where a profile came from:
#:
#: ``series``     the SERIES-DERIVED offer (``profile_for_series``): the pool
#:                axes whose spread in this series the local metrics pass
#:                measured above the producing instrument's noise floor — the
#:                set the model is asked to score (plan-gallery-ai-judgement
#:                P5);
#: ``vlm``        a model-chosen subset of the pool (P2) — the judge's own
#:                choice, which wins over the offer when it arrives;
#: ``heuristic``  the mode mapping — the LAST fallback, used only while the
#:                series has no discriminating measurement at all (or after a
#:                failed derivation), and named as a fallback by
#:                :func:`profile_source_label` so it is never mistaken for a
#:                measured offer.
#:
#: Anything else is coerced to ``heuristic`` (fail-open: a profile is always
#: describable).
PROFILE_SOURCE_SERIES = "series"
PROFILE_SOURCE_VLM = "vlm"
PROFILE_SOURCE_FALLBACK = "heuristic"
PROFILE_SOURCES: tuple[str, ...] = (
    PROFILE_SOURCE_SERIES,
    PROFILE_SOURCE_VLM,
    PROFILE_SOURCE_FALLBACK,
)

#: Why a VLM axis-set answer was NOT applied to the folder generation
#: (``GalleryState.profile_reject_reason``, plan-gallery-ai-judgement P2/M5:
#: "every loss is a visible state with a cause"). Codes, never prose — a surface
#: localizes them, so the reason survives a language switch.
#:
#: ``calls-built``      an AI request of this generation was already built under
#:                      the previous axis set, and the profile is part of that
#:                      request's cache identity (the freeze the plan keeps);
#: ``domain-algorithms`` the Algorithms domain owns the profile derivation;
#: ``stale-generation`` the folder changed while the selector was in flight;
#: ``hollow-answer``    the reply named no usable pool axis (heuristic kept).
PROFILE_REJECT_CALLS_BUILT = "calls-built"
PROFILE_REJECT_DOMAIN = "domain-algorithms"
PROFILE_REJECT_STALE = "stale-generation"
PROFILE_REJECT_HOLLOW = "hollow-answer"
PROFILE_REJECT_CODES: tuple[str, ...] = (
    PROFILE_REJECT_CALLS_BUILT,
    PROFILE_REJECT_DOMAIN,
    PROFILE_REJECT_STALE,
    PROFILE_REJECT_HOLLOW,
)


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


def axis_spreads(items) -> dict[str, float]:
    """``{axis_id: spread}`` for every pool axis the series can separate.

    ``spread`` is ``max − min`` of the axis' 0–100 quality score over the items
    that carry a value; axes with fewer than two measured values are omitted (a
    single value must never invent a signal). Registry (pool) order.

    A value for an axis is the item's engine record (``analysis_records``,
    ``status="ok"``) when the item has a record for that axis, else the legacy
    ``raw_for`` → ``score_for`` score. The record is already 0–100, so it is used
    as-is. A record that is not ``ok`` (``gap``/``error``) **excludes** the item
    from that axis — never 0, and never backfilled from ``item.metrics`` (the
    engine ran and had nothing, which is a different fact).

    The ONE spread over ITEM metrics, TWO named readers and no third:
    the P5 offer (:func:`profile_for_series` — "which axes can separate THIS
    series", i.e. what the model is asked about, and through
    ``profile_select.salience_axes`` the adaptive-probe summary) reads it to
    decide which axes are offered at all. It is NOT the rank's salience
    measurement: the rank / Jev vector asks a different question — "does this
    axis separate these variants under the producing INSTRUMENT's noise floor" —
    over the per-member vectors, and that answer lives in
    ``rank_fusion.axis_salience``.
    """
    # Deferred import: ``rank_fusion`` imports this module at load time, so a
    # module-level import would be circular. One reader of the records
    # (``rank_fusion._record_scores`` / ``_record_axes``) — never a second one.
    from tabs.image_gallery.services.rank_fusion import _record_axes, _record_scores

    try:
        members = list(items or ())
    except Exception:
        members = []
    if len(members) < 2:
        return {}
    record_maps: list[tuple[dict[str, float], frozenset[str]]] = []
    for item in members:
        try:
            record_maps.append((_record_scores(item), _record_axes(item)))
        except Exception:
            record_maps.append(({}, frozenset()))
    out: dict[str, float] = {}
    for axis_id in MEASURED_POOL:
        spec = spec_for(axis_id)
        if spec is None:
            continue
        values: list[int] = []
        for item, (record_scores, recorded_axes) in zip(members, record_maps):
            try:
                if axis_id in recorded_axes:
                    record_value = record_scores.get(axis_id)
                    if record_value is not None:
                        values.append(int(record_value))
                    continue  # a gap/error record excludes the item for this axis
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


@dataclass(frozen=True, eq=True)
class MetricProfile:
    """The axes a series is measured/scored on — a subset of ``MEASURED_POOL``.

    ``axis_ids`` is always pool-filtered, de-duplicated and in **registry
    order** (the dots, the report rows and the fusion mean are
    position-stable; the order carries no ranking intent). ``salient_axes``
    records which axes the series' own measured spread put in the offer (a
    subset of ``axis_ids``), for the trace. ``source`` explains the decision
    (``series`` | ``vlm`` | ``heuristic`` — see :data:`PROFILE_SOURCES` and
    :func:`profile_source_label`); ``mode`` is the normalized mode id.

    Hashable and comparable, so a cached profile is trivially equal to a
    freshly derived one (determinism check).
    """

    axis_ids: tuple[str, ...] = ()
    mode: str = ""
    source: str = "heuristic"
    salient_axes: tuple[str, ...] = ()

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
        object.__setattr__(
            self,
            "source",
            source if source in PROFILE_SOURCES else PROFILE_SOURCE_FALLBACK,
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


def profile_for_series(
    spreads,
    *,
    mode=None,
    has_reference: bool = False,
    domain=None,
) -> MetricProfile:
    """The OFFER for one series: the axes that can separate THESE variants (P5).

    The **third** question about the pool, named so it cannot be confused with
    the two that already exist:

    * ``metric_profile.axis_spreads`` — "which axes did the local metrics pass
      measure at all" (the raw spread source this function *consumes*);
    * ``rank_fusion.axis_salience`` — "may this axis carry weight in the ORDER
      under the producing instrument's noise" (measured over the per-member
      vectors the fusion already builds);
    * **this function** — "which axes are worth ASKING the model about for this
      series" (the offer). It reuses the spread source (``spreads`` is
      ``axis_spreads(items)``, passed in so this module stays free of item
      shapes) and the ONE floor resolver
      (``quality_read.axis_noise_floor(domain)``); it never re-measures a
      spread and never picks a floor number of its own.

    Why it exists (plan-gallery-ai-judgement J4 / §P5): the mode mapping asks
    the model for white balance, aesthetic and brisque on a series of ONE
    picture, where those axes are constant by construction, so the answer is a
    number that ranks nothing. An axis whose measured spread in
    this series is inside the instrument's noise floor cannot separate the
    variants and is therefore **not offered** — not merely hidden later.

    Rules (one offer per SERIES, never per image):

    - the axis must be eligible for *mode*: untagged axes always, ``photo``
      axes in ``camera`` only, ``reference`` axes only when *has_reference*
      (a source hub exists — without one a source-relative axis measures
      nothing);
    - an axis with a measured spread ``<= axis_noise_floor(domain)`` is not
      offered; the floor belongs to the instrument that produced the spreads,
      so *domain* defaults to the Algorithms domain (the local metrics pass);
    - an axis with NO measured spread is not offered either: nothing measured
      says it can separate these variants, and offering it is exactly the
      constant-axis complaint. A source-relative axis therefore appears when a
      source exists AND the local pass measured it with a real spread (SSIM and
      the source deltas are computed then; LPIPS/DISTS only when their optional
      backend ran);
    - no discriminating measurement at all (empty *spreads*, or every measured
      axis inside the floor) → the mode mapping, marked ``source=heuristic``
      (:func:`profile_source_label` names it a fallback). The mode mapping is
      the LAST fallback: no measurements yet, never a substitute for a series
      that has them.

    Pure and deterministic: registry (pool) order, input-permutation invariant,
    never fabricates an axis outside ``MEASURED_POOL``. Garbage input degrades
    to the fallback rather than raising.
    """
    try:
        from tabs.image_gallery.services.quality_read import axis_noise_floor

        floor = float(axis_noise_floor(domain))
    except Exception:
        floor = 0.0
    mid = mode_id(mode)
    try:
        measured = {
            str(axis): float(value)
            for axis, value in dict(spreads or {}).items()
            if value is not None
        }
    except Exception:
        measured = {}
    offered: list[str] = []
    salient: list[str] = []
    for axis_id in MEASURED_POOL:
        spec = spec_for(axis_id)
        if spec is None:
            continue
        tags = _tags_of(spec)
        is_reference = REFERENCE_TAG in tags
        if is_reference and not has_reference:
            continue
        if PHOTO_TAG in tags and mid != "camera":
            continue
        if axis_id not in measured:
            # No measured spread = nothing shows it can separate these variants.
            # "Not measured locally" is not "does not move", but the offer is a
            # claim about THIS series; an axis nobody measured has no evidence
            # behind it, and offering it is how the constant-axis complaint got
            # in (the model is then asked to score what the variants share).
            continue
        try:
            inside = measured[axis_id] <= floor
        except Exception:
            inside = True
        if inside:
            continue  # cannot separate this series — never offered
        offered.append(axis_id)
        salient.append(axis_id)
    if not offered:
        return profile_for_mode(mode)
    return MetricProfile(
        axis_ids=tuple(offered),
        mode=mid,
        source=PROFILE_SOURCE_SERIES,
        salient_axes=tuple(salient),
    )


def profile_source_label(profile) -> str:
    """Where the offered axis set came from, in the trace's own words (P5).

    ``"series-derived"`` — the series' measured spreads chose the axes;
    ``"judge-vlm"`` — the model's own choice (P2/P3) won;
    ``"heuristic-<mode> (fallback)"`` — the mode mapping, i.e. the LAST
    fallback, visible as such so a fallback offer is never read as a
    measurement. Never raises.
    """
    try:
        source = str(getattr(profile, "source", "") or "").strip().lower()
    except Exception:
        source = ""
    if source == PROFILE_SOURCE_VLM:
        return "judge-vlm"
    if source == PROFILE_SOURCE_SERIES:
        return "series-derived"
    try:
        mode = str(getattr(profile, "mode", "") or "")
    except Exception:
        mode = ""
    return f"heuristic-{mode} (fallback)" if mode else "heuristic (fallback)"


def format_profile(profile) -> str:
    """One-line profile summary for a log/trace line.

    ``"axes=a,b,c source=series mode=camera salient=x"`` — so an odd or empty
    measurement set is explained, not silent (plan §Observability). ``salient``
    is appended only when set. ``source`` is the raw code; the trace names where
    the offer came from with :func:`profile_source_label` (``series-derived`` /
    ``judge-vlm`` / ``heuristic-<mode> (fallback)``). (The old chip tooltip was
    the other reader; it was deleted with the chip —
    ``use_cases.profile_select.describe`` is the remaining caller.)
    """
    try:
        axes = ",".join(str(a) for a in (getattr(profile, "axis_ids", ()) or ()))
        text = (
            f"axes={axes or '-'} "
            f"source={getattr(profile, 'source', 'heuristic') or 'heuristic'} "
            f"mode={getattr(profile, 'mode', '') or '-'}"
        )
        salient = tuple(getattr(profile, "salient_axes", ()) or ())
        if salient:
            text += " salient=" + ",".join(str(a) for a in salient)
        return text
    except Exception:
        return "axes=- source=heuristic mode=-"


__all__ = [
    "EXCLUDED_AXES",
    "MEASURED_POOL",
    "MODES",
    "PHOTO_TAG",
    "PROFILE_REJECT_CALLS_BUILT",
    "PROFILE_REJECT_CODES",
    "PROFILE_REJECT_DOMAIN",
    "PROFILE_REJECT_HOLLOW",
    "PROFILE_REJECT_STALE",
    "PROFILE_SOURCE_FALLBACK",
    "PROFILE_SOURCE_SERIES",
    "PROFILE_SOURCE_VLM",
    "PROFILE_SOURCES",
    "REFERENCE_TAG",
    "MetricProfile",
    "axis_spreads",
    "format_profile",
    "mode_id",
    "pool_axis_ids",
    "profile_for_mode",
    "profile_for_series",
    "profile_source_label",
]
