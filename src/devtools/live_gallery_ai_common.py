#!/usr/bin/env python3
"""Shared half of the AI-domain live proofs: fixtures, stub answers, readings.

Split out of ``live_gallery_ai_chain`` (file-size policy) when that tool grew
the reset scenario. Everything here is used by BOTH proofs and by nothing in the
product: a series generator whose variants stay one perceptual group, the stub's
three answer shapes, the live cache readings and the process hygiene a live run
needs (a leftover app and a stale socket are the two ways these proofs fail).

Devtool only: no Qt import at module level, no display, no app runtime.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from pathlib import Path

#: The free axis no local detector can produce: if it appears in the AI record
#: with this score, the judge's number came from the answer and from nowhere
#: else. Distinctive on purpose (a plausible local value is not a proof).
JUDGE_ONLY_AXIS = "halation"
JUDGE_SCORE = 91
#: A registry axis the judge is also asked for. The local stage-2 lanes measure
#: their own number for it; the AI domain must show THIS one.
SHARED_AXIS = "sharpness"
JUDGE_SHARED_SCORE = 37
#: Local-only axes (never asked of the judge) that must stay out of the AI entry.
LOCAL_ONLY_AXES = ("ssim", "brisket", "entropy")

PROFILE_ANSWER = {
    "axes": [
        "sharpness",
        "noise",
        "exposure",
        {
            "name": JUDGE_ONLY_AXIS,
            "label": "Halation",
            "definition": "how far bright edges bleed into their surroundings; 0 = clean, 100 = glowing",
            "scale": "0-100",
            "direction": "lower-is-better",
            "why": "the sunset variant bleeds the most, the flat grey the least",
        },
        {
            "name": "micro_contrast",
            "label": "Micro contrast",
            "definition": "local tonal separation in midtones; 0 = flat, 100 = crisp",
            "scale": "0-100",
            "direction": "higher-is-better",
            "why": "the textured variant separates midtones the flat one does not",
        },
        {
            "name": "colour_banding",
            "label": "Colour banding",
            "definition": "visible steps in a smooth gradient; 0 = none, 100 = everywhere",
            "scale": "0-100",
            "direction": "lower-is-better",
            "why": "the gradient variant shows steps the photo variant cannot",
        },
    ]
}

SCORECARD_ANSWER = {
    "axes": {
        SHARED_AXIS: JUDGE_SHARED_SCORE,
        "noise": 12,
        "exposure": 88,
        JUDGE_ONLY_AXIS: JUDGE_SCORE,
        "micro_contrast": 64,
        "colour_banding": 23,
    },
    "reason": "stub scorecard",
    "defects": [],
    "axis_proposals": [],
    "confidence": 0.7,
}


def _socket_target() -> str:
    explicit = os.environ.get("IMGSLI_MCP_CONTROL_SOCKET")
    if explicit:
        return explicit
    return str(Path(os.environ.get("IMGSLI_CONTROL_DIR", "")) / "control.sock")


def _cache_files() -> list[Path]:
    out: list[Path] = []
    for kind in ("gallery_ai_cache", "gallery_local_metrics", "gallery_jev_cache", "gallery_vlm_cache"):
        directory = _cache_dir(kind)
        if not directory.is_dir():
            continue
        out.extend(p for p in directory.glob("*.json") if p.name != "version.json")
    return out


def _line_ms(line: str) -> int:
    """Wall-clock ms of a log line (``YYYY-MM-DD HH:MM:SS,mmm``), 0 when absent."""
    try:
        stamp = line.split(" - ")[0].strip()
        parsed = time.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f")
        return int(time.mktime(parsed) * 1000) + int(stamp[-3:])
    except Exception:
        return 0


def _stub_router(delay_s: float = 0.0):
    """One stub, three question shapes: profile, pairwise, scorecard."""

    def router(body: dict) -> str:
        if delay_s:
            time.sleep(delay_s)
        text = json.dumps(body, ensure_ascii=False)
        if "FROM 5 TO 8 axes" in text:
            return json.dumps(PROFILE_ANSWER, ensure_ascii=False)
        if "WINNER" in text.upper():
            return "WINNER: A"
        # The prompt is JSON-encoded inside the body, so its quotes arrive
        # escaped: match the bare word, not a quoted token (measured: a quoted
        # match never fired and the ranker got a scorecard -> "unusable response").
        if "ranking" in text or "rank aliases" in text:
            aliases = sorted(set(re.findall(r"img_\d+", text)), key=lambda a: int(a[4:]))
            return json.dumps(
                {"ranking": aliases, "score": 0.9, "reason": "stub rank"},
                ensure_ascii=False,
            )
        return json.dumps(SCORECARD_ANSWER, ensure_ascii=False)

    return router


def make_images(folder: Path, count: int) -> list[Path]:
    """A SERIES: one scene, small differences — dHash must keep them together.

    The gallery groups a series by perceptual hash (hamming <= 10) and the Jev
    rank needs a series of >= 2, so four unrelated pictures would prove the
    scorecard and nothing about ranking. Variants differ by a couple of levels
    of brightness and a sub-pixel blur, which a person sees and a dHash does not.
    """
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

    folder.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGB", (900, 600), (24, 28, 32))
    draw = ImageDraw.Draw(base)
    for step in range(0, 900, 18):
        shade = 40 + (step * 7) % 190
        draw.line([(step, 0), (step, 600)], fill=(shade, shade // 2 + 20, 90))
    for row in range(0, 600, 28):
        draw.line([(0, row), (900, row)], fill=(200, 180, 120))
    draw.ellipse([(120, 90), (420, 330)], fill=(210, 150, 60))
    draw.rectangle([(520, 200), (820, 470)], fill=(60, 90, 140))
    made: list[Path] = []
    for index in range(count):
        image = ImageEnhance.Brightness(base).enhance(1.0 + index * 0.03)
        if index % 2:
            image = image.filter(ImageFilter.GaussianBlur(radius=0.2 + index * 0.15))
        path = folder / f"scene_{index + 1:02d}.png"
        image.save(path)
        made.append(path)
    return made


def _cache_dir(kind: str) -> Path:
    """The app's per-kind cache directory (XDG_CACHE_HOME under a lease).

    Derived the way the app derives it — Qt's cache location is
    ``<XDG_CACHE_HOME>/<organization>/<application>`` and both names are
    ``BlinkTable`` (``src/__main__.py``) — with a rename-proof glob fallback so
    an app rename cannot silently read zero entries and "prove" a false negative.
    """
    root = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    direct = root / "BlinkTable" / "BlinkTable" / kind
    if direct.is_dir():
        return direct
    for candidate in sorted(root.glob(f"*/{'*'}/%s" % kind)):
        if candidate.is_dir():
            return candidate
    return direct


def _read_entries(kind: str) -> list[dict]:
    out: list[dict] = []
    directory = _cache_dir(kind)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        if path.name == "version.json":
            continue
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def _ai_axes(entries: list[dict]) -> list[dict]:
    """``{axes, profile_axes}`` per AI cache entry (shape-tolerant)."""
    rows = []
    for entry in entries:
        axes = entry.get("axes")
        rows.append({
            "axes": axes if isinstance(axes, dict) else {},
            "model": entry.get("model"),
            "answered_model": entry.get("answered_model"),
        })
    return rows


def _local_axis_values(entries: list[dict]) -> dict[str, float]:
    """Axis → value from the LOCAL metrics entries (stage-2 records)."""
    values: dict[str, float] = {}
    for entry in entries:
        for record in entry.get("analysis") or ():
            if not isinstance(record, dict):
                continue
            axis = str(record.get("axis") or record.get("id") or "")
            value = record.get("value")
            if axis and isinstance(value, (int, float)):
                values.setdefault(axis, float(value))
    return values


def _kill_leftover_apps() -> list[int]:
    """Kill app processes carrying THIS lease, before a run starts.

    ``--keep-app`` is how the tool queries a live app, so any failure path used
    to leave the app running; the next run then found a foreign app on the same
    display/profile holding a socket the harness had already unlinked (measured
    2026-10-28: two runs in a row waited 90 s for a socket nobody would create).
    Selection is by the process's own ``LIVE_LEASE`` environment, never by a
    command-line pattern (a pattern matches the shell running the kill).
    """
    lease = os.environ.get("LIVE_LEASE", "")
    if not lease:
        return []
    needle = f"LIVE_LEASE={lease}".encode()
    killed: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        try:
            environ = (entry / "environ").read_bytes()
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if needle not in environ or b"__main__.py" not in cmdline:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except OSError:
            continue
    return killed


def _stop_app(pid: int) -> None:
    """SIGTERM the app we started, wait, and drop its socket file.

    A leftover socket from a killed app makes the NEXT run connect to a dead
    address while ``wait_for(sock.exists())`` sees a file and passes — measured
    2026-10-28: the run failed with ``ConnectionRefusedError`` on a socket whose
    owner was already gone.
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.5)
    for key in ("IMGSLI_MCP_CONTROL_SOCKET",):
        path = os.environ.get(key)
        if path:
            try:
                Path(path).unlink()
            except OSError:
                pass


def _control_client(sock: Path):
    """The minimal control client (imported lazily: the module is a script)."""
    src = Path(__file__).resolve().parents[1]
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from devtools.live_gallery_ai_run import Control

    return Control(sock)
