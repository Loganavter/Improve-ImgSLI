"""Backend router for the gallery "Ask AI" surface (A2).

One frozen seam: ``answer(question, context, *, backend, ...) -> AskResult``.
The question kind selects the backend (the router enforces the contract):

- **text LLM** — summaries/narration over the measured table (no images);
- **VLM** — genuinely visual questions (images in the payload, ≤1024px);
- **Jev stub** — routing/priority is declared as an interface and raises
  ``AskNotConfigured`` (the UI degrades visibly, "routing not enabled").

Transport is the existing ``ai_client.call_sync`` (no new HTTP client). All
sync calls must run on a GenericWorker — never the UI thread. Advisory only:
the result is text/priority, never a mutation of rank/selection/store.
Fail-open: any backend error yields an ``AskResult`` with an error note, never
fabricated text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tabs.image_gallery.services.ai_client import (
    DEFAULT_FALLBACK_MODELS,
    AiResponseError,
    _ai_debug,
    call_sync,
)
from tabs.image_gallery.services.ask_answer_guard import (
    answer_violation,
    build_correction_feedback,
    is_numeric_question,
)
from tabs.image_gallery.services.ask_payload import (
    DEFAULT_ASK_MAX_TOKENS,
    _metric_labels,
    build_text_payload,
    build_vision_payload,
)

#: Backends the router can dispatch to.
BACKEND_TEXT = "text"
BACKEND_VLM = "vlm"
BACKEND_JEV = "jev"

#: Deferred routing gate (Jev): no text generation, no vision — routing only.
JEV_STUB = BACKEND_JEV

_VISUAL_HINTS = (
    "look",
    "visually",
    "visual",
    " see",
    "show me",
    "describe",
    "color",
    "colour",
    "blur",
    "grain",
    "sharpen",
    "artifact",
    "halo",
    "banding",
    "noise",
    "detail",
    "texture",
    "fring",
    "wrong",
)

_ROUTING_HINTS = (
    "route",
    "prioritize",
    "prioritise",
    "priority",
    " rank",
    "which series",
    "which one first",
    "order of",
    "triage order",
)

#: Headroom multiplier over the estimated visible-answer budget. Reasoning
#: tokens count against ``max_tokens``, so the total must cover both.
_EFFORT_HEADROOM = {"low": 1.25, "medium": 1.6, "high": 2.2}


def resolve_reasoning_effort(effort: str) -> str:
    """Normalize a configured effort to one the request can send.

    ``auto``/``none``/unknown collapse to ``low``: some models reason
    *mandatorily* (e.g. ``z-ai/glm-5.3-flash`` defaults to effort ``max``) and
    reject ``none``, so a low cap both avoids the rejection and leaves room
    for the visible answer.
    """
    value = str(effort or "auto").strip().lower()
    if value in ("medium", "high"):
        return value
    return "low"


def estimate_ask_max_tokens(context: dict, *, configured: int = 0, effort: str = "auto") -> int:
    """Pick an answer-token budget for one ask.

    A fixed budget is wrong when the scope grows (7 items vs 100): the context
    block and the requested summary both scale with the item count. Base the
    estimate on the scope's item count, multiply by the reasoning headroom for
    the chosen effort, and clamp to a sane range. An explicit ``configured``
    value (>0), e.g. from Settings, always wins.
    """
    try:
        configured = int(configured or 0)
    except Exception:
        configured = 0
    if configured > 0:
        return configured
    try:
        count = max(0, int((context or {}).get("count", 0) or 0))
    except Exception:
        count = 0
    answer_budget = 400 + min(count, 100) * 24  # 7 → ~570, 100 → ~2800
    headroom = _EFFORT_HEADROOM.get(resolve_reasoning_effort(effort), 1.25)
    return int(max(512, min(int(answer_budget * headroom), 16384)))


class AskNotConfigured(Exception):
    """Raised by the Jev routing stub — the backend is not wired yet."""


@dataclass(frozen=True)
class AskResult:
    """One answer (or a visible degrade). Never mutates gallery state."""

    text: str
    backend: str
    priority: int | None = None
    confidence: float | None = None
    cached: bool = False
    error: str | None = None
    #: True when the guard rejected the first answer and the single rewrite
    #: replaced it (see plan-gallery-ask-ai-answer-quality, P1).
    revised: bool = False


def route_backend(question: str, context: dict) -> str:
    """Pick a backend from the question kind (text / vlm / jev)."""
    q = str(question or "").strip().lower()
    if not q:
        return BACKEND_TEXT
    if any(hint in q for hint in _ROUTING_HINTS):
        return BACKEND_JEV
    if any(hint in q for hint in _VISUAL_HINTS):
        return BACKEND_VLM
    return BACKEND_TEXT


def resolve_backend(question: str, context: dict, *, include_images: bool | None = None) -> str:
    """Backend with the ask surface's include-images toggle applied.

    ``include_images=None`` keeps the auto routing (question kind). ``True``
    forces the vision backend (images in the payload); ``False`` forces the
    text backend even for a visual question (metrics only). A routing (Jev)
    question is never overridden.
    """
    backend = route_backend(question, context)
    if include_images is None or backend == BACKEND_JEV:
        return backend
    if include_images:
        return BACKEND_VLM
    return BACKEND_TEXT if backend == BACKEND_VLM else backend


def _coerce_text(value) -> str:
    """Best-effort text out of a chat message field (str or parts list)."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for part in value:
            try:
                if isinstance(part, dict):
                    if part.get("type") in (None, "text", "output_text"):
                        parts.append(str(part.get("text", "")))
                    elif part.get("text"):
                        parts.append(str(part["text"]))
                elif isinstance(part, str):
                    parts.append(part)
            except Exception:
                continue
        return "".join(parts).strip()
    return ""


