"""The metric profile — which axes apply to a gallery series (P0/P5/P7-A).

A **profile** is the axis set a series is measured and scored on. It has two
halves, and they are different PROVENANCE, not different quality:

- the **registry half** (``axis_ids``): axes of the fixed pool
  (``metric_scores.SPECS``, minus ``EXCLUDED_AXES``). The pool is immutable — only
  the active subset varies — and a local detector can produce every one of them,
  so ``rank_fusion.measured_axes_for`` answers from this half and the local rows,
  the fusion and the Jev vector keep ONE vocabulary. The set the model is ASKED
  about is derived from the SERIES (:func:`profile_for_series`, plan-gallery-ai-
  judgement P5): its measured axes above the producing instrument's noise floor.
  The mode mapping (:func:`profile_for_mode`) is only the LAST fallback — no
  discriminating measurement yet — and says so in the trace
  (:func:`profile_source_label`).
- the **judge half** (``axis_entries``): axes the model NAMED for THIS series,
  each a first-class ``models.AiAxisProposal`` (name + definition + scale +
  direction). No local producer exists for them and none is required — the judge
  measures them (plan-gallery-ai-judgement §OWNER REVISION 2026-10-22: "the judge
  names the axes … from 3 to 8, in free form"), and the intersection with a
  mode's axis set is gone: a free name with a definition is the normal case. The
  half's readers/normalization live in ``services.profile_judged``.

This module stays the single definition of "what the pool is", "which axes a mode
implies" and "what can be offered for a series".

The named metric domains (a manual "pin" that replaced the derived axis set)
were deleted with the stats-strip chip that selected them (owner decision
2026-10-20, ``plan-gallery-analysis-engine-2026-10-20`` §Product decision):
with no pin there is nothing to label, so the domain table, the stats-driven
domain guess and the domain-profile constructor went with it.

Registry rule (moved verbatim out of ``rank_fusion`` — single implementation,
never a second axis list):

- untagged axes (absolute local detectors) — every mode;
- ``reference`` axes (one needs a source hub) — ``fidelity`` only;
- ``photo`` axes (the BRISQUE content gate) — ``camera`` only;
- ``EXCLUDED_AXES`` (grouping artefacts, not quality) and non-MEASURED axes
  are never in the pool.

Pure: no Qt, no HTTP, no state. A registry id outside the pool is *dropped* from
``axis_ids``, never fabricated ("detector-unavailable axes are dropped" — plan
§Target pipeline step 4); a judge-named name outside the pool is an ENTRY, never
a fabricated registry id.

Audit-Meta: pattern=profile-contract size=562 reason="one profile contract: the closed pool, the mode mapping, the two domain slots and the axis-set builders must answer from ONE vocabulary; splitting them would let the AI slot and the Algorithms slot drift apart again (2026-10-26)."
"""

from __future__ import annotations

from dataclasses import dataclass

