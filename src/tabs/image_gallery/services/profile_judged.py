"""The JUDGE's own axes: provenance, normalization and the one reader (P7-A).

Split out of ``services/metric_profile`` (file-size policy; one seam per module):
a profile carries two halves and this module owns the second one — the axes a
model NAMED, which no local detector can produce.

- :func:`normalized_entries` is the only way an entry reaches a profile: a name is
  normalized, a missing name/definition is dropped, a name that IS a registry id
  of the same profile is not a second axis, the first occurrence of a name wins.
  Never raises — a junk row is dropped, never stored.
- :func:`judged_axis_entries` is the only READER of that half: the scorecard
  prompt asks for these by name, a surface labels them (never mixes them with a
  detector number in one bar without :func:`axis_provenance`).
- :func:`axis_provenance` answers "which instrument measures this axis here":
  ``measured-locally`` (a registry axis a detector can produce in this context),
  ``measured-by-judge`` (an axis the judge named, or a registry axis this context
  has no producer for) or ``""`` (no claim — never a guess). Plan-gallery-ai-
  judgement P7-A item 6.

The registry half (the pool, the mode mapping, the series offer) stays in
``services/metric_profile``; this module imports it LAZILY inside the one function
that needs it, so there is no import cycle and no second axis list.

Pure: no Qt, no HTTP, no state.
"""

from __future__ import annotations

import dataclasses

from tabs.image_gallery.models import AXIS_DIRECTION_DEFAULT, AiAxisProposal
from tabs.image_gallery.services.axis_proposal import (
    normalize_direction,
    normalize_name,
)

#: Which instrument measures an axis in a given context. Two tokens, never one
#: blended bar (plan-gallery-ai-judgement P7-A item 6): a registry axis a local
#: detector can produce is ``measured-locally``; an axis the judge named (or a
#: registry axis this context has no local producer for) is ``measured-by-judge``.
PROVENANCE_LOCAL = "measured-locally"
PROVENANCE_JUDGE = "measured-by-judge"
AXIS_PROVENANCE: tuple[str, ...] = (PROVENANCE_LOCAL, PROVENANCE_JUDGE)

#: Token → ``(i18n key, English default)`` for a SURFACE that must label the two
#: instruments (plan-gallery-ai-judgement P7-C: the rows/dots never mix them into
#: one indicator without a label). Same vocabulary, one mapping: a surface passes
#: its own translator, so the token itself stays language-free.
PROVENANCE_LABELS: dict[str, tuple[str, str]] = {
    PROVENANCE_LOCAL: (
        "image_gallery.quick_look.axis_measured_locally",
        "measured locally",
    ),
    PROVENANCE_JUDGE: (
        "image_gallery.quick_look.axis_measured_by_judge",
        "measured by the judge",
    ),
}


def provenance_label(provenance, translate=None) -> str:
    """Localized label for a provenance token (``""`` for an empty/unknown one).

    *translate* is the surface's ``translate(key, default)`` callable; without
    one the English default is returned (never a bare token in the UI).
    """
    try:
        token = str(provenance or "").strip()
    except Exception:
        return ""
    pair = PROVENANCE_LABELS.get(token)
    if pair is None:
        return ""
    key, default = pair
    if callable(translate):
        try:
            return str(translate(key, default))
        except Exception:
            pass
    return default


def normalized_entries(entries, registry_ids=()):
    """Judge-named entries, de-duplicated and free of unusable/duplicate rows.

    One rule for every producer of a profile (the selector, a cache read, a test
    double): a name is normalized, a missing name/definition is dropped, a name
    that IS a registry id of this profile (``registry_ids``) is not a second axis,
    and the first occurrence of a name wins. Never raises.
    """
    taken = {str(a) for a in (registry_ids or ())}
    out: list = []
    try:
        rows = list(entries or ())
    except Exception:
        return ()
    for entry in rows:
        try:
            name = normalize_name(getattr(entry, "name", ""))
            definition = str(getattr(entry, "definition", "") or "").strip()
            if not name or not definition or name in taken:
                continue
            if name in {str(getattr(row, "name", "")) for row in out}:
                continue
            direction = normalize_direction(getattr(entry, "direction", "")) or (
                AXIS_DIRECTION_DEFAULT
            )
            try:
                clean = dataclasses.replace(
                    entry, name=name, definition=definition, direction=direction
                )
            except Exception:
                # A duck-typed entry (a test double, a hand-built row) still
                # normalizes — a profile never carries an unusable axis.
                clean = AiAxisProposal(
                    name=name, definition=definition, direction=direction
                )
            out.append(clean)
            taken.add(name)
        except Exception:
            continue
    return tuple(out)


