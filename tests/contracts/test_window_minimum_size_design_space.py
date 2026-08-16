"""Tab pages must declare their main-window floor in design space.

``window_minimum_size()`` feeds the main window's ``setMinimumSize`` through
``minimum_floor_for_main_window`` (ui/layout_geometry.py). A *scaled* floor
(560 -> 840 px at 1.5x) can exceed the user's saved window height and force
the window taller — the Session Picker shelf visibly "resized the window"
when it barely fit the short window (see the session_picker investigations
doc on UI-scale first-frame bugs). The floor is a resizability floor, not a
content-fit guarantee: pages scroll their content, so the floor stays a
design constant.

Dogma: no ``scaled_px`` / ``UiScale`` usage inside any
``window_minimum_size`` implementation.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC

_FORBIDDEN_CALLS = {"scaled_px"}


def _iter_window_minimum_size_defs():
    for path in SRC.rglob("*.py"):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node.name == "window_minimum_size"
            ):
                yield path, node


def test_window_minimum_size_stays_design_space():
    offenders: list[str] = []
    for path, node in _iter_window_minimum_size_defs():
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                name = getattr(sub.func, "id", None)
                if name in _FORBIDDEN_CALLS:
                    offenders.append(f"{path}:{sub.lineno}: {name}(...)")
                if isinstance(sub.func, ast.Attribute) and sub.func.attr in (
                    "get_instance",
                    "factor",
                ):
                    offenders.append(f"{path}:{sub.lineno}: UiScale.{sub.func.attr}")
    assert not offenders, (
        "window_minimum_size() must stay design-space (unscaled): a scaled "
        "floor can exceed the saved window geometry and force the window "
        f"taller.\n{chr(10).join(offenders)}"
    )
