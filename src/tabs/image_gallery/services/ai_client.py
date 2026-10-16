"""OpenAI-compatible (OpenRouter et al.) chat-vision client for AI image tagging.

Stdlib ``urllib.request`` only (matches the project's one existing HTTP
precedent, ``shared.clipboard_images``) — no new dependency. ``call_sync`` must
only ever run on a worker thread (see ``controller.GalleryController``, which
wraps it in a ``GenericWorker``), never on the UI thread.
"""
# Audit-Meta: pattern=wire-client size=762 reason="one OpenAI-compatible vision client: request build + call_sync (streaming SSE reassembly + retry/429) + response parse + debug belong together — splitting scatters the wire contract"

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from shared.debug_flags import env_flag as _env_flag
from tabs.image_gallery.models import AiAnalysisResult
from tabs.image_gallery.services.ask_prompt import language_directive

logger = logging.getLogger("ImproveImgSLI")


def _ai_debug(msg: str, *args) -> None:
    """``IMGSLI_AI_DEBUG=1``-gated AI client trace ([ai] prefix).

    Logs the request shape, response status and ``x-ratelimit-*`` headers
    (429 diagnosis) — never the API key or image bytes.
    """
    if _env_flag("IMGSLI_AI_DEBUG"):
        logger.warning("[ai] " + msg, *args)


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


def _scorecard_axes(mode=None) -> tuple[tuple[str, str], ...]:
    """``(axis_id, label)`` for every axis the AI must score for *mode*.

    The set is the mode's applicable MEASURED axes (``measured_axes_for``) —
    single source of truth, never a second axis list here. Order = registry.
    """
    try:
        from tabs.image_gallery.services.metric_scores import spec_for
        from tabs.image_gallery.services.rank_fusion import measured_axes_for

        out: list[tuple[str, str]] = []
        for axis_id in measured_axes_for(mode):
            spec = spec_for(axis_id)
            out.append((axis_id, spec.label if spec is not None else axis_id))
        return tuple(out)
    except Exception:
        return ()


def build_prompt(mode=None, *, measured_block: str = "") -> str:
    """The analysis prompt: a per-axis scorecard for *mode* + verdict/defects.

    Every applicable axis is requested by canonical id with its positive label,
    so the model answers in the ids the report reads (see
    ``plan-gallery-ai-backend-owns-quality``). ``measured_block`` (local
    detector numbers) is attached as *context*, explicitly NOT authoritative.
    """
    axes = _scorecard_axes(mode)
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

_DEFECT_KINDS = (
    "halo",
    "banding",
    "blocking",
    "chroma_fringing",
    "noise",
    "over_smoothing",
    "invented_texture",
    "clipping",
    "other",
)


def _parse_score(value) -> int:
    """Parse a 0-100 score, clamped; -1 when unparsable."""
    try:
        return max(0, min(100, int(float(str(value).strip().rstrip("%")))))
    except Exception:
        return -1


def _parse_verdict(value) -> str:
    """Normalize to keep | reject | unknown."""
    try:
        v = str(value).strip().lower()
    except Exception:
        return "unknown"
    if v.startswith("keep"):
        return "keep"
    if v.startswith("reject"):
        return "reject"
    return "unknown"


def _parse_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


_AXIS_IDS = (
    "sharpness",
    "exposure",
    "clipping",
    "noise",
    "white_balance",
    "ssim",
    "detail_gain",
    "color_accuracy",
    "typicality",
    "aesthetic",
    "composition",
    "banding",
    "halo",
    "blocking",
    "over_smoothing",
    "invented_texture",
    "chroma_fringing",
)


def _parse_axis_notes(value) -> dict:
    """Normalize the axis_notes map: canonical ids only, short non-empty."""
    out: dict[str, str] = {}
    if not isinstance(value, dict):
        return out
    for k, v in value.items():
        try:
            key = str(k).strip().lower()
        except Exception:
            continue
        if key not in _AXIS_IDS:
            continue
        try:
            note = str(v).strip()
        except Exception:
            continue
        if note:
            out[key] = note[:120]
    return out


