"""Contract: service factories must return None when tab._widget is None.

During startup, ``create_startup_service`` probes all registered tabs by
capability.  With lazy tab initialization, a tab's page (and therefore its
UI widgets) may not exist yet (``tab._widget is None``).  Service factories
for such tabs MUST return ``None`` rather than creating a presenter with
``widget=None`` — the presenter would crash on first use.

Dogma: every ``create_service`` branch that passes ``tab._widget`` to a
presenter/controller constructor MUST guard with ``if tab._widget is None:
return None`` first.

Source: docs/dev/investigations/lazy-tab-initialization-plan.md
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC, iter_py, rel


def _service_factory_files() -> list[Path]:
    """Find all service factory modules (files containing create_service)."""
    factories: list[Path] = []
    for path in iter_py(SRC / "tabs"):
        text = path.read_text(encoding="utf-8")
        if "def create_service" in text and "tab._widget" in text:
            factories.append(path)
    return factories


def test_service_factories_guard_tab_widget():
    """Every service factory branch that uses tab._widget must guard against None."""
    offenders: list[str] = []
    for path in _service_factory_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel_path = rel(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "create_service":
                continue
            # Walk the function body for branches that use tab._widget
            # without a preceding None guard.
            _check_function_for_unguarded_widget(node, rel_path, offenders)
    assert not offenders, (
        "Service factories use tab._widget without a None guard:\n  "
        + "\n  ".join(offenders)
    )


def _check_function_for_unguarded_widget(
    func: ast.FunctionDef, rel_path: str, offenders: list[str]
) -> None:
    """Check that every use of tab._widget in *func* is guarded by a None check."""
    # Collect lines that are inside an `if tab._widget is None: return None` guard.
    guard_lines: set[int] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.If):
            if _is_widget_none_guard(node):
                # Only the if-body is guarded — walk body nodes only.
                for stmt in node.body:
                    for child in ast.walk(stmt):
                        if hasattr(child, "lineno"):
                            guard_lines.add(child.lineno)

    # Find all attribute accesses on tab._widget
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Attribute):
                if node.value.attr == "_widget" and node.value.value.id == "tab":
                    if node.lineno not in guard_lines:
                        offenders.append(
                            f"{rel_path}:{func.name} line {node.lineno}: "
                            f"tab._widget.{node.attr} without None guard"
                        )


def _is_widget_none_guard(node: ast.If) -> bool:
    """Check if an If node tests `tab._widget is None`."""
    test = node.test
    if isinstance(test, ast.Compare):
        if isinstance(test.left, ast.Attribute):
            if test.left.attr == "_widget" and isinstance(test.left.value, ast.Name):
                if test.left.value.id == "tab":
                    for op, comparator in zip(test.ops, test.comparators):
                        if isinstance(op, ast.Is) and isinstance(comparator, ast.Constant):
                            if comparator.value is None:
                                return True
    return False
