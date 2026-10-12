"""Deterministic answer-quality guard for the gallery Ask AI surface (pure).

Implements the P1 layer of ``plan-gallery-ask-ai-answer-quality``: a cheap,
network-free check that flags the failure modes the prompt alone does not
reliably prevent (metric recitals, percentages/numbers on a non-numeric
question, preamble/persona openers, over-length answers). On a flag the router
runs **one** rewrite; any failure keeps the original answer (fail-open).

No Qt, no HTTP — importable by tests and the eval harness.
"""

from __future__ import annotations

import re

#: A percentage or the word "percent"/"процент".
_PERCENT = re.compile(r"\d\s*%|\b\d{1,3}\s*(?:percent|процент\w*)\b", re.IGNORECASE)
#: Any bare number. ``\b`` keeps ``img_1`` (underscore is a word char) safe.
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
#: A question that asks for numbers — the number rule stands down.
_NUMERIC_QUESTION = re.compile(
    r"\d|%|\bpercent\w*\b|\bscore\w*\b|\bnumber\w*\b|\bhow many\b|"
    r"\bпроцент\w*\b|\bбалл\w*\b|\bсколько\b|\bчисл\w*\b|\bоценк\w*\b",
    re.IGNORECASE,
)
#: A preamble/persona opener (start of the answer).
_PREAMBLE = re.compile(
    r"^\s*(sure\b|of course\b|certainly\b|absolutely\b|"
    r"here (?:is|are|'s)\b|based on\b|as an?\b|i(?:'m| am)\b|"
    r"конечно\b|разумеется\b|вот\b|итак\b|на основе\b|как (?:ии|ассистент|"
    r"фотограф)\b|я\b)",
    re.IGNORECASE,
)


def is_numeric_question(question: str) -> bool:
    """Whether the user's question explicitly asks for numbers.

    Numbers are banned by default; this decides the exception. Comes from the
    *question*, never the answer.
    """
    return bool(_NUMERIC_QUESTION.search(str(question or "")))


def _sentence_count(text: str) -> int:
    parts = re.split(r"[.!?…]+", text)
    return len([p for p in parts if p.strip()])


def _label_violation(text: str, labels) -> str | None:
    """Flag a recital of a *distinctive* metric label.

    Deliberately conservative: only single-token labels of length >= 8 are
    matched, on word boundaries. Short/common labels ("Clean", "Detail") are
    skipped — flagging ordinary prose like "looks clean" would trigger needless
    rewrites, which is worse than missing a rare name-drop (that case is left to
    the prompt + a future model-based check).
    """
    for label in labels or ():
        lab = str(label or "").strip()
        if len(lab) < 8 or " " in lab or "(" in lab or ")" in lab:
            continue
        if re.search(rf"\b{re.escape(lab)}\b", text, re.IGNORECASE):
            return (
                f"names the metric '{lab}' although the question did not ask "
                "for numbers"
            )
    return None


def answer_violation(
    text: str,
    *,
    numeric: bool,
    labels: tuple[str, ...] | list[str] = (),
    max_sentences: int = 4,
) -> str | None:
    """Return a short reason if *text* breaks the answer contract, else ``None``.

    ``numeric`` is the verdict of :func:`is_numeric_question`; when true, the
    number/percentage rules do not apply. ``labels`` are the human metric labels
    (e.g. "Sharpness") whose recital is likewise unwanted on a non-numeric
    question.
    """
    t = str(text or "").strip()
    if not t:
        return "empty answer"
    if _PREAMBLE.match(t):
        return "starts with a preamble/persona instead of the answer"
    if not numeric:
        if _PERCENT.search(t):
            return "quotes percentages although the question did not ask for numbers"
        if _NUMBER.search(t):
            return "quotes numbers although the question did not ask for numbers"
        label_reason = _label_violation(t, labels)
        if label_reason:
            return label_reason
    count = _sentence_count(t)
    if count > max_sentences:
        return f"too long ({count} sentences; keep to <= {max_sentences})"
    return None


def build_correction_feedback(reason: str) -> str:
    """The feedback appended to the user turn for the single rewrite."""
    return (
        f"Your previous answer was rejected: {reason}. Rewrite it so it does "
        "not have that problem: give the practical decision directly, in plain "
        "language, without metric names or numbers unless the question asked "
        "for numbers, and without a preamble. Keep the same JSON envelope."
    )


__all__ = [
    "answer_violation",
    "build_correction_feedback",
    "is_numeric_question",
]
