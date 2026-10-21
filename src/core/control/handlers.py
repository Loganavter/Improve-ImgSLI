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

Audit-Meta: pattern=thin-owner reason="one frozen method table = one MCP tool surface; element/job/nav methods delegate to mixins, routing bodies live in drop_routing"
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Any, Callable, NamedTuple

from . import discovery, elements as element_inventory, jobs
from .capture import capture_live_png
from .discovery import MethodError, parse_key_sequence
from .drop_routing import (
    MEDIA_VIDEO,
    accepts_paths,
    drop_hint,
    media_kind,
    open_file_into,
    open_folder_into,
    route_paths,
)
from .nav_keys import NavMethodsMixin

#: Minimum-level filter ladder, mirroring the MCP ``read_log`` semantics.
_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

#: Values the live control channel accepts for the two scalar settings.
VALID_THEMES = ("light", "dark")
VALID_LANGUAGES = ("en", "ru", "zh", "pt_BR")

#: The only keys ``set_setting`` writes. A whitelist (not "anything QSettings
#: holds"): a control client must not be able to rewrite arbitrary app config.
#: ``theme``/``language`` keep their dedicated verbs (see
#: ``DEDICATED_SETTING_VERBS``) — one home per concern.
SETTING_WHITELIST: frozenset[str] = frozenset({"rhi_backend"})

#: Settings that already have a verb of their own; ``set_setting`` refuses them
#: by naming that verb instead of silently accepting a second write path.
DEDICATED_SETTING_VERBS: dict[str, str] = {
    "theme": "set_theme",
    "language": "set_language",
}

#: Render backends ``rhi_backend`` accepts (the app's own choice list).
VALID_RHI_BACKENDS: tuple[str, ...] = ("opengl", "vulkan")

#: Longest hold ``ui_press`` honours (ms) — a parked press never turns into a
#: multi-minute block inside one socket request.
MAX_HOLD_MS = 5000

#: The frozen method surface — one entry per MCP tool.
METHODS: tuple[str, ...] = (
    "capture_live",
    "dump_ui_layout",
    "get_capabilities",
    "get_state",
    "list_actions",
    "list_sessions",
    "list_surfaces",
    "nav_key",
    "open_file",
    "open_folder",
    "open_properties",
    "open_tab",
    "ping",
    "press_keys",
    "query_trace",
    "read_log",
    "run_action",
    "set_language",
    "set_setting",
    "set_theme", "jobs_cancel", "jobs_list", "ui_click", "ui_elements", "ui_focus",
    "ui_hover",
    "ui_nav_state",
    "ui_press",
)


class _HeldPress(NamedTuple):
    """A press parked by ``ui_press(release=false)``, awaiting its release."""

    element_id: str
    widget: Any
    pos: Any


def _clamp_hold_ms(value: Any) -> int:
    """``hold_ms`` as an int inside ``0..MAX_HOLD_MS`` (garbage reads as 0)."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_HOLD_MS, number))


def _widget_alive(widget: Any) -> bool:
    """False when Qt already deleted *widget* (a HUD/button that went away)."""
    try:
        from shiboken6 import isValid

        return bool(isValid(widget))
    except Exception:
        return True


def _send_mouse(widget: Any, pos: Any, *, press: bool) -> None:
    """Deliver one real mouse press/release to *widget* at *pos* (in-process)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    if press:
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=pos)
    else:
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=pos)


def _pause(milliseconds: int) -> None:
    """Pump the loop for a bounded hold (the same wait the resolver uses).

    ``QTest.qWait`` (not ``time.sleep``): the app has to stay live while a press
    is held, exactly as during ``resolve_element``'s retry budget. Split out so
    a test can observe the clamp without waiting it.
    """
    if milliseconds <= 0:
        return
    from PySide6.QtTest import QTest

    QTest.qWait(milliseconds)


def _open_file_hint(kind: str, wanted: str | None) -> str:
    """Actionable next step for a route that no tab accepted."""
    if kind == MEDIA_VIDEO:
        # Honest: there is no video intake in the app today (see
        # ``drop_routing.VIDEO_EXTENSIONS``) — naming a tab that takes videos
        # would pretend the file loaded.
        return (
            "this app has no video-file intake yet: the video editor edits "
            "recorded snapshots, it does not open a video file — pass an image "
            "file"
        )
    if wanted:
        return (
            "that tab did not accept the file; omit tab to let the router pick "
            "an accepting tab"
        )
    return (
        "open a tab that loads images (open_tab), then retry open_file"
    )


