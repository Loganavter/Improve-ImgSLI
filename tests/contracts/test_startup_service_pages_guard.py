"""Contract: service factories must return None when tab._widget is None.

During startup, ``create_startup_service`` probes all registered tabs by
capability.  With lazy tab initialization, a tab's page (and therefore its
UI widgets) may not exist yet (``tab._widget is None``).  Service factories
for such tabs MUST return ``None`` rather than creating a presenter with
``widget=None`` — the presenter would crash on first use.

Dogma: every ``create_service`` branch that uses ``tab._widget`` in any way
(attribute access OR keyword argument) MUST be preceded by
``if tab._widget is None: return None``.

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


def _find_tab_widget_usages(func: ast.FunctionDef) -> list[ast.AST]:
    """Find ALL AST nodes that reference tab._widget — both attribute access
    (``tab._widget.foo``) and keyword arguments (``widget=tab._widget``)."""
    usages: list[ast.AST] = []
    for node in ast.walk(func):
        # Pattern 1: tab._widget.attr (attribute access)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Attribute):
                if node.value.attr == "_widget" and isinstance(node.value.value, ast.Name):
                    if node.value.value.id == "tab":
                        usages.append(node)
        # Pattern 2: widget=tab._widget (keyword argument in a call)
        if isinstance(node, ast.keyword):
            if node.arg == "widget" and isinstance(node.value, ast.Attribute):
                if node.value.attr == "_widget" and isinstance(node.value.value, ast.Name):
                    if node.value.value.id == "tab":
                        usages.append(node)
    return usages


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
            _check_function_for_unguarded_widget(node, rel_path, offenders)
    assert not offenders, (
        "Service factories use tab._widget without a None guard:\n  "
        + "\n  ".join(offenders)
    )


def test_create_startup_service_uses_pages_only_guard():
    """create_startup_service must resolve against bootstrap-default tab only.

    Per docs/dev/tabs/capability-mechanisms.md, create_startup_service
    resolves strictly against the tab that declares is_bootstrap_default=True.
    It must NOT iterate all registered tabs.
    """
    registry_path = SRC / "tabs" / "registry.py"
    text = registry_path.read_text(encoding="utf-8")
    # Verify it calls _bootstrap_default_tab() (not _first_tab_answering_result)
    assert "_bootstrap_default_tab()" in text, (
        "create_startup_service must use _bootstrap_default_tab() "
        "to resolve against the bootstrap-default tab only"
    )
    # Verify it does NOT iterate self._tabs directly
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "create_startup_service":
            continue
        func_text = ast.get_source_segment(text, node)
        assert "_first_tab_answering_result" not in func_text, (
            "create_startup_service must NOT use _first_tab_answering_result "
            "(which iterates all tabs) — use _bootstrap_default_tab() instead"
        )
        assert "self._tabs" not in func_text, (
            "create_startup_service must NOT iterate self._tabs directly"
        )
        return
    assert False, "create_startup_service method not found"


def _check_function_for_unguarded_widget(
    func: ast.FunctionDef, rel_path: str, offenders: list[str]
) -> None:
    """Check that every use of tab._widget in *func* is guarded by a None check.

    Two patterns are recognized as guards:
    1. ``if tab._widget is None: return None`` — lines INSIDE the if-body
       are guarded (they only run when widget IS None, e.g. for early return).
    2. Lines AFTER an ``if tab._widget is None: return None`` block are
       guarded because the early return prevents execution when widget IS None.
    """
    guard_lines: set[int] = set()

    # First pass: find early-return guards and mark lines after them.
    if_nodes = [
        node for node in ast.walk(func)
        if isinstance(node, ast.If) and _is_widget_none_guard(node)
    ]
    for node in if_nodes:
        # Check if the if-body contains a return (early return pattern).
        has_return = any(
            isinstance(stmt, ast.Return)
            for stmt in node.body
        )
        if has_return:
            # Lines at the same level AFTER this if-block are guarded.
            for parent in ast.walk(func):
                body = getattr(parent, "body", None)
                if not isinstance(body, list):
                    continue
                try:
                    idx = body.index(node)
                except ValueError:
                    continue
                for sibling in body[idx + 1:]:
                    for child in ast.walk(sibling):
                        if hasattr(child, "lineno"):
                            guard_lines.add(child.lineno)

    # Also mark lines INSIDE the if-body as guarded (for completeness).
    for node in if_nodes:
        for stmt in node.body:
            for child in ast.walk(stmt):
                if hasattr(child, "lineno"):
                    guard_lines.add(child.lineno)

    # Find ALL usages of tab._widget (attribute access + keyword args)
    for usage in _find_tab_widget_usages(func):
        if usage.lineno not in guard_lines:
            # Build a human-readable description
            if isinstance(usage, ast.Attribute):
                desc = f"tab._widget.{usage.attr}"
            elif isinstance(usage, ast.keyword):
                desc = f"widget=tab._widget"
            else:
                desc = "tab._widget"
            offenders.append(
                f"{rel_path}:{func.name} line {usage.lineno}: "
                f"{desc} without None guard"
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
