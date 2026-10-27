"""The selector's axis CHOICES — the judge names the axes (plan P7-A).

Split out of ``services/axis_proposal`` (file-size policy, and two rules that only
share a vocabulary): this module classifies the **selector** reply — the 3..8 axes
a vision model names for a whole series — while ``axis_proposal`` owns the
per-image scorecard proposal rule. Both refuse the same way and speak the same
refusal codes.

The owner revision (plan-gallery-ai-judgement §OWNER REVISION 2026-10-22):

    "here are examples of possible axes (you are not obliged to take any of
    these) … determine from 3 to 8 axes in arbitrary form, exclusively the most
    differentiating axes for these pictures"

and its successor (owner rule 2026-10-27, verbatim):

    "we must not decide what is measurable and what is not. If the app said it
    needs such metrics, we draw them, period."

So the pool filter is GONE: an axis the model names is a first-class entry
(``models.AiAxisProposal``: name + label + definition + scale + direction), and
its name does not have to be a ``MEASURED_POOL`` id or an axis the current mode
can measure locally. The FORM of the answer does not decide legality either — a
bare string name and an object ``{name, label, definition, scale, direction}``
are the SAME axis.

What is still refused — STRUCTURE ONLY, with a recorded reason, never silently:

- an unusable / empty NAME (a phrase is not an axis);
- a name repeated inside one reply (the first occurrence wins);
- an unsupported SCALE on an object;
- a pick beyond :data:`AXIS_CHOICE_MAX` (the owner's upper bound).

A DEFINITION is metadata: missing or too short ⇒ the entry is stored with
``definition=""`` and the audit code ``no-definition``
(``axis_proposal.AUDIT_NO_DEFINITION``) is recorded on the choice set. It is
never a refusal and never a reason to drop the axis.

A name that IS a registry id is not a duplicate — it is that registry axis, and
routing it to ``registry_ids`` is what lets a local detector score it too
(provenance ``measured-locally`` vs the free axes' ``measured-by-judge``).

Pure: no Qt, no HTTP, no registry mutation.
"""

from __future__ import annotations

from dataclasses import dataclass

from tabs.image_gallery.models import (
    AXIS_DIRECTION_DEFAULT,
    AiAxisProposal,
)
from tabs.image_gallery.services.axis_proposal import (
    AUDIT_NO_DEFINITION,
    AXIS_PROPOSAL_SCALE,
    REJECT_LIMIT,
    REJECT_NAME,
    REJECT_REPEAT,
    REJECT_SCALE,
    definition_audit,
    direction_of,
    normalize_name,
    scale_of,
    storable_definition,
    storable_label,
)

#: How many axes the SELECTOR may keep (owner rule: "from 3 to 8"). The floor is
#: the instruction, not a parser refusal — a two-axis answer is kept as given (a
#: parser never fabricates a third) and the trace says so.
AXIS_CHOICE_MIN = 3
AXIS_CHOICE_MAX = 8


@dataclass(frozen=True)
class AxisChoiceSet:
    """The selector reply split into what it can become.

    ``registry_ids`` are the axes of the fixed pool the judge named (a local
    detector can produce them; the profile keeps them in ``axis_ids``).
    ``entries`` are the axes the judge NAMED that the pool does not have — each a
    first-class :class:`~tabs.image_gallery.models.AiAxisProposal` with a
    definition, a scale and a direction. ``refusals`` is ``(name, reason)`` for
    every pick that was NOT stored, so the loss is traceable and never silent.
    ``audits`` is ``(name, code)`` for every pick that WAS stored with a gap —
    today only ``no-definition`` (a definition is metadata, not a gate).

    A registry id and an entry are different PROVENANCE, not different quality:
    the first reads "measured locally", the second "measured by the judge".
    """

    registry_ids: tuple[str, ...] = ()
    entries: tuple[AiAxisProposal, ...] = ()
    refusals: tuple[tuple[str, str], ...] = ()
    audits: tuple[tuple[str, str], ...] = ()


def parse_axis_choices(value, *, limit: int = AXIS_CHOICE_MAX) -> AxisChoiceSet:
    """Classify a selector reply's ``axes`` list (never raises).

    Every element may be:

    - a string: a registry axis id, or a free axis NAME. A pool id stays a
      registry id; any other name becomes a first-class entry with
      ``definition=""`` and the ``no-definition`` audit code (a bare name is the
      terse answer shape, and the form must not decide legality);
    - an object: ``{name, label, definition, scale, direction}``. A name equal to a
      registry id is that registry axis (the model asked for a measurable
      dimension that already exists — the local detector should score it too);
      any other name becomes a first-class entry, which is the normal answer of
      the free-form selector. A missing/short definition is audited, not refused.
      ``label`` (the model's short human name) is stored as display text when the
      answer carries one; a reply without it keeps ``label=""`` and the surfaces
      read the name as words.

    The pool filter that used to drop every non-registry name is GONE (owner
    revisions 2026-10-22 and 2026-10-27): a free name is kept.
    """
    try:
        items = list(value or ())
    except Exception:
        return AxisChoiceSet()
    try:
        from tabs.image_gallery.services.metric_profile import MEASURED_POOL

        pool = frozenset(MEASURED_POOL)
    except Exception:
        pool = frozenset()

    registry: list[str] = []
    entries: list[AiAxisProposal] = []
    refusals: list[tuple[str, str]] = []
    audits: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _refuse(row_name: str, reason: str) -> None:
        refusals.append((row_name, reason))

    for index, item in enumerate(items):
        if isinstance(item, str):
            name = normalize_name(item)
            if not name:
                _refuse(item.strip() or f"#{index + 1}", REJECT_NAME)
                continue
            definition = ""
            label = ""
            direction = AXIS_DIRECTION_DEFAULT
        elif isinstance(item, dict):
            raw_name = item.get("name")
            name = normalize_name(raw_name)
            if not name:
                _refuse(str(raw_name or f"#{index + 1}")[:40], REJECT_NAME)
                continue
            raw_definition = str(item.get("definition", "") or "")
            definition = storable_definition(raw_definition)
            # The model's own short human name for the axis (display text, not
            # the key): the row header reads it, the parsers/ranker never do.
            label = storable_label(item.get("label"))
            # The direction follows the model's own words even when the text is
            # too thin to store ("0 = none" is a lower-is-better cue).
            direction = direction_of(item, raw_definition)
            if name not in pool and not scale_of(item.get("scale")):
                _refuse(name, REJECT_SCALE)
                continue
        else:
            _refuse(f"#{index + 1}", REJECT_NAME)
            continue

        if name in seen:
            _refuse(name, REJECT_REPEAT)
            continue
        if name in pool:
            seen.add(name)
            if name not in registry:
                registry.append(name)
            continue
        if len(entries) >= int(limit):
            _refuse(name, REJECT_LIMIT)
            continue
        seen.add(name)
        if definition_audit(definition):
            audits.append((name, AUDIT_NO_DEFINITION))
        entries.append(
            AiAxisProposal(
                name=name,
                definition=definition,
                scale=AXIS_PROPOSAL_SCALE,
                score=-1,  # chosen, not yet read: the scorecard fills the numbers
                direction=direction,
                label=label,
            )
        )
    return AxisChoiceSet(
        registry_ids=tuple(registry),
        entries=tuple(entries),
        refusals=tuple(refusals),
        audits=tuple(audits),
    )


__all__ = [
    "AXIS_CHOICE_MAX",
    "AXIS_CHOICE_MIN",
    "AxisChoiceSet",
    "parse_axis_choices",
]