#: Live dialogs opened through ``open_properties``. A parentless top-level
#: widget is owned by Python, so without a reference the dialog would be
#: garbage-collected right after ``show()``; closed ones are pruned on the next
#: call (``WA_DeleteOnClose`` makes them invalid rather than lingering).
_property_dialogs: list[Any] = []


def show_properties_dialog(path: Path, parent: Any = None) -> str:
    """Show the app's own image-properties dialog for *path*; return its class.

    Uses the ``plugins.image_properties`` service + ``ImagePropertiesDialog``
    (the same objects the Image Compare context menu opens) but **shows** it
    instead of running ``open_image_properties_dialog``: that opener is modal
    (``exec()``), which on the control channel would hold the socket request —
    and its reply — open until a human closed the dialog. Non-modal keeps the
    verb answerable; the dialog is the app's, not a control-surface copy.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import build_image_properties
    from resources.translations import get_current_language
    from resources.translations import tr as app_tr

    global _property_dialogs
    _property_dialogs = [d for d in _property_dialogs if _widget_alive(d)]

    properties = build_image_properties(path=path, display_name=path.name)
    dialog = ImagePropertiesDialog(
        properties,
        # Parent only a real widget: the dialog's own ``parent`` is a
        # ``QWidget`` hand-off, and a duck-typed host must not be passed on.
        parent=parent if isinstance(parent, QWidget) else None,
        current_language=get_current_language() or "en",
        tr_func=app_tr,
    )
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.show()
    dialog.raise_()
    if not dialog.isActiveWindow():
        # Guarded: a raw activateWindow() on an already-active window costs a
        # Wayland busy-cursor frame per call
        # (tests/contracts/test_no_unconditional_activation.py).
        dialog.activateWindow()
    _property_dialogs.append(dialog)
    return type(dialog).__name__



def _count_nodes(node: dict) -> int:
    total = 1
    for child in node.get("children") or []:
        if isinstance(child, dict):
            total += _count_nodes(child)
    return total


class ControlHandlers(
    element_inventory.ElementMethodsMixin, jobs.JobMethodsMixin, NavMethodsMixin
):
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
        #: A press parked by ``ui_press(release=false)`` (released by the next
        #: ``ui_press`` — see :meth:`_release_held_press`).
        self._held_press: _HeldPress | None = None

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
            "live_elements": True,
            "live_jobs": True,
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
        # Frozen P2 row shape (additive): ``reason`` is JSON null when runnable.
        frozen = (
            "action_id", "label", "owner_tab", "topic", "shortcut", "enabled", "reason",
        )
        return {
            "count": len(rows),
            "actions": [{key: row.get(key) for key in frozen} for row in rows],
        }

    def list_sessions(self, _params: dict[str, Any]) -> dict[str, Any]:
        from devtools.app_snapshot import dump_sessions

        sessions = dump_sessions(self._store())
        return {"count": len(sessions), "sessions": sessions}

    def get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        from devtools.app_snapshot import (
            dump_state,
            resolve_path_present,
            tab_page_widgets,
        )

        state = dump_state(self._store(), tab_widgets=tab_page_widgets(self._tabs()))
        path = params.get("path")
        if not path:
            return {"path": None, "state": state}
        found, resolved = resolve_path_present(state, str(path))
        if not found:
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
        hint = drop_hint(params)
        wanted = str(params.get("tab") or "").strip() or None
        if wanted is not None:
            # Targeted: a file-only tab gets the folder's images as files
            # (it has no driveable "add images" dialog) — see drop_routing.
            try:
                return open_folder_into(
                    target,
                    wanted,
                    tabs=self._tabs,
                    kinds=self._tab_kinds(),
                    run_action=self._run_action_id, hint=hint,
                )
            except ValueError as exc:
                raise MethodError(
                    str(exc),
                    "open that tab first (open_tab), then retry — a folder "
                    "aimed at a file-only tab loads as that tab's images",
                ) from None
        # Route via the tab's own drop path (what a user drag-and-drop uses).
        # No concrete tab is named (host isolation contract): the tab that
        # accepts a *directory* reveals itself through ``accepts_drop``.
        routed = route_paths(self._tabs(), [target], hint=hint)
        if routed is None:
            for session_type, tab in self._tabs():
                if accepts_paths(tab, [target]):
                    self._run_action_id(f"workspace.new_{session_type}")
            routed = route_paths(self._tabs(), [target], hint=hint)
        if routed is None:
            raise MethodError(
                "no live tab accepted the folder",
                "open a gallery-like tab once, then retry open_folder",
            )
        return {"routed": True, "path": str(target), "tab": routed}

    def open_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Load ONE file into a tab that accepts it; reject everything else.

        The receiving tab is discovered through its own
        ``accepts_drop``/``handle_drop`` (``drop_routing.open_file_into``) — the
        same path a drag-and-drop uses — so no concrete tab is named here
        (platform isolation, ``tests/contracts/test_platform_isolation.py``).
        Without a forced ``tab`` the candidate kinds are derived from the tabs
        themselves: the active tab first when it accepts the file, then every
        kind whose tab accepts it. A video names no receiver (the app has no
        video-file intake), so it fails by name instead of claiming a load that
        never happened.
        """
        raw = params.get("path")
        target = Path(str(raw)).expanduser() if raw else None
        if target is None or not target.is_file():
            raise MethodError(
                f"{target} is not an existing file",
                "pass an absolute (or ~-prefixed) path to an image file",
            )
        kind = media_kind(target)
        if not kind:
            raise MethodError(
                f"unsupported file type {target.suffix or target.name!r}",
                "pass an image or a video file "
                "(images: png, jpg, jpeg, bmp, tiff, tif, webp, jxl)",
            )
        wanted = str(params.get("tab") or "").strip() or None
        try:
            return open_file_into(
                target,
                wanted=wanted,
                candidates=self._file_candidates(target),
                tabs=self._tabs,
                kinds=self._tab_kinds(),
                run_action=self._run_action_id,
            )
        except ValueError as exc:
            raise MethodError(str(exc), _open_file_hint(kind, wanted)) from None

    def _file_candidates(self, path: Path) -> list[str]:
        """Tab kinds that accept *path*, the active one first (never a literal).

        Derived from the tabs' own ``accepts_drop`` (tab-agnostic host code):
        a tab that cannot take the file is never opened for it, which is also
        why a video opens nothing — no tab claims that intake.
        """
        accepting = [
            session_type
            for session_type, tab in self._tabs()
            if accepts_paths(tab, [path])
        ]
        active = self._active_kind()
        if active in accepting:
            accepting.remove(active)
            accepting.insert(0, active)
        return accepting

    def _active_kind(self) -> str | None:
        """The active workspace session's kind, or ``None`` (no live session)."""
        store = self._store()
        getter = getattr(store, "get_active_workspace_session", None)
        if not callable(getter):
            return None
        try:
            session = getter()
        except Exception:
            return None
        return getattr(session, "session_type", None)

    def open_properties(self, params: dict[str, Any]) -> dict[str, Any]:
        """Show the app's image-properties dialog for an existing file.

        Goes through ``plugins.image_properties`` (the service + dialog the
        Image Compare context menu uses, via ``show_properties_dialog``), never
        a control-surface re-implementation; the dialog is shown non-modally so
        this request can answer while it is on screen.
        """
        raw = params.get("path")
        target = Path(str(raw)).expanduser() if raw else None
        if target is None or not target.is_file():
            raise MethodError(
                f"{target} is not an existing file",
                "pass an absolute (or ~-prefixed) path to an existing image",
            )
        dialog = show_properties_dialog(target, self._window)
        return {"opened": True, "path": str(target), "dialog": dialog}

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

    def set_setting(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write one whitelisted scalar setting and report what it replaced.

        Only ``SETTING_WHITELIST`` keys are reachable here; ``theme`` and
        ``language`` keep their dedicated verbs (the refusal names them), so
        there is exactly one write path per setting. The value is persisted
        through ``_persist_setting`` (the same QSettings scope the app reads)
        and pushed into the live store through its own dispatcher — ``applied``
        says whether the running app adopted it now (``rhi_backend`` only takes
        effect after a restart, so the store holds it and the app reports it
        next start), ``persisted`` whether the write landed.
        """
        key = str(params.get("key") or "").strip()
        if key in DEDICATED_SETTING_VERBS:
            verb = DEDICATED_SETTING_VERBS[key]
            raise MethodError(
                f"{key!r} has its own verb — set_setting does not write it",
                f"call {verb} instead; set_setting writes: "
                + ", ".join(sorted(SETTING_WHITELIST)),
            )
        if key not in SETTING_WHITELIST:
            raise MethodError(
                f"{key!r} is not a settable key",
                "settable keys: "
                + ", ".join(sorted(SETTING_WHITELIST))
                + " (theme/language use set_theme/set_language)",
            )
        value = str(params.get("value") or "").strip()
        if key == "rhi_backend":
            value = value.lower()
            if value not in VALID_RHI_BACKENDS:
                raise MethodError(
                    f"unknown rhi_backend {value!r}",
                    "use one of: " + ", ".join(VALID_RHI_BACKENDS),
                )
        previous = self._read_setting(key)
        self._persist_setting(key, value)
        return {
            "key": key,
            "value": value,
            "applied": self._apply_setting(key, value),
            "persisted": True,
            "previous": previous,
        }

    def _read_setting(self, key: str) -> str | None:
        """The persisted value of *key*, or ``None`` when unset/unreadable."""
        try:
            from PySide6.QtCore import QSettings

            raw = QSettings("improve-imgsli", "improve-imgsli").value(key)
        except Exception:
            return None
        text = str(raw).strip() if raw is not None else ""
        return text or None

    def _apply_setting(self, key: str, value: str) -> bool:
        """Push *key* into the live store through its own dispatcher.

        Redux dogma: state changes go through a dispatched action, never a
        store write. ``False`` means no live store/dispatcher could take it
        (headless test window, or a failed dispatch) — the value is still
        persisted, so the next start reads it.
        """
        store = self._store()
        getter = getattr(store, "get_dispatcher", None)
        dispatcher = getter() if callable(getter) else None
        if dispatcher is None or key != "rhi_backend":
            return False
        from core.state_management.settings_actions import SetRhiBackendAction

        try:
            dispatcher.dispatch(SetRhiBackendAction(value))
        except Exception:
            return False
        return True

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
        """Inject a real key sequence (QTest) into the live focus widget.

        ``target`` (an id from ``ui_elements``) aims it at that widget instead:
        canvases are not in the window's focus chain (details in
        ``elements.resolve.key_target``).
        """
        from PySide6.QtTest import QTest

        sequence = parse_key_sequence(params.get("keys"))
        target = element_inventory.key_target(
            self._registry(),
            params.get("target"),
            fallback=element_inventory.focus_target(self._app, self._window),
        )
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

    def ui_press(self, params: dict[str, Any]) -> dict[str, Any]:
        """Press an element's left mouse button, optionally leaving it down.

        ``release=False`` parks the press (a control that acts while held) and
        answers immediately; the next ``ui_press(id, release=True)`` releases
        **that** widget — the same instance, whatever id resolves — so a hold
        is never orphaned. Resolving an element on any other path releases a
        parked press first, and a widget Qt already deleted is simply forgotten
        (a destroyed widget has no pressed state left to clear). ``hold_ms`` is
        the wait applied *between* press and release of one press+release,
        clamped to ``0..MAX_HOLD_MS``; releasing an earlier hold reports ``0``
        because this call did not hold it. The wait pumps the loop with the same
        bounded ``QTest.qWait`` the element resolver uses, so a hold can never
        outlive its clamp.
        """
        request_release = params.get("release", True)
        if request_release is not None and not isinstance(request_release, bool):
            raise MethodError(
                "ui_press 'release' must be a boolean",
                "release=true presses and releases; release=false parks the press",
            )
        hold_ms = _clamp_hold_ms(params.get("hold_ms", 0))
        if request_release is False:
            target = element_inventory.resolve_element(
                self._registry(), params.get("id")
            )
            self._release_held_press()  # a second hold never leaks the first
            pos = target.rect.center()
            _send_mouse(target.widget, pos, press=True)
            self._held_press = _HeldPress(target.id, target.widget, pos)
            return {"pressed": target.id, "held_ms": 0, "released": False}
        return self._press_and_release(params, hold_ms)

    def _press_and_release(
        self, params: dict[str, Any], hold_ms: int
    ) -> dict[str, Any]:
        """The releasing half of :meth:`ui_press` (one press+release, or a hold)."""
        held, self._held_press = self._held_press, None
        try:
            target = element_inventory.resolve_element(
                self._registry(), params.get("id")
            )
        except MethodError:
            # An id that no longer resolves must not leave the parked press
            # down: release it, then report the resolution failure.
            self._release_held_press(held)
            raise
        if held is not None and _widget_alive(held.widget):
            _send_mouse(held.widget, held.pos, press=False)
            return {"pressed": held.element_id, "held_ms": 0, "released": True}
        pos = target.rect.center()
        _send_mouse(target.widget, pos, press=True)
        _pause(hold_ms)
        _send_mouse(target.widget, pos, press=False)
        return {"pressed": target.id, "held_ms": hold_ms, "released": True}

    def _release_held_press(self, held: _HeldPress | None = None) -> None:
        """Release a parked press (default: the current one) and forget it."""
        parked = self._held_press if held is None else held
        self._held_press = None
        if parked is None or not _widget_alive(parked.widget):
            return
        _send_mouse(parked.widget, parked.pos, press=False)

#: The frozen method surface: one entry per MCP tool, built after the class body.
ControlHandlers._DISPATCH = {name: getattr(ControlHandlers, name) for name in METHODS}
