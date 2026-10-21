"""Scene command schemas + typed parameter validation (S2, host-neutral half).

One home for "what a command takes": the shared table lives in
``devtools.canvas_scene.commands`` (next to the implementations), and this module
turns it into an agent-facing contract — a hint string that carries the schema,
and a validator that refuses an unknown key / wrong type / out-of-range value
*with that hint*, so a caller never has to guess a parameter name.

No tab vocabulary here (platform isolation dogma); no state access either.
"""

from __future__ import annotations

import json
from typing import Any

from .discovery import MethodError

_TYPE_LABELS = {
    "str": "a string",
    "bool": "true or false",
    "int": "an integer",
    "float": "a number",
    "int_list": "a list of integers",
    "float_list": "a list of numbers",
}


def scene_command_specs() -> dict[str, dict[str, Any]]:
    """The shared command table (``{id: spec}``), imported lazily."""
    from devtools.canvas_scene.commands import SCENE_COMMANDS

    return SCENE_COMMANDS


def scene_command_names() -> list[str]:
    """Every scene command id (sorted); empty when the devtools tree is absent."""
    try:
        from devtools.canvas_scene.commands import command_names

        return command_names()
    except Exception:  # pragma: no cover - only when the devtools tree is absent
        return []


def commands_hint() -> str:
    """Every scene command name, for hints that must not leave the caller blind."""
    names = scene_command_names()
    if not names:
        return "no scene commands are registered"
    return "scene commands: " + ", ".join(names)


def schema_text(command_id: str, spec: dict[str, Any]) -> str:
    """`command(params) — summary; example {...}` — the one hint shape.

    The schema travels *in the error*, not only in a tool description: an agent
    that guessed a key gets the correct one back in the same round trip.
    """
    parts = []
    for name, param in spec["params"].items():
        label = _TYPE_LABELS.get(param["type"], param["type"])
        if not param.get("required", True):
            label += ", optional"
        parts.append(f"{name}: {label}{_bounds_text(param)}")
    example = json.dumps(spec.get("example") or {}, ensure_ascii=False)
    return f"{command_id}({', '.join(parts)}) — {spec['summary']}; example: {example}"


def _bounds_text(param: dict[str, Any]) -> str:
    low, high = param.get("minimum"), param.get("maximum")
    if low is not None and high is not None:
        return f" [{low}..{high}]"
    if low is not None:
        return f" [>= {low}]"
    if high is not None:
        return f" [<= {high}]"
    return ""


def validate_params(command_id: str, spec: dict[str, Any], raw: Any) -> dict[str, Any]:
    """Typed params or ``MethodError`` carrying the schema."""
    schema = spec["params"]
    hint = schema_text(command_id, spec)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise MethodError(f"{command_id} takes an object of params", hint)
    unknown = sorted(set(raw) - set(schema))
    if unknown:
        raise MethodError(
            f"unknown param(s) for {command_id}: "
            + ", ".join(repr(key) for key in unknown),
            hint,
        )
    params: dict[str, Any] = {}
    for name, param in schema.items():
        if name not in raw:
            if param.get("required", True):
                raise MethodError(
                    f"{command_id} is missing required param {name!r}", hint
                )
            continue
        value = raw[name]
        problem = _type_problem(param, value)
        if problem is not None:
            raise MethodError(f"{command_id}: param {name!r} must be {problem}", hint)
        low, high = param.get("minimum"), param.get("maximum")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if low is not None and value < low:
                raise MethodError(f"{command_id}: param {name!r} must be >= {low}", hint)
            if high is not None and value > high:
                raise MethodError(f"{command_id}: param {name!r} must be <= {high}", hint)
        params[name] = value
    return params


def _type_problem(param: dict[str, Any], value: Any) -> str | None:
    kind = param["type"]
    if kind == "str":
        return None if isinstance(value, str) else "a string"
    if kind == "bool":
        return None if isinstance(value, bool) else "true or false"
    if kind == "int":
        ok = isinstance(value, int) and not isinstance(value, bool)
        return None if ok else "an integer"
    if kind == "float":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return None if ok else "a number"
    if kind == "int_list":
        ok = isinstance(value, list) and all(
            isinstance(item, int) and not isinstance(item, bool) for item in value
        )
        return None if ok else "a list of integers"
    if kind == "float_list":
        ok = isinstance(value, list) and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value
        )
        return None if ok else "a list of numbers"
    return None  # pragma: no cover - the table only declares the kinds above
