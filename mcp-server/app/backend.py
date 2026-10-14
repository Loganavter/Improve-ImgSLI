"""Tool/resource/prompt handlers for the Improve-ImgSLI MCP server.

Stdlib only — no third-party imports — so the server runs in any Python 3.11+
without installing the (optional) ``mcp`` SDK. Everything the app exposes
headlessly is reached the way a developer would: a ``python src/__main__.py``
subprocess with the launcher's startup flags, plus the devtools
(``devtools.capture_surface``, ``devtools.app_snapshot``).

Phase 1 model (documented in ``README.md`` and ``docs/dev/MCP.md``):

- **reads** boot one headless app snapshot (``--dump-app-snapshot``) and cache
  it briefly; ``--dump-ui-layout`` boots for the widget tree; the log and
  tracer are read straight from disk;
- **mutations** start a fresh app process (``--open-tab`` / ``--run-action``) or
  persist a scalar setting through the app's own QSettings keys. There is no
  channel into an already-running window — that is the Phase-2 in-app control
  socket, out of scope here.

Security: local-only; ``run_action`` is allowlisted to ids present in the
ActionRegistry snapshot; ``open_folder`` accepts existing directories only;
no arbitrary paths, no Python evaluation, and no file *contents* are ever
returned (only the app's own log/trace/catalog artifacts).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

#: How long a headless app snapshot stays usable before a re-boot (seconds).
SNAPSHOT_TTL_S = 30.0

#: Subprocess wall-clock budget for a headless boot / capture (seconds).
DEFAULT_TIMEOUT_S = 120.0

_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_LEVEL_RE = re.compile(r"-\s*\[(?P<level>[A-Z]+)\]\s*-\s*(?P<rest>.*)")


class ToolError(Exception):
    """A tool failure that becomes ``isError: true`` with an actionable hint."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


def app_data_dir() -> Path:
    """Per-OS app data dir holding ``log.txt`` / ``trace.jsonl``.

    Mirrors ``sli_ui_toolkit.core.logging`` / ``core.tracing.file_sink``.
    """
    if sys.platform.startswith("linux"):
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:  # pragma: no cover - Windows
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "ImproveImgSLI"


def default_artifacts_dir() -> Path:
    """Where headless artifacts (layout dumps, captures) are written."""
    override = os.environ.get("IMGSLI_MCP_ARTIFACTS")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ImproveImgSLI" / "mcp"


def _count_nodes(node: dict) -> int:
    total = 1
    for child in node.get("children") or []:
        if isinstance(child, dict):
            total += _count_nodes(child)
    return total


def _read_level(line: str) -> str | None:
    match = _LEVEL_RE.search(line)
    return match.group("level") if match else None


