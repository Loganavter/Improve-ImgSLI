"""Headless snapshot of live app state + action catalog — one JSON blob.
Audit-Meta: pattern=leaf-collector size=exempt reason="one read-only snapshot serializer — actions/sessions/state/tab assertion slices share the depth-capped encoder and path resolver"

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

``state["tabs"]`` is the **assertion surface**: read-only, per-tab slices an
agent can compare against what the UI shows ("Quick Look shows image N") in
one ``get_state {path}`` call, with no overlay labels and no tracer. Values are
read from the tab's own live state (Redux session slots + the live tab widget);
a tab that is not the active session reports ``active: false`` and nulls, never
an exception, and an unreadable value is null rather than a plausible default.
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

    Each row carries ``enabled``/``reason`` (the P2 contract-honesty fields: is
    the action runnable *now*, and if not, why) so an agent can plan rather than
    fail at call time. ``registry`` is duck-typed (``all_actions()``) so a test
    can pass a real ``ActionRegistry`` built in-process without a ``MainWindow``.
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
                    # P2 contract honesty: why an agent cannot run it *now*.
                    # Duck-typed: a registry row without the (new) fields still
                    # reports enabled with no reason.
                    "enabled": bool(getattr(action, "enabled", True)),
                    "reason": getattr(action, "reason", None),
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


# -- tab-scoped assertion slices ------------------------------------------
#
# Slot addresses are literals on purpose: this devtool must not import a tab
# package (tabs stay behind their contract). Canonical homes:
# ``tabs/image_gallery/bootstrap_reducers.GALLERY_SLOT_NAME`` == "gallery",
# the gallery chrome façade namespace == "image_gallery", and
# ``tabs/multi_compare/use_cases/persistence._STATE_SLOT``.
_GALLERY_SLOT = "gallery"
_GALLERY_CHROME_SLOT = "image_gallery"
_MULTI_COMPARE_SLOT = "multi_compare.state"


def _active_session(store: Any) -> Any:
    """Active workspace session, or None (storeless/duck-typed test doubles)."""
    try:
        return store.get_active_workspace_session()
    except Exception:
        return None


def _session_slot(store: Any, name: str, session_id: Any) -> Any:
    """Read one session state slot; a missing session/slot is None, never raises."""
    if store is None or not session_id:
        return None
    try:
        return store.get_session_state_slot(name, session_id=session_id)
    except Exception:
        return None


def _text(value: Any) -> str | None:
    """Path/label as text; empty/missing becomes null (never a fake path)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value)
    except Exception:
        return None
    return text or None


def _number(value: Any, cast: type) -> Any:
    if value is None or isinstance(value, bool):
        return None
    try:
        return cast(value)
    except Exception:
        return None


def _controller_of(widget: Any) -> Any:
    """The widget's attached presenter, or None. Explicit links only."""
    if widget is None:
        return None
    for attr in ("_attached_controller", "_controller"):
        controller = getattr(widget, attr, None)
        if controller is not None:
            return controller
    resolve = getattr(widget, "_owner_for_triage", None)
    try:
        return resolve() if callable(resolve) else None
    except Exception:
        return None


