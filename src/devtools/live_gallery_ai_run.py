#!/usr/bin/env python3
"""Run ONE gallery AI analysis on a live app and print a verdict — deterministically.

Why this exists (2026-10-26): the first version of this proof was a shell
one-liner with `sleep 30` / `sleep 280` between steps. It "worked" by timing
luck, could print a summary even when the folder never opened, and burned five
minutes of wall clock doing nothing. A live proof needs THREE things this tool
guarantees instead:

1. **Condition waits, never sleeps.** The control socket is awaited by
   existence, every control call is checked for `ok`, and the run is declared
   finished by a LOG condition (`judge run done` + no `analyze …` line for a
   quiet window), not by a timeout guess.
2. **One verdict, not a log dump.** It prints a JSON summary with the numbers a
   proof is about (cards, misses, hits, calls, profile source, pairwise lines)
   and exits non-zero when the run did not settle.
3. **It drives what the operator would drive**: opens the gallery tab, drops the
   folder, switches the judgment domain to AI (the only way the pointwise judge
   starts), and stops the app it started — it never touches another instance.

Usage (inside a lease, so XDG/display/control dir are already isolated):

    IMGSLI_CONTROL=1 IMGSLI_AI_DEBUG=1 DISPLAY=:NN \
      venv/bin/python src/devtools/live_gallery_ai_run.py \
        --folder /path/to/images [--domain ai|algorithms]
        [--timeout 420] [--quiet 12]

`--lease <name>` allocates a lease itself (`live-lease alloc`), exports it, and
releases it on the way out — for a proof that does not have one yet.

Exit codes: 0 settled, 3 did not settle in time, 4 the app could not be driven
(socket/control/tab failure), 2 usage.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PY = REPO_ROOT / "venv" / "bin" / "python"

DOMAIN_LABEL_SUFFIX = {
    "ai": "gallery_toolbar_domain_switch_ai",
    "algorithms": "gallery_toolbar_domain_switch",
}


def _socket_path() -> Path:
    override = (os.environ.get("IMGSLI_MCP_CONTROL_SOCKET") or "").strip()
    if override:
        return Path(override)
    control_dir = (os.environ.get("IMGSLI_CONTROL_DIR") or "").strip()
    if control_dir:
        return Path(control_dir) / "control.sock"
    return Path.home() / ".local" / "share" / "BlinkTable" / "run" / "control.sock"


class Control:
    """Minimal one-line-JSON client; every call is checked, never assumed."""

    def __init__(self, path: Path, *, timeout: float = 180.0) -> None:
        self.path = path
        self.timeout = timeout

    def call(self, method: str, **params) -> dict:
        request: dict = {"id": 1, "method": method}
        if params:
            request["params"] = params
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect(str(self.path))
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
            raw = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                raw += chunk
                if b"\n" in chunk:
                    break
        reply = json.loads(raw.decode("utf-8", "replace").splitlines()[0])
        if not reply.get("ok"):
            raise RuntimeError(f"{method} failed: {reply}")
        return reply.get("result") or {}


def _wait_for(predicate, *, timeout: float, interval: float, what: str):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise TimeoutError(f"timed out after {timeout:.0f}s waiting for {what}")


def _log_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _count(lines: list[str], needle: str) -> int:
    return sum(1 for line in lines if needle in line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--domain", choices=sorted(DOMAIN_LABEL_SUFFIX), default="ai")
    parser.add_argument("--timeout", type=float, default=420.0)
    parser.add_argument("--quiet", type=float, default=12.0, help="seconds of no new analyze line = settled")
    parser.add_argument("--log", type=Path, default=Path("/tmp/opencode/live_gallery_ai_run.log"))
    parser.add_argument("--keep-app", action="store_true", help="do not stop the app on exit")
    parser.add_argument("--require-judge", action="store_true",
                        help="settle only on an explicit 'judge run done' (proofs that must spend calls)")
    args = parser.parse_args(argv)

    if not args.folder.is_dir():
        print(f"not a folder: {args.folder}", file=sys.stderr)
        return 2

    python = VENV_PY if VENV_PY.is_file() else Path(sys.executable)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    log_handle = args.log.open("w", encoding="utf-8")
    env = dict(os.environ)
    env.setdefault("IMGSLI_CONTROL", "1")
    env.setdefault("IMGSLI_AI_DEBUG", "1")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    app = subprocess.Popen(  # noqa: S603 — a fixed argv, no shell
        [str(python), str(REPO_ROOT / "src" / "__main__.py")],
        cwd=str(REPO_ROOT),
        stdout=log_handle,
        stderr=log_handle,
        env=env,
    )
    summary: dict = {"folder": str(args.folder), "domain": args.domain, "pid": app.pid, "log": str(args.log)}
    try:
        sock = _socket_path()
        _wait_for(lambda: sock.exists() and sock.is_socket(), timeout=90, interval=0.5,
                  what=f"the control socket at {sock}")
        control = Control(sock)

        _wait_for(lambda: control.call("ping").get("pong"), timeout=60, interval=1.0, what="ping")
        control.call("open_tab", tab="image_gallery")
        routed = control.call("open_folder", path=str(args.folder), tab="image_gallery")
        if not routed.get("routed"):
            print(f"folder not routed: {routed}", file=sys.stderr)
            return 4

        wanted = DOMAIN_LABEL_SUFFIX[args.domain]

        def current_domain():
            """The domain the app restored, from its own log.

            Clicking the AI switch when AI is ALREADY active flips it OFF — the
            first version of this tool did exactly that on a second run (a
            restored ``judgment_domain=ai``), so the run produced no analysis at
            all and the wait timed out. Read the state, then act.
            """
            lines = _log_lines(args.log)
            for line in reversed(lines):
                if "judgment domain ->" in line:
                    return line.rsplit("->", 1)[1].split()[0].strip().lower()
                if "view restored: judgment_domain=" in line:
                    return line.split("judgment_domain=", 1)[1].split()[0].strip().lower()
            return ""

        def find_switch():
            elements = (control.call("ui_elements").get("elements") or [])
            for element in elements:
                if str(element.get("label", "")).endswith(wanted):
                    return element.get("id")
            return None

        element_id = _wait_for(find_switch, timeout=120, interval=2.0, what=f"a visible {wanted} control")
        seen = current_domain()
        summary["domain_restored"] = seen or "unknown"
        if seen == args.domain:
            summary["switch"] = "already-active"
        else:
            control.call("ui_click", id=element_id)
            summary["switch"] = element_id
            _wait_for(lambda: current_domain() == args.domain, timeout=60, interval=1.0,
                      what=f"the judgment domain to become {args.domain}")

        # The run is settled when the judge reported a total AND no analyze line
        # has appeared for `--quiet` seconds (a late card would break the proof).
        routed_at = time.monotonic()

        def settled() -> bool:
            """Quiet, plus at least one analysis OR an explicit judge verdict.

            An all-HIT run never logs ``judge run done`` — the first version of
            this tool therefore reported "did not settle" for a PERFECT second
            run, which is the opposite of the truth. A routed folder plus a
            quiet window plus one observed analysis line (start or cache hit)
            is the honest condition; ``--require-judge`` keeps the strict form
            for proofs that need a real run.
            """
            lines = _log_lines(args.log)
            analysed = _count(lines, "analyze start") + _count(lines, "analyze cache HIT")
            judged = _count(lines, "judge run done")
            if args.require_judge and not judged:
                return False
            if not analysed and not judged:
                return False
            if (time.monotonic() - routed_at) < min(args.quiet, 15.0):
                return False
            return (time.time() - args.log.stat().st_mtime) >= args.quiet

        _wait_for(settled, timeout=args.timeout, interval=2.0, what="the judge run to settle")

        lines = _log_lines(args.log)
        summary.update(
            settled=True,
            analyze_starts=_count(lines, "analyze start"),
            analyze_misses=_count(lines, "analyze MISS"),
            judge_calls=[line.split("judge run done:")[1].strip() for line in lines if "judge run done:" in line],
            profile_sources=[
                line.split("profile source:")[1].strip()[:80]
                for line in lines
                if "profile source:" in line
            ],
            jev_applied=[line.split("jev rank applied:")[1].strip()[:90]
                         for line in lines if "jev rank applied:" in line],
            pairwise=[line.split("[ai] ")[1][:110] for line in lines if "judge_pairwise" in line],
            errors=_count(lines, "Traceback"),
        )
        return 0
    except TimeoutError as exc:
        summary.update(settled=False, reason=str(exc))
        return 3
    except Exception as exc:  # noqa: BLE001 — a failed drive is exit 4, never a traceback dump
        summary.update(settled=False, reason=f"{type(exc).__name__}: {exc}")
        return 4
    finally:
        if not args.keep_app:
            app.terminate()
            try:
                app.wait(timeout=15)
            except subprocess.TimeoutExpired:
                app.kill()
        log_handle.close()
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
