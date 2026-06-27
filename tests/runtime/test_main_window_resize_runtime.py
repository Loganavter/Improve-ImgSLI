"""Main-window interactive resize pins QRhi buffers until the resize burst settles."""

import ast
from pathlib import Path

RUNTIME = (
    Path(__file__).resolve().parents[2] / "src" / "ui" / "main_window" / "runtime.py"
)


def _method(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _calls(method: ast.FunctionDef, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def test_resize_freezes_qrhi_surface_once_per_resize_burst():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    handle_resize = _method(tree, "handle_resize")
    calls = _calls(handle_resize, "_freeze_rhi_surfaces")

    assert len(calls) == 1


def test_resize_installs_and_syncs_qrhi_resize_shield():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    handle_resize = _method(tree, "handle_resize")

    assert len(_calls(handle_resize, "_ensure_rhi_resize_shields")) == 1
    assert len(_calls(handle_resize, "_sync_rhi_resize_shields")) == 1


def test_debounced_resize_unfreezes_qrhi_surface_before_render_update():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    handle_debounced_resize = _method(tree, "handle_debounced_resize")
    calls = _calls(handle_debounced_resize, "_unfreeze_rhi_surfaces")

    assert len(calls) == 1


def test_debounced_resize_clears_qrhi_resize_shield():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    handle_debounced_resize = _method(tree, "handle_debounced_resize")

    assert len(_calls(handle_debounced_resize, "_clear_rhi_resize_shields")) == 1
