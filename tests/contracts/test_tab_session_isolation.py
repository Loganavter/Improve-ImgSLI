"""Gallery session-isolation dogma (Wave ISO).

Every ``gallery`` slot read in ``src/tabs/image_gallery/**`` prod code
passes an explicit ``session_id`` — never the active-session default — so a
live copy can only ever address its OWN session. The single sanctioned
active-session read is the is-active gate (session METADATA, not slot
data): ``get_active_workspace_session()`` may appear only inside the
allowlisted gate/lifecycle functions below.

Dogma source: Wave ISO frozen seam (§5) — own-session addressing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ._framework import ROOT, iter_py, parse, rel

GALLERY = ROOT / "src" / "tabs" / "image_gallery"


def _prod_files() -> list[Path]:
    return [p for p in iter_py(GALLERY) if "tests" not in p.parts]


def _call_nodes(tree: ast.Module, attr: str):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr
        ):
            yield node


def test_gallery_slot_reads_pass_explicit_session_id():
    """Zero session_id-less ``get_session_state_slot(...)`` in gallery prod code."""
    leaks: list[str] = []
    for py in _prod_files():
        tree = parse(py)
        if tree is None:
            continue
        for node in _call_nodes(tree, "get_session_state_slot"):
            keywords = {kw.arg for kw in node.keywords}
            if "session_id" not in keywords:
                leaks.append(f"{rel(py)}:{node.lineno} slot read without session_id=")
            for kw in node.keywords:
                if kw.arg == "session_id" and isinstance(kw.value, ast.Constant) and kw.value.value is None:
                    leaks.append(f"{rel(py)}:{node.lineno} slot read with session_id=None literal")
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


#: Functions allowed to read ACTIVE-session metadata (never slot data).
_ACTIVE_META_ALLOWLIST = frozenset(
    {
        "__init__",  # own-id capture at attach/create
        "_capture_initial_gallery_session_id",  # constructor fallback capture (metadata)
        "read_gallery_slot",  # explicit-active fallback for unbound legacy callers
        "_is_active_gallery_tab",  # THE is-active gate
        "bind_gallery_session",  # explicit (re)binding, never per-read resolve
        "resolve_owner_session_id",  # owner-chain id lookup for explicit addressing
        "restore_from",  # active check guards syncing a background session
        "deserialize_session",  # visible-session check before eager restore
        "_resolve_active_session_id",  # tab lifecycle session lookup
        "on_session_closed",  # live-active guard, not the closed id
    }
)


def test_gallery_active_session_reads_are_gate_only():
    """``get_active_workspace_session()`` in gallery prod lives only in the gate."""
    leaks: list[str] = []
    for py in _prod_files():
        tree = parse(py)
        if tree is None:
            continue
        # Map call line -> enclosing function name.
        func_at: dict[int, str] = {}

        class _Visitor(ast.NodeVisitor):
            def __init__(self):
                self._stack: list[str] = []

            def visit_FunctionDef(self, node):  # noqa: N802
                self._stack.append(node.name)
                self.generic_visit(node)
                self._stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node):  # noqa: N802
                func = getattr(node.func, "attr", None)
                if func == "get_active_workspace_session":
                    enclosing = self._stack[-1] if self._stack else "<module>"
                    if enclosing not in _ACTIVE_META_ALLOWLIST:
                        leaks.append(
                            f"{rel(py)}:{node.lineno} active-session read in "
                            f"{enclosing}() (allowlist: {sorted(_ACTIVE_META_ALLOWLIST)})"
                        )
                self.generic_visit(node)

        _Visitor().visit(tree)
        del func_at
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_gallery_copies_own_their_session_id():
    """Controller + widget capture their OWN session id and gate emits on it."""
    for name in ("controller.py", "widget.py"):
        text = (GALLERY / name).read_text(encoding="utf-8")
        assert "_gallery_session_id" in text, f"{name} never captures its own session id"
        assert "_is_active_gallery_tab" in text, f"{name} has no is-active gate"
    store_text = (GALLERY / "ui" / "gallery_store.py").read_text(encoding="utf-8")
    assert "resolve_owner_session_id" in store_text