def _gallery_slice(store: Any, session: Any, widget: Any) -> dict[str, Any]:
    """Image Gallery browse state + the live chrome knobs.

    Pool/selection/filter/folder come from the ``gallery`` session slot (its
    stated single source of truth); ``sort``/``judgment_domain`` are live
    widget/controller state, so they stay null when the page was never built.
    """
    active = getattr(session, "session_type", None) == "image_gallery"
    row: dict[str, Any] = {
        "active": active,
        "folder": None,
        "item_count": None,
        "selection": None,
        "selection_count": None,
        "filter_text": None,
        "sort": None,
        "judgment_domain": None,
        "metrics_cache_size": None,
    }
    if not active:
        return row
    session_id = getattr(session, "id", None)
    slot = _session_slot(store, _GALLERY_SLOT, session_id)
    if slot is not None:
        items = list(getattr(slot, "items", None) or [])
        selection = [
            path
            for path in (_text(entry) for entry in getattr(slot, "selection", None) or [])
            if path
        ]
        row["folder"] = _text(getattr(slot, "folder", None))
        row["item_count"] = len(items)
        row["selection"] = selection
        row["selection_count"] = len(selection)
        filter_text = getattr(slot, "filter_text", None)
        if isinstance(filter_text, str):
            row["filter_text"] = filter_text
    chrome = _session_slot(store, _GALLERY_CHROME_SLOT, session_id)
    if isinstance(chrome, dict):
        domain = chrome.get("judgment_domain")
        if isinstance(domain, str) and domain:
            row["judgment_domain"] = domain
    controller = _controller_of(widget)
    if controller is not None:
        # The controller's ``_judgment_domain`` is the triage authority; the
        # chrome slot is its persisted mirror.
        domain = getattr(controller, "_judgment_domain", None)
        if isinstance(domain, str) and domain:
            row["judgment_domain"] = domain
        items = getattr(getattr(controller, "state", None), "items", None)
        if items is not None:
            row["metrics_cache_size"] = sum(
                1 for item in items if getattr(item, "metrics", None)
            )
    sort_text = getattr(getattr(widget, "toolbar", None), "sort_text", None)
    if isinstance(sort_text, str) and sort_text:
        row["sort"] = sort_text
    return row


def _quick_look_slice(widget: Any, gallery_active: bool) -> dict[str, Any]:
    """Open Quick Look panel: item, series position, viewport, source side.

    The returned source_side names where the comparison's SOURCE is drawn:
    "preview" when the open item *is* the source, "inset" when the source
    inset shows a different image. Null when the panel is closed/no source.
    """
    row: dict[str, Any] = {
        "active": gallery_active,
        "open": None,
        "path": None,
        "index": None,
        "total": None,
        "zoom": None,
        "pan": None,
        "source_side": None,
    }
    if not gallery_active:
        return row
    overlay = getattr(widget, "_quick_look_overlay", None)
    if overlay is None:
        row["open"] = False
        return row
    try:
        is_open = bool(overlay.isVisible())
    except Exception:
        is_open = False
    row["open"] = is_open
    if not is_open:
        return row
    row["path"] = _text(getattr(getattr(overlay, "_current_item", None), "path", None))
    series = list(getattr(overlay, "_series_items", None) or [])
    row["total"] = len(series)
    row["index"] = _number(getattr(overlay, "_current_idx", None), int)
    canvas = getattr(overlay, "_preview_canvas", None)
    current_view = getattr(canvas, "current_view", None)
    try:
        view = current_view() if callable(current_view) else None
    except Exception:
        view = None
    if isinstance(view, (tuple, list)) and len(view) == 3:
        row["zoom"] = _number(view[0], float)
        row["pan"] = [_number(view[1], float), _number(view[2], float)]
    source = _text(getattr(overlay, "_source_path", None))
    if source and row["path"]:
        row["source_side"] = "preview" if source == row["path"] else "inset"
    return row


def _image_compare_slice(session: Any) -> dict[str, Any]:
    """Image Compare pair + viewport truth (paths, view mode, split, diff)."""
    active = getattr(session, "session_type", None) == "image_compare"
    row: dict[str, Any] = {
        "active": active,
        "left_path": None,
        "right_path": None,
        "mode": None,
        "split_ratio": None,
        "diff_mode": None,
    }
    if not active:
        return row
    document = getattr(session, "document", None)
    row["left_path"] = _text(getattr(document, "image1_path", None))
    row["right_path"] = _text(getattr(document, "image2_path", None))
    view = getattr(getattr(session, "viewport", None), "view_state", None)
    mode = getattr(view, "showing_single_image_mode", None)
    if isinstance(mode, int) and not isinstance(mode, bool):
        row["mode"] = mode
    row["split_ratio"] = _number(getattr(view, "split_position", None), float)
    row["diff_mode"] = _text(getattr(view, "diff_mode", None))
    return row


