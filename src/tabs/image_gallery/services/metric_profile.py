"""The metric profile — which measured axes apply to a gallery series (P0).

A **profile** is a subset of the fixed metric pool (``metric_scores.SPECS``):
the axes a series is measured and scored on. The pool itself is immutable —
only the *active subset* varies — so the local detectors, the VLM scorecard,
the rank fusion, the card dots and the Quick Look rows all speak ONE
vocabulary (``plan-adaptive-metric-profiles-2026-10-17`` §General model).

Today the profile is exactly the mode mapping (``profile_for_mode``); P1
derives it per context from a salience pre-analysis
(``use_cases/profile_select``) — this module stays the single definition of
"what the pool is" and "which axes a mode implies".

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
from tabs.image_gallery.services.metric_scores import SPECS

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


@dataclass(frozen=True, eq=True)
class MetricProfile:
    """The axes a series is measured/scored on — a subset of ``MEASURED_POOL``.

    ``axis_ids`` is always pool-filtered, de-duplicated and in **registry
    order** (the dots, the report rows and the fusion mean are
    position-stable; the order carries no ranking intent). ``salient_axes``
    records which axes the salience pass *added* on top of the mode base, for
    the trace — it is a subset of ``axis_ids``. ``source`` explains the
    decision (``heuristic`` | ``vlm``); ``mode`` is the normalized mode id.

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


def format_profile(profile) -> str:
    """One-line profile summary for a log/trace line (never raises).

    ``"axes=a,b,c source=heuristic mode=camera salient=x"`` — so an odd or
    empty measurement set is explained, not silent (plan §Observability).
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
    "PROFILE_SOURCES",
    "REFERENCE_TAG",
    "MetricProfile",
    "format_profile",
    "mode_id",
    "pool_axis_ids",
    "profile_for_mode",
]
