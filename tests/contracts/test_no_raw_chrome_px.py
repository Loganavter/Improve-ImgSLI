"""Ratchet: new raw chrome px must go through ``scaled_px`` / ``UiFont``.

Dogma source: the archived UI-scale plan §3 (private improve-imgsli-internal-docs repo) — chrome geometry is
design px multiplied by ``UiScale`` at exactly one boundary. A raw numeric
literal in a fixed-size call (or a raw ``setPixelSize``/``setPointSize``)
bypasses the factor, so files doing that must at least be scale-aware
(import ``scaled_px``) or be allowlisted canvas/image-space geometry.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.contracts._framework import SRC

# Canvas/image-space or infra files where raw fixed-size literals are
# intentional: the canvas widget minimum sizes are image-space (plan
# non-goals), the onboarding indicator is a window-relative fixed chip,
# and 0-sentinels everywhere are resets, not geometry.
_ALLOWLISTED_FILES = {
    Path("services/system/paste_direction_overlay.py"),  # button hit rects
    Path("tabs/image_compare/ui/primitives.py"),  # canvas image_label min
    Path("tabs/multi_compare/widget.py"),  # canvas widget min
    Path("shared_toolkit/ui/managers/font_manager.py"),  # app font bootstrap
}

_FIXED_SIZE_CALLS = (
    "setFixedSize",
    "setFixedHeight",
    "setFixedWidth",
    "setMinimumSize",
    "setMinimumHeight",
    "setMinimumWidth",
)
_FONT_SIZE_CALLS = ("setPixelSize", "setPointSize")

_NUMERIC_ARG = re.compile(r"^\s*[0-9]")


def _is_numeric_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _is_numeric_literal(node.operand)
    return False


def test_raw_chrome_px_goes_through_scaled_px():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC)
        if rel in _ALLOWLISTED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if "scaled_px" in text or "ui_font" in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name in _FIXED_SIZE_CALLS:
                for arg in node.args:
                    if _is_numeric_literal(arg):
                        offenders.append(f"{rel}:{node.lineno} {name}({ast.unparse(arg)})")
                        break
    assert not offenders, (
        "raw fixed-size literals bypass UiScale — wrap with scaled_px() "
        "(interface-scale plan §3):\n" + "\n".join(sorted(set(offenders)))
    )


def test_no_raw_font_size_literals_outside_font_infra():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC)
        if rel in _ALLOWLISTED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        # Scale-aware files (e.g. toolkit Label.setPixelSize, which routes
        # through ui_font internally) are already covered; flag only files
        # with raw font-size literals that have no scaling path at all.
        if "scaled_px" in text or "ui_font" in text or "apply_ui_font" in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name in _FONT_SIZE_CALLS and node.args and _is_numeric_literal(node.args[0]):
                offenders.append(f"{rel}:{node.lineno} {name}({ast.unparse(node.args[0])})")
    assert not offenders, (
        "raw setPixelSize/setPointSize bypass UiFont scaling — use "
        "ui_font()/paint_font() with design px:\n" + "\n".join(sorted(offenders))
    )