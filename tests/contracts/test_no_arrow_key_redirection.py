"""Ratchet: arrow key handlers must not remap vertical movement to horizontal.

The specific anti-pattern: Down (vertical) doing what Right (horizontal)
does, or Up doing what Left does.  This breaks spatial consistency —
users expect Down to go down, not right.

Left+Up together is fine (both navigate "backward" in a linear list).
Right+Down together is fine in grids.  Only Down→Right and Up→Left
redirections in *non-grid* contexts are forbidden.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC


def _keys_in_if_test(node: ast.If) -> set[str]:
    """Extract Key_* names from an if-test expression."""
    keys: set[str] = set()
    test = node.test

    # key in (Key_A, Key_B)  |  key in {Key_A, Key_B}
    if isinstance(test, ast.Compare):
        for c in [test.left, *test.comparators]:
            if isinstance(c, (ast.Tuple, ast.List, ast.Set)):
                for elt in c.elts:
                    if isinstance(elt, ast.Attribute) and elt.attr.startswith("Key_"):
                        keys.add(elt.attr)
            if isinstance(c, ast.Attribute) and c.attr.startswith("Key_"):
                keys.add(c.attr)

    # key in (Key_A, Key_B) via BoolOp
    if isinstance(test, ast.BoolOp):
        for v in test.values:
            if isinstance(v, ast.Compare):
                for c in [v.left, *v.comparators]:
                    if isinstance(c, (ast.Tuple, ast.List, ast.Set)):
                        for elt in c.elts:
                            if isinstance(elt, ast.Attribute) and elt.attr.startswith("Key_"):
                                keys.add(elt.attr)

    return keys


def test_no_down_remap_to_right():
    """Down must not be grouped with Right in linear key handlers."""
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "Key_Down" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        # Grid layouts legitimately map all four arrows
        if "_grid_columns" in text:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            keys = _keys_in_if_test(node)
            if "Key_Down" in keys and "Key_Right" in keys:
                offenders.append(
                    f"{path.relative_to(SRC)}:{node.lineno} "
                    f"Down grouped with Right"
                )
    assert not offenders, (
        "Down is remapped to Right — vertical movement must be separate:\n"
        + "\n".join(sorted(set(offenders)))
    )


def test_no_up_remap_to_left():
    """Up must not be grouped with Left in linear key handlers."""
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "Key_Up" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        if "_grid_columns" in text:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            keys = _keys_in_if_test(node)
            if "Key_Up" in keys and "Key_Left" in keys:
                offenders.append(
                    f"{path.relative_to(SRC)}:{node.lineno} "
                    f"Up grouped with Left"
                )
    assert not offenders, (
        "Up is remapped to Left — vertical movement must be separate:\n"
        + "\n".join(sorted(set(offenders)))
    )
