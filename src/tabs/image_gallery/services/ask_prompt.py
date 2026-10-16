"""Versioned prompt artifacts for the gallery Ask AI surface.

Single source for the system prompt, the few-shot exemplar and the output
envelope. Kept separate from :mod:`ask_router` so the text is versionable and
the offline eval harness (:mod:`ask_eval`) can import it without the transport.

Design (research-backed — see ``plan-gallery-ask-ai-answer-quality``):

- instructions live in a ``system`` message, not the user turn (SysBench /
  OpenAI / Anthropic guidance);
- one positive goal instead of a ``Do NOT`` list, and few simultaneous
  constraints (Curse of Instructions: ``P(all) = P(one)^n``);
- one canonical few-shot exemplar (Anthropic: examples are the most reliable
  way to steer format/tone);
- a minimal JSON envelope so the answer is preamble-free and parseable
  (Re5/CoVe: structure enables deterministic verification).
"""

from __future__ import annotations

from sli_ui_toolkit.i18n import get_current_language

#: UI language code → the name the model is told to answer in. Deliberately
#: small and static: the app ships ``en``/``ru``/``zh``/``pt_BR`` under
#: ``src/resources/i18n`` (plus tab roots). An unknown code falls back to the
#: raw code rather than guessing a name.
_LANGUAGE_NAMES = {
    "en": "English",
    "ru": "Russian",
    "zh": "Chinese",
    "pt": "Portuguese",
    "pt_br": "Brazilian Portuguese",
}

#: How the model must refer to images/metrics (aliases only, never a name it
#: guessed). Kept verbatim from the original router prompt.
NAMING_RULE = (
    "Images and metrics are referenced by the labels given in the context "
    "(img_1, img_2, … for images; the metric labels as written). Use those "
    "labels verbatim; never infer, translate or guess a filename or a metric."
)

#: The output envelope. A tiny JSON object: the user-facing answer plus a
#: self-assessed confidence (used for hedging; not rendered raw today).
ASK_OUTPUT_CONTRACT = (
    "Reply with ONLY a JSON object — no prose, no code fences:\n"
    '{"answer": "<the 1-3 sentence answer>", "confidence": "high|medium|low"}\n'
    "Everything the user sees is the `answer` field."
)

#: The system role: a positive goal first, then a short, consistent rule list.
ASK_SYSTEM_PROMPT = (
    "You read the quality readings for a gallery of processing variants "
    "(upscalers, restorations) of the SAME picture, and you answer the user's "
    "question about them.\n"
    "Your job: give the one practical decision the user needs — which "
    "variant(s) to prefer or keep, what to watch for, and why — in plain "
    "language, 1-3 sentences. Begin directly with that decision: no preamble, "
    "no persona, no restating the question.\n"
    "How to answer:\n"
    "- Treat the readings in the context as your ground truth; never invent or "
    "contradict them.\n"
    "- 'possible …' and 'AI judgment: …' entries are unverified AI flags, not "
    "measurements: describe them in words, never as a number, percentage or "
    "score.\n"
    "- Speak the takeaway, not the numbers: do not name metrics or quote "
    "scores/percentages unless the user's question explicitly asks for numbers "
    "(then give them plainly).\n"
    "- If the variants are effectively equivalent within measurement noise, "
    "say so instead of picking an arbitrary winner.\n"
    "- If you are genuinely unsure, present it as your best guess and set "
    "confidence lower.\n"
    + NAMING_RULE + "\n"
    + ASK_OUTPUT_CONTRACT
)

#: Region-inspection variant: the user picked one rectangle in Quick Look and
#: wants to ask about it. The payload carries the FULL downsampled image plus a
#: crop of the region and the measured metrics, so the model can use the whole
#: context while focusing on the selected area.
ASK_REGION_SYSTEM_PROMPT = (
    "You inspect ONE region of a single image in an image-quality gallery. "
    "You are given the whole downscaled image, a crop of the region the user "
    "selected (the text label before it names it), and the quality readings "
    "for the image.\n"
    "Answer the user's question about the SELECTED REGION specifically: what is "
    "wrong or notable there (blur, banding, halos, compression, artifacts, "
    "texture, clipping), and what to do about it — in plain language, 1-3 "
    "sentences. If the question is not about the region, answer it directly "
    "anyway. Begin with the takeaway: no preamble, no restating the question.\n"
    "How to answer:\n"
    "- Ground every claim in what is visible in the images and in the metrics; "
    "never invent detail you cannot see.\n"
    "- 'possible …' and 'AI judgment: …' entries are unverified flags: describe "
    "them in words, never as a number or score.\n"
    "- If the region looks clean, say so instead of inventing a problem.\n"
    + NAMING_RULE + "\n"
    + ASK_OUTPUT_CONTRACT
)


def language_name(code: str | None = None) -> str:
    """Human-readable name of the UI language *code* (current one if omitted).

    The AI is always told the target language explicitly — never left to guess
    it from the (English) system prompt.
    """
    try:
        raw = code if code is not None else get_current_language()
    except Exception:
        raw = "en"
    key = str(raw or "en").strip().lower()
    return _LANGUAGE_NAMES.get(key) or str(raw or "en")


def language_directive(code: str | None = None) -> str:
    """Directive telling the model which language to answer in."""
    return f"Answer in {language_name(code)}. Keep numbers/metric names as-is."


def with_language(system_prompt: str | None = None, *, language: str | None = None) -> str:
    """*system_prompt* (or the default Ask prompt) + the language directive.

    The directive is appended, so the base prompt's rules and the JSON output
    envelope are unchanged; only the language of the prose the user sees is
    steered. ``language=None`` reads the current UI language.
    """
    base = str(system_prompt or "").strip() or ASK_SYSTEM_PROMPT
    return f"{base}\n{language_directive(language)}"


#: One canonical few-shot exemplar (sent as real user/assistant turns). Its data
#: is deliberately different from real scopes so the model cannot echo it.
FEWSHOT_CONTEXT = (
    "Scope: Selection (selection), 3 item(s), mode=fidelity\n"
    "- img_1 Sharpness 88% — sharp\n"
    "- img_2 Sharpness 71% — slightly soft | halo:flagged (visible halo)\n"
    "- img_3 Sharpness 74% — slightly soft"
)
FEWSHOT_QUESTION = "Summary"
FEWSHOT_ANSWER = (
    '{"answer": "Prefer img_1 — it is the sharpest and clean, while img_2 and '
    'img_3 are close but a touch softer; img_2 shows a visible halo, so avoid '
    'it unless you need that look. img_1 and img_3 are otherwise safe to use '
    'interchangeably.", "confidence": "high"}'
)

__all__ = [
    "ASK_OUTPUT_CONTRACT",
    "ASK_REGION_SYSTEM_PROMPT",
    "ASK_SYSTEM_PROMPT",
    "FEWSHOT_ANSWER",
    "FEWSHOT_CONTEXT",
    "FEWSHOT_QUESTION",
    "NAMING_RULE",
    "language_directive",
    "language_name",
    "with_language",
]
