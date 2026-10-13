"""Every context-menu entry carries an icon (product rule).

Static AST scan: any ``ContextMenuAction(...)`` call under ``src/`` must pass an
``icon=`` keyword, so no right-click menu item in any tab can ship icon-less.
Test doubles under ``tests/`` are exempt (they build throwaway menus).

Dogma source: product rule "в каждом контекстном меню на каждом выборе должна
быть иконка".
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
EXCLUDE_PARTS = {
    "__pycache__",
    "tests",
    "venv",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _collect_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT)
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "ContextMenuAction":
                continue
            if not any(kw.arg == "icon" for kw in node.keywords):
                violations.append(f"{rel.as_posix()}:{node.lineno}")
    return violations


def test_every_context_menu_action_passes_icon() -> None:
    violations = _collect_violations()
    assert not violations, (
        "ContextMenuAction entries must pass icon= — every menu item shows an "
        "icon:\n  - " + "\n  - ".join(violations)
    )
