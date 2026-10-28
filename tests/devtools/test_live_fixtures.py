"""``live_fixtures`` — deterministic video, X clipboard and AI stub.

No display is required: the clipboard cases skip when ``DISPLAY`` is unset, and
the ffmpeg cases skip when the tools are missing. The point of the suite is that
each fixture is *checkable* rather than merely plausible: the clip is probed
with ffprobe and hashed twice, the stub is asked through urllib and its recorded
body is read back, and the module is imported in a child process with no display
and no ffmpeg.

Falsification: a base checkout has no ``src/devtools/live_fixtures.py``, so the
module import fails and every test below errors. A clip that is not
byte-reproducible (unpinned encoder/threads/metadata) fails the hash assertion;
an SSE path that returns a plain JSON body fails the ``data: [DONE]`` assert.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from devtools import live_fixtures as lf

REPO_ROOT = Path(__file__).resolve().parents[2]
_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
requires_ffmpeg = pytest.mark.skipif(
    not _HAS_FFMPEG, reason="ffmpeg/ffprobe not installed on this host"
)


@pytest.fixture()
def scratch() -> Path:
    """Scratch inside the clone (not /tmp), removed even when a test fails."""
    path = Path(tempfile.mkdtemp(prefix=".live-fixtures-test-", dir=REPO_ROOT))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# --- video ------------------------------------------------------------------


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,pix_fmt,r_frame_rate",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ],
        capture_output=True, text=True, timeout=60, check=True,
    )
    payload = json.loads(result.stdout)
    stream = (payload["streams"] or [])[0]
    return {
        "codec": stream["codec_name"],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "pix_fmt": stream["pix_fmt"],
        "fps": stream["r_frame_rate"],
        "duration": float(payload["format"]["duration"]),
    }


@requires_ffmpeg
def test_demo_video_is_640x360_six_seconds_and_byte_reproducible(scratch):
    path = scratch / "demo.mp4"

    returned = lf.make_demo_video(path)

    assert returned == path and path.is_file() and path.stat().st_size > 0
    probed = _probe(path)
    assert (probed["width"], probed["height"]) == (640, 360)
    assert probed["duration"] == pytest.approx(6.0, abs=0.1)
    assert probed["codec"] == "h264"
    assert probed["pix_fmt"] == "yuv420p"
    assert probed["fps"] == "30/1"

    first = hashlib.sha256(path.read_bytes()).hexdigest()
    lf.make_demo_video(path)
    second = hashlib.sha256(path.read_bytes()).hexdigest()
    assert first == second, "the clip encoder is not deterministic (threads/metadata pins?)"


@requires_ffmpeg
def test_demo_video_honours_a_custom_size_and_duration(scratch):
    path = scratch / "small.mp4"

    lf.make_demo_video(path, seconds=2.0, size=(320, 240))

    probed = _probe(path)
    assert (probed["width"], probed["height"]) == (320, 240)
    assert probed["duration"] == pytest.approx(2.0, abs=0.1)


def test_odd_size_is_a_hinted_fixture_error_not_a_crash(scratch):
    path = scratch / "odd.mp4"

    with pytest.raises(lf.FixtureError) as exc:
        lf.make_demo_video(path, size=(641, 360), seconds=1.0)

    message = str(exc.value)
    assert "even" in message, "an odd side must name the yuv420p constraint"
    assert "hint" in message and not path.exists()


def test_missing_ffmpeg_is_a_named_fixture_error(scratch, monkeypatch):
    monkeypatch.setenv("PATH", "")

    with pytest.raises(lf.FixtureError, match=r"ffmpeg not found"):
        lf.make_demo_video(scratch / "x.mp4", seconds=1.0)


# --- AI stub ----------------------------------------------------------------


def _post(url: str, body: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=10)


def _post_json(url: str, body: dict) -> dict:
    with _post(url, body) as response:
        return json.loads(response.read())


def test_stub_answers_chat_and_records_the_request_body():
    chat = {"model": "vision-model", "messages": [{"role": "user", "content": "describe"}],
            "temperature": 0}
    with lf.ai_stub_server("fixed answer") as stub:
        assert stub.base_url == f"http://127.0.0.1:{stub.port}/v1"

        reply = _post_json(stub.base_url + "/chat/completions", chat)

        assert reply["choices"][0]["message"]["content"] == "fixed answer"
        recorded = stub.requests[-1]
        assert recorded["method"] == "POST"
        assert recorded["path"] == "/v1/chat/completions"
        assert recorded["body"]["model"] == "vision-model"
        assert recorded["body"]["messages"] == chat["messages"]


def test_stub_streams_sse_chunks_and_done_with_the_same_answer():
    body = {"model": "vision-model", "stream": True, "messages": [
        {"role": "user", "content": "describe"}]}
    with lf.ai_stub_server("fixed answer") as stub:
        with _post(stub.base_url + "/chat/completions", body) as response:
            assert response.headers["Content-Type"].startswith("text/event-stream")
            text = response.read().decode("utf-8")

    events = [line[len("data: "):] for line in text.splitlines() if line.startswith("data: ")]
    assert events and events[-1] == "[DONE]", "an SSE answer must terminate with [DONE]"
    first = json.loads(events[0])
    assert first["choices"][0]["delta"]["content"] == "fixed answer"
    assert stub.requests[-1]["body"]["stream"] is True


def test_stub_models_endpoint_advertises_one_model():
    with lf.ai_stub_server("x") as stub:
        with urllib.request.urlopen(stub.base_url + "/models", timeout=10) as response:
            payload = json.loads(response.read())

    assert payload["object"] == "list"
    assert [model["id"] for model in payload["data"]] == [lf.STUB_MODEL_ID]
    assert stub.requests[-1]["method"] == "GET"


def test_stub_unknown_path_is_404_json_and_recorded():
    with lf.ai_stub_server("x") as stub:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(stub.base_url + "/nope", timeout=10)

        assert exc.value.code == 404
        payload = json.loads(exc.value.read())
        assert payload["error"]["message"] == "no route /v1/nope"
        assert stub.requests[-1]["path"] == "/v1/nope"


def test_stub_reads_a_json_answer_from_disk(scratch):
    answer = {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "from disk"},
                "finish_reason": "stop",
            }
        ]
    }
    path = scratch / "answer.json"
    path.write_text(json.dumps(answer), encoding="utf-8")

    with lf.ai_stub_server(path) as stub:
        reply = _post_json(
            stub.base_url + "/chat/completions",
            {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert reply["choices"][0]["message"]["content"] == "from disk"


def test_a_router_answers_each_question_shape_differently():
    """One stub, two questions: the profile proposal and the scorecard.

    A real AI-domain run asks both, and the two answers have different JSON
    shapes (a LIST of axis proposals vs an OBJECT of axis scores), so a single
    fixed reply cannot serve a run. The router sees the request body, which is
    the only place the difference is visible.
    """
    profile_answer = {"axes": [{"name": "halation", "label": "Halation",
                                "definition": "0 = none, 100 = everywhere",
                                "scale": "0-100", "direction": "lower-is-better"}]}
    scorecard_answer = {"axes": {"sharpness": 37}, "reason": "stub"}

    def router(body):
        # A real API puts JSON TEXT in ``content``, so a router answering a
        # parser must serialize: a dict here would arrive as an object and the
        # app's parser (which json.loads a string) would call it empty.
        text = json.dumps(body)
        chosen = profile_answer if "FROM 5 TO 8 axes" in text else scorecard_answer
        return json.dumps(chosen)

    with lf.ai_stub_server(router) as stub:
        first = _post_json(stub.base_url + "/chat/completions", {
            "model": "m",
            "messages": [{"role": "user", "content": "name FROM 5 TO 8 axes"}],
        })
        second = _post_json(stub.base_url + "/chat/completions", {
            "model": "m",
            "messages": [{"role": "user", "content": "score this frame"}],
        })

    assert json.loads(first["choices"][0]["message"]["content"]) == profile_answer
    assert json.loads(second["choices"][0]["message"]["content"]) == scorecard_answer
    assert len(stub.requests) == 2


def test_a_failing_router_answers_500_json_instead_of_dropping_the_connection():
    def router(body):
        raise RuntimeError("router exploded")

    with lf.ai_stub_server(router) as stub:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _post_json(stub.base_url + "/chat/completions", {"model": "m", "messages": []})

    assert exc.value.code == 500
    payload = json.loads(exc.value.read())
    assert "router exploded" in payload["error"]["message"]


def test_stub_close_frees_the_port_and_stops_its_thread():
    stub = lf.ai_stub_server("x")
    port = stub.port

    stub.close()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))  # a second bind must succeed
    finally:
        sock.close()
    assert not any(
        thread.name == "live-fixtures-ai-stub" and thread.is_alive()
        for thread in threading.enumerate()
    )


# --- clipboard --------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _try_read_clipboard():
    """Read the in-process clipboard, or ``None`` when that is not possible.

    Under the offscreen platform a process-local clipboard has nothing to do
    with the X selection, so the caller falls back to the ownership check.
    """
    if os.environ.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}:
        return None
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        image = app.clipboard().image()
        return None if image.isNull() else image
    except Exception:  # a platform plugin mismatch must not fail the suite
        return None


def test_clipboard_without_display_names_the_xvfb_hint(scratch, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)

    with pytest.raises(lf.FixtureError) as exc:
        lf.set_clipboard_image(scratch / "unused.png")

    message = str(exc.value)
    assert "X display" in message and "Xvfb" in message


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a live X display")
def test_clipboard_image_is_readable_and_owner_survives(scratch):
    from PIL import Image

    png = scratch / "clip.png"
    Image.new("RGB", (16, 12), (180, 20, 20)).save(png)

    clip = lf.set_clipboard_image(png)
    try:
        assert clip.pid > 0
        read = _try_read_clipboard()
        time.sleep(1.0)
        assert _pid_alive(clip.pid), "the owner child must stay alive to own the selection"
        if read is not None:
            assert not read.isNull()
    finally:
        pid = clip.pid
        clip.close()

    assert not _pid_alive(pid), "closing must reap the owner (no zombie)"


# --- import purity ----------------------------------------------------------


def test_import_is_side_effect_free_without_display_or_ffmpeg():
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    env["PATH"] = ""  # no ffmpeg, no ffprobe
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import sys\n"
        "import devtools.live_fixtures\n"
        "assert 'PySide6' not in sys.modules, 'import must not touch Qt'\n"
        "assert not [n for n in sys.modules if n.split('.')[0] in "
        "{'core', 'ui', 'tabs', 'plugins', 'shared'}], 'import must not touch the app'\n"
        "print('pure')\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "pure"
