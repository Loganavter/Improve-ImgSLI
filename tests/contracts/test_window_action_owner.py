"""Contract: the main window's action owner is ``action_registry``, never ``actions``.

``MainWindow`` instantiates ``MainWindowActions`` as ``self.action_registry``
(``src/ui/main_window/window.py:88``). Because the window *is* a ``QWidget``,
any ``window.actions`` read silently binds ``QWidget.actions()`` — a builtin
method — instead of failing loudly on a missing attribute, and call sites that
wrap the use in ``except Exception`` (both export notify paths did) lose the
feature with only a log line (bug row "IC/video export success notification
silently never fires", live 2026-10-21; probe
``tests/target_bug/test_export_notify_actions.py``).

This scan keeps a third call site from being written: no attribute read named
``actions`` on a window-like receiver, and the owner stays ``action_registry``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_WINDOW_FILE = _SRC / "ui" / "main_window" / "window.py"

# Receivers that denote the host window (not ``ui.actions.*`` module paths and
# not unrelated ``self.actions`` lists).
_WINDOW_RECEIVERS = {"main_window_app", "main_window", "window", "window_shell"}


def _dotted(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        return None
    else:
        return None
    return ".".join(reversed(parts))


def _window_actions_reads(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr != "actions":
            continue
        receiver = _dotted(node.value)
        if receiver is None:
            continue
        if receiver.split(".")[-1] in _WINDOW_RECEIVERS:
            hits.append(f"{path.relative_to(_REPO)}:{node.lineno} → {receiver}.actions")
    return hits


def test_no_window_actions_attribute_reads():
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        # Tests may read the builtin on purpose (the target probe derives its
        # signal from it); the production call sites are what this guards.
        if "tests" in path.relative_to(_SRC).parts:
            continue
        offenders.extend(_window_actions_reads(path))
    assert offenders == [], (
        "window.actions is QWidget.actions() (a builtin method) — the host window "
        "stores its action owner as action_registry:\n" + "\n".join(offenders)
    )


def test_main_window_publishes_the_action_owner_as_action_registry():
    tree = ast.parse(_WINDOW_FILE.read_text(encoding="utf-8"), filename=str(_WINDOW_FILE))
    assigned = {
        target.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    }
    assert "action_registry" in assigned, "MainWindow must publish self.action_registry"
    assert "actions" not in assigned, (
        "MainWindow must not shadow QWidget.actions() — that hides the real "
        "method and makes typos indistinguishable from working code"
    )