from tabs.image_gallery.models import MetricKind
from tabs.image_gallery.services.axis_spread import axis_spreads
from tabs.image_gallery.services.metric_scores import SPECS, spec_for
from tabs.image_gallery.services.profile_judged import (
    AXIS_PROVENANCE,
    PROVENANCE_JUDGE,
    PROVENANCE_LOCAL,
    axis_provenance,
    judged_axis_entries,
    normalized_entries,
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
#: ``vlm``        the model's own axis set — registry picks AND/OR axes it named
#:                in free form (P2/P7-A) — the judge's own choice, which wins
#:                over the offer when it arrives;
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

#: The two judgment domains and the ONE state slot each backend owns
#: (backend-isolation invariant I1). A profile is DOMAIN-TAGGED by its provenance:
#: a judge answer (``source="vlm"``) belongs to the AI backend; the series offer
#: and the mode mapping (``source="series"`` | ``"heuristic"``) belong to the
#: Algorithms backend. There is no third tag, so a profile is never unowned — and
#: the heuristic/mode mapping is legal ONLY in ``algorithms_profile``.
DOMAIN_ALGORITHMS = "algorithms"
DOMAIN_AI = "ai"
PROFILE_DOMAINS: tuple[str, ...] = (DOMAIN_ALGORITHMS, DOMAIN_AI)

#: ``GalleryState`` slot names. Read through the OWNING adapter
#: (``backends.algorithms`` / ``backends.ai``; :func:`profile_for_domain` is the
#: deprecated one-line delegate), never as a bare attribute: a stale reader of
#: the deleted single slot fails loudly.
ALGORITHMS_PROFILE_SLOT = "algorithms_profile"
AI_PROFILE_SLOT = "ai_profile"


class ForeignProfileError(ValueError):
    """A slot holds a profile the OTHER backend derived (invariant I1 broken)."""


def domain_of(profile) -> str:
    """The domain a profile belongs to, from its provenance. Never raises.

    ``vlm`` → :data:`DOMAIN_AI`; everything else (``series`` | ``heuristic`` |
    an absent/garbled source) → :data:`DOMAIN_ALGORITHMS`, because the local
    derivation is the only Algorithms producer and a profile with no judge
    provenance carries local axes.
    """
    try:
        source = str(getattr(profile, "source", "") or "").strip().lower()
    except Exception:
        source = ""
    return DOMAIN_AI if source == PROFILE_SOURCE_VLM else DOMAIN_ALGORITHMS


def profile_slot(domain) -> str:
    """The state slot name for *domain*; ``ValueError`` for anything else."""
    dom = str(domain or "").strip().lower()
    if dom == DOMAIN_ALGORITHMS:
        return ALGORITHMS_PROFILE_SLOT
    if dom == DOMAIN_AI:
        return AI_PROFILE_SLOT
    raise ValueError(
        f"unknown profile domain {domain!r}; expected one of {PROFILE_DOMAINS!r}"
    )


def profile_for_domain(state, domain):
    """DEPRECATED — one delegate to the domain's adapter (ADR 009 A2).

    The profile slots used to be a core read seam (this function decided which
    slot a domain reads and how a foreign tag is reported). Ownership now lives
    in the adapters: ``backends.algorithms`` / ``backends.ai`` each read their
    OWN slot, so this name does nothing but ask the owning adapter — the same
    three answers as before (the profile, ``None`` for an empty slot, a loud
    ``ForeignProfileError`` for a slot holding the other backend's profile) and
    ``ValueError`` for an unknown domain.

    The NAME disappears in ADR 009 wave A3 together with the by-domain lookups
    in the controller/use cases; it is kept only so this wave moves ownership
    without rewriting every consumer at once.
    """
    dom = str(domain or "").strip().lower()
    profile_slot(dom)  # ValueError for an unknown domain, before any lookup
    from tabs.image_gallery.backends.composition import backend

    return backend(dom).load_profile(state)


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
#: The selector produced NO profile at all: the AI call the selected backend
#: requires failed (not configured / no transport / transport error / no usable
#: answer). Owner rule 2026-10-26: in the AI backend this is an ERROR — the run
#: must not continue on the local axis set.
PROFILE_REJECT_FAILED = "selector-failed"
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
    ``EXCLUDED_AXES``. This is the *registry* half's vocabulary: an id here has a
    local producer, so ``axis_ids`` is always a subset of it. It is NOT the whole
    judged set any more — the judge may name axes that are not here, and those
    live in ``MetricProfile.axis_entries`` (plan P7-A).
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


@dataclass(frozen=True, eq=True)
class MetricProfile:
    """The axes a series is measured/scored on — registry half + judge half.

    ``axis_ids`` is the REGISTRY half: always pool-filtered, de-duplicated and in
    **registry order** (the dots, the report rows and the fusion mean are
    position-stable; the order carries no ranking intent). ``salient_axes``
    records which axes the series' own measured spread put in the offer (a
    subset of ``axis_ids``), for the trace. ``source`` explains the decision
    (``series`` | ``vlm`` | ``heuristic`` — see :data:`PROFILE_SOURCES` and
    :func:`profile_source_label`); ``mode`` is the normalized mode id.

    ``axis_entries`` is the JUDGE half (plan-gallery-ai-judgement P7-A): the axes
    the model NAMED for this series, each with a definition, a scale and a
    direction. They have no local producer by construction, so
    ``measured_axes_for`` never returns them — the scorecard prompt asks for them
    by name and the judge measures them. They are normalized here (name, non-empty
    definition, no duplicate of a registry id, first occurrence wins) so no caller
    can store an unusable one.

    Hashable and comparable, so a cached profile is trivially equal to a
    freshly derived one (determinism check).
    """

    axis_ids: tuple[str, ...] = ()
    mode: str = ""
    source: str = "heuristic"
    salient_axes: tuple[str, ...] = ()
    #: The judge's own axes — ``models.AiAxisProposal`` entries in profile order.
    axis_entries: tuple = ()

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
        object.__setattr__(
            self, "axis_entries", normalized_entries(self.axis_entries, ordered)
        )

    def __bool__(self) -> bool:
        return bool(self.axis_ids or self.axis_entries)

    def __iter__(self):
        return iter(self.axis_ids)

    def __len__(self) -> int:
        # Every axis the profile carries: the registry half the local detectors
        # read plus the axes the judge named for this series.
        return len(self.axis_ids) + len(self.axis_entries)

    def __contains__(self, axis_id) -> bool:
        try:
            name = str(axis_id)
        except Exception:
            return False
        return name in self.axis_ids or any(
            str(getattr(entry, "name", "")) == name for entry in self.axis_entries
        )


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
    ``judge-vlm`` / ``heuristic-<mode> (fallback)``). The judge's own axes are
    appended as ``judged=<name>~<direction>,…`` so the two halves are never
    confusable in the trace (``REVISION 2026-10-22`` item 6: provenance is a
    label, not a guess). (The old chip tooltip was the other reader; it was
    deleted with the chip — ``use_cases.profile_select.describe`` is the
    remaining caller.)
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
        judged = tuple(getattr(profile, "axis_entries", ()) or ())
        if judged:
            text += " judged=" + ",".join(
                f"{getattr(entry, 'name', '?')}~{getattr(entry, 'direction', '')}"
                for entry in judged
            )
        return text
    except Exception:
        return "axes=- source=heuristic mode=-"


