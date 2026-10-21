"""Chat-completion request payload for the AI client."""

from __future__ import annotations

import base64
from pathlib import Path

from tabs.image_gallery.services.ask_prompt import language_directive

from .prompt import _ai_debug, attach_measured_context, build_prompt


_EXT_TO_MIME = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".webp": "webp",
}

# OpenRouter-only fallback chain (tried in order when the primary model's
# provider is exhausted/overloaded). Cheap, vision, structured-output-capable.
# Only used when the base_url is OpenRouter; not valid on plain OpenAI APIs.
DEFAULT_FALLBACK_MODELS: tuple[str, ...] = (
    "z-ai/glm-5.3-flash",
    "openai/gpt-6-luna",
)

#: Floor for one scorecard answer: the prompt asks for a per-axis scorecard +
#: reason + defects, so it needs more than a one-line tie-break answer. The
#: shared estimator (``ask_router.estimate_ask_max_tokens``) adds the reasoning
#: headroom for the chosen effort; this floor keeps the old 900-token budget
#: from regressing while the effort is capped.
_ANALYZE_MIN_TOKENS = 1024


def _resolve_effort(effort: str) -> str:
    """Normalize the configured reasoning effort (the shared Ask-AI rule)."""
    try:
        from tabs.image_gallery.services.ask_router import resolve_reasoning_effort

        return resolve_reasoning_effort(effort)
    except Exception:
        return "low"


def _analyze_budget(effort: str, configured: int) -> int:
    """Answer-token budget for one scorecard call (shared Ask-AI estimator)."""
    try:
        from tabs.image_gallery.services.ask_router import estimate_ask_max_tokens

        budget = int(
            estimate_ask_max_tokens({"count": 1}, configured=configured, effort=effort)
        )
    except Exception:
        budget = 0
    return max(_ANALYZE_MIN_TOKENS, budget)


def mime_for_path(image_path) -> str:
    """Content type of *image_path* by suffix (``png`` when unknown).

    Suffix parsing only — no filesystem access. Exposed so a producer that
    already holds the bytes (``AnalysisContext.image_bytes``) names the same
    mime as the file-path path instead of growing a second suffix table.
    """
    return _EXT_TO_MIME.get(Path(image_path).suffix.lower(), "png")


def build_request_from_bytes(
    image_bytes: bytes,
    mime: str,
    *,
    model: str,
    prompt: str | None = None,
    mode=None,
    profile=None,
    metrics: dict | None = None,
    openrouter: bool = False,
    fallback_models: tuple[str, ...] | None = None,
    reasoning_effort: str = "auto",
    max_tokens: int = 0,
    temperature: float = 0.0,
    seed: int = 0,
) -> dict:
    """Chat-completion payload for already-read *image_bytes* (no file I/O).

    The ONE payload shape: :func:`build_request` reads the file and delegates
    here, and a producer holding executor-provided bytes calls this directly.
    Two builders would mean two payload policies — the defect this plan removes
    (B2: ``vlm_max_edge_px`` applied to one upload path only).
    """
    raw_bytes = bytes(image_bytes or b"")
    data = base64.b64encode(raw_bytes).decode("ascii")
    # Local (Algorithms-domain) numbers ride along as CONTEXT only — the AI's
    # own per-axis scorecard is the answer (plan-gallery-ai-backend-owns-quality).
    block = ""
    if metrics:
        try:
            from tabs.image_gallery.services.metric_scores import (
                format_measured_for_prompt,
            )

            block = format_measured_for_prompt(metrics)
        except Exception:
            block = ""
    if prompt is None:
        # Default prompt: request every applicable axis for this mode/profile.
        text = build_prompt(mode, profile=profile, measured_block=block)
    else:
        # A custom prompt goes through the SAME echo filter as the scorecard
        # prompt (plan-gallery-ai-judgement P3-E): the local numbers for an axis
        # the model is asked to judge are an echo, not an independent read.
        text = attach_measured_context(prompt, block, mode=mode, profile=profile)
    # Steer the prose fields (the assessment reason / defect notes) into the
    # current UI language; the JSON envelope itself is unchanged.
    text = f"{text}\n{language_directive()}"
    resolved_effort = _resolve_effort(reasoning_effort)
    payload: dict = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{data}"},
                    },
                ],
            }
        ],
        "max_tokens": _analyze_budget(reasoning_effort, max_tokens),
        # Force a JSON object so reasoning models cannot answer in prose.
        "response_format": {"type": "json_object"},
    }
    # Sampling knobs (plan-gallery-ai-judgement P3-D): sent only when the user
    # declared them — a default (0.0 / 0) means "the backend's own draw", and
    # leaving the field out keeps every existing payload byte-identical.
    if temperature and float(temperature) > 0:
        payload["temperature"] = float(temperature)
    if seed:
        payload["seed"] = int(seed)
    if openrouter:
        # OpenRouter extensions:
        # - reasoning.exclude: keep the chain-of-thought out of `content`.
        # - provider routing: a cheap model's default host can be an overloaded
        #   shared pool (429 upstream_provider_shared_pool, e.g. DeepInfra);
        #   pick a healthy provider that actually supports response_format.
        payload["reasoning"] = {"effort": resolved_effort, "exclude": True}
        payload["provider"] = {
            "require_parameters": True,
            "sort": "throughput",
            "allow_fallbacks": True,
        }
        # Model fallback chain: if the primary is exhausted (429 upstream),
        # OpenRouter tries the next one in order instead of failing outright.
        chain = [model] + [m for m in (fallback_models or DEFAULT_FALLBACK_MODELS) if m and m != model]
        if len(chain) > 1:
            payload["models"] = chain
            payload["route"] = "fallback"
    _ai_debug(
        "build_request model=%s openrouter=%s metrics=%d response_format=json_object "
        "reasoning_exclude=%s provider_routing=%s chain=%s prompt_chars=%d "
        "image_bytes=%d b64_chars=%d mime=%s effort=%s max_tokens=%s",
        model,
        openrouter,
        len(metrics or {}),
        "reasoning" in payload,
        "provider" in payload,
        payload.get("models"),
        len(text),
        len(raw_bytes),
        len(data),
        mime,
        resolved_effort,
        payload.get("max_tokens"),
    )
    return payload


def build_request(
    image_path: Path,
    *,
    model: str,
    prompt: str | None = None,
    mode=None,
    profile=None,
    metrics: dict | None = None,
    openrouter: bool = False,
    fallback_models: tuple[str, ...] | None = None,
    reasoning_effort: str = "auto",
    max_tokens: int = 0,
    temperature: float = 0.0,
    seed: int = 0,
) -> dict:
    """Payload for one image on disk — reads it once, then delegates.

    Signature and behaviour are unchanged for every existing caller; the file
    read stays here (the caller owns the path) and the payload comes from
    :func:`build_request_from_bytes`, so there is one payload policy.
    """
    image_path = Path(image_path)
    return build_request_from_bytes(
        image_path.read_bytes(),
        mime_for_path(image_path),
        model=model,
        prompt=prompt,
        mode=mode,
        profile=profile,
        metrics=metrics,
        openrouter=openrouter,
        fallback_models=fallback_models,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
    )
