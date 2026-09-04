"""B1 S9 pin: pixels never ride Redux state or in-place slot writes.

AST dogma (no runtime): ``CompareSlot`` is a path-only ``SlotSource`` —
no ``image`` field, no ``slot.image = ...`` in-place mutation anywhere in
tab production code, no ``image=`` payload on slot actions. Tiers travel
worker → ``MultiComparePixelCache`` → ``note_slot_pixels`` dispatch
(STORE replace-only). Guards the recon S9 violation from reappearing.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TAB_ROOT = Path(__file__).parents[2]
_PROD_FILES = sorted(
    p
    for p in _TAB_ROOT.rglob("*.py")
    if "tests" not in p.parts and p.name != "__init__.py"
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_compare_slot_has_no_pixel_field():
    """``CompareSlot`` carries id/path/label/revision only."""
    tree = _parse(_TAB_ROOT / "models.py")
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CompareSlot":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.add(stmt.target.id)
    assert fields == {"id", "path", "label", "revision"}, fields


def test_no_in_place_slot_image_writes():
    """No ``*.image = ...`` / ``*.image`` augmented writes in production code."""
    hits: list[str] = []
    for path in _PROD_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            targets: list = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            else:
                continue
            for target in targets:
                chain: list[str] = []
                cur = target
                while isinstance(cur, ast.Attribute):
                    chain.append(cur.attr)
                    cur = cur.value
                if chain and chain[0] == "image":
                    hits.append(f"{path.relative_to(_TAB_ROOT)}:{node.lineno}")
    assert hits == [], "in-place pixel writes (S9 violation):\n" + "\n".join(hits)


def test_no_image_payload_on_slot_actions():
    """``add_slot``/``CompareSlot(...)`` take no ``image=`` kwarg."""
    hits: list[str] = []
    for path in _PROD_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name in {"add_slot", "CompareSlot"}:
                kwarg_names = [kw.arg for kw in node.keywords]
                if "image" in kwarg_names:
                    hits.append(f"{path.relative_to(_TAB_ROOT)}:{node.lineno}")
    assert hits == [], "pixel payloads in slot constructors:\n" + "\n".join(hits)
