"""Analysis prompt construction + gated AI debug tracing."""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def _ai_debug(msg: str, *args) -> None:
    """``IMGSLI_AI_DEBUG=1``-gated AI client trace ([ai] prefix).

    Logs the request shape, response status and ``x-ratelimit-*`` headers
    (429 diagnosis) — never the API key or image bytes.
    """
    if _env_flag("IMGSLI_AI_DEBUG"):
        logger.warning("[ai] " + msg, *args)

def _ai_debug_enabled() -> bool:
    """True when the ``IMGSLI_AI_DEBUG`` trace gate is on."""
    return bool(_env_flag("IMGSLI_AI_DEBUG"))


def _ai_snippet(text, *, head: int = 600, tail: int = 240) -> str:
    """One-line, bounded preview of a model reply for the ``[ai]`` trace.

    Shows length + head…tail: a truncated answer loses its TAIL
    (``finish_reason=length``), a reasoning-only answer shows a long head —
    both visible without dumping the whole body into the log.
    """
    try:
        s = str(text or "")
    except Exception:
        return "<unprintable>"
    s = s.replace("\r", " ").replace("\n", " ")
    n = len(s)
    if n <= head + tail:
        return f"({n}c) {s}"
    return f"({n}c) {s[:head]} … {s[-tail:]}"


def _ratelimit_headers(headers) -> str:
    """Compact x-ratelimit-* + retry-after summary for one response."""
    try:
        out = []
        for k, v in (headers or {}).items():
            lk = str(k).lower()
            if lk.startswith("x-ratelimit") or lk in ("retry-after", "x-request-id"):
                out.append(f"{lk}={v}")
        return " ".join(out)
    except Exception:
        return ""

_PROMPT_CORE = (
    "You assess TECHNICAL image quality for a gallery that compares many "
    "processing variants (upscalers, restorations) of the SAME picture. "
    "Judge quality and DEFECTS only — never describe the scene, objects or "
    "content: they are identical across variants and add nothing.\n"
    "Score EVERY applicable axis listed below from 0 (worst) to 100 (best) in "
    "the \"axes\" object, as YOUR OWN read of this picture. When local "
    "measurements are shown they are the Algorithms domain's numbers, for "
    "context only — your scores are independent and need not match them.\n"
)

#: Default prompt for the no-mode / legacy case (all untagged measured axes).
PROMPT_TEMPLATE = _PROMPT_CORE

def _scorecard_axes(mode=None, *, profile=None) -> tuple[tuple[str, str], ...]:
    """``(axis_id, label)`` for every axis the AI must score.

    The set is the ACTIVE metric profile's applicable MEASURED axes
    (``measured_axes_for(mode, profile=profile)``) — single source of truth,
    never a second axis list here. ``profile`` (any object with ``.axis_ids``,
    canonically ``MetricProfile``) wins when given; ``profile=None`` is the
    mode mapping (fail-open). Order = registry.
    """
    try:
        from tabs.image_gallery.services.metric_scores import spec_for
        from tabs.image_gallery.services.rank_fusion import measured_axes_for

        out: list[tuple[str, str]] = []
        for axis_id in measured_axes_for(mode, profile=profile):
            spec = spec_for(axis_id)
            out.append((axis_id, spec.label if spec is not None else axis_id))
        return tuple(out)
    except Exception:
        return ()

def build_prompt(mode=None, *, profile=None, measured_block: str = "") -> str:
    """The analysis prompt: a per-axis scorecard for *mode* / *profile*.

    Every applicable axis is requested by canonical id with its positive label,
    so the model answers in the ids the report reads (see
    ``plan-gallery-ai-backend-owns-quality``). ``profile`` is the active
    metric profile (``measured_axes_for`` wins it over *mode*); ``profile=None``
    reproduces the mode mapping byte-for-byte. ``measured_block`` (local
    detector numbers) is attached as *context*, explicitly NOT authoritative.
    """
    axes = _scorecard_axes(mode, profile=profile)
    axis_parts = ", ".join(f'"{axis_id}": <0-100 {label}>' for axis_id, label in axes)
    text = (
        _PROMPT_CORE
        + "Reply with ONLY a JSON object, no prose and no code fences:\n"
        + '{"axes": {' + (axis_parts or '"<axis_id>": <0-100>') + "}, "
        + '"verdict": "keep|reject", "reason": "practical assessment", '
        '"defects": [{"kind": "halo|banding|blocking|chroma_fringing|noise|'
        'over_smoothing|invented_texture|clipping|other", '
        '"severity": "mild|flagged", "note": "short visual description"}], '
        '"composition": <0-100>, "confidence": <0.0-1.0>}\n'
        "axes: one 0-100 score per axis listed above; omit an axis you cannot "
        "judge (never invent a number you did not see).\n"
        "defects: report only artifacts you actually SEE; prefer an empty list "
        "when the image is clean. These are top-level observations.\n"
        "reason: 2-4 sentences — a PRACTICAL read of this image. Say what the "
        "processing actually did to it, whether the result is usable, and what "
        "a human should watch for. Base it on what you SEE.\n"
        "composition is your subjective framing/quality score.\n"
        "Output the JSON object ONLY: no reasoning, no analysis steps, no "
        "preamble, no prose before or after the JSON."
    )
    if measured_block:
        text = f"{text}\n\nLOCAL MEASUREMENTS (Algorithms domain, context only):\n{measured_block}"
    return text
