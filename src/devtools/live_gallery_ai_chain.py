#!/usr/bin/env python3
"""Prove the AI-domain chains on a LIVE app against a local stub — one verdict.

Why this exists (2026-10-28, W7 of the backend-isolation plan): the live proof
that needs no provider covered the Algorithms domain. The AI domain needs a
model answer, and the honest way to get one without the owner's keyring is the
AI stub (``live_fixtures.ai_stub_server``) in an isolated ``XDG_CONFIG_HOME``.
A real AI-domain run asks TWO different questions — the metric-profile proposal
wants a JSON *list* of axes, the scorecard a JSON *object* of scores — so the
stub is given a router and the two answers are distinguishable by value.

What it asserts (each one is a plan invariant, not a screenshot):

1. the app really talked to the stub: the router served the profile answer and
   at least one scorecard answer, and the request carried the image;
2. the judge's axes are the numbers the ANSWER carried: every AI cache entry
   holds the stub's distinctive score (the free axis nobody local can measure);
3. local numbers never arrive as judge values: the same picture's LOCAL metrics
   entry exists (the stage-2 lanes still run) and its value for the axis the
   judge also answered is a DIFFERENT number, so a substitution would show;
4. the profile the run used named the judge's free axes (the log's own line);
5. the gallery ranked, i.e. the numbers reached the ranker (``jev rank``).

Usage (inside a lease, so XDG/display/control dir are already isolated):

    IMGSLI_CONTROL=1 IMGSLI_TRACE=1 DISPLAY=:NN \\
      venv/bin/python src/devtools/live_gallery_ai_chain.py [--images 4]

``--lease <name>`` allocates a lease itself and releases it on the way out.

Exit codes: 0 every assertion held, 1 an assertion failed, 3 the run did not
settle, 4 the app could not be driven, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PY = REPO_ROOT / "venv" / "bin" / "python"

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
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from devtools.live_gallery_ai_run import Control

    return Control(sock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=None, help="series to open (made when absent)")
    parser.add_argument("--images", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--quiet", type=float, default=12.0)
    parser.add_argument("--delay", type=float, default=0.0, help="stub latency per answer (a slow provider)")
    parser.add_argument("--artifact", type=Path, default=Path("/tmp/opencode/w7-ai-chain.png"))
    parser.add_argument("--log", type=Path, default=Path("/tmp/opencode/w7-ai-chain.log"))
    parser.add_argument("--out", type=Path, default=Path("/tmp/opencode/w7-ai-chain.json"))
    parser.add_argument("--keep-app", action="store_true")
    parser.add_argument("--lease", default=None, help="allocate and release a lease for this proof")
    args = parser.parse_args(argv)

    lease = None
    if args.lease:
        from devtools import live_lease

        lease = live_lease.alloc(lane="gallery-judge-axes", task=args.lease)
        os.environ.update(lease.env)

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from devtools import help_live, live_fixtures

    folder = (args.folder or Path("/tmp/opencode/w7-ai-chain-series")).resolve()
    make_images(folder, max(2, args.images))

    verdict: dict = {"folder": str(folder), "domain": "ai", "lease": os.environ.get("LIVE_LEASE")}
    stub = live_fixtures.ai_stub_server(_stub_router(args.delay))
    app_pid: int | None = None
    try:
        config_home = os.environ.get("XDG_CONFIG_HOME")
        profile = help_live.write_profile(
            Path("/tmp/opencode/w7-ai-chain-root"),
            locale="en",
            theme="dark",
            width=1600,
            height=1000,
            extra_sections=help_live.ai_profile_sections(stub),
            config_home=Path(config_home) if config_home else None,
        )
        verdict["profile_conf"] = str(profile)
        verdict["stub_base_url"] = stub.base_url

        os.environ["IMGSLI_TRACE"] = "1"
        from devtools import live_gallery_ai_run as driver

        code = driver.main([
            "--folder", str(folder),
            "--domain", "ai",
            "--timeout", str(args.timeout),
            "--quiet", str(args.quiet),
            "--log", str(args.log),
            "--require-judge",
            "--keep-app",
        ])
        verdict["driver_exit"] = code
        if code != 0:
            verdict["reason"] = "the driver did not settle"
            return code if code in (2, 3, 4) else 1

        sock = Path(os.environ["IMGSLI_MCP_CONTROL_SOCKET"]) if os.environ.get(
            "IMGSLI_MCP_CONTROL_SOCKET"
        ) else Path(os.environ.get("IMGSLI_CONTROL_DIR", "")) / "control.sock"
        control = _control_client(sock)
        ping = control.call("ping")
        app_pid = int(ping.get("pid") or 0) or None
        verdict["app_pid"] = app_pid

        # The AI tail settling is NOT the local pass settling: the stage-2 lanes
        # keep measuring (measured 2026-10-28 — reading/killing right after the
        # judge finished found an empty local-metrics cache and would have
        # "proved" the local side absent).
        settled_local = False
        deadline = time.monotonic() + 150.0
        while time.monotonic() < deadline:
            state_now = control.call("get_state", path="tabs.image_gallery").get("state") or {}
            size = int(state_now.get("metrics_cache_size") or 0)
            count = int(state_now.get("item_count") or 0)
            if count and size >= count:
                settled_local = True
                break
            time.sleep(1.5)
        verdict["local_pass_settled"] = settled_local

        try:
            trace = control.call("query_trace", filter=JUDGE_ONLY_AXIS, n=40)
            verdict["trace_hits"] = [
                {"kind": row.get("kind"), "summary": str(row.get("summary"))[:120]}
                for row in (trace.get("records") or [])
            ][:12]
        except Exception as exc:  # noqa: BLE001 - a trace is evidence, not a gate
            verdict["trace_hits"] = f"unavailable: {type(exc).__name__}: {exc}"

        try:
            control.call("capture_live", path=str(args.artifact))
            verdict["artifact"] = str(args.artifact)
        except Exception as exc:  # noqa: BLE001
            verdict["artifact"] = f"capture failed: {type(exc).__name__}: {exc}"

        state = control.call("get_state", path="tabs.image_gallery")
        verdict["gallery_state"] = state.get("state")
        log_tail = control.call("read_log", n=400).get("lines") or []
        verdict["log_lines"] = {
            "judge_run_done": [ln["text"] for ln in log_tail if "judge run done" in ln.get("text", "")],
            "profile_source": [ln["text"] for ln in log_tail if "profile source" in ln.get("text", "")],
            "wire": [ln["text"] for ln in log_tail if "analyze wire ready" in ln.get("text", "")][:4],
            "rank": [ln["text"] for ln in log_tail if "jev rank" in ln.get("text", "")][:8],
            "analyze_start": [ln["text"] for ln in log_tail if "analyze start" in ln.get("text", "")][:8],
        }
    finally:
        if app_pid and not args.keep_app:
            _stop_app(app_pid)
        requests = list(stub.requests)
        stub.close()
        if lease is not None:
            lease.release()

    profile_calls = [r for r in requests if "FROM 5 TO 8 axes" in json.dumps(r.get("body") or {})]
    scorecard_calls = [
        r for r in requests
        if "WINNER" not in json.dumps(r.get("body") or {}).upper()
        and "FROM 5 TO 8 axes" not in json.dumps(r.get("body") or {})
        and (r.get("body") or {}).get("messages")
    ]
    verdict["stub_calls"] = {
        "total": len(requests),
        "profile": len(profile_calls),
        "scorecard": len(scorecard_calls),
        "models": sum(1 for r in requests if str(r.get("path", "")).rstrip("/") == "/v1/models"),
    }
    verdict["scorecard_request_has_image"] = bool(
        scorecard_calls
        and "data:image" in json.dumps(scorecard_calls[0].get("body") or {})
    )

    ai_entries = _ai_axes(_read_entries("gallery_ai_cache"))
    local_entries = _read_entries("gallery_local_metrics")
    local_values = _local_axis_values(local_entries)
    verdict["ai_entries"] = ai_entries
    verdict["local_axes"] = sorted(local_values)
    verdict["local_shared_value"] = local_values.get(SHARED_AXIS)

    checks: dict[str, bool] = {
        "profile_answer_served": len(profile_calls) >= 1,
        "scorecard_answer_served": len(scorecard_calls) >= 1,
        "scorecard_carried_the_image": verdict["scorecard_request_has_image"],
        "judge_axis_in_profile_log": any(
            JUDGE_ONLY_AXIS in line for line in verdict["log_lines"]["profile_source"]
        ),
        "ai_entries_written": bool(ai_entries),
        "judge_only_axis_is_the_answer_value": bool(ai_entries) and all(
            row["axes"].get(JUDGE_ONLY_AXIS) == JUDGE_SCORE for row in ai_entries
        ),
        "shared_axis_is_the_judge_number": bool(ai_entries) and all(
            row["axes"].get(SHARED_AXIS) == JUDGE_SHARED_SCORE for row in ai_entries
        ),
        "shared_axis_local_number_differs": local_values.get(SHARED_AXIS) is not None
        and local_values.get(SHARED_AXIS) != JUDGE_SHARED_SCORE,
        "no_local_only_axis_in_the_ai_entry": bool(ai_entries) and not any(
            axis in row["axes"] for row in ai_entries for axis in LOCAL_ONLY_AXES
        ),
        "rank_reached_the_ranker": any(
            marker in line
            for line in verdict["log_lines"]["rank"]
            for marker in ("jev rank complete", "jev rank applied", "jev rank =>")
        ),
        "judge_request_carried_no_local_metrics": bool(verdict["log_lines"].get("analyze_start"))
        and all("metrics=0" in line for line in verdict["log_lines"]["analyze_start"]),
    }
    verdict["checks"] = checks
    verdict["ok"] = all(checks.values())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: verdict[k] for k in ("ok", "checks", "stub_calls", "ai_entries", "artifact")},
                     ensure_ascii=False, indent=2))
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
