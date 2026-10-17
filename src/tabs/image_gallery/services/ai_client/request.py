"""Chat-completion request payload for the AI client."""

from __future__ import annotations

import base64
from pathlib import Path

from tabs.image_gallery.services.ask_prompt import language_directive

from .prompt import _ai_debug, build_prompt


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

def build_request(
    image_path: Path,
    *,
    model: str,
    prompt: str | None = None,
    mode=None,
    metrics: dict | None = None,
    openrouter: bool = False,
    fallback_models: tuple[str, ...] | None = None,
) -> dict:
    image_path = Path(image_path)
    mime = _EXT_TO_MIME.get(image_path.suffix.lower(), "png")
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
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
        # Default prompt: request every applicable axis for this mode.
        text = build_prompt(mode, measured_block=block)
    else:
        text = prompt
        if block:
            text = f"{text}\n\nLOCAL MEASUREMENTS (Algorithms domain, context only):\n{block}"
    # Steer the prose fields (verdict reason / defect notes) into the current
    # UI language; the JSON envelope itself is unchanged.
    text = f"{text}\n{language_directive()}"
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
        "max_tokens": 900,
        # Force a JSON object so reasoning models cannot answer in prose.
        "response_format": {"type": "json_object"},
    }
    if openrouter:
        # OpenRouter extensions:
        # - reasoning.exclude: keep the chain-of-thought out of `content`.
        # - provider routing: a cheap model's default host can be an overloaded
        #   shared pool (429 upstream_provider_shared_pool, e.g. DeepInfra);
        #   pick a healthy provider that actually supports response_format.
        payload["reasoning"] = {"exclude": True}
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
        "reasoning_exclude=%s provider_routing=%s chain=%s prompt_chars=%d",
        model,
        openrouter,
        len(metrics or {}),
        "reasoning" in payload,
        "provider" in payload,
        payload.get("models"),
        len(text),
    )
    return payload
