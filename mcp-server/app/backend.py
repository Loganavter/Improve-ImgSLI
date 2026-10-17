"""Tool/resource/prompt handlers for the Improve-ImgSLI MCP server.

Stdlib only — no third-party imports — so the server runs in any Python 3.11+
without installing the (optional) ``mcp`` SDK. Everything the app exposes
headlessly is reached the way a developer would: a ``python src/__main__.py``
subprocess with the launcher's startup flags, plus the devtools
(``devtools.capture_surface``, ``devtools.app_snapshot``).

Answering model (documented in ``README.md`` and ``docs/dev/MCP.md``):

- **live first** — when an instance is attached over the in-app control socket
  (``live.py``), *every* tool is proxied to it and the result is normalised into
  the shapes below. Results say ``source: "live"``.
- **fallback (Phase 1)** — with no live instance: reads boot a headless app
  snapshot (``--dump-app-snapshot``) and cache it briefly, ``--dump-ui-layout``
  boots for the widget tree, and the log/tracer are read from disk; mutations
  start a detached process (``--open-tab`` / ``--run-action``) or persist a
  scalar setting through the app's own QSettings keys. Results say
  ``source: "fallback"``. ``press_keys`` has no fallback and errors honestly.
- A transport failure while attached (``LiveUnavailable``) falls back for that
  call and pauses re-attaching briefly (``process_policy``/``live``); an
  app-reported failure (``LiveError``) is surfaced as a ``ToolError`` instead.

Fallback launches go through ``process_policy.launch_env`` — headless unless
``IMGSLI_MCP_DISPLAY`` opts in — and reuse a tab's live fallback process rather
than spawning a second window.

Security: local-only; ``run_action`` is allowlisted to ids present in the
ActionRegistry snapshot (the live app validates its own ids); ``open_folder``
accepts existing directories only; no arbitrary paths, no Python evaluation, and
no file *contents* are ever returned (only the app's own log/trace/catalog
artifacts).
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

from .live import LiveBackend, LiveError, LiveUnavailable, action_enabled, action_reason
from .process_policy import (
    PRESERVED_LOG_NAME,
    ProcessRegistry,
    launch_env,
    preserve_live_log,
)

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


def _edit_may_have_completed(exc: LiveUnavailable) -> ToolError:
    """A mutation whose request was written but never answered (plan P2).

    The app may already have applied the edit, so the caller must not treat
    this as "nothing happened": the message says so explicitly and the hint
    steers to re-reading state instead of retrying the edit.
    """
    return ToolError(
        f"{exc.message} — the operation may have completed",
        "the request was sent before the timeout; re-read state to confirm "
        "instead of retrying the edit",
    )


class AppBackend:
    """Handlers behind the MCP tools/resources/prompts.

    Every external effect is injectable (``snapshot_runner``,
    ``launcher``, ``settings_writer``, ``artifacts_dir``, ``python``,
    ``live_backend``, ``process_registry``) so the test-suite exercises the
    wiring without a GUI, a display, a subprocess, or the user's real QSettings.
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
        live_backend: LiveBackend | None = None,
        process_registry: ProcessRegistry | None = None,
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
        #: Live-instance adapter; ``client_if_alive`` gates every tool call.
        self.live = live_backend if live_backend is not None else LiveBackend()
        #: Fallback launches keyed by tab, so ``open_tab`` never spawns twice.
        self.processes = process_registry if process_registry is not None else ProcessRegistry()

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
        """Environment inheriting the session, plus the app's import path."""
        return self._with_import_path(dict(os.environ), extra)

    def _with_import_path(
        self, env: dict[str, str], extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        src = str(self.repo_root / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        if extra:
            env.update(extra)
        return env

    def _probe_env(self) -> dict[str, str]:
        """Headless env for read-only probe boots (see ``process_policy``)."""
        return self._with_import_path(launch_env(visible=False))

    def _launch_env(self) -> dict[str, str]:
        """Env for a detached fallback launch: headless unless ``IMGSLI_MCP_DISPLAY``."""
        return self._with_import_path(launch_env(visible=True))

    def _preserve_log_if_live(self) -> str | None:
        """Keep the running instance's log before a boot rewrites ``log.txt``.

        The app truncates ``log.txt`` on every start, so a fallback boot wipes
        the live app's log; ``read_log`` then serves the preserved copy while a
        live instance is attached (defect 3, ``process_policy``).
        """
        if self.live.client_if_alive() is None:
            return None
        return preserve_live_log(self.artifacts_dir, source=self.log_path)

    def _run_app(
        self,
        args: list[str],
        *,
        timeout: float | None = None,
    ) -> tuple[int, str, str]:
        """Blocking headless app run (used by the read-only probe flags)."""
        self._preserve_log_if_live()
        env = self._probe_env()
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
        self._preserve_log_if_live()
        if self._launcher is not None:
            return self._launcher(args)
        proc = subprocess.Popen(
            [self.python, str(self.repo_root / "src" / "__main__.py"), *args],
            env=self._launch_env(),
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
        code, _out, err = self._run_app([*args, "--dump-app-snapshot", str(target)])
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

    # -- live / fallback routing -------------------------------------------

    def _live_or_fallback(
        self, proxy: str, fallback: Callable[[], dict], *, mutating: bool = False, **params: Any
    ) -> dict:
        """Answer from the live app when attached, else from the Phase-1 path.

        A transport failure (``LiveUnavailable``) falls back for this call and
        parks re-attaching briefly; an app-reported failure (``LiveError``) is
        the live app's honest answer and is surfaced, not papered over.

        A *mutation* whose request already timed out on the wire is the one
        exception: the app may have applied it, so falling back would risk
        double-applying the edit — it fails with an explicit "may have
        completed" error instead (plan P2).
        """
        client = self.live.client_if_alive()
        if client is not None:
            try:
                return getattr(self.live, proxy)(client=client, **params)
            except LiveUnavailable as exc:
                if mutating and exc.timeout:
                    raise _edit_may_have_completed(exc)
                self.live.note_failure()
            except LiveError as exc:
                raise ToolError(exc.message, exc.hint)
        return fallback()

    def _preserved_log_path(self) -> Path | None:
        candidate = self.artifacts_dir / PRESERVED_LOG_NAME
        return candidate if candidate.is_file() else None

    # -- read-only tools ---------------------------------------------------

    def list_actions(self, *, query: str | None = None, owner_tab: str | None = None) -> dict:
        return self._live_or_fallback(
            "list_actions",
            lambda: self._fallback_list_actions(query=query, owner_tab=owner_tab),
            query=query,
            owner_tab=owner_tab,
        )

    def _fallback_list_actions(
        self, *, query: str | None = None, owner_tab: str | None = None
    ) -> dict:
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
                    "enabled": action_enabled(row),
                    "reason": action_reason(row),
                }
                for row in rows
            ],
            "source": "fallback",
        }

    def list_sessions(self) -> dict:
        return self._live_or_fallback("list_sessions", self._fallback_list_sessions)

    def _fallback_list_sessions(self) -> dict:
        sessions = list(self.snapshot().get("sessions") or [])
        return {"count": len(sessions), "sessions": sessions, "source": "fallback"}

    def get_state(self, *, path: str | None = None) -> dict:
        return self._live_or_fallback(
            "get_state", lambda: self._fallback_get_state(path=path), path=path
        )

    def _fallback_get_state(self, *, path: str | None = None) -> dict:
        state = self.snapshot().get("state") or {}
        if not path:
            return {"path": None, "state": state, "source": "fallback"}
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
        return {"path": path, "state": current, "source": "fallback"}

    def read_log(self, *, n: int = 200, level: str | None = None) -> dict:
        client = self.live.client_if_alive()
        if client is not None:
            preserved = self._preserved_log_path()
            if preserved is not None:
                # defect 3: a fallback boot rewrote log.txt, so the copy taken
                # just before it is the running instance's log — serve that.
                return self._read_log_file(preserved, n=n, level=level)
            try:
                return self.live.read_log(client=client, n=n, level=level)
            except LiveUnavailable:
                self.live.note_failure()
            except LiveError as exc:
                raise ToolError(exc.message, exc.hint)
        return self._read_log_file(self.log_path, n=n, level=level)

    def _read_log_file(self, path: Path, *, n: int, level: str | None) -> dict:
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
            "source": "fallback",
        }

    def query_trace(self, *, filter: str | None = None, n: int = 100) -> dict:
        return self._live_or_fallback(
            "query_trace", lambda: self._fallback_query_trace(filter=filter, n=n), filter=filter, n=n
        )

    def _fallback_query_trace(self, *, filter: str | None = None, n: int = 100) -> dict:
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
            "source": "fallback",
        }

    def dump_ui_layout(self, *, tab: str | None = None, out: str | None = None) -> dict:
        return self._live_or_fallback(
            "dump_ui_layout",
            lambda: self._fallback_dump_ui_layout(tab=tab, out=out),
            tab=tab,
            out=out,
        )

    def _fallback_dump_ui_layout(self, *, tab: str | None = None, out: str | None = None) -> dict:
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
        code, _stdout, err = self._run_app(args)
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
        return {
            "path": str(target),
            "tab": tab,
            "windows": len(windows),
            "node_count": nodes,
            "source": "fallback",
        }

    def list_surfaces(self) -> dict:
        return self._live_or_fallback("list_surfaces", self._fallback_list_surfaces)

    def _fallback_list_surfaces(self) -> dict:
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
        return {"count": len(rows), "surfaces": rows, "source": "fallback"}

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
        return self._live_or_fallback(
            "open_tab", lambda: self._fallback_open_tab(tab=tab), mutating=True, tab=tab
        )

    def _fallback_open_tab(self, *, tab: str) -> dict:
        from . import catalog

        if tab not in catalog.TAB_KINDS:
            raise ToolError(
                f"unknown tab {tab!r}",
                "use one of: " + ", ".join(catalog.TAB_KINDS),
            )
        existing = self.processes.live_pid(tab)
        if existing is not None:
            return {
                "launched": False,
                "pid": existing,
                "tab": tab,
                "reused": True,
                "source": "fallback",
            }
        pid = self._launch(["--open-tab", tab])
        self.processes.adopt(tab, pid)
        return {"launched": True, "pid": pid, "tab": tab, "source": "fallback"}

    def run_action(self, *, action_id: str, tab: str | None = None) -> dict:
        return self._live_or_fallback(
            "run_action",
            lambda: self._fallback_run_action(action_id=action_id, tab=tab),
            mutating=True,
            action_id=action_id,
            tab=tab,
        )

    def _fallback_run_action(self, *, action_id: str, tab: str | None = None) -> dict:
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
        if boot_tab:
            self.processes.adopt(boot_tab, pid)
        return {
            "launched": True,
            "pid": pid,
            "action_id": action_id,
            "tab": boot_tab,
            "source": "fallback",
        }

    def open_folder(self, *, path: str) -> dict:
        return self._live_or_fallback(
            "open_folder",
            lambda: self._fallback_open_folder(path=path),
            mutating=True,
            path=path,
        )

    def _fallback_open_folder(self, *, path: str) -> dict:
        target = Path(path).expanduser()
        if not target.is_dir():
            raise ToolError(
                f"{target} is not an existing directory",
                "pass an absolute (or ~-prefixed) path to a folder of images",
            )
        pid = self._launch(["--open-tab", "image_gallery"])
        self.processes.adopt("image_gallery", pid)
        return {
            "launched": True,
            "pid": pid,
            "path": str(target),
            "routed": False,
            "source": "fallback",
        }

    def set_theme(self, *, theme: str) -> dict:
        return self._live_or_fallback(
            "set_theme",
            lambda: self._fallback_persist("theme", theme, "theme"),
            mutating=True,
            theme=theme,
        )

    def set_language(self, *, language: str) -> dict:
        return self._live_or_fallback(
            "set_language",
            lambda: self._fallback_persist("language", language, "language"),
            mutating=True,
            language=language,
        )

    def press_keys(self, *, keys: str) -> dict:
        """Inject keyboard input into the live app — live-only, never faked.

        There is no headless analogue: without a running instance this answers
        an honest error instead of simulating the keys.
        """
        client = self.live.client_if_alive()
        if client is None:
            raise self._keys_need_live()
        try:
            return self.live.press_keys(client=client, keys=keys)
        except LiveUnavailable as exc:
            if exc.timeout:
                raise _edit_may_have_completed(exc)
            self.live.note_failure()
            raise self._keys_need_live()
        except LiveError as exc:
            raise ToolError(exc.message, exc.hint)

    @staticmethod
    def _keys_need_live() -> ToolError:
        return ToolError(
            "no live instance; keyboard input needs a running app",
            "start the app with the control socket enabled (see docs/dev/MCP.md), then retry",
        )

    def _live_only(self, proxy: str, error: ToolError, *, mutating: bool = True, **params: Any) -> dict:
        """Proxy a tool with no headless analogue — live-only, never faked.

        Follows the ``press_keys`` pattern: a missing instance (or a transport
        fault mid-call) answers ``error`` honestly instead of simulating the
        action; an app-reported failure keeps the app's own message and hint.
        A mutation's ``timeout`` is the exception — the request was on the wire,
        so the edit may have landed and is reported as such (plan P2); a read
        (``mutating=False``) keeps the plain honest error.
        """
        client = self.live.client_if_alive()
        if client is None:
            raise error
        try:
            return getattr(self.live, proxy)(client=client, **params)
        except LiveUnavailable as exc:
            if mutating and exc.timeout:
                raise _edit_may_have_completed(exc)
            self.live.note_failure()
            raise error
        except LiveError as exc:
            raise ToolError(exc.message, exc.hint)

    @staticmethod
    def _elements_need_live() -> ToolError:
        return ToolError(
            "no live instance; element targeting needs a running app",
            "start the app with the control socket enabled (see docs/dev/MCP.md), then retry",
        )

    # -- element targeting (live-only) --------------------------------------

    def ui_elements(self, *, scope: str | None = None, include_disabled: bool | None = None) -> dict:
        return self._live_only(
            "ui_elements",
            self._elements_need_live(),
            mutating=False,
            scope=scope,
            include_disabled=include_disabled,
        )

    def ui_click(self, *, id: str, button: str | None = None, count: int | None = None) -> dict:
        return self._live_only(
            "ui_click", self._elements_need_live(), id=id, button=button, count=count
        )

    def ui_hover(self, *, id: str) -> dict:
        return self._live_only("ui_hover", self._elements_need_live(), id=id)

    def ui_focus(self, *, id: str) -> dict:
        return self._live_only("ui_focus", self._elements_need_live(), id=id)

    def _fallback_persist(self, key: str, value: str, label: str) -> dict:
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
        return {
            label: value,
            "persisted": True,
            "applies_on": "next app start",
            "source": "fallback",
        }

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
        return self._live_or_fallback(
            "capture_surface",
            lambda: self._fallback_capture_surface(surface=surface, theme=theme, out=out),
            mutating=True,
            surface=surface,
            theme=theme,
            out=out,
        )

    def _fallback_capture_surface(
        self, *, surface: str, theme: str | None = None, out: str | None = None
    ) -> dict:
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
        # The devtool boots a real app (which truncates log.txt): keep the
        # running instance's log first (defect 3).
        self._preserve_log_if_live()
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
        return {"surface": surface, "path": str(saved), "theme": chosen_theme, "source": "fallback"}

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
                    "note": (
                        "Read from a headless snapshot; the set_theme/set_language tools "
                        "restyle a live instance immediately and otherwise apply on next start."
                    ),
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
