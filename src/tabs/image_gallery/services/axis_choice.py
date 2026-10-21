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

So the pool filter is GONE: an axis the model names is a first-class entry
(``models.AiAxisProposal``: name + definition + scale + direction), and its name
does not have to be a ``MEASURED_POOL`` id or an axis the current mode can
measure locally. What is still refused — with a recorded reason, never silently —
is a pick that is not MEASURABLE:

- an unusable / empty NAME (a phrase is not an axis);
- a bare name with no DEFINITION (nothing to score, and the app will not invent
  a meaning for it);
- a name repeated inside one reply (the first occurrence wins);
- a pick beyond :data:`AXIS_CHOICE_MAX` (the owner's upper bound).

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
    AXIS_PROPOSAL_SCALE,
    REJECT_DEFINITION,
    REJECT_LIMIT,
    REJECT_NAME,
    REJECT_REPEAT,
    REJECT_SCALE,
    direction_of,
    normalize_name,
    scale_of,
)

#: How many axes the SELECTOR may keep (owner rule: "from 3 to 8"). The floor is
#: the instruction, not a parser refusal — a two-axis answer is kept as given (a
#: parser never fabricates a third) and the trace says so.
AXIS_CHOICE_MIN = 3
AXIS_CHOICE_MAX = 8


def _definition_missing(definition: str) -> bool:
    """True when *definition* says nothing at all (the SELECTOR-level rule).

    The selector's rule is the owner's: a free name WITH a definition is the
    normal case, and the model's own vocabulary is the point — so this checks only
    that a definition EXISTS (a sentence, not a word or a placeholder). Judging
    whether the vocabulary is "technical enough" is the SCORECARD proposal rule
    (``axis_proposal._definition_problem``), where an invented per-image axis
    would otherwise become a weight in the order.
    """
    text = str(definition or "").strip()
    return len(text) < 10 or len(text.split()) < 2


@dataclass(frozen=True)
class AxisChoiceSet:
    """The selector reply split into what it can become.

    ``registry_ids`` are the axes of the fixed pool the judge named (a local
    detector can produce them; the profile keeps them in ``axis_ids``).
    ``entries`` are the axes the judge NAMED that the pool does not have — each a
    first-class :class:`~tabs.image_gallery.models.AiAxisProposal` with a
    definition, a scale and a direction. ``refusals`` is ``(name, reason)`` for
    every pick that was NOT stored, so the loss is traceable and never silent.

    A registry id and an entry are different PROVENANCE, not different quality:
    the first reads "measured locally", the second "measured by the judge".
    """

    registry_ids: tuple[str, ...] = ()
    entries: tuple[AiAxisProposal, ...] = ()
    refusals: tuple[tuple[str, str], ...] = ()


def parse_axis_choices(value, *, limit: int = AXIS_CHOICE_MAX) -> AxisChoiceSet:
    """Classify a selector reply's ``axes`` list (never raises).

    Every element may be:

    - a string: a registry axis id (the reply of a terse/older answer) — kept when
      it IS a pool id, refused as ``no-definition`` otherwise (a bare name with no
      meaning cannot be measured, and the app will not invent one);
    - an object: ``{name, definition, scale, direction}``. A name equal to a
      registry id is that registry axis (the model asked for a measurable
      dimension that already exists — the local detector should score it too);
      any other name becomes a first-class entry, which is the normal answer of
      the free-form selector.

    The pool filter that used to drop every non-registry name is GONE (owner
    revision 2026-10-22): a free name WITH a definition is kept.
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
    seen: set[str] = set()

    def _refuse(row_name: str, reason: str) -> None:
        refusals.append((row_name, reason))

    for index, item in enumerate(items):
        if isinstance(item, str):
            name = normalize_name(item)
            if not name:
                _refuse(item.strip() or f"#{index + 1}", REJECT_NAME)
                continue
            if name not in pool:
                # A bare name carries no meaning: it cannot be scored.
                _refuse(name, REJECT_DEFINITION)
                continue
            definition = ""
            direction = AXIS_DIRECTION_DEFAULT
        elif isinstance(item, dict):
            raw_name = item.get("name")
            name = normalize_name(raw_name)
            if not name:
                _refuse(str(raw_name or f"#{index + 1}")[:40], REJECT_NAME)
                continue
            definition = str(item.get("definition", "") or "").strip()[:240]
            direction = direction_of(item, definition)
            if name not in pool:
                if _definition_missing(definition):
                    _refuse(name, REJECT_DEFINITION)
                    continue
                if not scale_of(item.get("scale")):
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
        entries.append(
            AiAxisProposal(
                name=name,
                definition=definition,
                scale=AXIS_PROPOSAL_SCALE,
                score=-1,  # chosen, not yet read: the scorecard fills the numbers
                direction=direction,
            )
        )
    return AxisChoiceSet(
        registry_ids=tuple(registry),
        entries=tuple(entries),
        refusals=tuple(refusals),
    )


__all__ = [
    "AXIS_CHOICE_MAX",
    "AXIS_CHOICE_MIN",
    "AxisChoiceSet",
    "parse_axis_choices",
]
