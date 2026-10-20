#!/usr/bin/env python3
"""Measure the canonical MCP gallery loop's call cost against a live app.

``plan-mcp-agent-ergonomics-2026-10-20`` states its headline number as an
estimate: "the canonical scenario is 8-12 calls; target <= 5". That number was
read off agent transcripts, not measured. This probe measures it: it attaches
to an *already running* instance over the same control socket the MCP proxy
uses (``mcp-server/app/live.py`` owns discovery) and walks ``open_tab ->
open_folder -> wait_for(job_settled) -> ui_elements -> ui_click ->
wait_for(overlay) -> nav_key -> capture_surface``.

Two of those tools have no one-to-one control method, so their semantics are
spelled out client-side: wait_for polls ``jobs_list`` (job_settled) or
``ui_elements`` (role) exactly as ``backend.wait_for`` does — each poll is a
real wire call and is counted — and ``capture_surface`` with no surface is the
live ``capture_live`` call, whose ``method``/``rhi_layers`` provenance is kept.

Protocol choice: **one persistent connection**, one request id per call,
newline-delimited JSON ``{"id","method","params"}`` ->
``{"id","ok","result"|"error","hint"}`` — the proxy's own client shape, so
"one call" == "one request on the wire" stays unambiguous.

Without a live socket the tool exits 2 with a one-line "no live instance"; it
starts no display and no app. Stdlib only (the MCP protocol is frozen; a second
importer would couple the two) and Qt-free, so it runs headless.

Usage:
  python src/devtools/scenario_cost.py --folder /path/to/demo/images
  python src/devtools/scenario_cost.py --socket SOCK --folder DIR --budget 5 --json
  python src/devtools/scenario_cost.py --dry-run --folder DIR   # plan only
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

#: The plan this probe measures (quoted in ``--help``; lives outside this repo).
PLAN_ID = "plan-mcp-agent-ergonomics-2026-10-20"
SCENARIO_NAME = "canonical-image-gallery"
DEFAULT_BUDGET, ESTIMATE_CALLS = 5, (8, 12)  # the plan's target vs. its estimate
TAB = "image_gallery"  # every step is aimed at the plan's sample tab
KIND_GALLERY_POOL = "gallery_pool"
# The Quick Look overlay's observable inventory signal: its preview canvas is a
# ``QRhiWidget`` (role ``canvas``); the overlay frame is a plain widget with no
# role of its own (see ``core/control/elements/roles.py``).
OVERLAY_ROLE = "canvas"
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_WAIT_TIMEOUT_MS, DEFAULT_POLL_MS = 15_000, 100
MAX_SKIPPED_LINES = 100  # noise bound from the proxy's client
CONTROL_SOCKET_NAME, INSTANCE_POINTER_NAME = "control.sock", "instance.json"
SOCKET_OVERRIDE_ENV, CONTROL_DIR_ENV = "IMGSLI_MCP_CONTROL_SOCKET", "IMGSLI_CONTROL_DIR"

#: (step name, wire method, plan text) in execution order.
STEP_PLAN: tuple[tuple[str, str, str], ...] = (
    ("open_tab", "open_tab", 'open_tab {tab: "image_gallery"}'),
    ("open_folder", "open_folder", 'open_folder {path: <folder>, tab: "image_gallery"}'),
    ("wait_for:job_settled", "jobs_list", 'wait_for {job_settled: true, job_kind: "gallery_pool"}'),
    ("ui_elements", "ui_elements", 'ui_elements {scope: "image_gallery"}'),
    ("ui_click", "ui_click", "ui_click {id: <first card>}"),
    ("wait_for:element", "ui_elements", 'wait_for {role: "canvas"}'),
    ("nav_key", "nav_key", 'nav_key {keys: "Down,Down"}'),
    ("capture_surface", "capture_live", "capture_surface {} -> capture_live"),
)
WIRE_METHODS = {name: method for name, method, _plan in STEP_PLAN}

class ControlUnavailable(Exception):
    """No live instance answered: the socket is missing, refused, or closed."""

class ControlError(Exception):
    """The live app answered ``ok: false`` — the app's own refusal, not ours."""
    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message); self.message, self.hint = message, hint

