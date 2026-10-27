"""The JUDGE's own axes: provenance, normalization and the one reader (P7-A).

Split out of ``services/metric_profile`` (file-size policy; one seam per module):
a profile carries two halves and this module owns the second one — the axes a
model NAMED, which no local detector can produce.

- :func:`normalized_entries` is the only way an entry reaches a profile: a name is
  normalized, a missing name is dropped, a name that IS a registry id of the same
  profile is not a second axis, the first occurrence of a name wins. A
  missing/short DEFINITION is kept as ``""`` (metadata, never a gate — owner rule
  2026-10-27). Never raises — a junk row is dropped, never stored.
- :func:`judged_axis_entries` is the only READER of that half: the scorecard
  prompt asks for these by name, a surface labels them (never mixes them with a
  detector number in one bar without :func:`axis_provenance`).
- :func:`axis_display_name` is the only reader of how an axis is WORDED to a
  human: the model's own ``label`` when it gave one, else the id with its
  underscores read as spaces (the header used to be the raw snake_case id plus
  a definition cut to "…" — owner screenshot 2026-10-27).
- :func:`axis_provenance` answers "which instrument measured this axis here":
  with the record's ``producer`` it answers **who DID** (a ``vlm`` number is the
  judge's even on a registry axis, any other producer is a local detector);
  without one it answers **who CAN** — ``measured-locally`` (a registry axis a
  detector can produce in this context), ``measured-by-judge`` (an axis the
  judge named, or a registry axis this context has no producer for) or ``""``
  (no claim — never a guess). Plan-gallery-ai-judgement P7-A item 6; owner rule
  2026-10-27 ("provenance names who measured it").

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
    storable_label,
)

#: Which instrument measures an axis in a given context. Two tokens, never one
#: blended bar (plan-gallery-ai-judgement P7-A item 6): a registry axis a local
#: detector can produce is ``measured-locally``; an axis the judge named (or a
#: registry axis this context has no local producer for) is ``measured-by-judge``.
PROVENANCE_LOCAL = "measured-locally"
PROVENANCE_JUDGE = "measured-by-judge"
AXIS_PROVENANCE: tuple[str, ...] = (PROVENANCE_LOCAL, PROVENANCE_JUDGE)

#: The engine producer id of the model-authored scorecard — ``analysis.read``'s
#: ``AI_PRODUCER``. It is the ONE fact "the judge DID measure this": provenance
#: is read from the record's own producer, never inferred from an axis name
#: (owner rule 2026-10-27 — a judge-scored POOL axis is still the judge's number).
JUDGE_PRODUCER = "vlm"

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
    double): a name is normalized, an unusable NAME is dropped, a name that IS a
    registry id of this profile (``registry_ids``) is not a second axis, and the
    first occurrence of a name wins. Never raises.

    A missing/short DEFINITION is NOT a reason to drop an entry (owner rule
    2026-10-27): the model named the axis, the app draws it, and ``definition=""``
    carries "the model gave none" on the entry itself.

    The ``label`` is trimmed here and NOT normalized: it is display text in the
    model's own language, while ``name`` stays the key.
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
            label = storable_label(getattr(entry, "label", ""))
            if not name or name in taken:
                continue
            if name in {str(getattr(row, "name", "")) for row in out}:
                continue
            direction = normalize_direction(getattr(entry, "direction", "")) or (
                AXIS_DIRECTION_DEFAULT
            )
            try:
                clean = dataclasses.replace(
                    entry,
                    name=name,
                    definition=definition,
                    direction=direction,
                    label=label,
                )
            except Exception:
                # A duck-typed entry (a test double, a hand-built row) still
                # normalizes — a profile never carries an unusable axis.
                clean = AiAxisProposal(
                    name=name, definition=definition, direction=direction, label=label
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


def axis_display_name(axis, *, profile=None) -> str:
    """The human name to draw for *axis*: the model's ``label``, else the id.

    The ONE reader of "what does a human call this axis" (owner screenshot
    2026-10-27: the header was the machine id 'line_crispness' while the model
    had a perfectly good name to give). Order:

    - the ``label`` of the profile's own entry for *axis*, when it carries one
      (trimmed, never normalized — it is the model's words in the UI language);
    - else the axis itself with its underscores read as spaces (detail_gain →
      detail gain), which is also the honest fallback for a pre-label entry or a
      registry id;
    - ``""`` for an empty/unreadable axis.

    Never raises: a surface draws rows from whatever the store holds, and a
    broken profile must not take the panel down.
    """
    try:
        name = str(axis or "").strip()
    except Exception:
        return ""
    if not name:
        return ""
    try:
        for entry in judged_axis_entries(profile):
            if str(getattr(entry, "name", "") or "") != name:
                continue
            label = str(getattr(entry, "label", "") or "").strip()
            if label:
                return label
            break
    except Exception:
        pass
    return name.replace("_", " ")


def scorecard_axis_ids(mode=None, *, profile=None, domain=None) -> tuple[str, ...]:
    """Every axis the scorecard ASKS for — registry half then the judge's.

    The ONE asked-set resolver (P7-A/P7-B): the profile's registry axes
    (``rank_fusion.measured_axes_for``) followed by the axes the judge NAMED for
    this series, in profile order, de-duplicated. The registry half is the
    profile's own ``axis_ids``; a profile carrying ONLY judge axes therefore has
    no registry set to narrow.

    An axis-less profile (an AI slot the judge has not filled) is NOT this
    function's answer any more (ADR 009 A3): ``measured_axes_for`` raises
    ``NoProfileYet`` and it propagates — asking a model to score nothing is the
    defect the empty-profile guard exists for, and a silent ``()`` here would
    hide it one layer deeper. *domain* forwards the caller's judgment domain, so
    an AI-domain caller with NO profile at all gets the same typed refusal
    instead of the local mode mapping (free-axes W4).

    Callers: the scorecard prompt (to ask), the Jev vector (to carry), the card
    dots (to render) and the pairwise payload, so the question and the payload
    can never disagree about which axes exist.
    """
    from tabs.image_gallery.services.rank_fusion import measured_axes_for

    registry: tuple[str, ...] = measured_axes_for(mode, profile=profile, domain=domain)
    entries = judged_axis_entries(profile)
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


def axis_provenance(axis, *, mode=None, profile=None, producer=None) -> str:
    """Which instrument measured *axis* here: ``measured-locally`` / judge / ``""``.

    ``producer`` is the ONE "who DID" answer, and it wins when given: the record
    states which engine producer emitted the number, so a ``vlm`` value is the
    judge's even on a registry axis (a pool axis the model scored is the NORMAL
    case — ``ai_client.parse`` routes a registry pick into ``profile.axis_ids``)
    and any other producer is a local detector. Without it the answer is "who
    CAN", i.e. the ability rule below — a static property of the axis here, not
    a statement about a number that was read.

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
    try:
        did = str(producer or "").strip()
    except Exception:
        did = ""
    if did:
        return PROVENANCE_JUDGE if did == JUDGE_PRODUCER else PROVENANCE_LOCAL
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
    "JUDGE_PRODUCER",
    "PROVENANCE_JUDGE",
    "PROVENANCE_LABELS",
    "PROVENANCE_LOCAL",
    "axis_display_name",
    "axis_provenance",
    "judged_axis_entries",
    "normalized_entries",
    "provenance_label",
    "scorecard_axis_ids",
]
