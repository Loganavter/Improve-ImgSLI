"""Host-neutral entry for the ``get_canvas_scene`` read verb.

The control surface can run actions but cannot answer "where is the scene right
now". ``get_canvas_scene`` answers it: one read verb, deterministic JSON, no
writes and no rendering.

Split of responsibility (platform isolation dogma — ``src/core/`` must not name
a tab or its canvas features):

* **this module** resolves the tab, finds the live canvas widget, frames the
  honest "no canvas" answer, and owns the canonical serializer;
* ``devtools.canvas_scene`` holds the per-canvas adapters (panes, dividers,
  instances, canvas geometry, transform) — the same division of labour as
  ``app_snapshot`` / ``ui_layout_dump`` for the rest of the control channel.

The verb never mutates: lazy state accessors (``get_magnifier_widget_state``,
``ensure_zoom_viewport_state``, …) are avoided entirely, and a payload names the
source of every geometry block so a caller can tell a rendered value from a
documented default. ``RECON-canvas-scene-s0.md`` (F1-F4) is the evidence base.
"""

from __future__ import annotations

import json
from typing import Any

from .discovery import MethodError

#: Payload schema id — bumped when a field changes meaning, not when one is added.
SCENE_SCHEMA = "imgsli-canvas-scene/1"


def canonical_json(payload: Any) -> str:
    """Canonical JSON for a scene payload (sorted keys, stable floats).

    ``get_canvas_scene`` is a read: the same scene twice must serialize to the
    same bytes, so the sorted-key form is part of the contract, not a client
    convention.
    """
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def read_canvas_scene(handlers: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Serialize the live scene of one tab (read-only)."""
    from devtools.canvas_scene import empty_scene_payload, serialize_canvas

    tab = resolve_tab(handlers, params)
    page = page_widget(handlers, tab)
    canvas = find_canvas(page)
    tab_has_concept = _tab_has_canvas_concept(handlers, tab)

    if canvas is None:
        reason = _no_canvas_reason(page, tab_has_concept)
        return {
            **empty_scene_payload(reason),
            "schema": SCENE_SCHEMA,
            "tab": tab,
            "scene_source": None,
            "has_canvas": False,
            "tab_has_canvas_concept": tab_has_concept,
            "reason": reason,
        }

    payload = serialize_canvas(canvas)
    payload.update(
        {
            "schema": SCENE_SCHEMA,
            "tab": tab,
            "has_canvas": True,
            "tab_has_canvas_concept": tab_has_concept,
            "reason": None,
        }
    )
    return payload


# ---------------------------------------------------------------------------
# tab / page / canvas discovery (host-generic: no tab module is named)
# ---------------------------------------------------------------------------


def resolve_tab(handlers: Any, params: dict[str, Any]) -> str:
    """The tab kind this read targets: explicit ``tab``, else the active session."""
    kinds = sorted(session_type for session_type, _tab in handlers._tabs())
    requested = str(params.get("tab") or "").strip()
    hint = (
        "use one of: " + ", ".join(kinds)
        if kinds
        else "no workspace tab is registered yet"
    )
    if requested:
        if requested not in kinds:
            raise MethodError(f"unknown tab {requested!r}", hint)
        return requested
    from devtools.app_snapshot import dump_sessions

    for row in dump_sessions(handlers._store()):
        if row.get("active") and row.get("session_type") in kinds:
            return str(row["session_type"])
    raise MethodError(
        "no active workspace session to read a scene from",
        hint + " — pass tab=<kind>",
    )


def page_widget(handlers: Any, session_type: str) -> Any:
    """The live page widget for a tab kind (``None`` when it is not open).

    Named as a module function so a test can pin it to a real page it built
    itself; production resolves it through the same registry the rest of the
    control surface uses (``get_page`` never *creates* a page).
    """
    try:
        from tabs.registry import TabRegistry

        return TabRegistry().get_page(session_type)
    except Exception:
        return None


def find_canvas(page: Any) -> Any | None:
    """Topmost canvas-like widget in a page, or ``None`` (no mutation).

    Duck-typed on purpose: the host asks "can you serialize a scene?", not
    "are you tab X's canvas class". ``devtools.canvas_scene`` owns the
    capability predicates.
    """
    if page is None:
        return None
    from PySide6.QtWidgets import QWidget

    from devtools.canvas_scene import is_canvas_widget

    candidates = [page]
    try:
        candidates.extend(page.findChildren(QWidget))
    except Exception:
        pass
    for widget in candidates:
        if is_canvas_widget(widget):
            return widget
    return None


def _tab_has_canvas_concept(handlers: Any, tab: str) -> bool:
    """Does that tab ever own a canvas? (separates "no canvas" from "not open")."""
    for session_type, contract in handlers._tabs():
        if session_type != tab:
            continue
        provider = getattr(contract, "get_canvas_geometry_provider", None)
        if not callable(provider):
            return False
        try:
            return provider() is not None
        except Exception:
            return False
    return False


def _no_canvas_reason(page: Any, tab_has_concept: bool) -> str:
    if page is None:
        # A registered kind whose page was never created: the scene does not
        # exist yet, whatever the tab would declare once open.
        return "tab page is not open — open it with open_tab, then re-read the scene"
    if tab_has_concept:
        return "tab declares a canvas but no live canvas widget is in its page"
    return "this tab has no canvas concept (no panes, dividers or transform to report)"