def judged_axis_entries(profile=None) -> tuple:
    """The judge-named axes of *profile* (``()`` when it has none / is ``None``).

    The ONE reader of the judge half: the scorecard prompt asks for these by name,
    and a surface labels them ``measured-by-judge`` (:func:`axis_provenance`). They
    never enter ``measured_axes_for`` — that resolver is the registry half, so the
    local rows/fusion keep reading a pool id they can actually produce.
    """
    try:
        entries = tuple(getattr(profile, "axis_entries", ()) or ())
    except Exception:
        return ()
    return entries


def scorecard_axis_ids(mode=None, *, profile=None) -> tuple[str, ...]:
    """Every axis the scorecard ASKS for — registry half then the judge's.

    The ONE asked-set resolver (P7-A/P7-B): the profile's registry axes
    (``rank_fusion.measured_axes_for``, the mode mapping when no profile is
    given) followed by the axes the judge NAMED for this series, in profile
    order, de-duplicated. A profile carrying ONLY judge axes has no registry set
    to narrow, so the registry half is empty rather than the mode mapping — an
    absent profile (``None``) is the only case that falls back.

    Callers: the scorecard prompt (to ask) and the measured vector (to carry the
    answers), so the question and the payload can never disagree.
    """
    try:
        from tabs.image_gallery.services.rank_fusion import measured_axes_for

        registry: tuple[str, ...] = measured_axes_for(mode, profile=profile)
    except Exception:
        registry = ()
    entries = judged_axis_entries(profile)
    if (
        entries
        and profile is not None
        and not tuple(getattr(profile, "axis_ids", ()) or ())
    ):
        registry = ()
    out: list[str] = []
    for axis in registry:
        name = str(axis)
        if name and name not in out:
            out.append(name)
    for entry in entries:
        name = str(getattr(entry, "name", "") or "").strip()
        if name and name not in out:
            out.append(name)
    return tuple(out)


def axis_provenance(axis, *, mode=None, profile=None) -> str:
    """Which instrument measures *axis* here: ``measured-locally`` / judge / ``""``.

    - an axis the judge NAMED is ``measured-by-judge`` — no local producer exists;
    - a registry id a detector can produce in this mode is ``measured-locally``;
    - a registry id this mode has NO local producer for (a ``reference`` axis in
      a camera folder) is ``measured-by-judge`` when the profile asks for it —
      the model is the only one who can answer it;
    - anything else is ``""`` (no claim can be made — never a guess).
    """
    try:
        name = str(axis or "").strip()
    except Exception:
        return ""
    if not name:
        return ""
    if any(
        str(getattr(entry, "name", "")) == name
        for entry in judged_axis_entries(profile)
    ):
        return PROVENANCE_JUDGE
    # Deferred: ``metric_profile`` imports this module at load time.
    try:
        from tabs.image_gallery.services.metric_profile import (
            MEASURED_POOL,
            profile_for_mode,
        )
    except Exception:
        return ""
    if name not in MEASURED_POOL:
        return ""
    context_mode = mode if mode is not None else getattr(profile, "mode", None)
    try:
        local = set(profile_for_mode(context_mode).axis_ids)
    except Exception:
        local = set()
    if name in local:
        return PROVENANCE_LOCAL
    try:
        asked = name in tuple(getattr(profile, "axis_ids", ()) or ())
    except Exception:
        asked = False
    return PROVENANCE_JUDGE if asked else ""


__all__ = [
    "AXIS_PROVENANCE",
    "PROVENANCE_JUDGE",
    "PROVENANCE_LABELS",
    "PROVENANCE_LOCAL",
    "axis_provenance",
    "judged_axis_entries",
    "normalized_entries",
    "provenance_label",
    "scorecard_axis_ids",
]
