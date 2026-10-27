"""How the JUDGE's axes are WORDED on a surface (plan-gallery-ai-judgement P7-C).

P7-A let the model NAME the axes, P7-B made the scorecard measure them and the
ranker compare them. This module is the wording half of P7-C: the Quick Look row
and the card dot for an axis the judge named. It owns no measurement and no
second axis list — it reads the two seams that already exist:

- the entry itself (``profile.axis_entries`` via ``profile_judged``), so the row
  shows the judge's OWN wording rather than a registry label;
- ``profile_judged.axis_display_name`` (the ONE reader of "what does a human call
  this axis": the model's ``label``, else the id with ``_`` read as a space);
- ``jev_axes.axis_meaning`` (P7-B's meaning vocabulary), so the row's tooltip and
  the ranker's payload can never describe an axis differently;
- ``profile_judged.axis_provenance`` + ``provenance_label``, so a row/dot says
  which instrument is authoritative instead of blending the two halves.

The HEADER is the human name and nothing else (owner screenshot 2026-10-27: the
row read ``line_crispness — sharpness …``, i.e. a machine id with its meaning cut
to "…"). The definition is the model's own prose, so it belongs in the row
TOOLTIP, where it costs no width. Elision is therefore a pure width decision of
the label, never a character budget.

A REGISTRY axis is not touched here: its row keeps its registry label and its
existing wording byte for byte (the P7-C regression guard).

Pure: no Qt, no HTTP, no state.
"""

from __future__ import annotations

from tabs.image_gallery.services.jev_axes import axis_meaning
from tabs.image_gallery.services.profile_judged import (
    axis_display_name,
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
    """Row HEADER for a judge-named axis: its human name, never the raw id.

    ``label`` from the model when it gave one, else the id read as words
    (line_crispness → line crispness) — ``profile_judged.axis_display_name`` is
    the one place that decides, so every surface words the same axis the same
    way. No definition here: it is prose and it lives in the tooltip
    (:func:`judged_axis_tooltip`). *translate* is accepted for signature
    compatibility with the surfaces that also label provenance.
    """
    return axis_display_name(axis, profile=profile)


def judged_axis_tooltip(axis, *, profile=None, translate=None) -> str:
    """The row's tooltip: the human name, the model's meaning, the provenance.

    ``"Line crispness (line_crispness) — separated hairlines … · measured by the
    judge"``. The id stays visible HERE (and only with a label: without one the
    header already is the id) because a trace/debug reader must be able to tie
    the drawn row back to the stored axis; the definition is the model's own
    prose, which the fixed report column cannot show inline.
    """
    entry = judged_entry(axis, profile=profile)
    name = str(axis or "").strip()
    if entry is not None:
        name = str(getattr(entry, "name", "") or "").strip() or name
    if not name:
        return ""
    display = axis_display_name(name, profile=profile)
    head = f"{display} ({name})" if display and display != name else (display or name)
    meaning = str(axis_meaning(name, profile=profile) or "").strip()
    title = f"{head} — {meaning}" if meaning and meaning not in (name, display) else head
    label = provenance_label(axis_provenance(name, profile=profile), translate)
    return f"{title} · {label}" if label else title


def judged_axis_label(axis, *, profile=None, translate=None) -> str:
    """Short label for a dot/tooltip: ``name · provenance`` (no definition).

    A dot is a glyph, so the definition does not fit there; the hover tooltip
    carries the name and the provenance, and the row carries the human name.
    Semantics unchanged from P7-C (the id, not the label): a dot is a marker, and
    the card's own legend resolves it.
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
    "judged_axis_tooltip",
    "judged_entry",
]
