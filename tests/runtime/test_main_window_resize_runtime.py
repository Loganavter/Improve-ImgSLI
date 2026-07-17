"""Main-window resize: live chrome/letterbox; heavy schedule_update after settle."""

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


def test_resize_pulse_syncs_live_chrome():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    pulse = _method(tree, "_pulse_resize")
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "_sync_live_chrome"
        for node in ast.walk(pulse)
    )


def test_resize_pulse_does_not_schedule_update_mid_drag():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    pulse = _method(tree, "_pulse_resize")
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "schedule_update"
        for node in ast.walk(pulse)
    )


def test_settle_schedules_heavy_update():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    settle = _method(tree, "handle_debounced_resize")
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "schedule_update"
        for node in ast.walk(settle)
    )


def test_resize_uses_settle_gate():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    init = _method(tree, "__init__")
    assert any(
        isinstance(node, ast.Name) and node.id == "SettleGate"
        for node in ast.walk(init)
    )
    notify = _method(tree, "notify_resize")
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "ping"
        for node in ast.walk(notify)
    )


def test_resize_shield_defaults_off():
    import importlib
    import os

    import ui.main_window.runtime as runtime_mod

    os.environ.pop("IMGSLI_RESIZE_SHIELD", None)
    importlib.reload(runtime_mod)
    assert runtime_mod._resize_shield_enabled() is False

    os.environ["IMGSLI_RESIZE_SHIELD"] = "1"
    importlib.reload(runtime_mod)
    assert runtime_mod._resize_shield_enabled() is True

    os.environ.pop("IMGSLI_RESIZE_SHIELD", None)
    importlib.reload(runtime_mod)


def test_shield_helpers_still_wired_for_opt_in():
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    pulse = _method(tree, "_pulse_resize")
    settle = _method(tree, "handle_debounced_resize")
    assert len(_calls(pulse, "_freeze_rhi_surfaces")) == 1
    assert len(_calls(settle, "_unfreeze_rhi_surfaces")) == 1
    assert len(_calls(settle, "_clear_rhi_resize_shields")) == 1
