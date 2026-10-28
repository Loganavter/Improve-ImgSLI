"""The shapes a stub answer can take — and the ONE router that resolves one.

Split out of ``live_fixtures`` (file-size policy) when the AI stub grew
per-request answers: a real AI-domain run asks TWO different questions in one
session (the metric-profile proposal wants a JSON *list* of axes, the scorecard
wants a JSON *object* of axis scores), so a single fixed reply cannot answer
both. A callable answer receives the request body and returns any shape this
module accepts; everything else about the stub (HTTP, SSE, recording) stays in
``live_fixtures``.

Devtool only, side-effect free: no Qt, no network, no child process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

#: A reply the stub can serve: content, a full completion, a JSON file, or a
#: router ``(request_body) -> reply`` for a stub that must answer more than one
#: question shape.
Answer = (
    "dict | str | Path | Callable[[dict], dict | str]"
)


class AnswerError(ValueError):
    """The reply (or the router's reply) is not a shape the stub can serve."""


@dataclass(frozen=True)
class Resolved:
    """Resolved fixture answer: the message content plus an optional full body."""

    content: Any
    completion: dict | None


def load_answer(answer: Any) -> Resolved:
    """Resolve one reply (never a callable — see :func:`resolve_answer`)."""
    if isinstance(answer, Path):
        try:
            return load_answer(json.loads(Path(answer).read_text(encoding="utf-8")))
        except OSError as exc:
            raise AnswerError(f"could not read stub answer {answer}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AnswerError(f"stub answer {answer} is not JSON: {exc}") from exc
    if isinstance(answer, str):
        return Resolved(answer, None)
    if isinstance(answer, dict):
        if "choices" in answer:
            try:
                return Resolved(answer["choices"][0]["message"]["content"], dict(answer))
            except (IndexError, KeyError, TypeError) as exc:
                raise AnswerError(
                    "stub answer with 'choices' needs choices[0].message.content"
                ) from exc
        if "content" in answer:
            return Resolved(answer["content"], None)
        return Resolved(answer, None)
    raise AnswerError(
        f"stub answer must be a dict, str, Path or router callable, got {type(answer).__name__}"
    )


def resolve_answer(answer: Any, body: dict) -> Resolved:
    """The answer for ONE request: the fixed reply, or the router's reply.

    A router is called with the parsed request body, so a stub can answer the
    profile proposal and the scorecard differently. A router that raises or
    returns an unusable shape raises :class:`AnswerError` — the caller turns
    that into a 500 JSON, never a hanging connection.
    """
    if not callable(answer):
        return load_answer(answer)
    try:
        chosen = answer(body)
    except Exception as exc:  # noqa: BLE001 - a router bug is a fixture error
        raise AnswerError(
            f"stub answer router failed: {type(exc).__name__}: {exc}"
        ) from exc
    return load_answer(chosen)


def completion_body(answer: Resolved, model: str, *, created: int) -> dict:
    """The non-streaming OpenAI chat-completion body for *answer*."""
    if answer.completion is not None:
        return answer.completion
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer.content},
                "finish_reason": "stop",
            }
        ],
    }


def stream_text(answer: Resolved) -> str:
    """The delta text an SSE chunk carries for *answer*."""
    content = answer.content
    return content if isinstance(content, str) else json.dumps(
        content, ensure_ascii=False, sort_keys=True
    )


def sse_body(answer: Resolved, model: str, *, created: int) -> bytes:
    """One-chunk SSE body ending in ``data: [DONE]`` (same content as JSON)."""
    chunk = {
        "id": "chatcmpl-stub",
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": stream_text(answer)},
                "finish_reason": None,
            }
        ],
    }
    final = {
        "id": "chatcmpl-stub",
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return (
        f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
        "data: [DONE]\n\n"
    ).encode("utf-8")


__all__ = [
    "Answer",
    "AnswerError",
    "Resolved",
    "completion_body",
    "load_answer",
    "resolve_answer",
    "sse_body",
    "stream_text",
]
