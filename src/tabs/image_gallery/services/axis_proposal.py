"""VLM-proposed axes: the pool a model may extend (plan-gallery-ai-judgement P3-B).

The judged axis pool is the fixed registry (``metric_scores.SPECS``) plus the
AI-only ``composition`` — one vocabulary, resolved by
``rank_fusion.measured_axes_for`` and by nothing else. The model may *extend*
that pool for a series, but only with an axis it can actually measure:

- a NAME (a lowercase snake_case id, not a sentence);
- a DEFINITION that names a technical dimension (noise, halation, banding, …)
  and is not a description of the scene — the prompt's own rule: content is
  identical across variants and adds nothing;
- a SCALE it scores on (0–100 today);
- a SCORE on that scale for this image.

A proposal that fails any of those is **refused with a reason** and never
stored: an axis with no measurable meaning cannot be ranked on, and a stored
one would silently become a weight in the order (the "nine bars that meant
nothing" failure). Accepted proposals become ``models.AiAxisProposal`` entries
(``producer="vlm"``, ``kind="candidate"``) and travel with the scorecard into
the Jev vector by name.

Pure: no Qt, no HTTP, no registry mutation. The pool itself is never written —
the proposal lives on the result of the image that proposed it.
"""

from __future__ import annotations

import re

from tabs.image_gallery.models import AiAxisProposal

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
#: them and the trace stays stable across a language switch.
REJECT_NAME = "unusable-name"
REJECT_DEFINITION = "no-definition"
REJECT_CONTENT = "describes-content"
REJECT_SCALE = "unsupported-scale"
REJECT_SCORE = "no-score"
REJECT_DUPLICATE = "duplicate-pool-axis"
REJECT_LIMIT = "over-limit"
PROPOSAL_REJECT_CODES: tuple[str, ...] = (
    REJECT_NAME,
    REJECT_DEFINITION,
    REJECT_CONTENT,
    REJECT_SCALE,
    REJECT_SCORE,
    REJECT_DUPLICATE,
    REJECT_LIMIT,
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_ -]{1,39}$")

#: Vocabulary that makes a definition MEASURABLE: it names a technical
#: dimension of the image (what a detector or a careful eye could score). A
#: definition built only out of scene nouns has no such dimension.
_MEASURABLE_WORDS = frozenset(
    {
        "alias",
        "artifact",
        "banding",
        "bleed",
        "blotch",
        "blur",
        "brightness",
        "blockiness",
        "chroma",
        "chromatic",
        "clarity",
        "clipping",
        "colour",
        "color",
        "compression",
        "contrast",
        "crispness",
        "detail",
        "distortion",
        "dust",
        "edge",
        "exposure",
        "fidelity",
        "fringing",
        "glow",
        "grain",
        "halation",
        "halo",
        "highlight",
        "hue",
        "jpeg",
        "moire",
        "noise",
        "overshoot",
        "posterization",
        "resolution",
        "ringing",
        "saturation",
        "scratch",
        "sepia",
        "shadow",
        "sharpen",
        "sharpness",
        "smear",
        "smoothing",
        "softness",
        "speckle",
        "structure",
        "texture",
        "tone",
        "vignette",
        "white_balance",
    }
)

#: Scene/content vocabulary: a definition that is only about WHAT is depicted
#: cannot separate two variants of the same picture (the prompt's rule).
_CONTENT_WORDS = frozenset(
    {
        "animal",
        "background",
        "beauty",
        "beautiful",
        "building",
        "car",
        "character",
        "composition_subject",
        "dog",
        "face",
        "flower",
        "landscape",
        "person",
        "portrait",
        "scene",
        "sky",
        "subject",
        "tree",
    }
)

_WORD_RE = re.compile(r"[a-z_]+")


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


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(str(text or "").lower()))


def _definition_problem(definition: str) -> str:
    """``""`` when *definition* names a measurable dimension, else a code."""
    words = _words(definition)
    if len(definition.strip()) < 10 or len(words) < 2:
        return REJECT_DEFINITION
    if not (words & _MEASURABLE_WORDS):
        # A definition about the scene ("how pretty the sky looks") has no
        # dimension to score: identical across variants of one picture.
        return REJECT_CONTENT if (words & _CONTENT_WORDS) else REJECT_DEFINITION
    return ""


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


def _scale_of(value) -> str:
    try:
        text = str(value or "").strip().lower()
    except Exception:
        return ""
    return AXIS_PROPOSAL_SCALE if text in _SCALE_SPELLINGS else ""


def refusal_reason(entry) -> str:
    """Why *entry* is not a usable axis proposal (``""`` when it is)."""
    if not isinstance(entry, dict):
        return REJECT_NAME
    name = normalize_name(entry.get("name"))
    if not name:
        return REJECT_NAME
    duplicate = _pool_axis_for(name)
    if duplicate:
        return f"{REJECT_DUPLICATE}:{duplicate}"
    problem = _definition_problem(str(entry.get("definition", "") or ""))
    if problem:
        return problem
    if not _scale_of(entry.get("scale")):
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
        accepted.append(
            AiAxisProposal(
                name=name,
                definition=str(entry.get("definition", "") or "").strip()[:240],
                scale=AXIS_PROPOSAL_SCALE,
                score=_score_of(entry.get("score")),
            )
        )
    return tuple(accepted), tuple(refusals)


__all__ = [
    "AXIS_PROPOSAL_LIMIT",
    "AXIS_PROPOSAL_SCALE",
    "PROPOSAL_REJECT_CODES",
    "REJECT_CONTENT",
    "REJECT_DEFINITION",
    "REJECT_DUPLICATE",
    "REJECT_LIMIT",
    "REJECT_NAME",
    "REJECT_SCALE",
    "REJECT_SCORE",
    "normalize_name",
    "parse_proposals",
    "refusal_reason",
]
