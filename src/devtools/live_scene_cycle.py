#!/usr/bin/env python3
"""S3 — the full canvas scene cycle, one hop at a time, each hop observed.

Devtool only (nothing here is imported by the app runtime). It drives an
*already running* instance over the control socket and walks

    build a scene (Image Compare pair + loupes)
      -> verify it through ``get_canvas_scene`` (S1)
      -> capture a PNG
      -> record
      -> open the video editor
      -> export a video

and asserts every hop from something the app actually exposes. This is the
third phase of ``plan-canvas-scene-api-2026-10-21``; the S0 recon
(``RECON-canvas-scene-s0.md``) measured what is observable, and this tool is
written to that measurement instead of to what would be convenient.

Usage::

    # plan only: what will be asserted, and from which signal (no app needed)
    python src/devtools/live_scene_cycle.py --dry-run

    # a live run against the app on this machine (control channel on)
    python src/devtools/live_scene_cycle.py \\
        --image-a /data/left.jpg --image-b /data/right.jpg --out /tmp/cycle

    # a second run, gated against the first (PNG must be byte-identical)
    python src/devtools/live_scene_cycle.py --image-a ... --image-b ... \\
        --out /tmp/cycle2 --baseline /tmp/cycle/report.json

Exit codes: 0 every hop observed and every artifact present, 1 a hop failed or
timed out (the report carries the last observed state), 2 no live instance /
bad arguments.

## What is observed, and what is not

Each hop names its signal. There is no hop whose verdict is "it returned", and
there is no ``sleep`` used as a completion strategy: every wait is a bounded
poll of one of these conditions (timeout == failure with the last state).

===================================  ===================================  ==========================================
hop                                  observable (what is polled)          where it comes from
===================================  ===================================  ==========================================
pair loaded                          ``get_canvas_scene`` panes[].path    ``core/control/scene_read.py``
scene built / verified               the S1 scene JSON, re-read and       ``devtools/canvas_scene``
                                     compared against declared expects
PNG captured                         the artifact on disk + its            ``core/control/capture.py:208``
                                     ``rhi_layers`` (a grab with 0 means
                                     the QRhi canvas was not composited)
recording started                    the recorder's own frame trace        ``.../services/recorder.py:47-53``
                                     ``capture_frame ENTER is_recording`` (DEBUG-gated)
recording finalized                  the video editor's Find Actions        ``.../services/recording_flow.py:190``
                                     appear (the dialog is opened from
                                     ``on_recording_finalized``, and only
                                     when the recording has data)
video encoded                        ``Video export successful: <path>``    the encoder's own log line
                                     + the artifact at that path            + the export flow's
video export job                     **nothing** — video export is not a    ``core/control/jobs.py:56-64``
                                     job kind, so ``wait_for(job_settled)``
                                     cannot see it (named in ``unobservable``)
===================================  ===================================  ==========================================
Absolute citations (the short names above keep the table readable): the export
success line and the frame-count line are both in
``tabs/image_compare/plugins/video_editor/services/video_export/service.py``
(:961 success, :921 frames); the worker-owned "finished" line is in
``.../services/export_flow.py:190``; the recorder trace in
``.../services/recorder.py:47-53`` (gate) and ``:135`` (message).

The recording hop is the honest hard case: start and stop->finalize have no
Store field and no job, and their logging is DEBUG-only. So the cycle

* **start** — polls the recorder's frame trace. With ``--debug`` (logger at
  DEBUG) or ``IMGSLI_VIDEO_EDITOR_DEBUG=1`` the trace is in the log ring and the
  hop is ``observed``; without it the hop is reported ``unobservable`` **by
  name** with the reason and the substitute that carries the verdict (the
  editor-open condition below) — never silently assumed;
* **finalize** — uses the one substitute observable this tool builds
  (allowed by S3's R2, and it needs no app hook): the video editor's dialog
  contributes its Find Actions only while it is open, and it is opened from
  ``on_recording_finalized`` when a recording was pending. Waiting for those
  actions therefore *is* waiting for the finalize, through public surface.

Determinism is reported, never claimed: the still capture is a pure function of
the scene, so a second run is expected byte-identical (``--baseline`` gates it);
the recording's frame count follows **wall time** (``recorder.py:47-53``), so the
video is reported ``pinned: false`` with that reason unless the caller pins a
frame count with ``--expect-video-frames`` (then the observed count is compared).

Audit-Meta: pattern=devtool-pipeline size=exempt reason="one live-cycle contract: the hop plan, its observables, the wire client and the report shape are one document; splitting the hops from the report forks what 'observed' means"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# The transport + discovery are the MCP-ergonomics probe's own client: one
# socket protocol in the devtools (stdlib only, Qt-free), no second client.
from devtools.scenario_cost import (  # noqa: E402
    ControlClient,
    ControlError,
    ControlUnavailable,
    discover_socket,
    grow_poll_ms,
)

#: Report schema id — bumped when a field changes meaning, not when one is added.
SCHEMA = "imgsli-scene-cycle/1"
PLAN_ID = "plan-canvas-scene-api-2026-10-21"
DEFAULT_TAB = "image_compare"
DEFAULT_WAIT_S = 120.0
DEFAULT_EXPORT_S = 600.0
DEFAULT_POLL_MS = 100
DEFAULT_POLL_MAX_MS = 1000
#: One request/response round trip (the video export reply is immediate: the
#: encode runs on a worker, which is exactly why the artifact must be polled).
DEFAULT_REQUEST_TIMEOUT_S = 15.0
#: How long the *unobservable-by-design* recording-start trace is given. Short on
#: purpose: a long budget here would turn "no signal exists" into a slow timeout.
RECORDING_TRACE_BUDGET_S = 5.0
#: The artifact is written by ffmpeg before the success line is logged; this is a
#: flush grace, still a bounded poll, never a fixed wait.
ARTIFACT_SETTLE_S = 30.0

#: The two loupe centers the cycle alternates between. Idempotence matters here:
#: S2 refuses a command that changes nothing, so the cycle picks the position the
#: scene is *not* at (see ``_plan_scene_commands``).
LOUPE_POSITION_A = (0.30, 0.50)
LOUPE_POSITION_B = (0.70, 0.50)
LOUPE_SIZE = 0.22
DIVIDER_THICKNESS = 4

#: Recording-start trace (``recorder.py:47-53`` gate, message in ``_video_debug``
#: at ``recorder.py:135``). Substring, because the line also carries counters.
RECORDING_TRACE_MARKER = "capture_frame ENTER is_recording=True"
#: Video-export success lines: the encoder's "successful" line and the export
#: flow's worker-owned "finished" line (see the module docstring for the exact
#: citations).
VIDEO_SUCCESS_MARKERS = ("Video export successful: ", "Video export finished: ")
#: Failure lines worth surfacing in a timeout's last observed state.
VIDEO_FAILURE_MARKERS = ("FFmpeg exited with error code", "FFmpeg not found")
#: Frame-count line the encoder logs before rendering (cited in the docstring).
VIDEO_FRAMES_RE = re.compile(r"Rendering (\d+) frames to ")
#: Video-editor dialog Find Action prefix (``video_editor/actions.py`` PREFIX +
#: ``group.``). Registered only while the dialog is open.
EDITOR_ACTION_PREFIX = "image_compare.video_editor.group."
#: The export button's member key inside the dialog's ``video.export_actions``.
EXPORT_ACTION_SUFFIX = "image_compare.action.export_video"
#: Recording toggle action (``image_compare/actions/_common.py``) — a *toggle*,
#: handled explicitly (see ``SceneCycle._hop_record_start``), never re-run blindly.
RECORD_ACTION = "image_compare.record"
VIDEO_EDITOR_ACTION = "image_compare.video_editor"
MAGNIFIER_ENABLED_ACTION = "image_compare.magnifier.enabled"
#: Recording state slots / scene command vocabulary (S2).
MAGNIFIER_COMMAND = "magnifier.set_visible"
POSITION_COMMAND = "magnifier.set_position"
SIZE_COMMAND = "magnifier.set_size"
DIVIDER_THICKNESS_COMMAND = "divider.set_thickness"

#: Why the video cannot be promised deterministic (quoted in the report).
VIDEO_DETERMINISM_REASON = (
    "the recorder samples frames on a wall-clock timer "
    "(tabs/image_compare/plugins/video_editor/services/recorder.py:47-53), so the "
    "frame count follows how long the recording ran — a second run of the same "
    "scene produces a different clip. Pin it with --expect-video-frames only "
    "when the frame count is known in advance."
)
#: Why the video export has no job to wait on (quoted in the report).
VIDEO_JOB_REASON = (
    "video export is not a job kind (core/control/jobs.py:56-64 lists "
    "gallery_pool, metrics_pass, ai_analysis, export), so wait_for(job_settled) "
    "cannot observe it; the encode is observed through the log line + artifact"
)
#: Why the recording's start hop may be unobservable (quoted in the report).
RECORDING_START_REASON = (
    "recording start has no Store field and no job, and its trace is DEBUG-gated "
    "(tabs/image_compare/plugins/video_editor/services/recording_flow.py:190, "
    "recorder.py:47-53); the frame trace was not in the log ring, so this hop "
    "was NOT observed — the editor-open condition and the video artifact carry "
    "the verdict instead"
)

#: (step, wire method, plan text) in execution order — one source for the
#: dry-run plan, the report's ``plan`` block and ``run()``'s schedule.
STEP_PLAN: tuple[tuple[str, str, str], ...] = (
    ("open_tab", "open_tab", 'open_tab {tab: "image_compare"}'),
    ("load_pair", "open_folder", "open_folder {slot: 1} + open_folder {slot: 2} -> "
                                 "get_canvas_scene panes[].path"),
    ("build_scene", "set_scene_commands", "set_scene_commands {magnifier position/size/visible, "
                                          "divider thickness, verify: true}"),
    ("verify_scene", "get_canvas_scene",
     "get_canvas_scene -> the state this cycle promises"),
    ("capture_png", "capture_live",
     'capture_live {what: "image_compare"} -> artifact + rhi_layers'),
    ("record_start", "run_action",
     f"run_action {{{RECORD_ACTION}}} -> recorder frame trace"),
    ("scene_while_recording", "set_scene_commands",
     "set_scene_commands {loupe move} -> scene read"),
    ("stop_and_open_editor", "run_action", f"run_action {{{VIDEO_EDITOR_ACTION}}} -> "
                                           "video editor Find Actions appear"),
    ("export_video", "run_action", f"run_action {{{EXPORT_ACTION_SUFFIX}}} -> "
                                   '"Video export successful: <path>" + artifact'),
)


class CycleError(RuntimeError):
    """A hop could not be observed: the run fails, it does not pass."""


class CycleTimeout(CycleError):
    """A bounded wait expired — carries the last observation, never a pass."""

    def __init__(self, step: str, last: dict[str, Any], polls: int, budget_s: float) -> None:
        self.step, self.last, self.polls, self.budget_s = step, last, polls, budget_s
        super().__init__(
            f"{step}: no observable change within {budget_s:g}s/{polls} poll(s); "
            f"last observed: {json.dumps(last, sort_keys=True, ensure_ascii=False)}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "kind": "timeout",
            "budget_s": self.budget_s,
            "polls": self.polls,
            "message": f"no observable change within {self.budget_s:g}s ({self.polls} poll(s))",
            "last_observed": self.last,
        }


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _same_path(left: Any, right: Any) -> bool:
    """Path identity across the drop/load round trip (symlinks included)."""
    if not left or not right:
        return False
    first, second = str(left), str(right)
    if first == second:
        return True
    try:
        if os.path.normpath(first) == os.path.normpath(second):
            return True
        return os.path.realpath(first) == os.path.realpath(second)
    except OSError:
        return False


def _close(left: Any, right: Sequence[float], tolerance: float = 1e-3) -> bool:
    """Numeric equality for a scalar or a point, within a float tolerance."""
    values = list(left) if isinstance(left, (list, tuple)) else [left]
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return False
    if len(numbers) != len(right):
        return False
    return all(abs(value - float(wanted)) <= tolerance for value, wanted in zip(numbers, right))


def stage_input(path: Path, directory: Path) -> Path:
    """Put one image alone in *directory* (a symlink when possible).

    Image Compare's control verb for a targeted slot is ``open_folder`` + a
    ``slot`` hint (``open_file`` has no hint: a second ``open_file`` would land
    in slot 1 again — the tab defaults to slot 1). A folder holding exactly one
    image is therefore the honest way to name a slot, and the link keeps the
    source bytes in place.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for existing in directory.iterdir():
        if existing.is_file() or existing.is_symlink():
            existing.unlink()
    target = directory / path.name
    try:
        target.symlink_to(path)
    except OSError:
        try:
            os.link(path, target)
        except OSError:
            shutil.copyfile(path, target)
    return target


