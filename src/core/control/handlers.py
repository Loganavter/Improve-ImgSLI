"""Request handlers for the in-app control channel — one per MCP tool surface.

Built **only** on existing live objects (``devtools.app_snapshot``,
``devtools.ui_layout_dump``, the ActionRegistry, the tracer ring, a live log
ring, the running Qt windows); mutations call real ActionRegistry runners and
real tab methods, exactly as a user click would. Shapes mirror
``mcp-server/app/backend.py``, so the Phase-2 attach path is a proxy swap.

Honesty kept from Phase 1: ``query_trace`` refuses when the tracer was never
installed; ``open_folder`` reports ``routed`` only after a live tab accepted the
folder; ``capture_live`` names its grab method (a widget grab may still render a
QRhi/GL canvas blank — it reports what it produced).
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Any, Callable

from . import discovery
from .discovery import MethodError, capture_live_png, parse_key_sequence

#: Minimum-level filter ladder, mirroring the MCP ``read_log`` semantics.
_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

#: Values the live control channel accepts for the two scalar settings.
VALID_THEMES = ("light", "dark")
VALID_LANGUAGES = ("en", "ru", "zh", "pt_BR")

#: The frozen method surface — one entry per MCP tool.
METHODS: tuple[str, ...] = (
    "capture_live",
    "dump_ui_layout",
    "get_capabilities",
    "get_state",
    "list_actions",
    "list_sessions",
    "list_surfaces",
    "open_folder",
    "open_tab",
    "ping",
    "press_keys",
    "query_trace",
    "read_log",
    "run_action",
    "set_language",
    "set_theme",
)


def _count_nodes(node: dict) -> int:
    total = 1
    for child in node.get("children") or []:
        if isinstance(child, dict):
            total += _count_nodes(child)
    return total


class ControlHandlers:
    """Method dispatch over the live window/app.

    ``window`` is duck-typed (``.store`` plus optional live seams such as
    ``app_context.apply_theme_to_app``); ``registry`` defaults to the process
    ActionRegistry and is injectable for tests.
    """

    #: method name → bound handler; populated after the class body below.
    _DISPATCH: dict[str, Callable[["ControlHandlers", dict[str, Any]], Any]]

    def __init__(
        self,
        *,
        window: Any,
        app: Any = None,
        artifacts_dir: Path | str | None = None,
        log_ring: Any = None,
        registry_provider: Callable[[], Any] | None = None,
    ) -> None:
        self._window = window
        self._app = app
        self._artifacts = Path(artifacts_dir) if artifacts_dir else None
        self._log_ring = log_ring
        self._registry_provider = registry_provider

    # -- plumbing ----------------------------------------------------------

    def _registry(self) -> Any:
        if self._registry_provider is not None:
            return self._registry_provider()
        from ui.actions.registry import get_action_registry

        return get_action_registry()

    def _store(self) -> Any:
        return getattr(self._window, "store", None)

    def _artifacts_dir(self) -> Path:
        # Deferred import of the path helper (kept off the module header so the
        # env convention has exactly one definition, in ``discovery``).
        if self._artifacts is None:
            self._artifacts = discovery.artifacts_dir()
        self._artifacts.mkdir(parents=True, exist_ok=True)
        return self._artifacts

    def _tabs(self) -> list[tuple[str, Any]]:
        try:
            from tabs.registry import TabRegistry

            registry = TabRegistry()
        except Exception:
            return []
        return [
            (session_type, tab)
            for session_type in registry.registered_types
            if (tab := registry.get_tab(session_type)) is not None
        ]

    def _tab_kinds(self) -> list[str]:
        """``workspace.new_<kind>`` kinds — derived, never naming a concrete tab."""
        kinds: set[str] = set()
        try:
            for action in self._registry().all_actions():
                action_id = getattr(action, "action_id", "") or ""
                if action_id.startswith("workspace.new_"):
                    kinds.add(action_id[len("workspace.new_") :])
        except Exception:
            pass
        kinds.update(session_type for session_type, _tab in self._tabs())
        return sorted(kinds)

    def _run_action_id(self, action_id: str) -> bool:
        runner = getattr(self._registry().get(action_id), "run", None)
        if runner is None:
            return False
        runner()
        return True

    # -- dispatch ----------------------------------------------------------

    def capabilities(self) -> dict[str, Any]:
        return {
            "methods": sorted(METHODS),
            "live_actions": True,
            "live_capture": True,
            "live_keys": True,
            "subscribe": False,
        }

    def handle(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Run one method; raises ``MethodError`` for client-visible failures."""
        func = self._DISPATCH.get(method)
        if func is None:
            known = sorted(METHODS)
            close = difflib.get_close_matches(method, known, n=3, cutoff=0.6)
            hint = "known methods: " + ", ".join(known)
            if close:
                hint = "did you mean: " + ", ".join(close) + "? (" + hint + ")"
            raise MethodError(f"unknown method {method!r}", hint)
        return func(self, params or {})

    # -- read-only methods -------------------------------------------------

    def ping(self, _params: dict[str, Any]) -> dict[str, Any]:
        version = ""
        try:
            version = str(self._app.applicationVersion() or "") if self._app else ""
        except Exception:
            pass
        if not version:
            try:
                from core.constants import AppConstants

                version = str(getattr(AppConstants, "APP_VERSION", "") or "")
            except Exception:
                pass
        return {"pong": True, "pid": os.getpid(), "version": version}

    def get_capabilities(self, _params: dict[str, Any]) -> dict[str, Any]:
        return self.capabilities()

    def list_actions(self, params: dict[str, Any]) -> dict[str, Any]:
        from devtools.app_snapshot import dump_actions

        owner_tab = params.get("owner_tab")
        needle = str(params.get("query") or "").strip().lower()
        rows = []
        for action in dump_actions(self._registry()):
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

    def list_sessions(self, _params: dict[str, Any]) -> dict[str, Any]:
        from devtools.app_snapshot import dump_sessions

        sessions = dump_sessions(self._store())
        return {"count": len(sessions), "sessions": sessions}

    def get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        from devtools.app_snapshot import dump_state, resolve_path

        state = dump_state(self._store())
        path = params.get("path")
        if not path:
            return {"path": None, "state": state}
        resolved = resolve_path(state, str(path))
        if resolved is None:
            raise MethodError(
                f"no state at path {path!r}",
                "call get_state without a path to see the available keys",
            )
        return {"path": path, "state": resolved}

    def read_log(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._log_ring is None:
            raise MethodError(
                "no live log ring is attached",
                "reconnect after IMGSLI_CONTROL=1 attaches the ring at startup",
            )
        level = params.get("level")
        threshold = _LEVELS.index(level) if level in _LEVELS else None
        entries = self._log_ring.entries()
        selected = []
        for index, (severity, text) in enumerate(entries):
            if threshold is not None and severity not in _LEVELS:
                continue
            if threshold is not None and _LEVELS.index(severity) < threshold:
                continue
            selected.append({"n": index + 1, "level": severity, "text": text})
        try:
            n = int(params.get("n", 200))
        except (TypeError, ValueError):
            n = 200
        tail = selected[-n:] if n else selected
        return {
            "total_lines": len(entries),
            "returned": len(tail),
            "lines": tail,
        }

    def query_trace(self, params: dict[str, Any]) -> dict[str, Any]:
        from core.tracing.tracer import Tracer

        installed = getattr(Tracer, "_instance", None)
        if installed is None:
            raise MethodError(
                "the tracer is not installed in this process",
                "start the app with IMGSLI_TRACE=1 (or --debug) to record chains",
            )
        needle = str(params.get("filter") or params.get("query") or "").lower()
        serialized = []
        for record in installed.get_records():
            try:
                data = record.to_dict()
            except Exception:
                continue
            if needle and needle not in json.dumps(data, default=str, ensure_ascii=False).lower():
                continue
            serialized.append(data)
        try:
            n = int(params.get("n", 100))
        except (TypeError, ValueError):
            n = 100
        newest = list(reversed(serialized))[:n] if n else []
        return {"total_records": len(serialized), "returned": len(newest), "records": newest}

    def dump_ui_layout(self, params: dict[str, Any]) -> dict[str, Any]:
        tab = params.get("tab")
        if tab:
            self._run_action_id(f"workspace.new_{tab}")
        from devtools.ui_layout_dump import dump_all_windows

        data = dump_all_windows(self._registry())
        name = f"ui-layout-{tab}.json" if tab else "ui-layout.json"
        target = self._artifacts_dir() / name
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        windows = data.get("windows") or []
        nodes = sum(_count_nodes(win) for win in windows if isinstance(win, dict))
        return {"path": str(target), "tab": tab, "windows": len(windows), "node_count": nodes}

    def list_surfaces(self, _params: dict[str, Any]) -> dict[str, Any]:
        return discovery.live_surfaces(self._tabs(), page_of=self._page_of)

    def _page_of(self, session_type: str) -> bool:
        """Is that tab OPEN right now? Fail-open to False (see list_surfaces)."""
        try:
            from tabs.registry import TabRegistry

            return TabRegistry().get_page(session_type) is not None
        except Exception:
            return False

    # -- mutating methods --------------------------------------------------

    def open_tab(self, params: dict[str, Any]) -> dict[str, Any]:
        tab = str(params.get("tab") or "")
        kinds = self._tab_kinds()
        hint = (
            "use one of: " + ", ".join(kinds)
            if kinds
            else "no workspace tab is registered yet — retry after startup"
        )
        action_id = f"workspace.new_{tab}"
        if tab and self._run_action_id(action_id):
            return {
                "launched": False,
                "reused": True,
                "tab": tab,
                "action_id": action_id,
                "via": "action",
            }
        # Deferred tabs register their session blueprint *after* startup, so no
        # ``workspace.new_*`` action exists for them; the live-user path is the
        # session manager the New Session picker uses for exactly this.
        if tab and self._create_session(tab):
            return {
                "launched": False,
                "reused": True,
                "tab": tab,
                "action_id": None,
                "via": "session_manager",
            }
        raise MethodError(f"unknown tab {tab!r}", hint)

    def _create_session(self, tab: str) -> bool:
        """Create a session for a registered tab type via the session manager."""
        if not any(session_type == tab for session_type, _tab in self._tabs()):
            return False
        context = getattr(self._window, "app_context", None)
        create = getattr(getattr(context, "session_manager", None), "create_session", None)
        if not callable(create):
            return False
        try:
            create(tab)
        except Exception:
            return False
        return True

    def run_action(self, params: dict[str, Any]) -> dict[str, Any]:
        action_id = str(params.get("action_id") or "")
        known = sorted(a.action_id for a in self._registry().all_actions())
        if not self._run_action_id(action_id):
            close = difflib.get_close_matches(action_id, known, n=3, cutoff=0.5)
            hint = "call list_actions to see valid ids"
            if close:
                hint = "did you mean: " + ", ".join(close) + "? (" + hint + ")"
            raise MethodError(f"{action_id!r} is not a registered Find Action", hint)
        return {"ran": True, "action_id": action_id}

    def open_folder(self, params: dict[str, Any]) -> dict[str, Any]:
        raw = params.get("path")
        target = Path(str(raw)).expanduser() if raw else None
        if target is None or not target.is_dir():
            raise MethodError(
                f"{target} is not an existing directory",
                "pass an absolute (or ~-prefixed) path to a folder of images",
            )
        # Route via the tab's own drop path (what a user drag-and-drop uses).
        # No concrete tab is named (host isolation contract): the tab that
        # accepts a *directory* reveals itself through ``accepts_drop``.
        routed = self._route_folder(target)
        if routed is None:
            for session_type, tab in self._tabs():
                if self._accepts_folder(tab, target):
                    self._run_action_id(f"workspace.new_{session_type}")
            routed = self._route_folder(target)
        if routed is None:
            raise MethodError(
                "no live tab accepted the folder",
                "open a gallery-like tab once, then retry open_folder",
            )
        return {"routed": True, "path": str(target), "tab": routed}

    @staticmethod
    def _accepts_folder(tab: Any, folder: Path) -> bool:
        try:
            return bool(tab.accepts_drop([folder]))
        except Exception:
            return False

    def _route_folder(self, folder: Path) -> str | None:
        """Hand *folder* to the first tab that accepts it; returns its type."""
        for session_type, tab in self._tabs():
            if not self._accepts_folder(tab, folder):
                continue
            try:
                if tab.handle_drop([folder]):
                    return session_type
            except Exception:
                continue
        return None

    def set_theme(self, params: dict[str, Any]) -> dict[str, Any]:
        theme = str(params.get("theme") or "")
        if theme not in VALID_THEMES:
            raise MethodError(
                f"unknown theme {theme!r}", "use one of: " + ", ".join(VALID_THEMES)
            )
        self._persist_setting("theme", theme)
        context = getattr(self._window, "app_context", None)
        apply_to_app = getattr(context, "apply_theme_to_app", None)
        if callable(apply_to_app) and self._app is not None:
            apply_to_app(self._app)
        return {"theme": theme, "applied": True}

    def set_language(self, params: dict[str, Any]) -> dict[str, Any]:
        language = str(params.get("language") or "")
        if language not in VALID_LANGUAGES:
            raise MethodError(
                f"unknown language {language!r}",
                "use one of: " + ", ".join(VALID_LANGUAGES),
            )
        self._persist_setting("language", language)
        from resources.translations import emit_language_changed

        emit_language_changed(language)
        return {"language": language, "applied": True}

    def _persist_setting(self, key: str, value: str) -> None:
        """Persist via the app's own QSettings scope (same keys Phase 1 wrote)."""
        try:
            from PySide6.QtCore import QSettings

            settings = QSettings("improve-imgsli", "improve-imgsli")
            settings.setValue(key, value)
            settings.sync()
        except Exception as exc:
            raise MethodError(
                f"could not persist {key}={value!r}: {exc}",
                "check that the app config directory is writable",
            )

    # -- capture / input ---------------------------------------------------

    def capture_live(self, params: dict[str, Any]) -> dict[str, Any]:
        return capture_live_png(
            self._app, self._window, params.get("what"), self._artifacts_dir()
        )

    def press_keys(self, params: dict[str, Any]) -> dict[str, Any]:
        """Inject a real key sequence into the live focus widget (QTest)."""
        from PySide6.QtTest import QTest

        sequence = parse_key_sequence(params.get("keys"))
        target = self._key_target()
        if target is None:
            raise MethodError(
                "no live window to receive keys",
                "focus a window first (e.g. run_action platform.settings)",
            )
        for key, modifiers, _label in sequence:
            QTest.keyClick(target, key, modifiers)
        return {
            "pressed": [label for _key, _mods, label in sequence],
            "count": len(sequence),
            "target": type(target).__name__,
        }

    def _key_target(self) -> Any:
        """Active window's focus widget, else the main window (per spec)."""
        from PySide6.QtWidgets import QApplication, QWidget

        focused = None
        instance = self._app if self._app is not None else QApplication.instance()
        if instance is not None:
            try:
                window = instance.activeWindow()
                focused = window.focusWidget() if window is not None else None
            except Exception:
                focused = None
        if focused is None and isinstance(self._window, QWidget):
            focused = self._window
        return focused


#: The frozen method surface: one entry per MCP tool. Defined after the class
#: body so every method object exists before it is referenced.
ControlHandlers._DISPATCH = {name: getattr(ControlHandlers, name) for name in METHODS}