def _extract_text(raw: dict) -> str:
    """Pull the answer text out of a chat completion ``message.content``."""
    try:
        message = raw["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiResponseError(f"unexpected response shape: {exc}") from exc
    if not isinstance(message, dict):
        raise AiResponseError("unexpected message shape")
    text = _coerce_text(message.get("content"))
    if text:
        return text
    finish = None
    try:
        finish = raw["choices"][0].get("finish_reason")
    except Exception:
        pass
    _ai_debug(
        "ask empty content finish_reason=%s usage=%s",
        finish,
        raw.get("usage") if isinstance(raw, dict) else None,
    )
    raise AiResponseError(f"empty ask response (finish_reason={finish})")


def _coerce_confidence(value) -> float | None:
    """Map the envelope's confidence token (or a 0-1 float) to a number."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            v = float(value)
            return v if 0.0 <= v <= 1.0 else None
        token = str(value or "").strip().lower()
        return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(token)
    except Exception:
        return None


def _parse_answer_envelope(text: str) -> tuple[str, float | None]:
    """Tolerant decode of the answer envelope → ``(answer, confidence|None)``.

    Falls back to the raw text when the model did not emit the JSON object
    (provider/model behavior varies), so an answer is never lost to a
    formatting miss.
    """
    raw = str(text or "").strip()
    if not raw:
        return "", None
    obj = None
    start, end = raw.find("{"), raw.rfind("}")
    if 0 <= start < end:
        try:
            import json

            candidate = json.loads(raw[start : end + 1])
            if isinstance(candidate, dict):
                obj = candidate
        except Exception:
            obj = None
    if isinstance(obj, dict):
        answer = obj.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip(), _coerce_confidence(obj.get("confidence"))
    return raw, None


def _is_openrouter(base_url: str) -> bool:
    return "openrouter" in str(base_url or "").lower()


def _apply_openrouter_extensions(
    payload: dict, base_url: str, model: str, effort: str = "auto"
) -> dict:
    """OpenRouter knobs so a reasoning model always returns answer text.

    ``z-ai/glm-5.3-flash`` (and family) reasons *mandatorily* with default
    effort ``max`` — roughly 95% of ``max_tokens`` goes to hidden reasoning,
    so a small budget returns ``finish_reason: length`` with empty ``content``
    (observed: HTTP 200, zero chars). Cap the effort (see
    :func:`resolve_reasoning_effort`; the caller sizes ``max_tokens`` for the
    remaining answer); route to a healthy provider and fall back if the
    primary is exhausted.
    """
    if not _is_openrouter(base_url):
        return payload
    payload["reasoning"] = {"effort": resolve_reasoning_effort(effort)}
    payload["provider"] = {
        "require_parameters": True,
        "sort": "throughput",
        "allow_fallbacks": True,
    }
    chain = [model] + [m for m in DEFAULT_FALLBACK_MODELS if m and m != model]
    if len(chain) > 1:
        payload["models"] = chain
        payload["route"] = "fallback"
    return payload


def _jev_stub() -> AskResult:
    """Deferred routing backend: interface declared, not wired."""
    raise AskNotConfigured("routing backend is not enabled")


def answer(
    question: str,
    context: dict,
    *,
    backend: str,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    max_tokens: int = 0,
    reasoning_effort: str = "auto",
    system_prompt: str | None = None,
    transport: Callable[[str, str, dict], dict] | None = None,
) -> AskResult:
    """Answer *question* over *context* via *backend*. Worker thread only.

    ``max_tokens`` (0 = compute from the scope size via
    :func:`estimate_ask_max_tokens`) and ``reasoning_effort`` come from
    Settings. ``transport`` defaults to :func:`ai_client.call_sync`; tests
    inject a fake to capture the payload and avoid the network. Any failure
    (not configured, backend error, malformed response) returns an
    ``AskResult`` whose ``error`` is set and whose ``text`` is empty — never a
    fabricated answer.
    """
    backend = str(backend or BACKEND_TEXT).strip().lower() or BACKEND_TEXT
    if backend == "auto":
        backend = route_backend(question, context)

    if backend == BACKEND_JEV:
        try:
            return _jev_stub()
        except AskNotConfigured as exc:
            return AskResult(text="", backend=BACKEND_JEV, error=str(exc))

    if not (base_url and api_key and model):
        return AskResult(
            text="",
            backend=backend,
            error="AI is not configured (set the API key/model in Settings).",
        )

    budget = estimate_ask_max_tokens(
        context, configured=max_tokens, effort=reasoning_effort
    )
    call = transport or call_sync
    use_vision = backend == BACKEND_VLM
    if not use_vision:
        backend = BACKEND_TEXT

    def _one_call(correction: str) -> dict:
        if use_vision:
            payload = build_vision_payload(
                question, context, model=model, max_tokens=budget, correction=correction,
                system_prompt=system_prompt,
            )
        else:
            payload = build_text_payload(
                question, context, model=model, max_tokens=budget, correction=correction,
                system_prompt=system_prompt,
            )
        payload = _apply_openrouter_extensions(payload, base_url, model, reasoning_effort)
        return call(base_url, api_key, payload)

    try:
        raw = _one_call("")
        answer_text, confidence = _parse_answer_envelope(_extract_text(raw))
        result = AskResult(text=answer_text, backend=backend, confidence=confidence)

        # P1 — deterministic guard + at most ONE rewrite (fail-open: any failure
        # or a still-violating rewrite keeps the first answer).
        numeric = is_numeric_question(question)
        labels = _metric_labels(context)
        reason = answer_violation(answer_text, numeric=numeric, labels=labels)
        if reason:
            correction = (
                f"Previous answer:\n{answer_text}\n\n"
                + build_correction_feedback(reason)
            )
            try:
                raw2 = _one_call(correction)
                revised, revised_conf = _parse_answer_envelope(_extract_text(raw2))
                if revised and not answer_violation(
                    revised, numeric=numeric, labels=labels
                ):
                    return AskResult(
                        text=revised,
                        backend=backend,
                        confidence=revised_conf if revised_conf is not None else confidence,
                        revised=True,
                    )
            except Exception:
                pass
        return result
    except Exception as exc:
        return AskResult(
            text="",
            backend=backend,
            error=str(exc) or exc.__class__.__name__,
        )


__all__ = [
    "BACKEND_JEV",
    "BACKEND_TEXT",
    "BACKEND_VLM",
    "DEFAULT_ASK_MAX_TOKENS",
    "AskNotConfigured",
    "AskResult",
    "answer",
    "build_text_payload",
    "build_vision_payload",
    "estimate_ask_max_tokens",
    "resolve_backend",
    "resolve_reasoning_effort",
    "route_backend",
]
