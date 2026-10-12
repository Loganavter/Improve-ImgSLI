"""Open-vocabulary axis relevance (plan-gallery-two-domain-axes W1).

Pure: no Qt, no HTTP. Maps a *signal* (free-form tags from a content/AI/user
observation) to a relevance order over axes, and degrades an unmatched
observation to a candidate ``flag-for-review`` — never a fabricated number.

There is deliberately **no closed operation/content enum**: tags are free-form,
and an unknown/complementary tag never *drops* a measured axis from the result
(a measured axis is never hidden — measurement always runs; relevance is only
an ordering/foreground signal).
"""

from __future__ import annotations

from tabs.image_gallery.models import MetricKind
from tabs.image_gallery.services.metric_scores import SPECS

#: Canonical id of the candidate flag an unknown observation degrades to.
FLAG_FOR_REVIEW = "flag-for-review"


def normalize_tag(text) -> str:
    """Lowercase, unify separators, collapse whitespace (tag/token normal form)."""
    try:
        s = str(text or "").strip().lower()
    except Exception:
        return ""
    s = s.replace("_", " ").replace("-", " ")
    return " ".join(s.split())


def _axis_tags(spec) -> set[str]:
    return {normalize_tag(t) for t in (getattr(spec, "tags", ()) or ()) if t}


def relevant_axes(signal_tags=(), *, kind=None) -> list[str]:
    """Axis ids ordered by relevance to *signal_tags* (open vocabulary).

    Order: axes whose tags match the signal, then untagged axes, then the rest.
    **Every** axis of *kind* is returned — a measured axis is never hidden by an
    unknown signal, only re-ordered.
    """
    want = {normalize_tag(t) for t in (signal_tags or ()) if t}
    matched: list[str] = []
    untagged: list[str] = []
    other: list[str] = []
    for spec in SPECS:
        if kind is not None and spec.kind is not kind:
            continue
        tags = _axis_tags(spec)
        if tags and (tags & want):
            matched.append(spec.id)
        elif not tags:
            untagged.append(spec.id)
        else:
            other.append(spec.id)
    return matched + untagged + other


def known_axis(observation) -> str | None:
    """Existing axis id an observation maps to (id / label / tag), else ``None``."""
    obs = normalize_tag(observation)
    if not obs:
        return None
    for spec in SPECS:
        candidates = {normalize_tag(spec.id), normalize_tag(spec.label)} | _axis_tags(spec)
        if obs in candidates:
            return spec.id
    # Containment fallback: the observation phrase contains a label/tag.
    for spec in SPECS:
        for c in ({normalize_tag(spec.label)} | _axis_tags(spec)):
            if c and c in obs:
                return spec.id
    return None


def degrade_unknown(observation) -> str:
    """Observation → existing axis id, or ``FLAG_FOR_REVIEW``.

    An unknown observation becomes a candidate flag (no number) — the honest
    slot for an artifact the registry has no measured axis for.
    """
    return known_axis(observation) or FLAG_FOR_REVIEW


__all__ = [
    "FLAG_FOR_REVIEW",
    "degrade_unknown",
    "known_axis",
    "normalize_tag",
    "relevant_axes",
]
