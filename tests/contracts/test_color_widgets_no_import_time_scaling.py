"""Ratchet: color-picker chrome is scaled at USE time, never at import time.

``scaled_px(...)`` multiplies by the live ``UiScale`` factor, so a call
evaluated at **module scope or in a class body** runs exactly once — at
import. It therefore bakes the factor of the launch session into the value
and can never follow a later interface-scale change. That is how the picker
was broken (L5, owner report 2026-10-19): ``picker_dialog`` held
``_MIN_WIDTH = scaled_px(260)`` / ``_MIN_HEIGHT`` / ``_MAX_WIDTH`` module
constants and the ``_SVSquare.THUMB_RADIUS`` / ``_RecentColorChip.SIZE`` /
``CORNER_RADIUS`` / ``SWATCH_RADIUS`` / ``SWATCH_PADDING`` class attributes,
so the dialog chrome and its declared minimum stayed frozen at the build
factor.

Dogma: inside ``src/ui/widgets/color/`` no ``scaled_px(...)`` call may sit
outside a function body — keep the *design* number (a plain ``…_DP``
constant) and call ``scaled_px`` where it is used, then re-apply on the
``connect_ui_metrics`` appearance bus.

Model: the toolkit's own ``tests/test_px_scaling_contract.py``.
"""

from __future__ import annotations

import ast

from tests.contracts._framework import SRC

_TARGET = SRC / "ui" / "widgets" / "color"

_FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _is_scaled_px_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "id", "") == "scaled_px"


def _import_time_scaled_px(node: ast.AST) -> list[ast.Call]:
    """``scaled_px`` calls reachable without entering a function body.

    Module statements and class bodies both execute at import time; a
    ``FunctionDef``/``Lambda`` subtree is a use-time scope and is skipped —
    except its decorators, which also run at import time.
    """
    found: list[ast.Call] = []
    if isinstance(node, _FUNCTION_SCOPES):
        for decorator in getattr(node, "decorator_list", ()):
            found.extend(_import_time_scaled_px(decorator))
        return found
    if _is_scaled_px_call(node):
        found.append(node)
    for child in ast.iter_child_nodes(node):
        found.extend(_import_time_scaled_px(child))
    return found


def test_color_widgets_never_scale_px_at_import_time():
    offenders: list[str] = []
    for path in sorted(_TARGET.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in _import_time_scaled_px(tree):
            offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")

    assert not offenders, (
        "scaled_px() evaluated at import time bakes the launch scale factor "
        "into the value, so a later UI-scale change cannot re-derive it. Keep "
        "a design constant (…_DP) and call scaled_px() where it is used "
        "(then re-apply on the metrics bus):\n" + "\n".join(offenders)
    )
