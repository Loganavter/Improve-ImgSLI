"""Ratchet: no nested ``scaled_px`` calls (double scaling).

``scaled_px`` multiplies by the UI scale factor; calling it on an argument
that already contains a ``scaled_px`` result multiplies twice, and the
geometry drifts with ``factor^2``. The recent shelf's virtualization stride
was double-scaled this way (through a helper), blanking the scroll viewport
at factor > 1.0.

Dogma: the argument subtree of any ``scaled_px(...)`` call must not contain
another ``scaled_px(...)`` call. (Helper-mediated double scaling — passing an
already-scaled value into a helper that scales again — is not statically
visible here; it is covered by the runtime scale tests.)
"""

from __future__ import annotations

import ast

from tests.contracts._framework import SRC


def _is_scaled_px_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "id", "") == "scaled_px"


def test_no_nested_scaled_px():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not _is_scaled_px_call(node):
                continue
            for sub in ast.walk(node):
                if sub is node:
                    continue
                if _is_scaled_px_call(sub):
                    offenders.append(f"{path}:{node.lineno}")
                    break
    assert not offenders, (
        "Nested scaled_px(...) calls double-scale geometry (factor^2 drift). "
        "Scale once at the boundary and pass real px onward.\n"
        + "\n".join(offenders)
    )