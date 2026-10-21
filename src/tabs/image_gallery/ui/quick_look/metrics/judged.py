"""How the JUDGE's axes are WORDED on a surface (plan-gallery-ai-judgement P7-C).

P7-A let the model NAME the axes, P7-B made the scorecard measure them and the
ranker compare them. This module is the wording half of P7-C: the Quick Look row
and the card dot for an axis the judge named. It owns no measurement and no
second axis list — it reads the two seams that already exist:

- the entry itself (``profile.axis_entries`` via ``profile_judged``), so the row
  shows the judge's OWN name and its definition rather than a registry label;
- ``jev_axes.axis_meaning`` / ``axis_direction`` (P7-B's meaning/direction
  vocabulary), so the row and the ranker's payload can never describe an axis
  differently;
- ``profile_judged.axis_provenance`` + ``provenance_label``, so a row/dot says
  which instrument is authoritative instead of blending the two halves.

A REGISTRY axis is not touched here: its row keeps its registry label and its
existing wording byte for byte (the P7-C regression guard). Only a name the
judge invented gets the ``name — meaning · provenance`` shape, and only that
shape is elided (its length is the model's, not the design's).

Pure: no Qt, no HTTP, no state.
"""

from __future__ import annotations

from tabs.image_gallery.services.jev_axes import axis_meaning
from tabs.image_gallery.services.profile_judged import (
    axis_provenance,
    judged_axis_entries,
    provenance_label,
)


def judged_entry(axis, profile=None):
    """The judge's entry for *axis* (``None`` when this profile did not name it)."""
    try:
        name = str(axis or "").strip()
    except Exception:
        return None
    if not name:
        return None
    for entry in judged_axis_entries(profile):
        if str(getattr(entry, "name", "") or "") == name:
            return entry
    return None


def is_judged_axis(axis, profile=None) -> bool:
    """True when *axis* is a name the JUDGE invented for this series."""
    return judged_entry(axis, profile=profile) is not None


def judged_axis_title(axis, *, profile=None, translate=None) -> str:
    """Row title for a judge-named axis: ``name — meaning · provenance``.

    The name is the judge's own wording (never a localized registry label: no
    translation key can exist for a word the model invented); the meaning is the
    definition it gave, which is what makes the axis measurable. The provenance
    suffix is the localized P7-A token, so the registry and judge halves are
    never mixed into one unlabeled indicator.
    """
    entry = judged_entry(axis, profile=profile)
    name = str(getattr(entry, "name", "") or axis or "").strip()
    if not name:
        return ""
    meaning = str(axis_meaning(name, profile=profile) or "").strip()
    title = f"{name} — {meaning}" if meaning and meaning != name else name
    label = provenance_label(axis_provenance(name, profile=profile), translate)
    return f"{title} · {label}" if label else title


def judged_axis_label(axis, *, profile=None, translate=None) -> str:
    """Short label for a dot/tooltip: ``name · provenance`` (no definition).

    A dot is a glyph, so the definition does not fit there; the hover tooltip
    carries the name and the provenance, and the row carries the meaning.
    """
    entry = judged_entry(axis, profile=profile)
    name = str(getattr(entry, "name", "") or axis or "").strip()
    if not name:
        return ""
    label = provenance_label(axis_provenance(name, profile=profile), translate)
    return f"{name} · {label}" if label else name


__all__ = [
    "is_judged_axis",
    "judged_axis_label",
    "judged_axis_title",
    "judged_entry",
]