class AppBackend:
    """Handlers behind the MCP tools/resources/prompts.

    Every external effect is injectable (``snapshot_runner``,
    ``launcher``, ``settings_writer``, ``artifacts_dir``, ``python``) so the
    test-suite exercises the wiring without a GUI, a display, a subprocess, or
    the user's real QSettings.
    """

    def __init__(
        self,
        repo_root: Path | str,
        *,
        python: str | None = None,
        artifacts_dir: Path | str | None = None,
        data_dir: Path | str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        snapshot_ttl_s: float = SNAPSHOT_TTL_S,
        snapshot_runner: Callable[[str | None], dict] | None = None,
        launcher: Callable[[list[str]], int] | None = None,
        settings_writer: Callable[[str, str], None] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._python = python
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else default_artifacts_dir()
        self.data_dir = Path(data_dir) if data_dir else app_data_dir()
        self.timeout_s = timeout_s
        self.snapshot_ttl_s = snapshot_ttl_s
        self._snapshot_runner = snapshot_runner
        self._launcher = launcher
        self._settings_writer = settings_writer
        self._snaps: dict[str, tuple[dict, float]] = {}

    # -- paths / process plumbing ------------------------------------------

    @property
    def python(self) -> str:
        """Interpreter that can import the app (venv when present)."""
        if self._python:
            return self._python
        for candidate in (
            self.repo_root / "venv" / "bin" / "python",
            self.repo_root / "venv" / "Scripts" / "python.exe",
        ):
            if candidate.is_file():
                return str(candidate)
        return sys.executable

    @property
    def log_path(self) -> Path:
        return self.data_dir / "log.txt"

    @property
    def trace_path(self) -> Path:
        return self.data_dir / "trace.jsonl"

    def _app_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ)
        src = str(self.repo_root / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        if extra:
            env.update(extra)
        return env

    def _run_app(
        self,
        args: list[str],
        *,
        offscreen: bool,
        timeout: float | None = None,
    ) -> tuple[int, str, str]:
        """Blocking app run (used by headless probe flags)."""
        env = self._app_env({"QT_QPA_PLATFORM": "offscreen"} if offscreen else None)
        cmd = [self.python, str(self.repo_root / "src" / "__main__.py"), *args]
        try:
            proc = subprocess.run(
                cmd,
                env=env,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(
                f"the app did not finish within {int(timeout or self.timeout_s)}s",
                "try a narrower request (e.g. dump_ui_layout without a tab) or "
                "raise IMGSLI_MCP_TIMEOUT in the server environment",
            )
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _launch(self, args: list[str]) -> int:
        """Detached app launch (mutating tools) — returns the child pid."""
        if self._launcher is not None:
            return self._launcher(args)
        proc = subprocess.Popen(
            [self.python, str(self.repo_root / "src" / "__main__.py"), *args],
            env=self._app_env(),
            cwd=str(self.repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return int(proc.pid)

    # -- snapshot ----------------------------------------------------------

    def snapshot(self, *, tab: str | None = None, refresh: bool = False) -> dict:
        """Headless app snapshot (cached per opened tab), or raise ``ToolError``.

        ``tab`` opens that workspace tab before the dump so its own actions
        register — the reason ``list_actions(owner_tab=...)`` can see tab
        catalogs at all (without a tab only the host actions exist).
        """
        now = time.monotonic()
        key = tab or ""
        cached = self._snaps.get(key)
        if not refresh and cached is not None and now - cached[1] < self.snapshot_ttl_s:
            return cached[0]
        if self._snapshot_runner is not None:
            try:
                data = self._snapshot_runner(tab)
            except ToolError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise ToolError(f"snapshot probe failed: {exc}", "run './launcher.sh install'")
        else:
            data = self._boot_snapshot(tab)
        if not isinstance(data, dict) or "actions" not in data:
            raise ToolError(
                "the app snapshot was malformed",
                "check the app log (read_log) for a startup failure",
            )
        self._snaps[key] = (data, now)
        return data

    def _boot_snapshot(self, tab: str | None) -> dict:
        name = f"app-snapshot-{tab}.json" if tab else "app-snapshot.json"
        target = self.artifacts_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        args = ["--open-tab", tab] if tab else []
        code, _out, err = self._run_app(
            [*args, "--dump-app-snapshot", str(target)], offscreen=True
        )
        if code != 0 or not target.is_file():
            detail = err.strip().splitlines()[-1] if err.strip() else f"exit {code}"
            raise ToolError(
                f"headless app snapshot failed ({detail})",
                "run './launcher.sh install' to build the venv, then retry",
            )
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ToolError(f"could not parse the app snapshot: {exc}", "retry list_actions")

    def _invalidate_snapshot(self) -> None:
        self._snaps.clear()

    def _actions(self, tab: str | None = None) -> list[dict]:
        return list(self.snapshot(tab=tab).get("actions") or [])

    # -- read-only tools ---------------------------------------------------

    def list_actions(self, *, query: str | None = None, owner_tab: str | None = None) -> dict:
        from . import catalog

        # A tab catalog only exists once that tab is created, so filter by a
        # tab we know how to open ⇒ boot with it open.
        boot_tab = owner_tab if owner_tab in catalog.TAB_KINDS else None
        needle = (query or "").strip().lower()
        rows = []
        for action in self._actions(boot_tab):
            if owner_tab and action.get("owner_tab") != owner_tab:
                continue
            if needle:
                haystack = " ".join(
                    str(action.get(field) or "")
                    for field in ("action_id", "label", "label_key")
                ).lower()
                if needle not in haystack:
                    continue
            rows.append(action)
        rows.sort(key=lambda row: (row.get("owner_tab") or "", row.get("action_id") or ""))
        return {
            "count": len(rows),
            "actions": [
                {
                    "action_id": row.get("action_id"),
                    "label": row.get("label"),
                    "owner_tab": row.get("owner_tab"),
                    "topic": row.get("topic"),
                    "shortcut": row.get("shortcut"),
                }
                for row in rows
            ],
        }

    def list_sessions(self) -> dict:
        sessions = list(self.snapshot().get("sessions") or [])
        return {"count": len(sessions), "sessions": sessions}

    def get_state(self, *, path: str | None = None) -> dict:
        state = self.snapshot().get("state") or {}
        if not path:
            return {"path": None, "state": state}
        current: Any = state
        for part in str(path).split("."):
            if part == "":
                continue
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise ToolError(
                    f"no state at path {path!r}",
                    "call get_state without a path to see the available keys",
                )
        return {"path": path, "state": current}

    def read_log(self, *, n: int = 200, level: str | None = None) -> dict:
        path = self.log_path
        if not path.is_file():
            raise ToolError(
                f"no log file at {path}",
                "start the app once (./launcher.sh run) so it writes a log",
            )
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            raise ToolError(f"cannot read the log: {exc}", "check file permissions")
        threshold = _LEVELS.index(level) if level in _LEVELS else None
        selected = []
        for index, line in enumerate(lines):
            severity = _read_level(line)
            if threshold is not None and severity not in _LEVELS:
                continue
            if threshold is not None and _LEVELS.index(severity) < threshold:
                continue
            selected.append({"n": index + 1, "level": severity, "text": line})
        tail = selected[-int(n) :] if n else selected
        return {
            "path": str(path),
            "total_lines": len(lines),
            "returned": len(tail),
            "lines": tail,
        }

    def query_trace(self, *, filter: str | None = None, n: int = 100) -> dict:
        path = self.trace_path
        if not path.is_file():
            raise ToolError(
                f"no tracer file at {path}",
                "run './launcher.sh run --debug' (IMGSLI_TRACE=1) to record a chain first",
            )
        needle = (filter or "").lower()
        records: list[dict] = []
        total = 0
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ToolError(f"cannot read the tracer file: {exc}", "check file permissions")
        with handle:
            for index, line in enumerate(handle):
                line = line.strip()
                if not line:
                    continue
                if needle and needle not in line.lower():
                    continue
                total += 1
                try:
                    record = json.loads(line)
                except ValueError:
                    record = {"raw": line}
                if isinstance(record, dict):
                    record.setdefault("_line", index + 1)
                    records.append(record)
        newest = list(reversed(records))[: int(n)] if n else []
        return {
            "path": str(path),
            "total_records": total,
            "returned": len(newest),
            "records": newest,
        }

    def dump_ui_layout(self, *, tab: str | None = None, out: str | None = None) -> dict:
        if out:
            target = Path(out).expanduser()
        else:
            name = f"ui-layout-{tab}.json" if tab else "ui-layout.json"
            target = self.artifacts_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        args = ["--dump-ui-layout", str(target)]
        if tab:
            args = ["--open-tab", tab, *args]
        code, _stdout, err = self._run_app(args, offscreen=True)
        if code != 0 or not target.is_file():
            detail = err.strip().splitlines()[-1] if err.strip() else f"exit {code}"
            raise ToolError(
                f"widget-tree dump failed ({detail})",
                "retry without tab, or check the app log (read_log)",
            )
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ToolError(f"could not parse the layout dump: {exc}", "retry dump_ui_layout")
        windows = data.get("windows") or []
        nodes = sum(_count_nodes(win) for win in windows if isinstance(win, dict))
        return {"path": str(target), "tab": tab, "windows": len(windows), "node_count": nodes}

    def list_surfaces(self) -> dict:
        surfaces = self._capture_surfaces()
        rows = [
            {
                "name": name,
                "description": data.get("description", ""),
                "isolated": bool(data.get("isolated")),
            }
            for name, data in surfaces.items()
        ]
        rows.sort(key=lambda row: row["name"])
        return {"count": len(rows), "surfaces": rows}

    def _capture_surfaces(self) -> dict[str, dict]:
        try:
            src = str(self.repo_root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from devtools.capture_surface import SURFACES

            return {
                name: {"description": surface.description, "isolated": surface.isolated}
                for name, surface in SURFACES.items()
            }
        except Exception as exc:
            raise ToolError(
                f"cannot enumerate capture surfaces: {exc}",
                "ensure PySide6 is installed (./launcher.sh install)",
            )

    # -- mutating tools ----------------------------------------------------

    def open_tab(self, *, tab: str) -> dict:
        from . import catalog

        if tab not in catalog.TAB_KINDS:
            raise ToolError(
                f"unknown tab {tab!r}",
                "use one of: " + ", ".join(catalog.TAB_KINDS),
            )
        pid = self._launch(["--open-tab", tab])
        return {"launched": True, "pid": pid, "tab": tab}

    def run_action(self, *, action_id: str, tab: str | None = None) -> dict:
        from . import catalog

        # Tab-scoped ids (``image_compare.*``) only exist once the tab is
        # created; infer the tab from the id so validation can succeed.
        boot_tab = tab
        if boot_tab is None:
            prefix = action_id.split(".", 1)[0]
            if prefix in catalog.TAB_KINDS:
                boot_tab = prefix
        known = {row.get("action_id") for row in self._actions(boot_tab)}
        if action_id not in known:
            close = difflib.get_close_matches(action_id, sorted(known), n=3, cutoff=0.5)
            hint = "call list_actions to see valid ids"
            if close:
                hint = "did you mean: " + ", ".join(close) + "? (" + hint + ")"
            raise ToolError(f"{action_id!r} is not a registered Find Action", hint)
        args = ["--run-action", action_id]
        if boot_tab:
            args = ["--open-tab", boot_tab, *args]
        pid = self._launch(args)
        return {"launched": True, "pid": pid, "action_id": action_id, "tab": boot_tab}

    def open_folder(self, *, path: str) -> dict:
        target = Path(path).expanduser()
        if not target.is_dir():
            raise ToolError(
                f"{target} is not an existing directory",
                "pass an absolute (or ~-prefixed) path to a folder of images",
            )
        pid = self._launch(["--open-tab", "image_gallery"])
        return {"launched": True, "pid": pid, "path": str(target), "routed": False}

    def set_theme(self, *, theme: str) -> dict:
        return self._persist("theme", theme, "theme")

    def set_language(self, *, language: str) -> dict:
        return self._persist("language", language, "language")

    def _persist(self, key: str, value: str, label: str) -> dict:
        try:
            if self._settings_writer is not None:
                self._settings_writer(key, value)
            else:
                self._write_setting(key, value)
        except Exception as exc:
            raise ToolError(
                f"could not persist {label}={value!r}: {exc}",
                "check that the app config directory is writable",
            )
        self._invalidate_snapshot()
        return {label: value, "persisted": True, "applies_on": "next app start"}

    def _write_setting(self, key: str, value: str) -> None:
        """Persist one scalar via the app's own QSettings scope (org/app keys)."""
        script = (
            "import sys\n"
            "from PySide6.QtCore import QSettings\n"
            "settings = QSettings('improve-imgsli', 'improve-imgsli')\n"
            "settings.setValue(sys.argv[1], sys.argv[2])\n"
            "settings.sync()\n"
        )
        subprocess.run(
            [self.python, "-c", script, key, str(value)],
            env=self._app_env(),
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    # -- capture -----------------------------------------------------------

    def capture_surface(self, *, surface: str, theme: str | None = None, out: str | None = None) -> dict:
        surfaces = self._capture_surfaces()
        if surface not in surfaces:
            close = difflib.get_close_matches(surface, sorted(surfaces), n=3, cutoff=0.5)
            hint = "call list_surfaces to see valid names"
            if close:
                hint = "did you mean: " + ", ".join(close) + "? (" + hint + ")"
            raise ToolError(f"unknown surface {surface!r}", hint)
        chosen_theme = theme or "dark"
        out_dir = Path(out).expanduser() if out else self.artifacts_dir / "captures"
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.python,
            str(self.repo_root / "src" / "devtools" / "capture_surface.py"),
            surface,
            "--out",
            str(out_dir),
            "--theme",
            chosen_theme,
        ]
        try:
            proc = subprocess.run(
                cmd,
                env=self._app_env(),
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(
                f"capture of {surface!r} timed out",
                "check DISPLAY points at a private Xvfb (docs/dev/SCREENSHOTS.md)",
            )
        if proc.returncode != 0:
            raise ToolError(
                f"capture of {surface!r} failed (exit {proc.returncode})",
                "start a private Xvfb and export DISPLAY (docs/dev/SCREENSHOTS.md)",
            )
        saved = self._parse_saved_path(proc.stdout, out_dir, surface)
        if saved is None:
            raise ToolError(
                f"capture of {surface!r} produced no PNG",
                "re-run with a display and check the app log",
            )
        return {"surface": surface, "path": str(saved), "theme": chosen_theme}

    @staticmethod
    def _parse_saved_path(stdout: str, out_dir: Path, surface: str) -> Path | None:
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("saved "):
                candidate = Path(line[len("saved ") :].split(" ")[0])
                if candidate.is_file():
                    return candidate
        fallback = out_dir / f"{surface}.png"
        return fallback if fallback.is_file() else None

    # -- resources ---------------------------------------------------------

    def read_resource(self, uri: str) -> dict:
        """Return ``{uri, mimeType, text}`` for a concrete resource URI."""
        text = self._resource_text(uri)
        mime = "text/plain" if uri == "app://log" else "application/json"
        return {"uri": uri, "mimeType": mime, "text": text}

    def _resource_text(self, uri: str) -> str:
        from . import catalog

        if uri == "app://actions":
            return json.dumps({"actions": self._actions()}, ensure_ascii=False, indent=2)
        if uri == "app://state":
            return json.dumps(self.snapshot().get("state") or {}, ensure_ascii=False, indent=2)
        if uri == "app://sessions":
            return json.dumps({"sessions": self.list_sessions()["sessions"]}, ensure_ascii=False, indent=2)
        if uri == "app://theme":
            snap = self.snapshot()
            return json.dumps(
                {
                    "theme": snap.get("theme"),
                    "language": snap.get("language"),
                    "ui_scale_factor": snap.get("ui_scale_factor"),
                    "note": "Phase 1 reads a headless snapshot; set_theme/set_language apply on next start.",
                },
                ensure_ascii=False,
                indent=2,
            )
        if uri == "app://log":
            tail = self.read_log(n=200)
            return "\n".join(line["text"] for line in tail["lines"])
        if uri == "app://ui-layout":
            return self._read_artifact(self.artifacts_dir / "ui-layout.json")
        if uri.startswith("app://action/"):
            action_id = uri[len("app://action/") :]
            prefix = action_id.split(".", 1)[0]
            tab = prefix if prefix in catalog.TAB_KINDS else None
            for row in self._actions(tab) or self._actions():
                if row.get("action_id") == action_id:
                    return json.dumps(row, ensure_ascii=False, indent=2)
            raise ToolError(
                f"no action with id {action_id!r}",
                "read app://actions for the host catalog, or list_actions(owner_tab=...) for a tab",
            )
        match = re.fullmatch(r"app://tab/(?P<name>[^/]+)/layout", uri)
        if match:
            name = match.group("name")
            if name not in catalog.TAB_KINDS:
                raise ToolError(
                    f"unknown tab {name!r}",
                    "use one of: " + ", ".join(catalog.TAB_KINDS),
                )
            return self._read_artifact(self.artifacts_dir / f"ui-layout-{name}.json")
        raise ToolError(
            f"unknown resource {uri!r}",
            "list resources via resources/list",
        )

    def _read_artifact(self, path: Path) -> str:
        if not path.is_file():
            raise ToolError(
                f"no artifact at {path.name} yet",
                "call dump_ui_layout first (with the matching tab) to produce it",
            )
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ToolError(f"cannot read {path.name}: {exc}", "retry the producing tool")

    # -- prompts -----------------------------------------------------------

    def get_prompt(self, name: str, arguments: dict | None = None) -> dict:
        args = arguments or {}
        if name == "diagnose_gallery":
            symptom = args.get("symptom") or "(symptom not given)"
            body = (
                "Investigate an Image Gallery issue in Improve-ImgSLI.\n\n"
                f"Symptom: {symptom}\n\n"
                "Follow the diagnosis ladder, cheapest first:\n"
                "1. read_log (level=WARNING) — recent app errors/lifecycle.\n"
                "2. dump_ui_layout (tab=image_gallery) — geometry, visibility, "
                "colors of the gallery chrome; look for invisible overlays or "
                "zero-size cells.\n"
                "3. list_actions (owner_tab=image_gallery) then run_action for a "
                "harmless toggle to compare states.\n"
                "4. query_trace for the dispatch/render chain around the fault.\n"
                "5. capture_surface surface=gallery-populated for a visual check.\n\n"
                "Diff each probe against the nearest working path before forming "
                "a mechanism hypothesis; do not stack more than two live probes "
                "without a narrowed layer."
            )
            return {"description": "Diagnose an Image Gallery issue.", "text": body}
        if name == "capture_and_inspect":
            surface = args.get("surface") or "(surface not given)"
            body = (
                "Capture and inspect an Improve-ImgSLI surface.\n\n"
                f"Surface: {surface}\n\n"
                "1. list_surfaces — confirm the exact name and whether it is "
                "isolated (QRhi/GL surfaces render blank).\n"
                "2. capture_surface with the name and a theme.\n"
                "3. dump_ui_layout for the same tab — geometry/color facts to "
                "cross-check the screenshot.\n"
                "4. Summarize deltas: what moved, what changed color, what is "
                "missing versus the expected layout.\n\n"
                "Remember the live canvas is not capturable headlessly; only "
                "chrome is meaningful for those surfaces."
            )
            return {"description": "Capture and inspect a surface.", "text": body}
        raise ToolError(f"unknown prompt {name!r}", "list prompts via prompts/list")
