"""Ratchet: no visible-widget orphans (Wayland stillborn-toplevel busy cursor).

``X.setParent(None)`` on a still-visible widget instantly maps a top-level
window (fresh wl_surface + xdg_toplevel, activation token stamped with the
stale input serial); destroyed milliseconds later, the token can never be
consumed and Mutter holds the global busy cursor until the sequence timeout
— with zero cursor/activation calls in app code
(`inv-busy-cursor-wayland-2026-10-03`, Improve-ImgSLI `21c031f6`).

A call site complies when, in the same function before the detach,
  (a) the same receiver is hidden (``hide()`` / ``setVisible(False)``), or
  (b) the site is listed in ``ALLOWLIST`` (provably never visible, e.g.
      construction-time before first show, or a non-widget QObject).

Adding a new raw ``setParent(None)`` fails loudly: hide first, or justify
in ``ALLOWLIST``. Scans the app tree plus the toolkit checkout (sibling
``../sli-ui-toolkit`` or ``$SLI_TOOLKIT_DIR``) when resolvable.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from tests.contracts._framework import ROOT, parse

pytestmark = pytest.mark.slow

APP_SRC = ROOT / "src"


def _toolkit_base() -> Path | None:
    override = os.environ.get("SLI_TOOLKIT_DIR", "").strip()
    candidates = [Path(override)] if override else []
    candidates.append(ROOT.parent / "sli-ui-toolkit" / "src")
    for base in candidates:
        if base.is_dir():
            return base
    return None


# path (repo-relative, forward slashes) -> {enclosing function: reason}.
# Only for sites provably unable to orphan a *visible* widget.
ALLOWLIST: dict[str, dict[str, str]] = {
    # App: construction-time assembly, dialog hidden until exec/show.
    "src/plugins/help/dialog.py": {
        "_install_sidebar_splitter": "construction-time only via _build_ui in __init__, dialog never shown",
        "_build_ui": "construction-time only in __init__, dialog never shown",
    },
    # App: QShortcut is not a widget — no wl_surface can map.
    "src/ui/actions/binder.py": {
        "clear": "QShortcut target, non-widget QObject",
        "drop_prefix": "QShortcut target, non-widget QObject",
    },
    # App: pooled cards are hidden at recycle before re-homing.
    "src/tabs/image_gallery/ui/grid_view/pool.py": {
        "_acquire_card": "pooled cards hidden at recycle (_recycle_card)",
    },
    # Toolkit: resize filter is a QObject, not a QWidget.
    "src/sli_ui_toolkit/ui/windows/frameless/lifecycle.py": {
        "_set_resize_filter": "QObject target, never maps a surface",
    },
    # Toolkit: intentional toplevel restore — window is shown right after.
    "src/sli_ui_toolkit/ui/inspector/modality.py": {
        "restore_modality": "deliberate toplevel restore with immediate show()",
    },
}


def _is_test_path(path: Path) -> bool:
    parts = path.parts
    return "tests" in parts or path.name.startswith("test_")


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _receiver_text(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        try:
            return ast.unparse(func.value).strip()
        except Exception:
            return ""
    return ""


def _iter_setparent_none(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "setParent"):
            continue
        if node.args and _is_none(node.args[0]):
            yield node


def _enclosing_func(tree: ast.AST, lineno: int) -> str | None:
    best: str | None = None
    best_start = -1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", 10**9) or 10**9
            if start <= lineno <= end and start > best_start:
                best, best_start = node.name, start
    return best


def _hide_before(tree: ast.AST, func_name: str, receiver: str, lineno: int) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != func_name:
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", 10**9) or 10**9
        if not (start <= lineno <= end):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            f = sub.func
            if not (isinstance(f, ast.Attribute) and f.attr in ("hide", "setVisible")):
                continue
            if getattr(sub, "lineno", 0) >= lineno:
                continue
            if f.attr == "setVisible":
                if not (sub.args and isinstance(sub.args[0], ast.Constant) and sub.args[0].value is False):
                    continue
            if _receiver_text(sub) == receiver:
                return True
    return False


def _scan_base(base: Path, prefix: str) -> list[str]:
    violations: list[str] = []
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if _is_test_path(path):
            continue
        rel = f"{prefix}/" + path.relative_to(base).as_posix()
        try:
            tree = parse(path)
        except Exception:
            continue
        for node in _iter_setparent_none(tree):
            lineno = getattr(node, "lineno", 0)
            func = _enclosing_func(tree, lineno)
            receiver = _receiver_text(node)
            if func is not None and _hide_before(tree, func, receiver, lineno):
                continue
            allowed = ALLOWLIST.get(rel, {})
            if func is not None and func in allowed:
                continue
            violations.append(f"{rel}:{lineno} ({func or '?'} :: {receiver or '?'})")
    return violations


def test_no_visible_orphan_setparent():
    violations = _scan_base(APP_SRC, "src")
    toolkit = _toolkit_base()
    if toolkit is not None:
        violations += _scan_base(toolkit, "src")
    assert not violations, (
        "setParent(None) without same-receiver hide() first "
        "(stillborn-toplevel busy cursor — hide before unparent, or justify "
        "in ALLOWLIST):\n" + "\n".join(violations)
    )