def _multi_compare_slice(store: Any, session: Any) -> dict[str, Any]:
    """Multi Compare slot grid: slot count, filled paths, focused slot id."""
    active = getattr(session, "session_type", None) == "multi_compare"
    row: dict[str, Any] = {
        "active": active,
        "slot_count": None,
        "filled": None,
        "focused_slot": None,
    }
    if not active:
        return row
    state = _session_slot(store, _MULTI_COMPARE_SLOT, getattr(session, "id", None))
    if state is None:
        return row
    slots = list(getattr(state, "slots", None) or [])
    count = getattr(state, "slot_count", None)
    try:
        row["slot_count"] = int(count()) if callable(count) else len(slots)
    except Exception:
        row["slot_count"] = len(slots)
    row["filled"] = [
        path
        for path in (_text(getattr(slot, "path", None)) for slot in slots)
        if path
    ]
    focused = getattr(state, "focused_slot_id", None)
    if isinstance(focused, int) and not isinstance(focused, bool):
        row["focused_slot"] = focused
    return row


def tab_page_widgets(tabs: Any) -> dict[str, Any]:
    """``session_type`` -> live page widget from ``(session_type, tab)`` pairs.

    Duck-typed over the ``TabContract`` shape (``widget`` property, or the
    private ``_widget`` slot on tabs that have no public accessor) so this
    devtool never imports a tab package. Only widget-local assertion facts need
    the page (Quick Look overlay, gallery sort); tab state is read from slots.
    """
    widgets: dict[str, Any] = {}
    try:
        pairs = list(tabs)
    except Exception:
        return widgets
    for session_type, tab in pairs:
        widget = getattr(tab, "widget", None)
        if widget is None:
            widget = getattr(tab, "_widget", None)
        if widget is not None:
            widgets[str(session_type)] = widget
    return widgets


def dump_tabs(store: Any, tab_widgets: dict[str, Any] | None = None) -> dict[str, Any]:
    """Per-tab assertion slices; a tab that is not active reports nulls.

    ``tab_widgets`` maps ``session_type`` -> live page widget (the handler reads
    them off the tab registry). Only widget-local facts need it (Quick Look,
    gallery sort); everything else comes from the own session's state slots, so
    a storeless or page-less call degrades to nulls instead of raising.
    """
    session = _active_session(store)
    widgets = tab_widgets if isinstance(tab_widgets, dict) else {}
    gallery_widget = widgets.get("image_gallery")
    gallery = _gallery_slice(store, session, gallery_widget)
    gallery["quick_look"] = _quick_look_slice(gallery_widget, gallery["active"])
    return {
        "image_gallery": gallery,
        "image_compare": _image_compare_slice(session),
        "multi_compare": _multi_compare_slice(store, session),
    }


def dump_state(store: Any, *, tab_widgets: dict[str, Any] | None = None) -> dict[str, Any]:
    """Redux ``Store`` slices that are meaningful out of process.

    Deliberately omits ``runtime_cache`` (transient GPU/texture bookkeeping,
    huge and meaningless to a fresh reader). ``settings``/``workspace`` come
    from the dataclasses; the active document is summarized to paths.

    ``tabs`` is the assertion surface (see module docstring): read-only,
    addressed as ``tabs.<tab>[.<sub-slice>]``, with ``active`` naming whether
    that tab is the active workspace session. A missing tab/slice answers
    ``active: false`` + nulls; it is never an exception.
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
    state["tabs"] = dump_tabs(store, tab_widgets=tab_widgets)
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


def resolve_path_present(data: Any, path: str | None) -> tuple[bool, Any]:
    """Navigate a dotted ``a.b.0`` path, reporting presence separately.

    ``(False, None)`` = the path does not exist; ``(True, None)`` = the value
    at that path is JSON null. An assertion surface needs that distinction: a
    null Quick Look field is data, not an unknown path.
    """
    if not path:
        return True, data
    current = data
    for part in str(path).split("."):
        if part == "":
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
                continue
            except (ValueError, IndexError):
                return False, None
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
            continue
        return False, None
    return True, current


def resolve_path(data: Any, path: str | None) -> Any:
    """Navigate a dotted ``a.b.0`` path into a decoded snapshot value.

    Returns ``None`` for a missing key so a caller can distinguish "no slice"
    from an exception; ``""``/``None`` returns ``data`` unchanged. Callers that
    must tell a null value from a missing key use ``resolve_path_present``.
    """
    return resolve_path_present(data, path)[1]
