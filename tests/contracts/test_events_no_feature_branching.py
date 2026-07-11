"""Shared event code must not branch on feature-specific state.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md Anti-patterns
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

FEATURE_VIEWSTATE_FIELDS = (
    "overlay_enabled",
)

FEATURE_INTERACTION_FLAGS = (
    "is_dragging_overlay_handle",
    "is_dragging_overlay_split",
    "is_dragging_split_line",
)

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

ALIAS_LEAK_ALLOWLIST: set[str] = set()

def _events_files() -> list:
    return iter_py(EVENTS_ROOT)

# multi_compare has no shared `src/events/` mouse module of its own — its
# canvas widget (`src/tabs/multi_compare/ui/canvas_widget.py`) both routes
# gestures *and* legitimately owns widget-level chrome (RMB context menu,
# middle-button pan, wheel-zoom, both double-click behaviors — see the D1
# gesture-mapping note in docs/dev/MULTI_COMPARE_QRHI_REFACTOR.md for why
# those stay inline). So the tests above, which are scoped to
# `EVENTS_ROOT`/`MOUSE_FILE`, do not and should not cover it wholesale — a
# blanket "no branching" rule would contradict D1's own scope decision. This
# narrower check only guards the two gestures that *were* extracted
# (divider-drag, slot-drag): their transient state (`_divider_drag`,
# `_lmb_press_pos`, `_lmb_press_slot_id`) must only be touched through
# `resolve_press`/`iter_active` inside the mouse event methods, not read
# directly for routing, mirroring `test_mouse_does_not_branch_on_feature_interaction_flags`.
MULTI_COMPARE_CANVAS_WIDGET = (
    SRC / "tabs" / "multi_compare" / "ui" / "canvas_widget.py"
)
MULTI_COMPARE_GESTURE_STATE_FIELDS = (
    "_divider_drag",
    "_lmb_press_pos",
    "_lmb_press_slot_id",
)
MULTI_COMPARE_ROUTING_METHODS = (
    "mousePressEvent",
    "mouseMoveEvent",
    "mouseReleaseEvent",
)

def _method_source(tree: ast.AST, src_lines: list[str], class_name: str, method_name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return "\n".join(src_lines[item.lineno - 1 : item.end_lineno])
    return ""

def test_multi_compare_canvas_widget_does_not_branch_on_gesture_state_directly():
    src = read(MULTI_COMPARE_CANVAS_WIDGET)
    tree = ast.parse(src)
    src_lines = src.splitlines()
    leaks: list[str] = []
    for method_name in MULTI_COMPARE_ROUTING_METHODS:
        method_src = _method_source(
            tree, src_lines, "MultiCompareCanvasWidget", method_name
        )
        for field in MULTI_COMPARE_GESTURE_STATE_FIELDS:
            if re.search(rf"self\.{field}\b", method_src):
                leaks.append(f"{method_name} reads self.{field}")
    assert not leaks, (
        "multi_compare's canvas_widget.py mouse-routing methods must resolve "
        "the divider-drag / slot-drag gestures via "
        "`tabs.multi_compare.canvas.gesture_resolver` "
        "(`resolve_press`/`iter_active`), not by reading their transient "
        "state fields directly — that state must only be touched inside "
        "each feature's own `interaction.py`/`gestures.py`:\n  "
        + "\n  ".join(leaks)
    )

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
