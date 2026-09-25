"""No unlisted app-wide event filters or focus grabs (Wave E tripwire).

Default-deny over ``src/**/*.py``: any ``.installEventFilter(`` call whose
receiver is the QApplication (``app``/``qApp``/``QApplication``) and any
``PopupFocusReason``/``ActiveWindowFocusReason`` use must be listed in
``tests/topology_allowlist.json`` (``app_filters`` / ``focus_reasons``).
Add the family/file + justification there — never silence this test.

Dogma source: Wave E topology conformity (default-deny harness).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWLIST = ROOT / "tests" / "topology_allowlist.json"
SRC = ROOT / "src"

APP_RECEIVERS = ("app", "qApp", "qapp", "application")


def _load_allowlist() -> dict:
    return json.loads(ALLOWLIST.read_text(encoding="utf-8"))


def _iter_py(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _receiver_text(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        try:
            return ast.unparse(func.value).strip()
        except Exception:
            return ""
    return ""


def _is_app_receiver(receiver: str) -> bool:
    if receiver in APP_RECEIVERS:
        return True
    if "QApplication" in receiver:
        return True
    return False


def find_unlisted_app_filters(allowlist: dict) -> list[str]:
    """Files installing an app-targeted event filter outside the allowlist."""
    allowed = set((allowlist.get("app_filters") or {}).keys())
    violations: list[str] = []
    for path in _iter_py(SRC):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "installEventFilter"
                and _is_app_receiver(_receiver_text(node))
            ):
                rel = path.relative_to(ROOT).as_posix()
                if rel not in allowed:
                    violations.append(f"{rel}:{node.lineno}")
                break
    return sorted(violations)


def find_unlisted_focus_reasons(allowlist: dict) -> list[str]:
    """Files grabbing Popup|ActiveWindow focus outside the allowlist."""
    allowed = set((allowlist.get("focus_reasons") or {}).keys())
    violations: list[str] = []
    for path in _iter_py(SRC):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "PopupFocusReason" not in text and "ActiveWindowFocusReason" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        hit = any(
            isinstance(node, ast.Attribute)
            and node.attr in ("PopupFocusReason", "ActiveWindowFocusReason")
            for node in ast.walk(tree)
        )
        if hit:
            rel = path.relative_to(ROOT).as_posix()
            if rel not in allowed:
                violations.append(rel)
    return sorted(violations)


def test_no_unlisted_app_event_filter():
    allowlist = _load_allowlist()
    violations = find_unlisted_app_filters(allowlist)
    assert not violations, (
        "app-targeted installEventFilter outside tests/topology_allowlist.json "
        f"[app_filters]: {violations}"
    )


def test_no_unlisted_popup_or_active_window_focus():
    allowlist = _load_allowlist()
    violations = find_unlisted_focus_reasons(allowlist)
    assert not violations, (
        "PopupFocusReason/ActiveWindowFocusReason outside "
        f"tests/topology_allowlist.json [focus_reasons]: {violations}"
    )
