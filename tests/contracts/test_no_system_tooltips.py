"""System tooltips are not allowed in the codebase.

Tooltips are rendered by sli_ui_toolkit's custom ``PathTooltip`` bubble,
installed application-wide via ``install_application_tooltips`` (see
``src/__main__.py`` and ``src/core/bootstrap.py``).

The toolkit's ``_ApplicationTooltipInterceptor`` intercepts
``QEvent.Type.ToolTip`` and renders an in-window bubble, so calls like
``widget.setToolTip(...)`` remain valid — the *system* tooltip never fires.

What is forbidden:

* Using ``QToolTip`` (the static class) — ``QToolTip.showText`` and friends
  bypass the application event filter and produce a native OS tooltip.
* Constructing a window with ``Qt.WindowType.ToolTip`` for the purpose of
  displaying tooltip-like hover text. The flag itself is allowlisted only
  for the in-window value-popup bubbles in ``shared_toolkit/ui/overlay_layer.py``,
  which are popups, not tooltips.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC, iter_py

WINDOW_TOOLTIP_ALLOWLIST: set[Path] = {
    Path("shared_toolkit/ui/overlay_layer.py"),
}


def _qttooltip_offenses(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "QToolTip":
                    lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "QToolTip":
            lines.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id == "QToolTip":
            lines.append(node.lineno)
    return lines


def _window_tooltip_flag_offenses(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "ToolTip"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "WindowType"
        ):
            lines.append(node.lineno)
    return lines


def test_no_qtooltip_usage_anywhere():
    offenders: list[str] = []
    for path in iter_py(SRC):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = path.relative_to(SRC)
        for lineno in _qttooltip_offenses(tree):
            offenders.append(f"{rel}:{lineno}")

    assert offenders == [], (
        "Direct QToolTip usage is forbidden — system tooltips bypass the "
        "toolkit's PathTooltip bubble. Use widget.setToolTip(...) instead "
        "(the application event filter renders the custom bubble). Offenders:\n  "
        + "\n  ".join(offenders)
    )


def test_no_window_tooltip_flag_outside_allowlist():
    offenders: list[str] = []
    for path in iter_py(SRC):
        rel = path.relative_to(SRC)
        if rel in WINDOW_TOOLTIP_ALLOWLIST:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for lineno in _window_tooltip_flag_offenses(tree):
            offenders.append(f"{rel}:{lineno}")

    assert offenders == [], (
        "Qt.WindowType.ToolTip creates a native tooltip-class window and "
        "is allowlisted only for shared_toolkit/ui/overlay_layer.py "
        "(value popups, not tooltips). Use the toolkit tooltip system "
        "(setToolTip + install_application_tooltips) for hover hints. "
        "Offenders:\n  " + "\n  ".join(offenders)
    )