def _parse_axes(value) -> dict[str, int]:
    """Normalize the open per-axis scorecard: canonical ids → 0-100.

    Unknown ids are dropped (never fabricated), unparsable values dropped.
    """
    out: dict[str, int] = {}
    if not isinstance(value, dict):
        return out
    try:
        from tabs.image_gallery.services.metric_scores import SCORECARD_AXIS_IDS

        allowed = SCORECARD_AXIS_IDS
    except Exception:
        allowed = None
    for k, v in value.items():
        try:
            key = str(k).strip().lower()
        except Exception:
            continue
        if allowed is not None and key not in allowed:
            continue
        score = _parse_score(v)
        if score >= 0:
            out[key] = score
    return out


def _parse_defects(value) -> tuple:
    """Normalize a defects list into ``AiDefect`` tuples (kind/severity)."""
    from tabs.image_gallery.models import AiDefect

    out = []
    if not isinstance(value, list):
        return ()
    for item in value:
        if isinstance(item, str):
            kind, severity, note = item, "mild", ""
        elif isinstance(item, dict):
            kind = str(item.get("kind", "") or "").strip().lower().replace(" ", "_")
            severity = str(item.get("severity", "") or "mild").strip().lower()
            note = str(item.get("note", "") or "").strip()
        else:
            continue
        if not kind:
            continue
        if kind not in _DEFECT_KINDS:
            kind = "other"
        if severity not in ("clean", "mild", "flagged"):
            severity = "mild"
        if severity == "clean":
            continue  # a "clean" defect is not a defect
        out.append(AiDefect(kind=kind, severity=severity, note=note))
    return tuple(out)

def _axis_flags_from_defects(defects) -> tuple:
    """Map AI-reported defects to AI-sourced candidate axes (never numbers).

    Uses ``axis_policy.degrade_unknown`` so an observation that maps to a known
    axis id gets it; anything else degrades to ``flag-for-review``. These are
    candidate flags (text; see plan-gallery-two-domain-axes) — the numeric
    per-axis answer is the scorecard (``AiAnalysisResult.axes``), never a flag.
    """
    from tabs.image_gallery.models import AiAxisFlag
    from tabs.image_gallery.services.axis_policy import degrade_unknown

    out = []
    for d in defects or ():
        try:
            axis = degrade_unknown(getattr(d, "kind", "") or getattr(d, "note", ""))
            out.append(
                AiAxisFlag(
                    id=axis,
                    label=str(getattr(d, "kind", "") or ""),
                    kind="candidate",
                    note=str(getattr(d, "note", "") or ""),
                )
            )
        except Exception:
            continue
    return tuple(out)


_EXT_TO_MIME = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".webp": "webp",
}


class AiClientError(Exception):
    """Base for all typed errors raised by this module."""


class AiAuthError(AiClientError):
    """401/403 — bad or missing API key."""


class AiRateLimitError(AiClientError):
    """429 — too many requests."""

    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AiNetworkError(AiClientError):
    """Connection failure, timeout, DNS error, etc."""


class AiServerError(AiNetworkError):
    """5xx — the API host answered but failed (overloaded / broken deploy).

    Subclasses :class:`AiNetworkError` so legacy ``except AiNetworkError``
    handlers keep working; callers that need the distinction catch this type
    first. A 5xx is *not* proof the network is down — surfacing it as a plain
    network error sends users to check their Wi-Fi instead of retrying later.
    """

    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AiResponseError(AiClientError):
    """Malformed/unexpected response body."""


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


# Retry policy for overloaded servers (429 / 5xx): honor Retry-After, else
# short exponential backoff. Worker thread only — never sleep on the UI thread.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 1.0
_RETRY_MAX_DELAY_S = 30.0


def _retry_delay_s(retry_after: str | None, attempt: int) -> float:
    """Delay before retrying attempt ``attempt`` (1-based)."""
    if retry_after:
        try:
            # Retry-After is usually delta-seconds; HTTP-dates fall back below.
            delay = float(str(retry_after).strip())
            if delay >= 0:
                return min(delay, _RETRY_MAX_DELAY_S)
        except (TypeError, ValueError):
            pass
    return min(_RETRY_BASE_DELAY_S * (2.0 ** max(0, attempt - 1)), _RETRY_MAX_DELAY_S)


def _iter_response_lines(response, first: bytes):
    """Yield *first*, then the remaining lines of *response* (SSE framing)."""
    yield first
    while True:
        line = response.readline()
        if not line:
            return
        yield line


