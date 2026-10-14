"""Headless snapshot of live app state + action catalog — one JSON blob.

Devtool only: nothing here is imported by the application runtime. It exists
because the two things an agent needs to *drive* the app headlessly — the
ActionRegistry catalog and the Redux ``Store`` slices — are **runtime state**,
populated while the window is built. There is no on-disk file to read and no
restart-free way to ask a *running* process (that is the Phase-2 in-app control
socket in ``docs/dev/MCP.md``).

Wired via ``launcher.sh run --dump-app-snapshot <path>`` / the app's
``--dump-app-snapshot PATH`` flag: the app boots, this module serializes what
it found, writes JSON, and the process exits (mirrors ``--dump-ui-layout``).
Consumed by the host MCP server (``mcp-server/app/backend.py``).

Everything is read-only and best-effort per field — a widget or a store slot
the encoder cannot interpret degrades to a truncated ``str()`` instead of
aborting the whole snapshot, so one exotic value never blanks the surface.

The pure functions (``dump_actions``/``dump_sessions``/``dump_state``) take the
live objects and are unit-testable in-process without a window, which is how
``tests/devtools/test_app_snapshot.py`` exercises them.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: Schema tag on every snapshot, so consumers can detect shape changes.
SNAPSHOT_SCHEMA = "imgsli-app-snapshot/1"

#: Depth cap for the generic encoder (settings/document nesting is shallow).
_MAX_DEPTH = 6


def _display(key: str | None) -> str:
    """Resolve an i18n key to the current language, falling back to the key."""
    if not key:
        return ""
    try:
        from resources.translations import get_current_language, tr

        text = tr(key, get_current_language() or "en")
    except Exception:
        return key
    return text if text and text != key else key


def encode(value: Any, *, depth: int = 0) -> Any:
    """Best-effort JSON-safe conversion, dataclass-aware and depth-capped.

    Order matters: primitives first, then dataclasses (``Store``'s
    ``SettingsState``/``DocumentModel``/``WorkspaceSession`` are dataclasses),
    then the ``ui_layout_dump._jsonable`` recipe for everything else. Unknown
    objects become a truncated ``str()`` so a single opaque Qt handle cannot
    fail the dump.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 400:
            return value[:400] + "…"
        return value
    if depth >= _MAX_DEPTH:
        return "<max-depth>"
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {}
        for field in dataclasses.fields(value):
            try:
                raw = getattr(value, field.name)
            except Exception:
                continue
            out[field.name] = encode(raw, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)[:32]
        return [encode(item, depth=depth + 1) for item in items]
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:32]:
            out[str(key)] = encode(item, depth=depth + 1)
        return out
    try:
        import enum

        if isinstance(value, enum.Enum):
            return value.name
    except Exception:
        pass
    try:
        text = str(value)
    except Exception:
        return "<?>"
    return text if len(text) <= 400 else text[:400] + "…"


def dump_actions(registry: Any) -> list[dict[str, Any]]:
    """Catalog rows from the ``ActionRegistry`` — ids, labels, owners.

    ``registry`` is duck-typed (``all_actions()``) so a test can pass a real
    ``ActionRegistry`` built in-process without a ``MainWindow``.
    """
    rows: list[dict[str, Any]] = []
    try:
        actions = list(registry.all_actions())
    except Exception:
        return rows
    for action in actions:
        try:
            rows.append(
                {
                    "action_id": action.action_id,
                    "label": _display(action.label_key) or action.action_id,
                    "label_key": action.label_key,
                    "description": _display(action.description_key),
                    "owner_tab": action.owner_tab,
                    "topic": action.topic,
                    "shortcut": action.shortcut,
                    "breadcrumb": [
                        _display(segment) or segment
                        for segment in (action.breadcrumb or ())
                        if segment
                    ],
                    "runnable": action.run is not None,
                }
            )
        except Exception:
            continue
    rows.sort(key=lambda row: (row.get("owner_tab") or "", row["action_id"]))
    return rows


def dump_sessions(store: Any) -> list[dict[str, Any]]:
    """Workspace sessions (id, type, title, active) — Store-owned, no Qt."""
    workspace = getattr(store, "workspace", None)
    active = getattr(workspace, "active_session_id", None)
    rows: list[dict[str, Any]] = []
    for session in getattr(workspace, "sessions", None) or []:
        try:
            session_id = session.id
            rows.append(
                {
                    "id": session_id,
                    "session_type": session.session_type,
                    "title": session.title,
                    "active": session_id == active,
                }
            )
        except Exception:
            continue
    return rows


def _document_summary(document: Any) -> dict[str, Any]:
    """Shallow document view: type + image paths — never full pixel state."""
    if document is None:
        return {}
    summary: dict[str, Any] = {"type": type(document).__name__}
    for attr in ("image1_path", "image2_path", "path", "images"):
        try:
            value = getattr(document, attr, None)
        except Exception:
            continue
        if value in (None, "", [], {}):
            continue
        if attr == "images" and isinstance(value, (list, tuple)):
            paths = []
            for item in list(value)[:32]:
                path = getattr(item, "path", None)
                paths.append(path if isinstance(path, str) else encode(item))
            summary["images"] = paths
        else:
            summary[attr] = encode(value)
    return summary


def dump_state(store: Any) -> dict[str, Any]:
    """Redux ``Store`` slices that are meaningful out of process.

    Deliberately omits ``runtime_cache`` (transient GPU/texture bookkeeping,
    huge and meaningless to a fresh reader). ``settings``/``workspace`` come
    from the dataclasses; the active document is summarized to paths.
    """
    state: dict[str, Any] = {
        "settings": encode(getattr(store, "settings", None)),
        "workspace": {
            "sessions": dump_sessions(store),
            "active_session_id": getattr(
                getattr(store, "workspace", None), "active_session_id", None
            ),
        },
    }
    try:
        state["document"] = _document_summary(getattr(store, "document", None))
    except Exception:
        state["document"] = {}
    return state


def dump_snapshot(store: Any, registry: Any) -> dict[str, Any]:
    """Full snapshot: schema tag + actions + state + derived theme/language."""
    state = dump_state(store)
    settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
    return {
        "schema": SNAPSHOT_SCHEMA,
        "actions": dump_actions(registry),
        "state": state,
        "sessions": state["workspace"]["sessions"],
        "theme": settings.get("theme"),
        "language": settings.get("current_language"),
        "ui_scale_factor": settings.get("ui_scale_factor"),
    }


def resolve_path(data: Any, path: str | None) -> Any:
    """Navigate a dotted ``a.b.0`` path into a decoded snapshot value.

    Returns ``None`` for a missing key so a caller can distinguish "no slice"
    from an exception; ``""``/``None`` returns ``data`` unchanged.
    """
    if not path:
        return data
    current = data
    for part in str(path).split("."):
        if part == "":
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
                continue
            except (ValueError, IndexError):
                return None
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
            continue
        return None
    return current
