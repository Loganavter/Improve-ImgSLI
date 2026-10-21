"""The command half of the canvas scene channel — ``run_action(params)`` +
``set_scene_commands`` (S2 of the canvas scene plan).

Why this module exists: for an agent, "the action ran" is not evidence. A scene
command is accepted only when it is

1. **named** — an id from the shared table, never a key/value soup;
2. **typed** — every parameter has a type (and range); an unknown key is
   refused *with the schema in the hint*, so the caller never has to guess;
3. **idempotent** — value-taking (an absolute target), so re-running it lands in
   the same state; a toggle has no place here;
4. **verified by re-reading** — after each command the scene is re-read through
   the S1 read verb (``scene_read.read_canvas_scene``, one scene source, two
   consumers) and the caller's ``expect`` paths are checked. A command that
   changed nothing, or changed something the caller did not declare, is a
   **failure**, not a success.

This module owns resolution, ordering and the two handler surfaces; the schema
lives in :mod:`core.control.scene_command_schema`, the verdict in
:mod:`core.control.scene_command_verify`, and the tab-aware half (schemas, scope,
implementations through the feature command registry / the tab's dispatch) in
``devtools.canvas_scene.commands``. No tab vocabulary here (platform isolation
dogma) and no state writes: a command dispatches.
"""

from __future__ import annotations

from typing import Any

from . import scene_read
from .discovery import MethodError
from .scene_command_schema import (
    commands_hint,
    scene_command_names,
    scene_command_specs,
    schema_text,
    validate_params,
)
from .scene_command_verify import scene_changes, verify_command

#: How many changed scene paths one result reports (the scene is small; keep a
#: pathological scene from flooding the channel).
_MAX_CHANGED = 100


# ---------------------------------------------------------------------------
# canvas resolution (one source of tab/canvas discovery, shared with the read)
# ---------------------------------------------------------------------------


def resolve_scene_canvas(handlers: Any, tab: str | None) -> tuple[str, Any]:
    """``(tab kind, live canvas)`` for a command, or an honest ``MethodError``."""
    requested = str(tab).strip() if tab else ""
    tab_kind = scene_read.resolve_tab(handlers, {"tab": requested} if requested else {})
    page = scene_read.page_widget(handlers, tab_kind)
    canvas = scene_read.find_canvas(page)
    if canvas is None:
        raise MethodError(
            f"tab {tab_kind!r} has no live canvas to command",
            scene_read._no_canvas_reason(
                page, scene_read._tab_has_canvas_concept(handlers, tab_kind)
            ),
        )
    return tab_kind, canvas


# ---------------------------------------------------------------------------
# one command
# ---------------------------------------------------------------------------


