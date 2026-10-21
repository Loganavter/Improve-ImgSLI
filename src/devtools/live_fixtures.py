#!/usr/bin/env python3
"""Deterministic inputs for the figures a still surface cannot show.

Devtool only. ``help_figures.py`` builds widget figures and ``help_live.py``
drives a running app; this module supplies the *content* they cannot carry:

* :func:`make_demo_video` — a byte-reproducible H.264 clip for the video editor.
* :func:`set_clipboard_image` — an X clipboard image owned for a with-block.
* :func:`ai_stub_server` — one fixed OpenAI-compatible chat answer, no key or
  network.

Import is side-effect free: no display, no ``QApplication``, no child process
and no app runtime until a function is called (pinned by
``tests/devtools/test_live_fixtures.py``). The encoder is pinned (libx264, CRF
0, ``+bitexact``, metadata stripped, one thread), so identical arguments give
identical bytes; the test asserts the hash instead of trusting it.
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

#: Fixed id on ``GET /v1/models`` (and the fallback request model); never a real one.
STUB_MODEL_ID = "stub-model"
STUB_CREATED = 1_700_000_000

DEFAULT_VIDEO_SECONDS = 6.0
DEFAULT_VIDEO_SIZE = (640, 360)
VIDEO_FPS = 30
CLIPBOARD_READY_TIMEOUT_S = 10.0
#: A raw ffmpeg log is hundreds of lines; only the last few explain a failure.
_TAIL_LINES = 24


class FixtureError(RuntimeError):
    """A fixture could not be produced; the message names the next action."""


def _tail(text: str | bytes | None, *, lines: int = _TAIL_LINES) -> str:
    if not text:
        return "(no output)"
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    kept = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(kept[-lines:]) or "(no output)"


def _require_tool(name: str, hint: str) -> str:
    found = shutil.which(name)
    if not found:
        raise FixtureError(f"{name} not found on PATH; hint: {hint}")
    return found


# --- Video -----------------------------------------------------------------


def make_demo_video(
    path: Path,
    *,
    seconds: float = DEFAULT_VIDEO_SECONDS,
    size: tuple[int, int] = DEFAULT_VIDEO_SIZE,
) -> Path:
    """Write a deterministic test clip for the video-editor figures.

    ``testsrc2`` supplies moving content and a sine tone supplies audio, so the
    editor has a real duration, real frames and a waveform. Raises
    :class:`FixtureError` when the size cannot be encoded (yuv420p needs even
    sides), when ffmpeg/ffprobe is absent or fails (stderr tail included), or
    when the written file misses the requested size or duration (±0.1 s).
    """
    path = Path(path)
    width, height = int(size[0]), int(size[1])
    if seconds <= 0:
        raise FixtureError(f"seconds must be > 0, got {seconds!r}")
    if width <= 0 or height <= 0:
        raise FixtureError(f"size must be positive, got {width}x{height}")
    if width % 2 or height % 2:
        # ffmpeg's testsrc2 silently rounds an odd side down, so without this
        # the fixture would be a different size than the caller asked for.
        raise FixtureError(
            f"{width}x{height}: H.264 yuv420p needs even width and height; "
            "hint: use an even size such as 640x360"
        )

    ffmpeg = _require_tool("ffmpeg", "install ffmpeg (the clip is generated, not committed)")
    ffprobe = _require_tool("ffprobe", "install ffprobe alongside ffmpeg")
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "lavfi",
        "-i", f"testsrc2=size={width}x{height}:rate={VIDEO_FPS}:duration={seconds:g}",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds:g}",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-threads", "1",
        "-crf", "0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        # bitexact on the format and each codec drops the encoder version
        # strings/timestamps that would otherwise differ between hosts.
        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-movflags", "+faststart", "-f", "mp4", str(path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=max(60.0, seconds * 30.0)
        )
    except subprocess.TimeoutExpired as exc:
        raise FixtureError(
            f"ffmpeg timed out after {exc.timeout:.0f}s; hint: shorten seconds or check the encoder"
        ) from exc
    if result.returncode != 0:
        raise FixtureError(f"ffmpeg failed (exit {result.returncode}):\n{_tail(result.stderr)}")

    _check_video(ffprobe, path, width=width, height=height, seconds=seconds)
    return path


def _check_video(ffprobe: str, path: Path, *, width: int, height: int, seconds: float) -> None:
    """Post-check the written file instead of trusting ffmpeg's exit code."""
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ],
        capture_output=True, text=True, timeout=60.0,
    )
    if result.returncode != 0:
        raise FixtureError(f"ffprobe failed on {path.name}:\n{_tail(result.stderr)}")
    try:
        payload = json.loads(result.stdout)
        stream = (payload.get("streams") or [])[0]
        got_size = (int(stream["width"]), int(stream["height"]))
        got_seconds = float(payload["format"]["duration"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FixtureError(f"ffprobe returned no usable video stream for {path.name}: {exc}") from exc

    if got_size != (width, height):
        raise FixtureError(
            f"{path.name}: requested {width}x{height}, ffmpeg wrote "
            f"{got_size[0]}x{got_size[1]}; hint: yuv420p needs even dimensions"
        )
    if abs(got_seconds - seconds) > 0.1:
        raise FixtureError(
            f"{path.name}: requested {seconds:g}s, ffprobe reports {got_seconds:g}s "
            "(tolerance 0.1s)"
        )


# --- Clipboard -------------------------------------------------------------

#: Runs in a child process: X11 clipboard ownership dies with its process, so
#: the child blocks in the Qt event loop until the parent terminates it.
#: ``ready`` on stdout is the handshake — before it, the selection is not set.
_CLIPBOARD_CHILD = r"""
import sys

from PySide6.QtGui import QGuiApplication, QImage

app = QGuiApplication(sys.argv[:1])
image = QImage(sys.argv[1])
if image.isNull():
    print("could not load image: " + sys.argv[1], file=sys.stderr, flush=True)
    raise SystemExit(3)
app.clipboard().setImage(image)
app.processEvents()
print("ready", flush=True)
raise SystemExit(app.exec())
"""


class ClipboardImage:
    """Owns the X clipboard of the current DISPLAY for as long as it is alive."""

    def __init__(self, pid: int, process: subprocess.Popen) -> None:
        self.pid = int(pid)
        self._process = process

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Stop the owner child and reap it (no zombie, no lingering selection)."""
        process = self._process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def set_clipboard_image(path: Path) -> ClipboardImage:
    """Put *path* on the X clipboard until the returned object is closed.

    A helper process sets the image and stays in its Qt event loop (X11
    ownership needs a live client); :class:`ClipboardImage` terminates it. The
    parent waits for a ``ready`` handshake (≤10 s), so a caller can paste
    immediately. Raises :class:`FixtureError` without a ``DISPLAY`` (with the
    Xvfb hint), if the image is missing, or if the child never became ready
    (its stderr tail is included).
    """
    if not (os.environ.get("DISPLAY") or "").strip():
        raise FixtureError(
            "clipboard needs a live X display; hint: start a private Xvfb "
            "(e.g. `Xvfb :91 -screen 0 1400x1000x24 &`) and export DISPLAY=:91"
        )
    path = Path(path)
    if not path.is_file():
        raise FixtureError(f"clipboard image not found: {path}")

    env = dict(os.environ)
    # The caller may itself run under the offscreen Qt platform (tests do);
    # the child must talk to the real X server to own the selection.
    env["QT_QPA_PLATFORM"] = "xcb"
    process = subprocess.Popen(
        [sys.executable, "-c", _CLIPBOARD_CHILD, str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
        env=env, text=True,
    )
    clip = ClipboardImage(process.pid, process)
    try:
        _await_clipboard_ready(process, CLIPBOARD_READY_TIMEOUT_S)
    except BaseException:
        clip.close()
        raise
    return clip


def _await_clipboard_ready(process: subprocess.Popen, timeout: float) -> None:
    """Read stdout until the ``ready`` line, the child dies, or *timeout*."""
    assert process.stdout is not None
    fd = process.stdout.fileno()
    os.set_blocking(fd, False)
    buffered = b""
    deadline = time.monotonic() + timeout
    while True:
        if b"ready\n" in buffered:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FixtureError(
                "clipboard helper did not report 'ready' within "
                f"{timeout:.0f}s; stderr:\n{_clipboard_stderr(process)}"
            )
        if process.poll() is not None:
            try:  # one last drain: "ready" may race with a fast exit
                buffered += os.read(fd, 65536)
            except (BlockingIOError, OSError):
                pass
            if b"ready\n" in buffered:
                return
            raise FixtureError(
                "clipboard helper exited before it owned the selection "
                f"(code {process.returncode}); stderr:\n{_clipboard_stderr(process)}"
            )
        try:
            ready, _, _ = select.select([fd], [], [], min(0.1, remaining))
        except InterruptedError:
            continue
        if not ready:
            continue
        try:
            buffered += os.read(fd, 65536)
        except (BlockingIOError, OSError):
            continue


def _clipboard_stderr(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return _tail(process.stderr.read() if process.stderr is not None else None)


@dataclass(frozen=True)
class _Answer:
    """Resolved fixture answer: the message content plus an optional full body."""

    content: Any
    completion: dict | None


def _load_answer(answer: dict | str | Path) -> _Answer:
    if isinstance(answer, Path):
        try:
            return _load_answer(json.loads(Path(answer).read_text(encoding="utf-8")))
        except OSError as exc:
            raise FixtureError(f"could not read stub answer {answer}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FixtureError(f"stub answer {answer} is not JSON: {exc}") from exc
    if isinstance(answer, str):
        return _Answer(answer, None)
    if isinstance(answer, dict):
        if "choices" in answer:
            try:
                return _Answer(answer["choices"][0]["message"]["content"], dict(answer))
            except (IndexError, KeyError, TypeError) as exc:
                raise FixtureError(
                    "stub answer with 'choices' needs choices[0].message.content"
                ) from exc
        if "content" in answer:
            return _Answer(answer["content"], None)
        return _Answer(answer, None)
    raise FixtureError(f"stub answer must be a dict, str or Path, got {type(answer).__name__}")


def _completion_body(answer: _Answer, model: str) -> dict:
    if answer.completion is not None:
        return answer.completion
    message = {"role": "assistant", "content": answer.content}
    return {
        "id": "chatcmpl-stub", "object": "chat.completion",
        "created": STUB_CREATED, "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
    }


def _stream_text(answer: _Answer) -> str:
    content = answer.content
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)


def _sse_body(answer: _Answer, model: str) -> bytes:
    chunk = {
        "id": "chatcmpl-stub", "object": "chat.completion.chunk",
        "created": STUB_CREATED, "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": _stream_text(answer)},
            "finish_reason": None,
        }],
    }
    final = {
        "id": "chatcmpl-stub", "object": "chat.completion.chunk",
        "created": STUB_CREATED, "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return (
        f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
        "data: [DONE]\n\n"
    ).encode("utf-8")


def _error(message: str) -> dict:
    return {"error": {"message": message, "type": "invalid_request_error"}}


class _StubServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], answer: _Answer, requests: list[dict]):
        self.answer = answer
        self.recorded = requests
        super().__init__(address, _StubHandler)


class _StubHandler(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible surface: models, chat completions, 404 JSON."""

    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib name
        """Silence the default stderr access log (a fixture is not a server)."""

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]
        self._record("GET", path, None, b"")
        if path.rstrip("/") != "/v1/models":
            self._send_json(404, _error(f"no route {self.path}"))
            return
        self._send_json(200, {
            "object": "list",
            "data": [{"id": STUB_MODEL_ID, "object": "model",
                      "created": STUB_CREATED, "owned_by": "live-fixtures"}],
        })

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._record("POST", path, None, raw)
            self._send_json(400, _error("body is not JSON"))
            return
        if not isinstance(body, dict):
            self._record("POST", path, None, raw)
            self._send_json(400, _error("body must be a JSON object"))
            return
        self._record("POST", path, body, raw)
        if path.rstrip("/") != "/v1/chat/completions":
            self._send_json(404, _error(f"no route {path}"))
            return
        server = self.server
        assert isinstance(server, _StubServer)
        model = str(body.get("model") or STUB_MODEL_ID)
        if body.get("stream"):
            payload = _sse_body(server.answer, model)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
            return
        self._send_json(200, _completion_body(server.answer, model))

    def _record(self, method: str, path: str, body: dict | None, raw: bytes) -> None:
        server = self.server
        assert isinstance(server, _StubServer)
        #: Recorded verbatim so a test can prove the body shape the app sent.
        server.recorded.append({
            "method": method,
            "path": path,
            "body": body,
            "headers": dict(self.headers),
            "raw": raw.decode("utf-8", "replace"),
        })

    def _send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
        self.wfile.flush()


class AiStub:
    """A running OpenAI-compatible stub; close it with ``with`` or :meth:`close`."""

    def __init__(self, server: _StubServer) -> None:
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="live-fixtures-ai-stub", daemon=True
        )
        self._thread.start()
        self.port = int(server.server_address[1])
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        #: Every request seen, in arrival order: method, path, parsed body,
        #: headers and raw body.
        self.requests: list[dict] = server.recorded

    def __enter__(self) -> "AiStub":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Stop the server and join its thread (the port is free afterwards)."""
        if self._thread.is_alive():
            self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        if self._thread.is_alive():  # pragma: no cover - shutdown() is bounded
            raise FixtureError("AI stub thread did not stop")


def ai_stub_server(answer: dict | str | Path, *, port: int = 0) -> AiStub:
    """Serve ``/v1/chat/completions`` and ``/v1/models`` on localhost.

    *answer* is the fixed reply: a plain string becomes
    ``choices[0].message.content``, a dict is either a full completion (when it
    carries ``choices``) or the content mapping, and a :class:`~pathlib.Path`
    is read as JSON. The non-streaming JSON response and the streaming SSE
    response (``data: …`` chunks then ``data: [DONE]``) carry the same answer.

    Bound to ``127.0.0.1`` only; ``port=0`` picks a free port. Every request is
    recorded on :attr:`AiStub.requests`; unknown paths answer 404 JSON.
    """
    requests: list[dict] = []
    server = _StubServer(("127.0.0.1", int(port)), _load_answer(answer), requests)
    return AiStub(server)