# ---------------------------------------------------------------------------
# the cycle
# ---------------------------------------------------------------------------


class SceneCycle:
    """One observed run: build -> verify -> capture -> record -> export.

    ``channel`` is anything with ``call(method, params) -> dict`` — the live
    ``ControlClient``, or a test double standing in for the app. ``clock`` and
    ``sleep`` are injected so a timeout is provable without waiting it out.
    """

    def __init__(
        self,
        *,
        channel: Any,
        out_dir: Path | str,
        tab: str = DEFAULT_TAB,
        wait_s: float = DEFAULT_WAIT_S,
        export_s: float = DEFAULT_EXPORT_S,
        poll_ms: int = DEFAULT_POLL_MS,
        poll_max_ms: int = DEFAULT_POLL_MAX_MS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        baseline: Mapping[str, Any] | None = None,
        expect_video_frames: int | None = None,
    ) -> None:
        self.channel = channel
        self.out_dir = Path(out_dir)
        self.tab = tab
        self.wait_s = float(wait_s)
        self.export_s = float(export_s)
        self.poll_ms = max(int(poll_ms), 1)
        self.poll_max_ms = max(int(poll_max_ms), self.poll_ms)
        self.clock, self.sleep = clock, sleep
        self.baseline = dict(baseline) if isinstance(baseline, Mapping) else None
        self.expect_video_frames = expect_video_frames
        self.wire_calls = 0
        self._loupe_id: str | None = None
        self.report: dict[str, Any] = self._empty_report()

    # -- report scaffolding -------------------------------------------------

    def _empty_report(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "plan": PLAN_ID,
            "ok": False,
            "tab": self.tab,
            "out_dir": str(self.out_dir),
            "wire_calls": 0,
            "budgets": {
                "wait_s": self.wait_s,
                "export_s": self.export_s,
                "poll_ms": self.poll_ms,
                "poll_max_ms": self.poll_max_ms,
            },
            "plan_steps": [
                {"step": name, "method": method, "plan": text}
                for name, method, text in STEP_PLAN
            ],
            "steps": [],
            "unobservable": [],
            "failures": [],
            "artifacts": {"png": None, "video": None},
            "scene": None,
            "scene_json": None,
            "determinism": {
                "png": {"verdict": "unknown", "sha256": None, "baseline_sha256": None},
                "video": {
                    "pinned": self.expect_video_frames is not None,
                    "expected_frames": self.expect_video_frames,
                    "observed_frames": None,
                    "reason": VIDEO_DETERMINISM_REASON,
                },
            },
        }

    def _step(
        self,
        name: str,
        observable: str,
        status: str,
        detail: str,
        **extra: Any,
    ) -> dict[str, Any]:
        record = {
            "step": name,
            "observable": observable,
            "status": status,
            "detail": detail,
        }
        record.update(extra)
        self.report["steps"].append(record)
        return record

    def _fail(self, error: dict[str, Any]) -> None:
        self.report["failures"].append(error)
        self.report["ok"] = False

    def _name_unobservable(self, step: str, reason: str, substitute: str) -> None:
        self.report["unobservable"].append(
            {"step": step, "reason": reason, "substitute": substitute}
        )

    # -- transport ----------------------------------------------------------

    def _call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """One wire call; every attempt counts (a poll is not free)."""
        self.wire_calls += 1
        result = self.channel.call(method, params or {})
        self.report["wire_calls"] = self.wire_calls
        return result if isinstance(result, dict) else {}

    def _poll(
        self,
        step: str,
        probe: Callable[[], tuple[bool, dict[str, Any]]],
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        """Poll *probe* until it reports done; a timeout raises with the last state.

        The interval only decides how often the condition is re-read; it is not
        a completion strategy (R3). The deadline is checked *after* a probe, so
        one observation always happens even with a zero budget.
        """
        deadline = self.clock() + float(timeout_s)
        interval, polls = self.poll_ms, 0
        last: dict[str, Any] = {"observed": "nothing yet"}
        while True:
            polls += 1
            matched, last = probe()
            if matched:
                return {"polls": polls, "last": last}
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise CycleTimeout(step, {**last, "polls": polls}, polls, timeout_s)
            self.sleep(min(interval / 1000.0, remaining))
            interval = grow_poll_ms(interval, self.poll_max_ms)

    # -- log ring -----------------------------------------------------------

    def _log(self, *, since: int = 0) -> list[dict[str, Any]]:
        """The app's own log ring (``n`` is 1-based, stable across polls)."""
        result = self._call("read_log", {"n": 0, "level": "DEBUG"})
        rows = [row for row in result.get("lines") or [] if isinstance(row, dict)]
        return [row for row in rows if int(row.get("n") or 0) > int(since)]

    def _log_floor(self) -> int:
        """Highest log index seen — later hops must not read an older signal."""
        result = self._call("read_log", {"n": 0})
        return int(result.get("total_lines") or 0)

    @staticmethod
    def _marker_line(rows: list[dict[str, Any]], markers: Sequence[str]) -> str | None:
        for row in rows:
            text = str(row.get("text") or "")
            if any(marker in text for marker in markers):
                return text
        return None

    def _log_tail(self, rows: list[dict[str, Any]], count: int = 12) -> list[str]:
        return [str(row.get("text") or "") for row in rows[-count:]]

    # -- scene reads --------------------------------------------------------

    def _scene(self) -> dict[str, Any]:
        return self._call("get_canvas_scene", {"tab": self.tab})

    @staticmethod
    def _pane_paths(scene: Mapping[str, Any]) -> dict[int, str | None]:
        paths: dict[int, str | None] = {}
        for row in scene.get("panes") or []:
            if not isinstance(row, Mapping):
                continue
            try:
                slot = int(row.get("slot"))
            except (TypeError, ValueError):
                continue
            paths[slot] = row.get("path")
        return paths

    # ------------------------------------------------------------------
    # hops
    # ------------------------------------------------------------------

    def _hop_open_tab(self) -> dict[str, Any]:
        result = self._call("open_tab", {"tab": self.tab})
        return {
            "status": "observed",
            "detail": f"tab={result.get('tab', self.tab)} via={result.get('via', 'action')}",
            "substitutes": [],
            "evidence": {"tab": result.get("tab", self.tab)},
        }

    def _hop_load_pair(self, image_a: Path, image_b: Path) -> dict[str, Any]:
        """Load slot 1 and slot 2 through the slot-hinted drop path."""
        staged: dict[int, Path] = {}
        for slot, source in ((1, image_a), (2, image_b)):
            staged[slot] = stage_input(source, self.out_dir / "inputs" / f"slot{slot}")
            self._call(
                "open_folder",
                {"path": str(staged[slot].parent), "tab": self.tab, "slot": slot},
            )

        def probe() -> tuple[bool, dict[str, Any]]:
            scene = self._scene()
            paths = self._pane_paths(scene)
            loaded = {
                slot: _same_path(paths.get(slot), staged[slot]) for slot in (1, 2)
            }
            state = {
                "panes": [{"slot": slot, "path": paths.get(slot)} for slot in sorted(paths)],
                "expected": {str(slot): str(staged[slot]) for slot in staged},
                "loaded": {str(slot): loaded[slot] for slot in loaded},
                "render_layout_available": (scene.get("render_layout") or {}).get("available"),
            }
            return all(loaded.values()), state

        waited = self._poll("load_pair", probe, timeout_s=self.wait_s)
        return {
            "status": "observed",
            "detail": (
                f"scene panes carry both staged inputs (slot 1 -> "
                f"{staged[1].name}, slot 2 -> {staged[2].name}) after "
                f"{waited['polls']} poll(s)"
            ),
            "substitutes": [],
            "evidence": {"panes": waited["last"].get("panes"), "staged": {
                str(slot): str(path) for slot, path in staged.items()
            }},
        }

    def _ensure_loupe(self) -> dict[str, Any]:
        """Make sure the scene has at least one magnifier instance (or say why not).

        The S2 command vocabulary *adjusts* instances; it cannot create one, and
        the only control-reachable creator is the magnifier toolbar toggle — a
        toggle, so it is pressed only when the read says there is nothing to
        adjust, and the read afterwards is the authority (a toggle that ran is
        not a loupe that exists).
        """
        scene = self._scene()
        if scene.get("magnifiers"):
            return {"pressed": False, "detail": "scene already carries a magnifier instance"}
        result = self._call("run_action", {"action_id": MAGNIFIER_ENABLED_ACTION})

        def probe() -> tuple[bool, dict[str, Any]]:
            current = self._scene()
            rows = current.get("magnifiers") or []
            return bool(rows), {
                "magnifiers": [row.get("id") for row in rows if isinstance(row, Mapping)],
                "scene_source": current.get("scene_source"),
                "unavailable": current.get("unavailable"),
            }

        try:
            waited = self._poll("build_scene", probe, timeout_s=self.wait_s)
        except CycleTimeout as exc:
            raise CycleError(
                "no magnifier instance exists and the magnifier toggle did not create "
                f"one (action={MAGNIFIER_ENABLED_ACTION!r}, ran="
                f"{bool(result.get('ran'))}). In the multi-instance UI mode the toggle "
                "only reveals an existing instance — add a loupe with the instances "
                "toolbar first, then re-run. Last scene: "
                + json.dumps(exc.last, sort_keys=True, ensure_ascii=False)
            ) from None
        return {
            "pressed": True,
            "detail": f"{MAGNIFIER_ENABLED_ACTION} created the default instance "
                      f"({waited['polls']} poll(s))",
        }

    def _plan_scene_commands(
        self, scene: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """The value-taking commands + the post-conditions they must reach.

        Every command is included only when the scene does not already hold the
        target: S2 refuses a command that changed nothing, and a recipe that
        re-sends an already-satisfied value would fail on its second run. The
        loupe position alternates (A/B), so a re-run is still a real move.
        """
        magnifiers = [row for row in scene.get("magnifiers") or [] if isinstance(row, Mapping)]
        if not magnifiers:
            raise CycleError("the scene reports no magnifier instance to command")
        index = next(
            (position for position, row in enumerate(magnifiers) if row.get("visible")), 0
        )
        row = magnifiers[index]
        model = row.get("model") or {}
        magnifier_id = str(row.get("id") or "")
        current_position = model.get("position_relative") or [0.5, 0.5]
        target_position = (
            LOUPE_POSITION_B if _close(current_position, LOUPE_POSITION_A) else LOUPE_POSITION_A
        )

        commands: list[dict[str, Any]] = []
        expects: dict[str, Any] = {}
        skipped: list[str] = []

        def add(command: dict[str, Any], expect: dict[str, Any]) -> None:
            commands.append({**command, "expect": expect})
            expects.update(expect)

        if not row.get("visible"):
            add(
                {"action": MAGNIFIER_COMMAND, "params": {"id": magnifier_id, "visible": True}},
                {f"magnifiers[{index}].visible": True},
            )
        else:
            skipped.append(f"{MAGNIFIER_COMMAND} (already visible)")

        if not _close(current_position, target_position):
            add(
                {
                    "action": POSITION_COMMAND,
                    "params": {
                        "id": magnifier_id,
                        "x": target_position[0],
                        "y": target_position[1],
                    },
                },
                {f"magnifiers[{index}].model.position_relative": list(target_position)},
            )
        else:
            skipped.append(f"{POSITION_COMMAND} (already at the target)")

        if not _close(model.get("size_relative"), [LOUPE_SIZE]):
            add(
                {"action": SIZE_COMMAND, "params": {"id": magnifier_id, "size": LOUPE_SIZE}},
                {f"magnifiers[{index}].model.size_relative": LOUPE_SIZE},
            )
        else:
            skipped.append(f"{SIZE_COMMAND} (already at the target)")

        dividers = [row for row in scene.get("dividers") or [] if isinstance(row, Mapping)]
        if dividers and float(dividers[0].get("thickness") or 0.0) != float(DIVIDER_THICKNESS):
            add(
                {
                    "action": DIVIDER_THICKNESS_COMMAND,
                    "params": {"thickness": DIVIDER_THICKNESS},
                },
                {"dividers[0].thickness": float(DIVIDER_THICKNESS)},
            )
        elif dividers:
            skipped.append(f"{DIVIDER_THICKNESS_COMMAND} (already at the target)")

        self._loupe_id = magnifier_id
        return commands, {
            "expects": expects,
            "skipped": skipped,
            "index": index,
            "position": list(target_position),
        }

    def _hop_build_scene(self) -> dict[str, Any]:
        loupe = self._ensure_loupe()
        scene = self._scene()
        commands, plan = self._plan_scene_commands(scene)
        evidence: dict[str, Any] = {"skipped": plan["skipped"], "loupe": loupe["detail"]}
        if not commands:
            return {
                "status": "observed",
                "detail": "scene already holds the declared state; no command was a no-op "
                          f"({len(plan['skipped'])} satisfied, 0 sent)",
                "substitutes": [],
                "evidence": evidence,
            }
        result = self._call(
            "set_scene_commands",
            {"tab": self.tab, "commands": commands, "verify": True},
        )
        evidence["applied"] = [
            {"action": row.get("action"), "changed_count": row.get("changed_count"),
             "verified": row.get("verified")}
            for row in result.get("applied") or []
            if isinstance(row, Mapping)
        ]
        if not result.get("ok", False):
            error = result.get("error") or {}
            raise CycleError(
                "the scene commands did not land: "
                f"{error.get('kind')} at #{error.get('index')} "
                f"({error.get('action')}): {error.get('message')}"
            )
        return {
            "status": "observed",
            "detail": f"{result.get('count')} scene command(s) applied and verified by "
                      f"the S2 re-read; {len(plan['skipped'])} already satisfied",
            "substitutes": [],
            "evidence": evidence,
        }

    def _hop_verify_scene(self) -> dict[str, Any]:
        """Re-read the scene (S1) and check the state this cycle promises.

        The promise is a *state*, not a transcript: the loupe exists and is
        visible at one of the two declared positions with the declared size, and
        the divider carries the declared thickness. The build alternative moves
        the loupe between A and B, so "which one" is read back, never assumed.
        """

        def probe() -> tuple[bool, dict[str, Any]]:
            scene = self._scene()
            problems = self._target_problems(scene)
            return not problems, {
                "problems": problems,
                "magnifiers": [
                    {"id": row.get("id"), "visible": row.get("visible"),
                     "position": (row.get("model") or {}).get("position_relative")}
                    for row in scene.get("magnifiers") or []
                    if isinstance(row, Mapping)
                ],
                "dividers": [
                    {"thickness": row.get("thickness"), "visible": row.get("visible")}
                    for row in scene.get("dividers") or []
                    if isinstance(row, Mapping)
                ],
            }

        waited = self._poll("verify_scene", probe, timeout_s=self.wait_s)
        scene = self._scene()
        self.report["scene"] = scene
        self._write_scene_json(scene)
        return {
            "status": "observed",
            "detail": f"scene JSON holds the declared state after {waited['polls']} poll(s)",
            "substitutes": [],
            "evidence": {"targets": waited["last"]},
        }

    def _target_problems(self, scene: Mapping[str, Any]) -> list[str]:
        """Every way the re-read scene fails this cycle's promise (empty = holds)."""
        problems: list[str] = []
        magnifiers = [row for row in scene.get("magnifiers") or [] if isinstance(row, Mapping)]
        if not magnifiers:
            return ["scene reports no magnifier instance"]
        row = next(
            (candidate for candidate in magnifiers
             if str(candidate.get("id")) == str(self._loupe_id)),
            next(
                (candidate for candidate in magnifiers if candidate.get("visible")),
                magnifiers[0],
            ),
        )
        if not row.get("visible"):
            problems.append(f"magnifier {row.get('id')!r} is not visible")
        model = row.get("model") or {}
        if not _close(model.get("size_relative"), [LOUPE_SIZE]):
            problems.append(
                f"magnifier {row.get('id')!r} size_relative is "
                f"{model.get('size_relative')!r}, expected {LOUPE_SIZE}"
            )
        position = model.get("position_relative") or [0.5, 0.5]
        if not (_close(position, LOUPE_POSITION_A) or _close(position, LOUPE_POSITION_B)):
            problems.append(
                f"magnifier {row.get('id')!r} position_relative is {position!r}, "
                f"expected one of {list(LOUPE_POSITION_A)} / {list(LOUPE_POSITION_B)}"
            )
        dividers = [row for row in scene.get("dividers") or [] if isinstance(row, Mapping)]
        if dividers:
            thickness = dividers[0].get("thickness")
            if not _close(thickness, [float(DIVIDER_THICKNESS)]):
                problems.append(
                    f"divider thickness is {thickness!r}, expected {DIVIDER_THICKNESS}"
                )
        return problems

    def _write_scene_json(self, scene: Mapping[str, Any]) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        text = canonical_json(scene)
        target = self.out_dir / "scene.json"
        target.write_text(text, encoding="utf-8")
        self.report["scene_json"] = {
            "path": str(target),
            "sha256": sha256_text(text),
            "bytes": len(text.encode("utf-8")),
        }

    def _hop_capture_png(self) -> dict[str, Any]:
        result = self._call("capture_live", {"what": self.tab})
        raw_path = str(result.get("path") or "")
        if not raw_path:
            raise CycleError("capture_live returned no artifact path")
        source = Path(raw_path)
        rhi_layers = result.get("rhi_layers")
        layers = (
            rhi_layers
            if isinstance(rhi_layers, int) and not isinstance(rhi_layers, bool)
            else None
        )

        def probe() -> tuple[bool, dict[str, Any]]:
            state = {
                "path": str(source),
                "exists": source.is_file(),
                "bytes": source.stat().st_size if source.is_file() else None,
                "method": result.get("method"),
                "rhi_layers": rhi_layers,
            }
            return bool(state["exists"] and (state["bytes"] or 0) > 0), state

        waited = self._poll("capture_png", probe, timeout_s=self.wait_s)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        copy = self.out_dir / "scene.png"
        shutil.copyfile(source, copy)
        digest = sha256_file(copy)
        if layers == 0:
            # A grab without a live canvas frame is the documented failure mode
            # (``capture.py`` composes QRhi frames for exactly this reason): the
            # PNG exists but does not show the scene, so it is not a capture.
            raise CycleError(
                "capture_live produced a PNG with rhi_layers=0: the QRhi canvas was "
                "not composited into the grab, so the artifact does not show the scene "
                "(see core/control/capture.py:33-52)"
            )
        self.report["artifacts"]["png"] = {
            "path": str(copy),
            "source_path": str(source),
            "bytes": copy.stat().st_size,
            "sha256": digest,
            "size": result.get("size"),
            "method": result.get("method"),
            "rhi_layers": rhi_layers,
        }
        self._judge_png(digest)
        return {
            "status": "observed",
            "detail": f"PNG {copy.stat().st_size} bytes, sha256={digest[:12]}…, "
                      f"method={result.get('method')} rhi_layers={rhi_layers} "
                      f"({waited['polls']} poll(s))",
            "substitutes": [],
            "evidence": self.report["artifacts"]["png"],
        }

    def _judge_png(self, digest: str) -> None:
        """Compare against the baseline report's PNG (only when one was given)."""
        verdict = self.report["determinism"]["png"]
        verdict["sha256"] = digest
        if self.baseline is None:
            verdict["verdict"] = "unknown"
            verdict["reason"] = (
                "no --baseline report was passed, so byte stability is not claimed; "
                "run the cycle twice and pass the first report as --baseline"
            )
            return
        previous = ((self.baseline.get("artifacts") or {}).get("png") or {})
        baseline_sha = previous.get("sha256")
        verdict["baseline_sha256"] = baseline_sha
        if not baseline_sha:
            verdict["verdict"] = "unknown"
            verdict["reason"] = "the baseline report carries no PNG sha256"
            return
        if str(baseline_sha) == digest:
            verdict["verdict"] = "byte_stable"
            verdict["reason"] = "byte-identical to the baseline run's PNG"
            return
        verdict["verdict"] = "differs"
        verdict["reason"] = (
            "the PNG differs from the baseline run: the same scene must render the "
            "same bytes, so either the scene differed or the capture is not reproducible"
        )
        self._fail({
            "step": "capture_png",
            "kind": "png_not_reproducible",
            "message": verdict["reason"],
            "last_observed": {"sha256": digest, "baseline_sha256": baseline_sha},
        })

    def _hop_record_start(self) -> dict[str, Any]:
        """Press the record toggle; observe the recorder's own frame trace."""
        floor = self._log_floor()
        self._call("run_action", {"action_id": RECORD_ACTION})

        def probe() -> tuple[bool, dict[str, Any]]:
            rows = self._log(since=floor)
            line = self._marker_line(rows, (RECORDING_TRACE_MARKER,))
            return line is not None, {
                "marker": RECORDING_TRACE_MARKER,
                "matched": line,
                "lines": self._log_tail(rows),
            }

        try:
            waited = self._poll("record_start", probe, timeout_s=RECORDING_TRACE_BUDGET_S)
        except CycleTimeout as exc:
            self.report["recording_trace"] = {"observed": False, "last": exc.last}
            self._name_unobservable("record_start", RECORDING_START_REASON,
                                    "the editor-open condition (stop_and_open_editor) and "
                                    "the produced video artifact")
            return {
                "status": "unobservable",
                "detail": "no recorder frame trace in the log ring — this hop is NOT "
                          "observed (see unobservable[])",
                "substitutes": ["editor_open", "video_artifact"],
                "evidence": exc.last,
            }
        self.report["recording_trace"] = {"observed": True, "line": waited["last"]["matched"]}
        return {
            "status": "observed",
            "detail": "recorder frame trace seen: "
                      f"{str(waited['last']['matched'])[-80:]}",
            "substitutes": [],
            "evidence": {"marker": RECORDING_TRACE_MARKER,
                         "line": waited["last"]["matched"]},
        }

    def _hop_scene_while_recording(self) -> dict[str, Any]:
        """Do real work inside the recording instead of waiting a fixed time.

        The recorder samples whatever the store holds at each tick, so a scene
        that moves while recording is what makes the clip non-static. This is
        also the only honest way to give the recording a duration without a
        ``sleep``: the hop is a verified scene command, bounded by its own read.
        """
        scene = self._scene()
        commands, plan = self._plan_scene_commands(scene)
        position_commands = [
            command for command in commands if command["action"] == POSITION_COMMAND
        ]
        if not position_commands:
            return {
                "status": "skipped",
                "detail": "the loupe is already at both declared positions (no move to make)",
                "substitutes": [],
                "evidence": {"skipped": plan["skipped"]},
            }
        result = self._call(
            "set_scene_commands",
            {"tab": self.tab, "commands": position_commands, "verify": True},
        )
        if not result.get("ok", False):
            error = result.get("error") or {}
            raise CycleError(
                f"the mid-recording scene move did not land: {error.get('message')}"
            )
        return {
            "status": "observed",
            "detail": "loupe moved and verified while recording "
                      f"({len(position_commands)} command(s))",
            "substitutes": [],
            "evidence": {"expects": plan["expects"]},
        }

    def _editor_actions(self, needle: str = EDITOR_ACTION_PREFIX) -> list[dict[str, Any]]:
        result = self._call("list_actions", {"query": needle})
        return [row for row in result.get("actions") or [] if isinstance(row, dict)]

    def _hop_stop_and_open_editor(self) -> dict[str, Any]:
        """Stop the recording by opening the editor; the dialog opening *is* the signal.

        ``open_video_editor`` sets ``_pending_open_editor`` and stops the
        recording when one is running, and the editor is only opened from
        ``on_recording_finalized`` (``recording_flow.py:152-207``). Its Find
        Actions are registered while the dialog is open, so their appearance is
        a public observable of "finalize finished" — the smallest substitute R2
        allows, built in this tool with no app hook.

        One trap this hop refuses to walk into: if the editor was **already
        open** (a second cycle on the same app session), its actions being
        present is not evidence about *this* recording's finalize. The hop then
        presses the action anyway (it is what stops the recording) and reports
        itself ``unobservable``, leaving the verdict to the export log line and
        artifact.
        """
        floor = self._log_floor()
        already_open = bool(self._editor_actions())
        self._call("run_action", {"action_id": VIDEO_EDITOR_ACTION})

        def probe() -> tuple[bool, dict[str, Any]]:
            actions = self._editor_actions()
            export = self._export_action(actions)
            return bool(actions), {
                "editor_action_count": len(actions),
                "export_action_id": export,
                "log": self._log_tail(self._log(since=floor)),
            }

        if already_open:
            state = probe()[1]
            self.report["editor"] = {
                "export_action_id": state.get("export_action_id"),
                "action_count": state.get("editor_action_count"),
            }
            self._name_unobservable(
                "stop_and_open_editor",
                "the video editor was already open before this hop, so its Find "
                "Actions appearing is not evidence that THIS recording finalized "
                "(recording_flow.py:190 opens it from on_recording_finalized only "
                "when the open was pending)",
                "the export log line (newer than this hop) and the produced video "
                "artifact",
            )
            return {
                "status": "unobservable",
                "detail": "the editor was already open — the stop was sent, but the "
                          "finalize of this recording has no signal here",
                "substitutes": ["export_log_line", "video_artifact"],
                "evidence": state,
            }

        waited = self._poll("stop_and_open_editor", probe, timeout_s=self.wait_s)
        self.report["editor"] = {
            "export_action_id": waited["last"].get("export_action_id"),
            "action_count": waited["last"].get("editor_action_count"),
        }
        return {
            "status": "observed",
            "detail": "video editor Find Actions registered "
                      f"({waited['last']['editor_action_count']}) after "
                      f"{waited['polls']} poll(s) — the dialog only opens post-finalize",
            "substitutes": [],
            "evidence": waited["last"],
        }

    @staticmethod
    def _export_action(actions: Sequence[Mapping[str, Any]]) -> str | None:
        for row in actions:
            action_id = str(row.get("action_id") or "")
            if action_id.endswith(EXPORT_ACTION_SUFFIX):
                return action_id
        return None

    def _hop_export_video(self) -> dict[str, Any]:
        actions = self._editor_actions()
        export_id = self._export_action(actions) or (
            (self.report.get("editor") or {}).get("export_action_id")
        )
        if not export_id:
            raise CycleError(
                "the video editor is open but contributes no "
                f"{EXPORT_ACTION_SUFFIX!r} action; cannot press export"
            )
        floor = self._log_floor()
        self._call("run_action", {"action_id": export_id})

        def probe() -> tuple[bool, dict[str, Any]]:
            rows = self._log(since=floor)
            line = self._marker_line(rows, VIDEO_SUCCESS_MARKERS)
            failures = [
                row for row in rows
                if any(
                    marker in str(row.get("text") or "")
                    for marker in VIDEO_FAILURE_MARKERS
                )
            ]
            frames = self._frames_reported(rows)
            state = {
                "success_line": line,
                "failure_lines": [str(row.get("text") or "") for row in failures],
                "frames_reported": frames,
                "lines": self._log_tail(rows),
            }
            return line is not None, state

        waited = self._poll("export_video", probe, timeout_s=self.export_s)
        success = str(waited["last"]["success_line"])
        video_path = self._path_from_line(success, VIDEO_SUCCESS_MARKERS)
        if video_path is None:
            raise CycleError(f"the success line carries no path: {success!r}")
        target = Path(video_path)

        def artifact() -> tuple[bool, dict[str, Any]]:
            exists = target.is_file()
            state = {
                "path": str(target),
                "exists": exists,
                "bytes": target.stat().st_size if exists else None,
            }
            return bool(exists and (state["bytes"] or 0) > 0), state

        settled = self._poll(
            "export_video", artifact, timeout_s=min(self.wait_s, ARTIFACT_SETTLE_S)
        )
        frames = waited["last"].get("frames_reported")
        self.report["artifacts"]["video"] = {
            "path": str(target),
            "bytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "frames_reported": frames,
            "success_line": success,
        }
        determinism = self.report["determinism"]["video"]
        determinism["observed_frames"] = frames
        determinism["pinned"] = self.expect_video_frames is not None
        if self.expect_video_frames is not None:
            if frames is None:
                raise CycleError(
                    "the encode log carries no frame count, so the pinned count "
                    f"({self.expect_video_frames}) cannot be checked: {success!r}"
                )
            if int(frames) != int(self.expect_video_frames):
                raise CycleError(
                    f"pinned frame count mismatch: expected {self.expect_video_frames}, "
                    f"the encoder reported {frames}"
                )
            determinism["reason"] = (
                "pinned by the caller: the encode reported the declared frame count"
            )
        return {
            "status": "observed",
            "detail": f"encode finished ({target.stat().st_size} bytes, "
                      f"frames={frames}) and the artifact is on disk after "
                      f"{settled['polls']} poll(s)",
            "substitutes": [],
            "evidence": self.report["artifacts"]["video"],
        }

    @staticmethod
    def _path_from_line(line: str, markers: Sequence[str]) -> str | None:
        for marker in markers:
            if marker in line:
                value = line.split(marker, 1)[1].strip()
                return value or None
        return None

    @staticmethod
    def _frames_reported(rows: Sequence[Mapping[str, Any]]) -> int | None:
        for row in reversed(list(rows)):
            match = VIDEO_FRAMES_RE.search(str(row.get("text") or ""))
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    return None
        return None

    # ------------------------------------------------------------------
    # the schedule
    # ------------------------------------------------------------------

    def run(self, image_a: Path | str, image_b: Path | str) -> dict[str, Any]:
        """Walk the cycle; always return a report (failures included)."""
        self.report = self._empty_report()
        self.wire_calls = 0
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.report["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.report["inputs"] = {"a": str(image_a), "b": str(image_b)}
        # Nothing about the video export is a job (R1) — say it in every report.
        self._name_unobservable("video_export_job", VIDEO_JOB_REASON,
                                "the export log line + the artifact on disk")

        schedule: list[tuple[str, str, Callable[[], dict[str, Any]]]] = [
            ("open_tab", "open_tab returns the tab it focused", self._hop_open_tab),
            ("load_pair",
             "get_canvas_scene panes[].path == the staged inputs",
             lambda: self._hop_load_pair(Path(str(image_a)), Path(str(image_b)))),
            ("build_scene", "set_scene_commands verify=True", self._hop_build_scene),
            ("verify_scene", "get_canvas_scene re-read vs declared expects",
             self._hop_verify_scene),
            ("capture_png", "artifact on disk (non-empty) + rhi_layers != 0",
             self._hop_capture_png),
            ("record_start", f"log ring: {RECORDING_TRACE_MARKER!r}", self._hop_record_start),
            ("scene_while_recording", "set_scene_commands verify=True",
             self._hop_scene_while_recording),
            ("stop_and_open_editor", "list_actions: video editor Find Actions",
             self._hop_stop_and_open_editor),
            ("export_video", f"log ring: {VIDEO_SUCCESS_MARKERS[0]!r} + artifact",
             self._hop_export_video),
        ]
        blocked_by: str | None = None
        for name, observable, hop in schedule:
            if blocked_by is not None:
                self._step(name, observable, "skipped", f"an earlier hop failed: {blocked_by}")
                continue
            try:
                outcome = hop()
            except CycleTimeout as exc:
                self._step(name, observable, "failed", str(exc), last_observed=exc.last)
                self._fail(exc.to_dict())
                blocked_by = name
                continue
            except (CycleError, ControlError, ControlUnavailable) as exc:
                hint = getattr(exc, "hint", None)
                detail = f"{exc}" + (f" (hint: {hint})" if hint else "")
                self._step(name, observable, "failed", detail)
                self._fail({
                    "step": name,
                    "kind": "refused" if isinstance(exc, ControlError) else "failed",
                    "message": str(exc),
                    "hint": hint,
                    "last_observed": {"scene": self.report.get("scene") is not None},
                })
                blocked_by = name
                continue
            except Exception as exc:  # a crashed hop is a failed run, not a traceback
                self._step(name, observable, "failed",
                           f"{type(exc).__name__}: {exc}")
                self._fail({
                    "step": name,
                    "kind": "crashed",
                    "message": f"{type(exc).__name__}: {exc}",
                    "hint": "this is a bug in the cycle tool, not a verdict about the app",
                    "last_observed": {
                        "scene_sha256": (self.report.get("scene_json") or {}).get("sha256")
                    },
                })
                blocked_by = name
                continue
            self._step(
                name,
                observable,
                outcome.get("status", "observed"),
                outcome.get("detail", ""),
                substitutes=outcome.get("substitutes") or [],
                evidence=outcome.get("evidence"),
            )

        self.report["ok"] = not self.report["failures"]
        self.report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.report["wire_calls"] = self.wire_calls
        return self.report


# ---------------------------------------------------------------------------
# canonical serialization (S1's own contract, not a second one)
# ---------------------------------------------------------------------------


def canonical_json(payload: Any) -> str:
    """Sorted-key JSON — the same bytes two runs of one scene must produce."""
    from core.control.scene_read import canonical_json as scene_canonical_json

    return scene_canonical_json(payload)


# ---------------------------------------------------------------------------
# plan / summary text
# ---------------------------------------------------------------------------


def format_plan(tab: str = DEFAULT_TAB, wait_s: float = DEFAULT_WAIT_S,
                export_s: float = DEFAULT_EXPORT_S) -> str:
    lines = [
        "canvas scene cycle (S3 of " + PLAN_ID + ")",
        f"tab: {tab}",
        f"budgets: wait {wait_s:g}s per hop, video export {export_s:g}s "
        "(every wait is a bounded condition poll; a timeout is a failure)",
        "hops (each names the signal that decides it):",
    ]
    lines += [f"  {index}. {name:<22} {plan}" for index, (name, _m, plan) in
              enumerate(STEP_PLAN, start=1)]
    lines += [
        "named as unobservable by every run (no signal exists today):",
        "  - video_export_job: " + VIDEO_JOB_REASON,
        "  - record_start *when the debug trace is not in the log ring*: "
        + RECORDING_START_REASON,
        "determinism:",
        "  - png: byte-identical on a second run of the same scene; gate it with "
        "--baseline <first report.json>",
        "  - video: not promised — " + VIDEO_DETERMINISM_REASON,
        "dry-run: nothing was sent",
    ]
    return "\n".join(lines)


def format_summary(report: Mapping[str, Any]) -> str:
    ok = "OK" if report.get("ok") else "FAILED"
    lines = [
        f"canvas scene cycle: {ok}",
        f"tab: {report.get('tab')}  socket calls: {report.get('wire_calls')}",
        "hops:",
    ]
    for index, step in enumerate(report.get("steps") or [], start=1):
        lines.append(
            f"  {index}. {step.get('step', '?'):<22} {str(step.get('status')):<12} "
            f"{step.get('detail', '')}"
        )
    for row in report.get("unobservable") or []:
        lines.append(f"  UNOBSERVABLE {row.get('step')}: {row.get('reason')}")
    png = ((report.get("artifacts") or {}).get("png") or {})
    video = ((report.get("artifacts") or {}).get("video") or {})
    if png:
        lines.append(f"png: {png.get('path')} ({png.get('bytes')} bytes, "
                     f"sha256={str(png.get('sha256'))[:12]}…)")
    if video:
        lines.append(f"video: {video.get('path')} ({video.get('bytes')} bytes, "
                     f"frames={video.get('frames_reported')})")
    determinism = report.get("determinism") or {}
    if determinism:
        lines.append(f"png determinism: {(determinism.get('png') or {}).get('verdict')}")
        lines.append(f"video determinism: pinned={(determinism.get('video') or {}).get('pinned')} "
                     f"({(determinism.get('video') or {}).get('reason', '')[:60]}…)")
    for failure in report.get("failures") or []:
        lines.append(f"FAILED {failure.get('step')}: {failure.get('message')}")
        last = failure.get("last_observed")
        if last:
            lines.append(
                "  last observed: "
                + json.dumps(last, sort_keys=True, ensure_ascii=False)[:400]
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_scene_cycle",
        description=(
            "Drive the full canvas scene cycle (build -> verify -> capture -> record -> "
            "video export) on a live instance and assert each hop from something the app "
            "observes: the scene JSON, the log ring, and the produced artifacts. No hop "
            "is decided by a sleep, and a hop with no observable is named as such."
        ),
        epilog=(
            "Exit codes: 0 every hop observed and every artifact present, 1 a hop failed "
            "or timed out (the report carries the last observed state), 2 no live "
            "instance / bad arguments. Run --dry-run first: it prints the hop plan and "
            "the signal behind each hop, and sends nothing."
        ),
    )
    parser.add_argument("--image-a", metavar="PATH", help="left image of the pair")
    parser.add_argument("--image-b", metavar="PATH", help="right image of the pair")
    parser.add_argument("--out", metavar="DIR",
                        help="artifact dir (scene.json, scene.png, report.json)")
    parser.add_argument("--socket", metavar="PATH",
                        help="control socket; default: the app's own discovery")
    parser.add_argument("--tab", default=DEFAULT_TAB, help=f"tab kind (default {DEFAULT_TAB})")
    parser.add_argument("--report", metavar="PATH",
                        help="report path (default <out>/report.json)")
    parser.add_argument("--baseline", metavar="PATH",
                        help="a previous report.json; its PNG sha256 gates this run's PNG")
    parser.add_argument("--expect-video-frames", type=int, default=None, metavar="N",
                        help="pin the video frame count (default: report non-deterministic)")
    parser.add_argument("--wait-s", type=float, default=DEFAULT_WAIT_S, metavar="S",
                        help=f"per-hop wait budget (default {DEFAULT_WAIT_S:g}s)")
    parser.add_argument("--export-s", type=float, default=DEFAULT_EXPORT_S, metavar="S",
                        help=f"video export budget (default {DEFAULT_EXPORT_S:g}s)")
    parser.add_argument("--poll-ms", type=int, default=DEFAULT_POLL_MS, metavar="MS",
                        help=f"first poll interval (default {DEFAULT_POLL_MS}); grows")
    parser.add_argument("--poll-max-ms", type=int, default=DEFAULT_POLL_MAX_MS, metavar="MS",
                        help=f"poll interval ceiling (default {DEFAULT_POLL_MAX_MS})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT_S, metavar="S",
                        help="one request/response round trip")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, send nothing")
    return parser


def main(argv: Sequence[str] | None = None, *, client: Any | None = None,
         env: Mapping[str, str] | None = None,
         clock: Callable[[], float] = time.monotonic,
         sleep: Callable[[float], None] = time.sleep) -> int:
    """CLI entry. ``client``/``clock``/``sleep`` are the test injection seams."""
    args = _build_parser().parse_args(argv)
    if args.dry_run:
        print(format_plan(args.tab, args.wait_s, args.export_s))
        return 0
    missing = [flag for flag in ("image_a", "image_b", "out") if not getattr(args, flag)]
    if missing:
        print("error: missing " + ", ".join("--" + name.replace("_", "-") for name in missing)
              + " (or pass --dry-run to see the plan)")
        return 2
    image_a, image_b = Path(args.image_a).expanduser(), Path(args.image_b).expanduser()
    for path in (image_a, image_b):
        if not path.is_file():
            print(f"error: not an existing image file: {path}")
            return 2
    out_dir = Path(args.out).expanduser()
    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).expanduser().read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"error: cannot read --baseline {args.baseline}: {exc}")
            return 2

    socket_path: Path | None = None
    if client is None:
        socket_path = Path(args.socket).expanduser() if args.socket else discover_socket(env)
        if socket_path is None:
            print("no live instance: no control socket found (start the app with the "
                  "control channel on: IMGSLI_CONTROL=1)")
            return 2
        client = ControlClient(socket_path, timeout=args.timeout)
    cycle = SceneCycle(
        channel=client,
        out_dir=out_dir,
        tab=args.tab,
        wait_s=args.wait_s,
        export_s=args.export_s,
        poll_ms=args.poll_ms,
        poll_max_ms=args.poll_max_ms,
        baseline=baseline,
        expect_video_frames=args.expect_video_frames,
        clock=clock,
        sleep=sleep,
    )
    cycle.report["socket"] = str(socket_path) if socket_path is not None else "<injected client>"
    try:
        report = cycle.run(image_a, image_b)
    finally:
        try:
            client.close()
        except Exception:
            pass
    report_path = Path(args.report).expanduser() if args.report else (out_dir / "report.json")
    report["report_path"] = str(report_path)
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
                               encoding="utf-8")
    except OSError as exc:
        print(f"warning: could not write the report to {report_path}: {exc}")
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
          if args.json else format_summary(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
