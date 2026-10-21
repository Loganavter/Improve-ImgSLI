"""Scene command verification: diff two scene reads, judge the declared intent.

The rule this module enforces (plan ``discriminator``): *a scene command is
verified only by re-reading the scene and matching the intended state; a command
that "ran" but did not change the scene is a failure.* Three verdicts, reported
together:

* a declared ``expect`` path/value the re-read scene does not hold (the intent
  was not reached, or the field is not where the caller thought);
* **nothing changed at all** (a value-taking command that was already satisfied —
  a no-op is not an outcome);
* a change **outside** the declared paths and the command's declared scope
  (something else moved, which is how a command silently corrupts a scene).

Pure functions over the payload ``scene_read.read_canvas_scene`` returns: the
verifier reads the scene through the S1 verb's own serializer, never a second
geometry source.
"""

from __future__ import annotations

from typing import Any

#: Float tolerance for a declared post-condition (the scene reports floats).
TOLERANCE = 1e-6


def flatten_scene(payload: Any, prefix: str = "") -> dict[str, Any]:
    """``{"magnifiers[0].visible": False, ...}`` — every leaf of a scene payload."""
    leaves: dict[str, Any] = {}
    if isinstance(payload, dict):
        for key in payload:
            leaves.update(
                flatten_scene(payload[key], f"{prefix}.{key}" if prefix else str(key))
            )
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            leaves.update(flatten_scene(item, f"{prefix}[{index}]"))
    else:
        leaves[prefix] = payload
    return leaves


def scene_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Scene paths whose leaf value differs between two reads (sorted)."""
    first, second = flatten_scene(before), flatten_scene(after)
    changed = []
    for path in sorted(set(first) | set(second)):
        if path not in first or path not in second:
            changed.append(path)
        elif not values_match(first[path], second[path]):
            changed.append(path)
    return changed


def values_match(got: Any, wanted: Any) -> bool:
    """Declared-value equality (floats within tolerance; a bool is never 1)."""
    if isinstance(wanted, bool) or isinstance(got, bool):
        return isinstance(wanted, bool) and isinstance(got, bool) and got is wanted
    if isinstance(wanted, (int, float)) and isinstance(got, (int, float)):
        return abs(float(got) - float(wanted)) <= TOLERANCE
    if isinstance(wanted, list) and isinstance(got, list):
        return len(wanted) == len(got) and all(
            values_match(got_item, wanted_item)
            for got_item, wanted_item in zip(got, wanted)
        )
    return got == wanted


def _segments(path: str) -> tuple[str, ...]:
    """``"magnifiers[0].visible"`` → ``("magnifiers", "0", "visible")``."""
    out: list[str] = []
    token = ""
    index = 0
    while index < len(path):
        char = path[index]
        if char == ".":
            if token:
                out.append(token)
            token = ""
        elif char == "[":
            if token:
                out.append(token)
            token = ""
            close = path.find("]", index)
            if close < 0:
                return tuple(out)
            out.append(path[index + 1 : close])
            index = close
        else:
            token += char
        index += 1
    if token:
        out.append(token)
    return tuple(out)


def resolve_scene_path(payload: Any, path: str) -> tuple[bool, Any]:
    """Value at ``path`` in a scene payload, or ``(False, None)``."""
    current = payload
    for segment in _segments(path):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.lstrip("-").isdigit():
            position = int(segment)
            if not -len(current) <= position < len(current):
                return False, None
            current = current[position]
        else:
            return False, None
    return True, current


def _scope_paths(
    spec: dict[str, Any], params: dict[str, Any]
) -> tuple[tuple[str, ...], ...]:
    """The command's declared scope as segment tuples (``{id}`` filled in)."""
    out = []
    for template in spec.get("scope") or ():
        try:
            resolved = template.format(**params)
        except (KeyError, IndexError):
            resolved = template
        out.append(_segments(resolved))
    return tuple(out)


def _is_declared(path: str, declared: tuple[tuple[str, ...], ...]) -> bool:
    segments = _segments(path)
    for prefix in declared:
        if not prefix:
            continue
        if segments[: len(prefix)] == prefix:
            return True
        if len(segments) < len(prefix) and prefix[: len(segments)] == segments:
            return True
    return False


def verify_command(
    spec: dict[str, Any],
    params: dict[str, Any],
    after: dict[str, Any],
    expect: dict[str, Any],
    changed: list[str],
) -> dict[str, Any] | None:
    """The verification verdict for one command (``None`` = verified).

    ``spec`` carries the command's declared ``scope`` (the scene subtrees it is
    allowed to touch), ``params`` fills the scope templates and ``expect`` is the
    caller's declared post-condition. Reporting every problem at once lets one
    retry fix them all.
    """
    problems: list[str] = []
    for path, wanted in expect.items():
        found, got = resolve_scene_path(after, str(path))
        if not found:
            problems.append(f"expect path {path!r} is not in the scene")
        elif not values_match(got, wanted):
            problems.append(f"{path}: expected {wanted!r}, scene reports {got!r}")
    if not changed:
        problems.append(
            "the command ran but changed nothing in the scene "
            "(idempotent no-op: the target already had that value)"
        )
    declared = tuple(_segments(str(path)) for path in expect) + _scope_paths(spec, params)
    stray = [path for path in changed if not _is_declared(path, declared)]
    if stray:
        problems.append(
            "changed scene paths the command does not declare: " + ", ".join(stray[:8])
        )
    if not problems:
        return None
    return {"problems": problems, "changed": changed}
