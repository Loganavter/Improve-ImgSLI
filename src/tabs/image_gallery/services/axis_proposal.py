"""Model-NAMED axes: the per-image proposal rule and the shared axis vocabulary.

Two producers name axes in this app, and this module owns the rules they SHARE
plus the scorecard's own:

- the **scorecard** (``services/ai_client/parse``) lets a per-image reply add at
  most :data:`AXIS_PROPOSAL_LIMIT` dimensions the asked set is missing, each with
  this image's score. That rule lives here: name, definition (metadata), 0–100
  scale, score.
- the **selector** (``use_cases/profile_ai``) asks the model for 3..8 axes for a
  whole series (plan-gallery-ai-judgement §OWNER REVISION 2026-10-22). Its
  classification is ``services/axis_choice`` — a separate rule for a separate
  reply shape, importing the vocabulary from here (``normalize_name``,
  ``direction_of``, ``scale_of``, the refusal codes).

Shared vocabulary: a NAME (an axis id, not a phrase), a DEFINITION, a 0–100
SCALE and a DIRECTION ("higher is better" unless the definition says otherwise).

Owner rule (2026-10-27, verbatim): *"we must not decide what is measurable and
what is not. If the app said it needs such metrics, we draw them, period."* So
the DEFINITION is METADATA, never a gate: the old English whitelist
(``_MEASURABLE_WORDS`` / ``_CONTENT_WORDS``) judged the model's vocabulary and
dropped every axis it did not recognise — including every non-English one — and
it is DELETED. A missing or too-short definition is stored as ``""`` and recorded
as the audit code :data:`AUDIT_NO_DEFINITION`; the axis is KEPT.

What is still refused — structure only, with a recorded reason, never silently:
an unusable/empty NAME, a duplicate of a pool axis, a name repeated inside one
reply, an unsupported SCALE and a missing SCORE (plus the per-image limit).
Accepted proposals become ``models.AiAxisProposal`` entries (``producer="vlm"``,
``kind="candidate"``, plus the direction) and travel with the scorecard into the
Jev vector by name.

Pure: no Qt, no HTTP, no registry mutation. The pool itself is never written —
the proposal lives on the result of the image that proposed it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.models import (
    AXIS_DIRECTION_DEFAULT,
    AXIS_DIRECTIONS,
    AiAxisProposal,
)

logger = logging.getLogger(APP_LOGGER_NAME)

#: The only scale a scorecard answer may use (the pool's own 0-100 quality
#: scale). A proposal on another scale cannot be compared with a measured axis.
AXIS_PROPOSAL_SCALE = "0-100"

#: Accepted spellings of that scale (normalized to :data:`AXIS_PROPOSAL_SCALE`).
_SCALE_SPELLINGS = frozenset(
    {
        "0-100",
        "0..100",
        "0 to 100",
        "0–100",
        "0—100",
        "0-100%",
    }
)

#: Upper bound per image: a proposal is a *gap* in the pool, not a second
#: scorecard. Beyond this the reply is over-limit and the extra ones are refused.
AXIS_PROPOSAL_LIMIT = 2

#: Refusal codes (the recorded reason). Codes, never prose: a surface localizes
#: them and the trace stays stable across a language switch. Every one of them is
#: a STRUCTURE rule — nothing here judges what the model chose to measure.
REJECT_NAME = "unusable-name"
REJECT_SCALE = "unsupported-scale"
REJECT_SCORE = "no-score"
REJECT_DUPLICATE = "duplicate-pool-axis"
REJECT_LIMIT = "over-limit"
#: A name repeated inside ONE reply (the first occurrence is kept).
REJECT_REPEAT = "repeated-axis"
PROPOSAL_REJECT_CODES: tuple[str, ...] = (
    REJECT_NAME,
    REJECT_SCALE,
    REJECT_SCORE,
    REJECT_DUPLICATE,
    REJECT_LIMIT,
    REJECT_REPEAT,
)

#: Audit code (NOT a refusal): the model named the axis but gave no usable
#: definition. The entry is stored with ``definition=""`` and this code records
#: why it says nothing (owner rule 2026-10-27: a definition is metadata, never a
#: reason to drop an axis the app asked for).
AUDIT_NO_DEFINITION = "no-definition"
AUDIT_CODES: tuple[str, ...] = (AUDIT_NO_DEFINITION,)

#: What a definition must say to be STORED instead of audited as absent: a
#: sentence, not a word or a placeholder. Whitespace-split words on purpose — the
#: judge answers in the UI language, and the old ``[a-z_]`` regex made every
#: non-English definition "empty".
MIN_DEFINITION_CHARS = 10
MIN_DEFINITION_WORDS = 2

#: A name is an axis id, not a phrase: 2–40 characters, starts with a letter,
#: then letters/digits/underscore/space/hyphen (Unicode letters allowed — the
#: judge answers in the UI language, "чистота" is a valid axis name).
_NAME_RE = re.compile(r"^[^\W\d_][\w \-]{1,39}$", re.UNICODE)


def definition_audit(definition) -> str:
    """``""`` when *definition* is storable, else :data:`AUDIT_NO_DEFINITION`.

    An audit code, not a refusal: the owner rule (2026-10-27) is that the app
    never decides what a model may measure, so a missing/short definition costs
    the definition, never the axis. Whitespace words, so any language passes.
    """
    try:
        text = str(definition or "").strip()
    except Exception:
        return AUDIT_NO_DEFINITION
    if len(text) < MIN_DEFINITION_CHARS or len(text.split()) < MIN_DEFINITION_WORDS:
        return AUDIT_NO_DEFINITION
    return ""


def storable_definition(definition) -> str:
    """The definition to STORE for *definition*: its text, or ``""`` if too thin.

    ``""`` is how "the model gave none" is expressed on an entry (see
    ``models.AiAxisProposal``): one field, no second flag, so a cached entry and a
    fresh one stay equal.
    """
    try:
        text = str(definition or "").strip()[:240]
    except Exception:
        return ""
    return "" if definition_audit(text) else text


#: Storage ceiling for a display LABEL. Not a display cut: the header is elided
#: by the width it actually has (``ui/quick_look/metrics/rows.py``). This only
#: keeps a paragraph out of a field whose contract is "a short human name"; the
#: ceiling is generous so a real label is never the thing that gets shortened.
MAX_LABEL_CHARS = 80


def storable_label(label) -> str:
    """The human-readable NAME to STORE for *label* (``""`` when unreadable).

    Display text, not an id: trimmed and capped, and deliberately NOT passed
    through :func:`normalize_name` — the model answers in the UI language
    ("Резкость линий", "Line crispness"), and lowercasing/underscoring that would
    turn the human name back into the machine key this field exists to replace.
    ``""`` means "the model gave none" and the surfaces fall back to the name
    (``profile_judged.axis_display_name``).
    """
    try:
        text = str(label or "").strip()
    except Exception:
        return ""
    return text[:MAX_LABEL_CHARS]


def normalize_name(raw) -> str:
    """Canonical axis id for a proposed name (``""`` when unusable).

    Lowercase, spaces/hyphens → ``_``, collapsed. A name must look like an axis
    id (for example "halation" or "sepia_drift"), never a phrase.
    """
    try:
        text = str(raw or "").strip().lower()
    except Exception:
        return ""
    text = re.sub(r"[\s-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text or not _NAME_RE.match(text.replace("_", " ")):
        return ""
    return text


def _pool_axis_for(name: str) -> str:
    """The existing pool axis *name* duplicates (``""`` when it is new)."""
    try:
        from tabs.image_gallery.services.axis_policy import known_axis
        from tabs.image_gallery.services.metric_scores import SCORECARD_AXIS_IDS

        if name in SCORECARD_AXIS_IDS:
            return name
        resolved = known_axis(name.replace("_", " "))
        if resolved:
            return str(resolved)
        # A pooled id written with a different separator still duplicates it.
        for axis_id in SCORECARD_AXIS_IDS:
            if axis_id.replace("_", "") == name.replace("_", ""):
                return axis_id
    except Exception:
        return ""
    return ""


def _score_of(value) -> int:
    try:
        score = int(float(str(value).strip().rstrip("%")))
    except Exception:
        return -1
    return score if 0 <= score <= 100 else -1


def normalize_direction(value) -> str:
    """Canonical direction token for *value* (``""`` when it says nothing).

    Accepts the canonical tokens plus the spellings a model actually writes
    ("higher", "higher_is_better", "more is better", "lower", "less-is-better",
    "max"/"min"). An unknown value returns ``""`` so the caller applies the
    definition/default rule instead of storing a guess.
    """
    try:
        text = re.sub(r"[\s_]+", "-", str(value or "").strip().lower())
    except Exception:
        return ""
    text = text.strip("-")
    if not text:
        return ""
    if text in AXIS_DIRECTIONS:
        return text
    if text in {"higher", "more", "more-is-better", "higher-better", "max", "up", "asc"}:
        return AXIS_DIRECTIONS[0]
    if text in {"lower", "less", "less-is-better", "lower-better", "min", "down", "desc"}:
        return AXIS_DIRECTIONS[1]
    return ""


#: Definition phrases that flip the DEFAULT direction: the owner rule is
#: "higher is better unless the definition says otherwise", so a definition that
#: names 0 as the good end ("0 = no ringing") is a lower-is-better axis.
_LOWER_IS_BETTER_CUES: tuple[str, ...] = (
    "lower is better",
    "lower-is-better",
    "less is better",
    "smaller is better",
    "fewer is better",
    "0 = no",
    "0=no",
    "0 = none",
    "0=none",
    "0 = clean",
    "0=clean",
    "0 is clean",
    "0 = absent",
)


def direction_of(entry, definition=None) -> str:
    """The direction of an axis entry: explicit field, else its definition.

    ``entry`` may be the raw reply dict (``{"direction": "lower-is-better"}``) or
    any object carrying ``.direction``. An explicit but unrecognized value is
    ignored in favour of the definition; the fallback is
    ``AXIS_DIRECTION_DEFAULT`` ("higher is better").
    """
    if isinstance(entry, dict):
        explicit = entry.get("direction")
    else:
        explicit = getattr(entry, "direction", "")
    token = normalize_direction(explicit)
    if token:
        return token
    if definition is None:
        if isinstance(entry, dict):
            definition = entry.get("definition")
        else:
            definition = getattr(entry, "definition", "")
    text = str(definition or "").strip().lower()
    for cue in _LOWER_IS_BETTER_CUES:
        if cue in text:
            return AXIS_DIRECTIONS[1]
    return AXIS_DIRECTION_DEFAULT


def scale_of(value) -> str:
    try:
        text = str(value or "").strip().lower()
    except Exception:
        return ""
    return AXIS_PROPOSAL_SCALE if text in _SCALE_SPELLINGS else ""


def refusal_reason(entry) -> str:
    """Why *entry* is not a usable axis proposal (``""`` when it is).

    Structure only, per the owner rule: a name, a duplicate of a pool axis, the
    0–100 scale and a score. The DEFINITION is metadata and never a reason
    (:func:`definition_audit` records its absence instead).
    """
    if not isinstance(entry, dict):
        return REJECT_NAME
    name = normalize_name(entry.get("name"))
    if not name:
        return REJECT_NAME
    duplicate = _pool_axis_for(name)
    if duplicate:
        return f"{REJECT_DUPLICATE}:{duplicate}"
    if not scale_of(entry.get("scale")):
        return REJECT_SCALE
    if _score_of(entry.get("score")) < 0:
        return REJECT_SCORE
    return ""


def parse_proposals(value, *, limit: int = AXIS_PROPOSAL_LIMIT):
    """``(accepted, refusals)`` for one reply's ``axis_proposals`` field.

    ``accepted`` is a tuple of :class:`AiAxisProposal` (``producer="vlm"``,
    ``kind="candidate"``); ``refusals`` is a tuple of ``(name, reason)`` for
    every entry that was NOT stored — an unusable entry still has a name (or
    ``"#"`` + position when it has none) so the loss is traceable. Unknown
    duplicates inside one reply keep the first occurrence. Never raises.

    A missing/short definition does not refuse anything: the entry is stored with
    ``definition=""`` and the audit code :data:`AUDIT_NO_DEFINITION` is logged
    (owner rule 2026-10-27).
    """
    accepted: list[AiAxisProposal] = []
    refusals: list[tuple[str, str]] = []
    try:
        entries = list(value or ())
    except Exception:
        return (), ()
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        name = normalize_name((entry or {}).get("name")) if isinstance(entry, dict) else ""
        row_name = name or f"#{index + 1}"
        reason = refusal_reason(entry)
        if not reason and name in seen:
            reason = REJECT_DUPLICATE + ":repeat"
        if not reason and len(accepted) >= int(limit):
            reason = REJECT_LIMIT
        if reason:
            refusals.append((row_name, reason))
            continue
        seen.add(name)
        raw_definition = str(entry.get("definition", "") or "")
        audit = definition_audit(raw_definition)
        if audit:
            logger.debug(
                "axis proposal kept with an audit code: %s=%s (the definition is "
                "metadata, never a refusal)",
                name,
                audit,
            )
        definition = storable_definition(raw_definition)
        accepted.append(
            AiAxisProposal(
                name=name,
                definition=definition,
                scale=AXIS_PROPOSAL_SCALE,
                score=_score_of(entry.get("score")),
                # The DIRECTION follows what the model wrote, even when that text
                # is too thin to keep as the stored definition ("0 = none").
                direction=direction_of(entry, raw_definition),
                # The model's own short human name for the axis: display text,
                # never the key (the header used to be the raw id — owner
                # screenshot 2026-10-27).
                label=storable_label(entry.get("label")),
            )
        )
    return tuple(accepted), tuple(refusals)


__all__ = [
    "AUDIT_CODES",
    "AUDIT_NO_DEFINITION",
    "AXIS_PROPOSAL_LIMIT",
    "AXIS_PROPOSAL_SCALE",
    "MAX_LABEL_CHARS",
    "MIN_DEFINITION_CHARS",
    "MIN_DEFINITION_WORDS",
    "PROPOSAL_REJECT_CODES",
    "REJECT_DUPLICATE",
    "REJECT_LIMIT",
    "REJECT_NAME",
    "REJECT_REPEAT",
    "REJECT_SCALE",
    "REJECT_SCORE",
    "definition_audit",
    "direction_of",
    "normalize_direction",
    "normalize_name",
    "parse_proposals",
    "refusal_reason",
    "scale_of",
    "storable_definition",
    "storable_label",
]
