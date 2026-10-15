"""Streaming transport: `call_sync` reassembles SSE into the non-streaming shape.

The gallery sends `stream: true` so `timeout` becomes an IDLE timeout (gap
between chunks) instead of a hard ceiling on a slow reasoning model/router —
the root cause behind the tie-break/r rank latency wall. These tests pin the
reassembly contract: every caller (`parse_tie_break_response`, the Ask-AI
parser, `jev_client`) keeps reading `choices[0].message.content` / `usage`.

Falsification: a delta dropped, `usage`/`finish_reason` lost, the request not
actually streamed, or a provider that ignores `stream` (single JSON body) not
handled.
"""

from __future__ import annotations

import io
import json

import pytest

from tabs.image_gallery.services import ai_client


class _FakeStream:
    """Minimal urlopen response: line reads + a tail read for the JSON fallback."""

    def __init__(self, blob: bytes) -> None:
        self._buf = io.BytesIO(blob)
        self.status = 200
        self.headers = {}

    def readline(self) -> bytes:
        return self._buf.readline()

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install(monkeypatch, blob: bytes) -> dict:
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeStream(blob)

    monkeypatch.setattr(ai_client.urllib.request, "urlopen", fake_urlopen)
    return captured


def _sse(*chunks: dict) -> bytes:
    lines = b"".join(f"data: {json.dumps(c)}\n\n".encode("utf-8") for c in chunks)
    return lines + b"data: [DONE]\n\n"


def test_call_sync_reassembles_content_finish_and_usage(monkeypatch) -> None:
    captured = _install(monkeypatch, _sse(
        {"id": "gen-1", "model": "z-ai/glm-5.3-flash", "provider": "Crusoe",
         "choices": [{"index": 0, "delta": {"role": "assistant"}}]},
        {"choices": [{"index": 0, "delta": {"content": "WINNER: B"}}]},
        {"choices": [{"index": 0, "delta": {"content": "\nCONFIDENCE: 0.7"}}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
         "usage": {"completion_tokens": 50, "completion_tokens_details": {"reasoning_tokens": 0}}},
    ))
    out = ai_client.call_sync("https://openrouter.ai/api/v1", "key", {"model": "m"})

    msg = out["choices"][0]["message"]
    assert msg["content"] == "WINNER: B\nCONFIDENCE: 0.7"
    assert msg["role"] == "assistant"
    assert out["choices"][0]["finish_reason"] == "stop"
    assert out["model"] == "z-ai/glm-5.3-flash" and out["provider"] == "Crusoe"
    assert out["usage"]["completion_tokens"] == 50

    # The request was actually streamed (idle-timeout semantics) and asked for usage.
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["stream_options"] == {"include_usage": True}


def test_call_sync_collects_reasoning_and_reports_deltas(monkeypatch) -> None:
    _install(monkeypatch, _sse(
        {"choices": [{"index": 0, "delta": {"reasoning": "thinking..."}}]},
        {"choices": [{"index": 0, "delta": {"content": "answer"}}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ))
    seen: list[str] = []
    out = ai_client.call_sync("https://openrouter.ai/api/v1", "key", {}, on_delta=seen.append)

    assert out["choices"][0]["message"]["content"] == "answer"
    assert out["choices"][0]["message"]["reasoning"] == "thinking..."
    assert seen == ["answer"]


def test_call_sync_falls_back_to_a_plain_json_body(monkeypatch) -> None:
    # A provider that ignores `stream` answers with one (pretty-printed) object.
    blob = b'{\n  "model": "m",\n  "choices": [{"message": {"role": "assistant", "content": "hi"}}]\n}\n'
    _install(monkeypatch, blob)
    out = ai_client.call_sync("https://openrouter.ai/api/v1", "key", {})
    assert out["choices"][0]["message"]["content"] == "hi"


def test_call_sync_raises_on_an_empty_stream(monkeypatch) -> None:
    _install(monkeypatch, b"")
    with pytest.raises(ai_client.AiResponseError):
        ai_client.call_sync("https://openrouter.ai/api/v1", "key", {})


def test_streamed_tie_break_response_parses(monkeypatch, tmp_path) -> None:
    """End-to-end: a streamed reply drives the real tie-break parser."""
    from pathlib import Path

    from tabs.image_gallery.services import vlm

    _install(monkeypatch, _sse(
        {"choices": [{"index": 0, "delta": {"content": "WINNER: A\nCONFIDENCE: 0.9\nREASON: sharper"}}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ))
    raw = ai_client.call_sync("https://openrouter.ai/api/v1", "key", {"model": "m"})
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    result = vlm.parse_tie_break_response(raw, model="m", path_a=Path(a), path_b=Path(b))
    assert result.winner_path.endswith("a.png")