def _parse_json_body(body: bytes) -> dict:
    try:
        obj = json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise AiResponseError(f"invalid JSON in response: {exc}") from exc
    if not isinstance(obj, dict):
        raise AiResponseError("unexpected response body (not an object)")
    return obj


def _consume_stream_chunk(chunk: dict, state: dict, on_delta) -> None:
    """Fold one SSE chunk into the accumulating response *state*."""
    if chunk.get("model"):
        state["model"] = chunk["model"]
    if chunk.get("provider"):
        state["provider"] = chunk["provider"]
    if chunk.get("id"):
        state["id"] = chunk["id"]
    if chunk.get("usage"):
        state["usage"] = chunk["usage"]
    for choice in chunk.get("choices") or ():
        if not isinstance(choice, dict):
            continue
        if choice.get("finish_reason"):
            state["finish"] = choice["finish_reason"]
        delta = choice.get("delta")
        if isinstance(delta, dict):
            if delta.get("role"):
                state["role"] = delta["role"]
            text = delta.get("content")
            if isinstance(text, str) and text:
                state["content"] += text
                if on_delta is not None:
                    try:
                        on_delta(text)
                    except Exception:
                        pass
            reasoning = delta.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                state["reasoning"] += reasoning
        # A provider that ignored `stream` may answer one message object instead.
        message = choice.get("message")
        if isinstance(message, dict) and not state["content"]:
            if isinstance(message.get("content"), str):
                state["content"] = message["content"]
            if isinstance(message.get("reasoning"), str):
                state["reasoning"] = message["reasoning"]


def _finalize_stream(state: dict) -> dict:
    """Rebuild the non-streaming chat-completion dict that callers already parse."""
    message: dict = {"role": state["role"], "content": state["content"]}
    if state["reasoning"]:
        message["reasoning"] = state["reasoning"]
    out: dict = {
        "id": state["id"],
        "model": state["model"],
        "provider": state["provider"],
        "choices": [{"index": 0, "message": message, "finish_reason": state["finish"]}],
    }
    if state["usage"] is not None:
        out["usage"] = state["usage"]
    return out