__all__ = [
    "AI_PROFILE_SLOT",
    "ALGORITHMS_PROFILE_SLOT",
    "AXIS_PROVENANCE",
    "DOMAIN_AI",
    "DOMAIN_ALGORITHMS",
    "EXCLUDED_AXES",
    "ForeignProfileError",
    "MEASURED_POOL",
    "MODES",
    "PHOTO_TAG",
    "PROFILE_DOMAINS",
    "PROFILE_REJECT_CALLS_BUILT",
    "PROFILE_REJECT_CODES",
    "PROFILE_REJECT_DOMAIN",
    "PROFILE_REJECT_HOLLOW",
    "PROFILE_REJECT_STALE",
    "PROFILE_SOURCE_FALLBACK",
    "PROFILE_SOURCE_SERIES",
    "PROFILE_SOURCE_VLM",
    "PROFILE_SOURCES",
    "PROVENANCE_JUDGE",
    "PROVENANCE_LOCAL",
    "REFERENCE_TAG",
    "MetricProfile",
    "axis_provenance",
    "axis_spreads",
    "domain_of",
    "format_profile",
    "judged_axis_entries",
    "mode_id",
    "pool_axis_ids",
    "profile_for_domain",
    "profile_for_mode",
    "profile_for_series",
    "profile_slot",
    "profile_source_label",
]