class ControlClient:
    """One persistent connection to the app's control socket."""
    def __init__(self, socket_path: Path | str, *, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self.socket_path, self.timeout = Path(socket_path), float(timeout)
        self._sock: socket.socket | None = None
        self._buffer, self._counter = b"", 0
    def _connect(self) -> socket.socket:
        if self._sock is not None:
            return self._sock
        if not self.socket_path.exists():
            raise ControlUnavailable(f"no live instance: no socket at {self.socket_path}")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
        except OSError as exc:
            sock.close()
            raise ControlUnavailable(f"no live instance: cannot connect: {exc}") from None
        self._sock, self._buffer = sock, b""
        return sock
    def _read(self, sock: socket.socket, request_id: int) -> dict:
        deadline, skipped = time.monotonic() + self.timeout, 0
        while True:
            if b"\n" not in self._buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ControlUnavailable("sent, no reply: timed out waiting for the app")
                sock.settimeout(remaining)
                try:
                    chunk = sock.recv(65536)
                except OSError as exc:  # includes socket.timeout
                    raise ControlUnavailable(f"sent, no reply: socket read failed: {exc}") from None
                if not chunk:
                    raise ControlUnavailable("sent, no reply: the app closed the control socket")
                self._buffer += chunk
                continue
            line, self._buffer = self._buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                message = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                message = None
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
            # A notification or stale frame: ignore it, but never loop on a
            # stream that only emits noise.
            skipped += 1
            if skipped > MAX_SKIPPED_LINES:
                raise ControlUnavailable("sent, no reply: no response with our request id")
    def call(self, method: str, params: dict | None = None) -> dict:
        self._counter += 1
        request_id = self._counter
        payload = json.dumps({"id": request_id, "method": method, "params": params or {}},
                             ensure_ascii=False)
        try:
            self._connect().sendall(payload.encode("utf-8") + b"\n")
        except ControlUnavailable:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise ControlUnavailable(f"not sent: control socket write failed: {exc}") from None
        try:
            message = self._read(self._sock, request_id)  # type: ignore[arg-type]
        except ControlUnavailable:
            self.close()
            raise
        if message.get("ok") is not True:
            hint = message.get("hint")
            raise ControlError(str(message.get("error") or f"{method} failed"),
                               str(hint) if hint else None)
        result = message.get("result")
        return result if isinstance(result, dict) else {}
    def close(self) -> None:
        sock, self._sock = self._sock, None
        self._buffer = b""
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

def _is_socket(path: Path) -> bool:
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False

def _pointer_socket(directory: Path) -> Path | None:
    """The socket named by ``instance.json``, else the sibling control socket.

    The pid is not consulted: the probe only needs a place to try.
    """
    candidate = directory / CONTROL_SOCKET_NAME
    try:
        data = json.loads((directory / INSTANCE_POINTER_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    field_value = data.get("socket") if isinstance(data, dict) else None
    if isinstance(field_value, str) and field_value.strip():
        pointed = Path(field_value.strip()).expanduser()
        if _is_socket(pointed):
            return pointed
    return candidate if _is_socket(candidate) else None

def _socket_in_dir(directory: Path) -> Path | None:
    return _pointer_socket(directory) if directory.is_dir() else None

def discover_socket(env: Mapping[str, str] | None = None) -> Path | None:
    """Locate the control socket, or ``None`` when no instance is attachable.

    Priority (the app's own order): ``IMGSLI_MCP_CONTROL_SOCKET`` -> an explicit
    ``IMGSLI_CONTROL_DIR`` -> ``$XDG_RUNTIME_DIR`` when writable -> the app data
    ``run`` dir. Nothing usable reads "no live instance", never an error.
    """
    source = dict(os.environ) if env is None else env
    explicit = (source.get(SOCKET_OVERRIDE_ENV) or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if _is_socket(path) else None
    override_dir = (source.get(CONTROL_DIR_ENV) or "").strip()
    if override_dir:
        return _socket_in_dir(Path(override_dir).expanduser())
    runtime = (source.get("XDG_RUNTIME_DIR") or "").strip()
    if runtime and os.path.isdir(runtime) and os.access(runtime, os.W_OK):
        found = _socket_in_dir(Path(runtime))
        if found is not None:
            return found
    base = source.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return _socket_in_dir(Path(base) / "ImproveImgSLI" / "run")

@dataclass
class StepResult:
    """One logical step: what was attempted, how it ended, what it cost."""
    name: str
    method: str
    status: str  # "ok" | "error" | "blocked"
    detail: str = ""
    wire_calls: int = 0
    def to_dict(self) -> dict[str, Any]:
        return {"step": self.name, "method": self.method, "status": self.status,
                "ok": self.status == "ok", "detail": self.detail, "wire_calls": self.wire_calls}

@dataclass
class Report:
    """The whole run: per-step results plus the counted wire requests."""
    socket: str
    folder: str
    budget: int
    steps: list[StepResult] = field(default_factory=list)
    calls: int = 0
    capture_method: str | None = None
    capture_rhi_layers: int | None = None
    @property
    def over_budget(self) -> bool: return self.calls > self.budget
    @property
    def capture_provenance(self) -> str:
        if self.capture_method and self.capture_rhi_layers is not None:
            return "method+rhi_layers"
        missing = [n for n, ok in (("method", bool(self.capture_method)),
                                   ("rhi_layers", self.capture_rhi_layers is not None)) if not ok]
        return "incomplete:" + ",".join(missing)
    def to_dict(self) -> dict[str, Any]:
        return {"scenario": SCENARIO_NAME, "plan": PLAN_ID, "socket": self.socket,
                "folder": self.folder, "calls": self.calls, "budget": self.budget,
                "over_budget": self.over_budget, "estimate": list(ESTIMATE_CALLS),
                "steps": [step.to_dict() for step in self.steps],
                "provenance": {"source": "live", "capture": self.capture_provenance,
                               "method": self.capture_method,
                               "rhi_layers": self.capture_rhi_layers}}

class ScenarioRunner:
    """Walks the canonical sequence over one client, counting wire calls."""
    def __init__(self, client: Any, *, folder: Path, socket_label: str,
                 budget: int = DEFAULT_BUDGET, wait_timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
                 poll_ms: int = DEFAULT_POLL_MS,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.client, self.folder = client, folder
        self.report = Report(socket=socket_label, folder=str(folder), budget=budget)
        self.wait_timeout_ms, self.poll_ms = int(wait_timeout_ms), max(int(poll_ms), 1)
        self.sleep, self.transport_dead = sleep, False
        # The card chosen by ``ui_elements``; the click reuses it instead of
        # re-reading the inventory (a read the real scenario never makes).
        self.card_id = ""
    def _wire(self, method: str, params: dict | None = None) -> tuple[dict | None, str | None]:
        """One wire request; ``(result, error)``. Every attempt is counted."""
        self.report.calls += 1
        try:
            return self.client.call(method, params), None
        except ControlUnavailable as exc:
            self.transport_dead = True
            return None, f"unavailable: {exc}"
        except ControlError as exc:
            hint = f" ({exc.hint})" if exc.hint else ""
            return None, f"app refused: {exc.message}{hint}"
    def _finish(self, name: str, status: str, detail: str, start: int) -> StepResult:
        step = StepResult(name, WIRE_METHODS[name], status, detail, self.report.calls - start)
        self.report.steps.append(step); return step
    def _blocked(self, name: str, reason: str) -> None:
        # Issues nothing, so the count still reflects only attempted calls.
        self._finish(name, "blocked", f"blocked:{reason}", self.report.calls)
    def _simple(self, name: str, params: dict,
                describe: Callable[[dict], tuple[str, str]]) -> None:
        """One request plus a result-derived verdict (tab/folder/click/keys)."""
        start = self.report.calls
        result, error = self._wire(WIRE_METHODS[name], params)
        if error:
            self._finish(name, "error", error, start)
            return
        status, detail = describe(result or {})
        self._finish(name, status, detail, start)
    def _poll(self, name: str, params: dict,
              observe: Callable[[dict], tuple[bool, str]],
              timeout_detail: Callable[[str], str], start: int) -> StepResult:
        """Poll until ``observe`` holds; a timeout is a normal blocked result
        carrying the last observed state (MCP wait_for semantics), not a crash.
        """
        deadline, polls = time.monotonic() + self.wait_timeout_ms / 1000.0, 0
        while True:
            polls += 1
            result, error = self._wire(WIRE_METHODS[name], params)
            if error:
                return self._finish(name, "error", error, start)
            matched, detail = observe(result or {})
            if matched:
                return self._finish(name, "ok", f"{detail} after {polls} poll(s)", start)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self._finish(name, "blocked", timeout_detail(detail), start)
            self.sleep(min(self.poll_ms / 1000.0, remaining))
    def _open_tab(self) -> None:
        self._simple("open_tab", {"tab": TAB},
                     lambda r: ("ok", f"tab={r.get('tab', TAB)} via={r.get('via', 'action')}"))
    def _open_folder(self) -> None:
        # ``routed: false`` is the proxy's honest "the tab did not take it":
        # a failed step, not a crash.
        self._simple("open_folder", {"path": str(self.folder), "tab": TAB},
                     lambda r: ("ok" if r.get("routed") is not False else "error",
                                f"tab={r.get('tab', TAB)} routed={r.get('routed')}"))
    def _wait_for_jobs(self) -> None:
        """``wait_for {job_settled: true}``: poll ``jobs_list`` until clear."""
        def observe(result: dict) -> tuple[bool, str]:
            rows = [r for r in result.get("jobs") or [] if isinstance(r, dict)]
            pending = [r for r in rows if r.get("kind") == KIND_GALLERY_POOL]
            # ``jobs_list`` only lists active passes, so "no row" is "settled".
            if pending:
                return False, f"{len(pending)} {KIND_GALLERY_POOL} row(s) still running"
            return True, "settled"
        self._poll("wait_for:job_settled", {}, observe,
                   lambda detail: f"blocked:job_settled timeout after "
                                  f"{self.wait_timeout_ms} ms ({detail})", self.report.calls)
    def _ui_elements(self) -> StepResult:
        start = self.report.calls
        result, error = self._wire("ui_elements", {"scope": TAB})
        if error:
            return self._finish("ui_elements", "error", error, start)
        rows = [r for r in (result or {}).get("elements") or [] if isinstance(r, dict)]
        cards = [r for r in rows
                 if r.get("role") == "card" and r.get("visible") and r.get("enabled")]
        detail = f"{len(rows)} element(s), {len(cards)} card(s)"
        if not cards:
            return self._finish("ui_elements", "blocked",
                                f"blocked:no-card-in-ui_elements ({detail})", start)
        self.card_id = str(cards[0].get("id") or "")
        return self._finish("ui_elements", "ok", f"{detail}, first={self.card_id}", start)
    def _click(self) -> None:
        self._simple("ui_click", {"id": self.card_id},
                     lambda r: ("ok" if r.get("clicked", True) else "error",
                                f"id={self.card_id}"))
    def _wait_for_overlay(self) -> None:
        """``wait_for {element: <overlay>}``: poll ``ui_elements`` for the canvas."""
        def observe(result: dict) -> tuple[bool, str]:
            rows = [r for r in result.get("elements") or [] if isinstance(r, dict)]
            found = next((r for r in rows if r.get("role") == OVERLAY_ROLE
                          and r.get("visible") and r.get("enabled")), None)
            if found is None:
                return False, f"no visible+enabled role={OVERLAY_ROLE!r} element"
            return True, f"id={found.get('id')} role={OVERLAY_ROLE}"
        self._poll("wait_for:element", {"scope": TAB, "include_disabled": True}, observe,
                   lambda detail: f"blocked:overlay timeout after "
                                  f"{self.wait_timeout_ms} ms ({detail})", self.report.calls)
    def _nav_key(self) -> None:
        # ``activated: false`` means the window was not OS-active, so the keys
        # measured nothing a real keyboard could reach either: not ok.
        def describe(result: dict) -> tuple[str, str]:
            handled = [str(s.get("handled")) for s in result.get("steps") or []
                       if isinstance(s, dict)]
            activated = result.get("activated")
            return ("ok" if activated is not False else "error",
                    f"handled={','.join(handled) or '<none>'} activated={activated}")
        self._simple("nav_key", {"keys": "Down,Down"}, describe)
    def _capture(self) -> None:
        start = self.report.calls
        result, error = self._wire("capture_live", {})
        if error:
            self._finish("capture_surface", "error", error, start)
            return
        method, raw = (result or {}).get("method"), (result or {}).get("rhi_layers")
        layers = raw if isinstance(raw, int) and not isinstance(raw, bool) else None
        self.report.capture_method = str(method) if method else None
        self.report.capture_rhi_layers = layers
        missing = [n for n, ok in (("method", bool(method)), ("rhi_layers", layers is not None))
                   if not ok]
        detail = f"method={method} rhi_layers={raw}" + (
            f" missing={','.join(missing)}" if missing else "")
        self._finish("capture_surface", "ok" if not missing else "error", detail, start)
    def run(self) -> Report:
        for step in (self._open_tab, self._open_folder, self._wait_for_jobs):
            step()
            if self.transport_dead:
                return self._skip_rest()
        elements = self._ui_elements()
        if self.transport_dead:
            return self._skip_rest()
        if elements.status != "ok":
            # Nothing to click: the rest has no prerequisite. Name it.
            self._blocked("ui_click", "no-card-in-ui_elements")
            self._blocked("wait_for:element", "no-overlay-to-wait-for")
            self._blocked("nav_key", "no-overlay-to-navigate")
            self._blocked("capture_surface", "no-overlay-to-capture")
            return self.report
        for step in (self._click, self._wait_for_overlay, self._nav_key, self._capture):
            step()
            if self.transport_dead:
                return self._skip_rest()
        return self.report
    def _skip_rest(self) -> Report:
        """Transport is gone: report the rest as blocked, not crash."""
        seen = {step.name for step in self.report.steps}
        for name, _method, _plan in STEP_PLAN:
            if name not in seen:
                self._blocked(name, "transport-failure")
        return self.report

def format_plan(folder: Path | None, budget: int) -> str:
    lines = [f"scenario: {SCENARIO_NAME}", f"plan: {PLAN_ID}", f"folder: {folder if folder is not None else '<folder>'}",
             f"budget: {budget} (the plan's estimate was "
             f"{ESTIMATE_CALLS[0]}-{ESTIMATE_CALLS[1]} calls; target <= {budget})",
             "steps (every wire request counts, including wait_for polls):"]
    lines += [f"  {i}. {name:<20} {plan}" for i, (name, _m, plan) in enumerate(STEP_PLAN, 1)]
    lines.append("dry-run: nothing was sent")
    return "\n".join(lines)

def format_summary(report: Report) -> str:
    lines = [f"scenario: {SCENARIO_NAME}", f"plan: {PLAN_ID}", f"socket: {report.socket}",
             f"folder: {report.folder}", "steps:"]
    for index, step in enumerate(report.steps, start=1):
        lines.append(f"  {index}. {step.name:<20} {step.status:<7} method={step.method} "
                     f"calls={step.wire_calls} {step.detail}".rstrip())
    lines += [f"calls={report.calls}",
              f"budget: {report.calls}/<={report.budget}"
              f"{' EXCEEDED' if report.over_budget else ''}",
              f"provenance: source=live capture={report.capture_provenance}"]
    return "\n".join(lines)

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scenario_cost",
        description=("Measure the canonical MCP gallery loop against a live app and count "
                     "the wire calls it really costs. The plan's 8-12 figure was an "
                     "estimate read off agent transcripts; this is the probe behind it."),
        epilog=(f"Budget rationale: {PLAN_ID} calls the canonical loop 8-12 calls and "
                f"sets a target of <= {DEFAULT_BUDGET}. Each logical step is one MCP tool call, "
                "but this probe counts the transport honestly: a wait_for step polls (jobs_list "
                "or ui_elements), so the measured number can exceed the logical step count. "
                "Exit codes: 0 within budget, 1 over budget, 2 no live instance/folder."),
    )
    parser.add_argument("--socket", metavar="PATH",
                        help="control socket; default: proxy discovery "
                        f"({SOCKET_OVERRIDE_ENV}, {CONTROL_DIR_ENV}, $XDG_RUNTIME_DIR, app data)")
    parser.add_argument("--folder", metavar="PATH", help="demo folder of images (required to run)")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, metavar="M",
                        help=f"fail (exit 1) above M wire calls (default {DEFAULT_BUDGET})")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, send nothing")
    parser.add_argument("--wait-timeout-ms", type=int, default=DEFAULT_WAIT_TIMEOUT_MS,
                        metavar="MS", help="budget for one wait_for step")
    parser.add_argument("--poll-ms", type=int, default=DEFAULT_POLL_MS, metavar="MS",
                        help="floor between wait_for polls")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, metavar="S",
                        help="one request/response round-trip budget")
    return parser

def main(argv: Sequence[str] | None = None, *, client: Any | None = None,
         env: Mapping[str, str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    folder = Path(args.folder).expanduser() if args.folder else None
    if args.dry_run:
        print(format_plan(folder, args.budget)); return 0
    if folder is None:
        print("error: no demo folder: pass --folder PATH (a folder of images)"); return 2
    if not folder.is_dir():
        print(f"error: demo folder does not exist: {folder}"); return 2
    socket_path: Path | None = None
    if client is None:
        socket_path = Path(args.socket).expanduser() if args.socket else discover_socket(env)
        if socket_path is None:
            print("no live instance: no control socket found (start the app with control on)")
            return 2
        client = ControlClient(socket_path, timeout=args.timeout)
    runner = ScenarioRunner(
        client, folder=folder,
        socket_label=str(socket_path) if socket_path is not None else "<injected client>",
        budget=args.budget, wait_timeout_ms=args.wait_timeout_ms, poll_ms=args.poll_ms)
    try:
        report = runner.run()
    finally:
        try:
            client.close()
        except Exception:
            pass
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
          if args.json else format_summary(report))
    return 1 if report.over_budget else 0

if __name__ == "__main__":
    sys.exit(main())