def run_one_command(
    handlers: Any,
    command_id: str,
    raw_params: Any,
    *,
    expect: Any = None,
    tab: str | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    """Validate → resolve → read → apply → re-read → verify; one command."""
    from devtools.canvas_scene.commands import canvas_scene_source

    spec = scene_command_specs().get(command_id)
    if spec is None:
        raise MethodError(
            f"{command_id!r} is not a scene command", _unknown_command_hint(command_id)
        )

    params = validate_params(command_id, spec, raw_params)
    if expect is not None and not isinstance(expect, dict):
        raise MethodError(
            f"{command_id}: expect must be an object of scene path → value",
            schema_text(command_id, spec),
        )
    if verify and not isinstance(expect, dict):
        raise MethodError(
            f"{command_id}: verify=True needs expect (a scene path → expected value)",
            schema_text(command_id, spec)
            + ' | expect example: {"magnifiers[0].visible": true, '
            '"dividers[0].thickness": 5}',
        )

    tab_kind, canvas = resolve_scene_canvas(handlers, tab)
    source = canvas_scene_source(canvas)
    if source != spec["canvas"]:
        raise MethodError(
            f"{command_id} applies to a {spec['canvas']} scene, but tab "
            f"{tab_kind!r} reports {source or 'no scene'}",
            commands_hint(),
        )

    before = scene_read.read_canvas_scene(handlers, {"tab": tab_kind})
    spec["apply"](canvas, params, tab=tab_kind)
    after = scene_read.read_canvas_scene(handlers, {"tab": tab_kind})
    changed = scene_changes(before, after)

    failure = verify_command(spec, params, after, expect or {}, changed) if verify else None
    return {
        "ran": True,
        "action_id": command_id,
        "scene_command": True,
        "tab": tab_kind,
        "params": params,
        "changed": changed[:_MAX_CHANGED],
        "changed_count": len(changed),
        "expect": dict(expect) if isinstance(expect, dict) else None,
        "verified": None if not verify else failure is None,
        "failure": failure,
    }


def _unknown_command_hint(command_id: str) -> str:
    import difflib

    hint = commands_hint()
    close = difflib.get_close_matches(command_id, scene_command_names(), n=3, cutoff=0.5)
    if close:
        hint = "did you mean: " + ", ".join(close) + "? (" + hint + ")"
    return hint


# ---------------------------------------------------------------------------
# the two handler surfaces
# ---------------------------------------------------------------------------


def scene_command_run(handlers: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    """``run_action`` routing: a scene command result, or ``None`` (a Find Action)."""
    action_id = str(params.get("action_id") or "")
    if action_id in scene_command_specs():
        has_expect = params.get("expect") is not None
        return run_one_command(
            handlers,
            action_id,
            params.get("params") or {},
            expect=params.get("expect"),
            tab=params.get("tab"),
            verify=has_expect,
        )
    if "params" in params or "expect" in params:
        raise MethodError(
            f"{action_id!r} is a Find Action: it takes no params and cannot be verified",
            "params/expect belong to scene commands — " + commands_hint(),
        )
    return None


def run_scene_command_list(handlers: Any, params: dict[str, Any]) -> dict[str, Any]:
    """``set_scene_commands``: an ordered list, stopping at the first error."""
    raw = params.get("commands")
    verify = bool(params.get("verify", True))
    tab = params.get("tab")
    if not isinstance(raw, list) or not raw:
        raise MethodError(
            "set_scene_commands needs a non-empty list of commands",
            'each item is {"action": <scene command id>, "params": {...}, '
            '"expect": {<scene path>: <value>}}; ' + commands_hint(),
        )

    applied: list[dict[str, Any]] = []
    stopped_at: int | None = None
    error: dict[str, Any] | None = None
    for index, item in enumerate(raw):
        action_id = ""
        try:
            if not isinstance(item, dict):
                raise MethodError(
                    f"command #{index} must be an object with action/params/expect",
                    commands_hint(),
                )
            action_id = str(item.get("action") or "")
            result = run_one_command(
                handlers,
                action_id,
                item.get("params") or {},
                expect=item.get("expect"),
                tab=tab,
                verify=verify,
            )
        except MethodError as exc:
            stopped_at = index
            error = {
                "index": index,
                "action": action_id or None,
                "kind": "invalid_command",
                "message": exc.message,
                "hint": exc.hint,
            }
            break
        except Exception as exc:  # a crashed command path is not a client error
            stopped_at = index
            error = {
                "index": index,
                "action": action_id or None,
                "kind": "command_crashed",
                "message": f"{type(exc).__name__}: {exc}",
                "hint": "call get_canvas_scene to see the scene the command landed in",
            }
            break
        applied.append(
            {
                "index": index,
                "action": action_id,
                "tab": result["tab"],
                "params": result["params"],
                "changed": result["changed"],
                "changed_count": result["changed_count"],
                "expect": result["expect"],
                "verified": result["verified"],
                "failure": result["failure"],
            }
        )
        if result["verified"] is False:
            stopped_at = index
            error = {
                "index": index,
                "action": action_id,
                "kind": "verification_failed",
                "message": "; ".join((result["failure"] or {}).get("problems") or []),
                "hint": "the scene is authoritative: read it (get_canvas_scene) and "
                "declare the expect it actually reports, or fix the command params",
            }
            break

    scene: dict[str, Any] | None = None
    if applied or stopped_at is not None:
        try:
            scene = scene_read.read_canvas_scene(handlers, {"tab": tab} if tab else {})
        except MethodError:
            scene = None
    tab_kind = applied[-1]["tab"] if applied else (scene or {}).get("tab", tab)
    return {
        "ok": error is None,
        "verified": None if not verify else error is None,
        "count": len(applied),
        "applied": applied,
        "stopped_at": stopped_at,
        "error": error,
        "tab": tab_kind,
        "scene": scene,
    }
