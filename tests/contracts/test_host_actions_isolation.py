"""Host shell must not import tab action modules (capability dogma)."""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_HOST_ROOTS = (
    _REPO / "src" / "ui" / "presenters",
    _REPO / "src" / "ui" / "main_window",
)


def _iter_py_files(root: Path):
    yield from root.rglob("*.py")


def _imports_tab_actions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.endswith(".actions") and node.module.startswith("tabs."):
                hits.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith("tabs.") and name.endswith(".actions"):
                    hits.append(name)
    return hits


def test_host_shell_does_not_import_tab_actions_modules():
    offenders: list[str] = []
    for root in _HOST_ROOTS:
        for path in _iter_py_files(root):
            for module in _imports_tab_actions(path):
                offenders.append(f"{path.relative_to(_REPO)} → {module}")
    assert offenders == []
