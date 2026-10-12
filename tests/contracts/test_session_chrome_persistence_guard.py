"""Ratchet: tab session chrome persists through ``SessionState`` only.

Per-session tab chrome (toolbar switches, divider/label styling) and its
last-used QSettings value must go through the ``tabs.use_cases.session_state``
facade. A tab that hand-rolls its own QSettings last-used read/write, or
re-introduces the retired multi_compare helper names, reopens the drift the
facade removed (two homes for the same value, silent seed mismatches).

Rules (AST scan of tab code, ``tests`` excluded):

(a) ``QSettings(...)`` constructed in ``src/tabs/*/tab.py`` or
    ``src/tabs/*/use_cases/persistence.py``. Chrome goes through
    ``SessionState``. Allowlisted: ``src/tabs/use_cases/session_state.py`` (the
    facade itself) and ``src/tabs/*/services/*_store.py`` (settings stores such
    as ``AiSettingsStore``, a different and legitimate concern).
(b) The retired hand-rolled names ``_save_last_settings``,
    ``_load_last_settings``, ``_settings_from_qsettings`` and
    ``_settings_from_sibling_session`` anywhere in non-test ``src/tabs`` code.

Sanctioned, NOT a violation: image_compare's store-driven session ``viewport``
(``store.viewport`` session data) is the other sanctioned session-state
mechanism. It is not QSettings chrome and this guard does not scan for it.
"""

from __future__ import annotations

import ast
import fnmatch

from ._framework import SRC, iter_py, rel

ALLOWLIST_PATTERNS = (
    "src/tabs/use_cases/session_state.py",
    "src/tabs/*/services/*_store.py",
)
PERSISTENCE_PATTERNS = (
    "src/tabs/*/tab.py",
    "src/tabs/*/use_cases/persistence.py",
)
RETIRED_NAMES = frozenset(
    {
        "_save_last_settings",
        "_load_last_settings",
        "_settings_from_qsettings",
        "_settings_from_sibling_session",
    }
)


def _allowlisted(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in ALLOWLIST_PATTERNS)


def _persistence_scope(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in PERSISTENCE_PATTERNS)


def _qsettings_calls(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "QSettings":
            lines.append(node.lineno)
    return lines


def _retired_name_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in RETIRED_NAMES:
            lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr in RETIRED_NAMES:
            lines.append(node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in RETIRED_NAMES:
            lines.append(node.lineno)
        elif isinstance(node, ast.alias) and (node.asname or node.name) in RETIRED_NAMES:
            lines.append(getattr(node, "lineno", 0))
    return lines


def find_violations(sources: dict[str, str]) -> list[str]:
    """Return one message per violation; ``sources`` maps repo-relative path to text."""
    out: list[str] = []
    for path in sorted(sources):
        if _allowlisted(path):
            continue
        tree = ast.parse(sources[path])
        if _persistence_scope(path):
            for line in _qsettings_calls(tree):
                out.append(
                    f"{path}:{line}: QSettings(...) in tab chrome code. Chrome last-used "
                    "persistence belongs to tabs.use_cases.session_state.SessionState "
                    "(bind it with fields + apply); a tab-local QSettings reopens the "
                    "two-homes drift."
                )
        for line in _retired_name_lines(tree):
            out.append(
                f"{path}:{line}: retired hand-rolled chrome helper name (one of "
                f"{sorted(RETIRED_NAMES)}). Use SessionState.set/remember/seed_slot/"
                "apply_from_slot/serialize/deserialize instead."
            )
    return out


def _real_tree_sources() -> dict[str, str]:
    return {rel(p): p.read_text(encoding="utf-8") for p in iter_py(SRC / "tabs")}


def test_tabs_do_not_hand_roll_session_chrome_persistence():
    violations = find_violations(_real_tree_sources())
    assert not violations, "\n".join(violations)


def test_guard_flags_synthetic_tab_qsettings():
    src = (
        "from PySide6.QtCore import QSettings\n"
        "def remember(v):\n"
        "    QSettings('a', 'b').setValue('k', v)\n"
    )
    violations = find_violations({"src/tabs/fake_tab/use_cases/persistence.py": src})
    assert len(violations) == 1
    assert "QSettings(...)" in violations[0]
    assert "SessionState" in violations[0]


def test_guard_flags_synthetic_tab_py_qsettings_attribute_form():
    src = "import PySide6.QtCore as qc\nS = qc.QSettings('a', 'b')\n"
    violations = find_violations({"src/tabs/fake_tab/tab.py": src})
    assert len(violations) == 1


def test_guard_flags_retired_helper_names():
    src = "def _save_last_settings(d, l):\n    pass\n"
    violations = find_violations({"src/tabs/fake_tab/controller.py": src})
    assert len(violations) == 1
    assert "_save_last_settings" in violations[0]


def test_guard_passes_allowlisted_facade_and_store():
    qs = "from PySide6.QtCore import QSettings\nS = QSettings('a', 'b')\n"
    assert find_violations(
        {
            "src/tabs/use_cases/session_state.py": qs,
            "src/tabs/image_gallery/services/ai_settings_store.py": qs,
        }
    ) == []


def test_guard_ignores_qsettings_outside_persistence_scope():
    src = "from PySide6.QtCore import QSettings\nS = QSettings('a', 'b')\n"
    assert find_violations({"src/tabs/fake_tab/widget.py": src}) == []