def _read_stream(response, *, on_delta=None) -> dict:
    """Reassemble an SSE chat stream into a non-streaming response dict.

    A provider that ignores ``stream`` answers with one (possibly multi-line)
    JSON object — detected from the first meaningful line and parsed as a whole.
    An empty body raises :class:`AiResponseError`.
    """
    first = b""
    probe = ""
    while True:
        first = response.readline()
        if not first:
            raise AiResponseError("empty streaming response")
        probe = first.decode("utf-8", "replace").strip()
        if probe and not probe.startswith(":"):
            break
    if not probe.startswith("data:"):
        return _parse_json_body(first + response.read())

    state: dict = {
        "role": "assistant",
        "content": "",
        "reasoning": "",
        "finish": None,
        "model": None,
        "provider": None,
        "id": None,
        "usage": None,
    }
    for raw in _iter_response_lines(response, first):
        text = raw.decode("utf-8", "replace").strip()
        if not text or text.startswith(":") or not text.startswith("data:"):
            continue
        data = text[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(chunk, dict):
            _consume_stream_chunk(chunk, state, on_delta)
    return _finalize_stream(state)


def call_sync(
    base_url: str,
    api_key: str,
    payload: dict,
    *,
    timeout: float = 30.0,
    on_delta=None,
) -> dict:
    """Blocking streaming chat/completions POST — call only from a worker thread.

    Sends ``stream: true`` and reassembles the SSE stream into the SAME dict a
    non-streaming call returns, so every caller and parser is unchanged. Because
    the body is consumed incrementally, ``timeout`` bounds the gap *between*
    chunks (an **idle** timeout), not the whole generation — a slow reasoning
    model or router no longer hits a hard wall, it fails only if the stream truly
    stalls. ``on_delta(text)`` (optional) receives each content delta as it
    arrives.
    """
    import time

    stream_payload = dict(payload)
    stream_payload["stream"] = True
    stream_payload.setdefault("stream_options", {"include_usage": True})
    url = base_url.rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(stream_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    _ai_debug("POST %s (stream)", url)
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = _read_stream(response, on_delta=on_delta)
            _ai_debug(
                "HTTP %s attempt=%d %s",
                getattr(response, "status", "?"),
                attempt,
                _ratelimit_headers(getattr(response, "headers", None)),
            )
            return result
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            _ai_debug(
                "HTTP %s attempt=%d %s body=%.200s",
                exc.code,
                attempt,
                _ratelimit_headers(exc.headers),
                body.replace("\n", " "),
            )
            if exc.code in (401, 403):
                raise AiAuthError(f"HTTP {exc.code}: {body}") from exc
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if attempt < _RETRY_MAX_ATTEMPTS:
                    _ai_debug("429 retry %d after %.1fs", attempt, _retry_delay_s(retry_after, attempt))
                    time.sleep(_retry_delay_s(retry_after, attempt))
                    continue
                raise AiRateLimitError(f"HTTP 429: {body}", retry_after=retry_after) from exc
            if exc.code is not None and 500 <= exc.code <= 599:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if attempt < _RETRY_MAX_ATTEMPTS:
                    _ai_debug("5xx retry %d after %.1fs", attempt, _retry_delay_s(retry_after, attempt))
                    time.sleep(_retry_delay_s(retry_after, attempt))
                    continue
                raise AiServerError(f"HTTP {exc.code}: {body}", retry_after=retry_after) from exc
            raise AiNetworkError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            _ai_debug("URLError: %s", exc.reason)
            raise AiNetworkError(str(exc.reason)) from exc
        except TimeoutError as exc:
            _ai_debug("stream idle timeout after %.1fs", timeout)
            raise AiNetworkError("stream idle timeout") from exc


_REASONING_BLOCK_RE = re.compile(
    r"<(think|thinking|reasoning|analysis)>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_reasoning(text: str) -> str:
    """Remove chain-of-thought wrappers many reasoning models emit.

    `` thinking…<｜end▁of▁thinking｜>`` / ``<reasoning>…</reasoning>`` blocks are dropped so
    the JSON extractor only sees the answer, not the model's scratchpad.
    """
    try:
        return _REASONING_BLOCK_RE.sub("", str(text)).strip()
    except Exception:
        return text


def _extract_json(content: str) -> dict | None:
    """Best-effort JSON object out of a model reply (fences/prose tolerated)."""
    s = _strip_reasoning(content)
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s[:4].lower() == "json":
            s = s[4:].strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    try:
        i, j = s.find("{"), s.rfind("}")
        if 0 <= i < j:
            obj = json.loads(s[i : j + 1])
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return None


_LEGACY_LINE_RE = re.compile(
    r"^\s*(DESCRIPTION|TAGS|VERDICT|SHARPNESS|NOISE|EXPOSURE|COMPOSITION|REASON)\s*:",
    re.IGNORECASE,
)


def _looks_like_legacy_lines(content: str) -> bool:
    """True only when EVERY non-empty line is a legacy ``KEY: value`` line.

    A blanket "contains a marker" check is fooled by chain-of-thought that
    happens to write ``- Sharpness: 253 (quality 63%)`` — that must NOT be
    mistaken for the legacy format (it would dump the reasoning).
    """
    try:
        lines = [ln for ln in content.splitlines() if ln.strip()]
    except Exception:
        return False
    if not lines:
        return False
    hits = sum(1 for ln in lines if _LEGACY_LINE_RE.match(ln))
    return hits == len(lines)


def _parse_lines(content: str, model: str) -> AiAnalysisResult:
    """Legacy line-order fallback (DESCRIPTION/TAGS/VERDICT lines)."""
    description = content.strip()
    tags: tuple[str, ...] = ()
    sharpness = noise = exposure = composition = -1
    verdict, reason = "unknown", ""
    for line in content.splitlines():
        line = line.strip()
        upper = line.upper()
        if upper.startswith("DESCRIPTION:"):
            description = line.split(":", 1)[1].strip()
        elif upper.startswith("TAGS:"):
            raw_tags = line.split(":", 1)[1]
            tags = tuple(t.strip() for t in raw_tags.split(",") if t.strip())
        elif upper.startswith("SHARPNESS:"):
            sharpness = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("NOISE:"):
            noise = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("EXPOSURE:"):
            exposure = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("COMPOSITION:"):
            composition = _parse_score(line.split(":", 1)[1])
        elif upper.startswith("VERDICT:"):
            verdict = _parse_verdict(line.split(":", 1)[1])
        elif upper.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    axes = {
        key: value
        for key, value in (
            ("sharpness", sharpness),
            ("noise", noise),
            ("exposure", exposure),
            ("composition", composition),
        )
        if value >= 0
    }
    return AiAnalysisResult(
        description=description,
        tags=tags,
        model=model,
        analyzed_at_iso=datetime.now(timezone.utc).isoformat(),
        sharpness=sharpness,
        noise=noise,
        exposure=exposure,
        composition=composition,
        verdict=verdict,
        verdict_reason=reason,
        axes=axes,
    )


def parse_response(raw: dict, *, model: str) -> AiAnalysisResult:
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiResponseError(f"unexpected response shape: {exc}") from exc

    if not isinstance(content, str) or not content.strip():
        raise AiResponseError("empty response content")

    obj = _extract_json(content)
    _ai_debug("parse content_chars=%d json_found=%s", len(content), obj is not None)
    if obj is None:
        # Accept the legacy KEY: value format, but NOT free-form prose /
        # chain-of-thought: dumping the model's reasoning into the block is
        # worse than an honest parse error (surfaced as "Could not parse…").
        if _looks_like_legacy_lines(content):
            _ai_debug("parse fallback=legacy_lines")
            return _parse_lines(content, model)
        _ai_debug("parse NO-JSON -> AiResponseError first200=%.200s", content.replace("\n", " "))
        raise AiResponseError("model did not return the required JSON object")

    # Open per-axis scorecard (new prompt) with the legacy named fields merged
    # in, so an old reply / old prompt still fills the same scorecard.
    axes = _parse_axes(obj.get("axes"))
    for key in ("sharpness", "noise", "exposure", "composition"):
        if key in axes or obj.get(key) is None:
            continue
        score = _parse_score(obj.get(key))
        if score >= 0:
            axes[key] = score
    defects = _parse_defects(obj.get("defects"))
    return AiAnalysisResult(
        description="",
        tags=(),
        model=model,
        analyzed_at_iso=datetime.now(timezone.utc).isoformat(),
        sharpness=axes.get("sharpness", -1),
        noise=axes.get("noise", -1),
        exposure=axes.get("exposure", -1),
        composition=axes.get("composition", -1),
        verdict=_parse_verdict(obj.get("verdict", "")),
        verdict_reason=str(obj.get("reason", "") or "").strip(),
        defects=defects,
        confidence=_parse_confidence(obj.get("confidence")),
        axis_notes=_parse_axis_notes(obj.get("axis_notes")),
        axis_flags=_axis_flags_from_defects(defects),
        axes=axes,
    )


def _emit_phase(on_phase: Callable[[str], None] | None, phase: str) -> None:
    """Best-effort activity hook: a UI-side failure must never fail analysis."""
    if on_phase is None:
        return
    try:
        on_phase(phase)
    except Exception:
        logger.debug("activity phase hook failed", exc_info=True)


def analyze_image_sync(
    image_path: Path,
    *,
    base_url: str,
    api_key: str,
    model: str,
    mode=None,
    metrics: dict | None = None,
    fallback_models: tuple[str, ...] | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> AiAnalysisResult:
    """Full request→parse pipeline. Call only from a worker thread.

    ``mode`` selects the applicable axis set the prompt requests (the AI-domain
    scorecard). ``on_phase`` (optional) receives ``"analyzing"`` before the
    request is built and ``"waiting"`` right before the blocking HTTP call.
    """
    openrouter = "openrouter" in str(base_url or "").lower()
    _ai_debug(
        "analyze start path=%s model=%s host=%s mode=%s metrics=%d",
        image_path, model, base_url, getattr(mode, "value", mode), len(metrics or {}),
    )
    _emit_phase(on_phase, "analyzing")
    payload = build_request(
        image_path,
        model=model,
        mode=mode,
        metrics=metrics,
        openrouter=openrouter,
        fallback_models=fallback_models,
    )
    _emit_phase(on_phase, "waiting")
    raw = call_sync(base_url, api_key, payload)
    return parse_response(raw, model=model)
