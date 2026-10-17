"""Blocking streaming HTTP transport for the AI client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .errors import (
    AiAuthError,
    AiNetworkError,
    AiRateLimitError,
    AiResponseError,
    AiServerError,
)
from .prompt import _ai_debug, _ai_snippet, _ratelimit_headers


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
    _ai_debug("POST %s (stream) body_bytes=%d", url, len(getattr(request, "data", b"") or b""))
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
            # Extended response trace: finish_reason reveals truncation
            # ("length" => the JSON was cut at max_tokens), usage shows the
            # token split, and the content/reasoning snippets show WHAT the
            # model actually returned when a later parse fails.
            try:
                _choice = (result.get("choices") or [{}])[0]
                _msg = _choice.get("message") if isinstance(_choice, dict) else {}
                _content = _msg.get("content") if isinstance(_msg, dict) else ""
                _reason = _msg.get("reasoning") if isinstance(_msg, dict) else ""
                _ai_debug(
                    "response model=%s finish=%s content_chars=%d reasoning_chars=%d "
                    "usage=%s content=%s",
                    result.get("model"),
                    _choice.get("finish_reason") if isinstance(_choice, dict) else None,
                    len(_content or ""),
                    len(_reason or ""),
                    result.get("usage"),
                    _ai_snippet(_content),
                )
                if _reason:
                    _ai_debug("response reasoning=%s", _ai_snippet(_reason))
            except Exception:
                pass
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
