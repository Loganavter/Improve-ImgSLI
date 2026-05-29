"""Shared event code must not branch on feature-specific state.

Dogma source: docs/dev/CANVAS_FEATURES.md Anti-patterns
("Adding new central ``if feature == ...`` logic",
 "Duplicating state in both feature-owned storage and flat ``ViewState``").

Shared event modules under ``src/events/`` should resolve canvas gestures via
``GestureResolver`` and call only feature-neutral alias namespaces (currently
``preview.*`` is the only neutral namespace; new ones are added as features
generalize). They must not read feature-specific flat ViewState flags or
branch on feature-specific drag flags.
"""

from __future__ import annotations

import ast
import re

import pytest

from ._framework import SRC, iter_py, read, rel

# ViewState fields that smell like feature-coupled flat duplicates. Shared
# event code reading these is a sign that feature state leaked into ViewState.
FEATURE_VIEWSTATE_FIELDS = (
    "overlay_enabled",
)

# interaction_state flags that name a specific feature's drag mode. Shared
# event code branching on these is the old "if magnifier else divider"
# disguised as a flag check.
FEATURE_INTERACTION_FLAGS = (
    "is_dragging_overlay_handle",
    "is_dragging_overlay_split",
    "is_dragging_split_line",
)

# Capability alias namespaces that name a specific canvas feature. Shared
# event code (``src/events/``) must not look these up directly — features
# own gestures, preview workflows, and interaction helpers. Feature-neutral
# namespaces (``preview.*``, ``render.*``) are fine.
FEATURE_ALIAS_PREFIXES = (
    "overlay.",
    "splitter.",
    "magnifier.",
    "divider.",
    "guides.",
    "capture.",
)

EVENTS_ROOT = SRC / "events"
MOUSE_FILE = EVENTS_ROOT / "image_label" / "mouse.py"

# Files known to still leak feature aliases pending their own refactor.
# Each entry is a TODO with the eventual destination noted; do not extend
# this list without a tracking entry in docs/dev/TEST_COVERAGE_PLAN.md.
ALIAS_LEAK_ALLOWLIST: set[str] = set()


def _events_files() -> list:
    return iter_py(EVENTS_ROOT)


def test_mouse_does_not_read_flat_viewstate_feature_flags():
    src = read(MOUSE_FILE)
    leaks: list[str] = []
    for field in FEATURE_VIEWSTATE_FIELDS:
        pattern = rf"view_state\.{field}\b"
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(pattern, line):
                leaks.append(f"{rel(MOUSE_FILE)}:{i} reads view_state.{field}")
    assert not leaks, (
        "events/image_label/mouse.py reads feature-coupled flat ViewState "
        "flags; feature state must be queried through a gesture binding's "
        "predicate, not via shared event code:\n  " + "\n  ".join(leaks)
    )


def test_mouse_does_not_branch_on_feature_interaction_flags():
    src = read(MOUSE_FILE)
    leaks: list[str] = []
    for flag in FEATURE_INTERACTION_FLAGS:
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(rf"interaction_state\.{flag}\b", line):
                leaks.append(f"{rel(MOUSE_FILE)}:{i} reads interaction_state.{flag}")
    assert not leaks, (
        "events/image_label/mouse.py branches on feature-specific drag flags; "
        "use ``GestureResolver.iter_active`` + binding.is_active instead:\n  "
        + "\n  ".join(leaks)
    )


def test_events_do_not_call_feature_aliases_directly():
    """No file under ``src/events/`` may use feature-named alias prefixes."""
    leaks: list[str] = []
    for path in _events_files():
        if rel(path) in ALIAS_LEAK_ALLOWLIST:
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError as exc:
            pytest.fail(f"could not parse {path}: {exc}")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name)
                else None
            )
            if name != "get_canvas_feature_command_by_alias":
                continue
            if not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            alias = first.value
            if any(alias.startswith(prefix) for prefix in FEATURE_ALIAS_PREFIXES):
                leaks.append(
                    f"{rel(path)}:{node.lineno} calls alias {alias!r} "
                    f"(move into the owning feature's package)"
                )
    assert not leaks, "\n  " + "\n  ".join(leaks)
