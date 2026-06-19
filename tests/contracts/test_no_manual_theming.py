"""Manual UI theming in Python is constrained to theme infrastructure.

Dogma source: docs/dev/UI_INSPECTOR.md and toolkit docs/DESIGN_LANGUAGE.md.
New themed UI should use ThemeManager-registered QSS files with palette tokens
or toolkit style tokens, not ad-hoc setStyleSheet/get_color glue.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC


ALLOWED_THEME_INFRA_FILES = {
    Path("core/bootstrap.py"),
    Path("core/theme.py"),
    Path("devtools/ui_inspector/installer.py"),
    Path("devtools/ui_inspector/qss_index.py"),
    Path("devtools/ui_inspector/widget_snapshot.py"),
    Path("ui/theming.py"),
}

MANUAL_THEME_CALLS = {
    "setStyleSheet",
    "get_color",
    "try_get_color",
    "apply_theme",
    "apply_theme_to_dialog",
    "apply_theme_to_app",
}


def test_no_manual_theming_calls_outside_theme_infra():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC)
        if rel in ALLOWED_THEME_INFRA_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if name in MANUAL_THEME_CALLS:
                offenders.append(f"{rel}:{node.lineno} {name}()")

    assert offenders == []
