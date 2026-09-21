"""Dialog activation parenting: transient parents + no deferred activation ticks.

Wayland xdg-activation tokens go stale across event-loop turns: any
``activateWindow()`` reached via ``singleShot``/retry/fade callback is denied
and the compositor parks the host as demanding-attention ("App is ready"
banner). Attached dialogs of the focused window activate freely, so every
modeless top-level must carry a transient parent at map time, and show/hide
paths must schedule no deferred activation ticks (synchronous widget
``setFocus`` consumes no token).
"""

from __future__ import annotations

import ast
import inspect
import warnings
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _make_active(widget: QWidget) -> None:
    # Offscreen ignores activateWindow(); the (deprecated but functional)
    # explicit setter is the only way to stage an active window here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        QApplication.setActiveWindow(widget)


def _read_source(relpath: str) -> ast.Module:
    return ast.parse((SRC_ROOT / relpath).read_text(encoding="utf-8"))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name}() not found")


def _activation_calls(func: ast.FunctionDef) -> list[str]:
    """Attribute-call names inside ``func`` that spend an xdg-activation token."""
    found: list[str] = []
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in ("activateWindow", "requestActivate", "request_window_activation")
        ):
            found.append(f"{node.func.attr}@{node.lineno}")
    return found


def test_help_dialog_carries_transient_parent(qapp):
    from plugins.help.plugin import HelpPlugin

    host = QWidget()
    host.show()
    plugin = HelpPlugin()
    plugin.show_dialog(parent=host, language="en")
    try:
        assert plugin._dialog is not None
        assert plugin._dialog.isVisible()
        assert plugin._dialog.parent() is host
    finally:
        plugin._dialog.close()


def test_video_editor_open_editor_parents_dialog(qapp, monkeypatch):
    from tabs.image_compare.plugins.video_editor import plugin as video_plugin

    seen: dict = {}

    class _FakeDialog:
        def __init__(self, *args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            self.destroyed = _FakeSignal()
            self.readyToShow = _FakeSignal()

        def show(self):
            pass

    monkeypatch.setattr(video_plugin, "VideoEditorDialog", _FakeDialog)
    host = QWidget()
    host.show()
    plugin = video_plugin.VideoEditorPlugin()
    plugin.open_editor([object()], object(), host)
    assert seen["kwargs"].get("parent") is host


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass


def test_palette_forwards_transient_parent(qapp, monkeypatch):
    from ui.actions.palette import dialog as palette_dialog  # noqa: F401 — import guard
    import ui.actions.palette as palette_pkg

    seen: dict = {}

    class _FakePalette:
        def __init__(self, parent=None, **kwargs):
            seen["parent"] = parent

        def exec(self):
            return 0

    monkeypatch.setattr(palette_pkg, "FindActionDialog", _FakePalette)
    monkeypatch.setattr(palette_pkg, "center_on_reference", lambda *a, **k: None)

    host = QWidget()
    host.show()
    palette_pkg.show_command_palette(parent=host)
    assert seen["parent"] is host

    # No reference: fall back to the active window, never None.
    _make_active(host)
    assert QApplication.activeWindow() is host
    palette_pkg.show_command_palette()
    assert seen["parent"] is host


def test_non_modal_message_defaults_to_active_window(qapp):
    from shared_toolkit.ui.message_dialog import MessageKind, open_non_modal_message

    host = QWidget()
    host.show()
    _make_active(host)
    assert QApplication.activeWindow() is host
    dialog = open_non_modal_message(
        None, kind=MessageKind.INFORMATION, title="t", text="b"
    )
    try:
        assert dialog.parent() is host
    finally:
        dialog.close()


def test_settings_show_path_has_no_deferred_activation():
    tree = _read_source("plugins/settings/dialog.py")
    for name in ("showEvent", "focus_initial_widget"):
        func = _find_function(tree, name)
        assert _activation_calls(func) == [], f"{name}() must not spend xdg tokens"
    show = _find_function(tree, "showEvent")
    singleshot = [
        node
        for node in ast.walk(show)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "singleShot"
    ]
    assert singleshot == [], "showEvent() must not defer focus/activation ticks"


def test_help_hide_path_has_no_window_activation():
    tree = _read_source("plugins/help/dialog.py")
    func = _find_function(tree, "hideEvent")
    assert _activation_calls(func) == [], "hideEvent() keeps widget setFocus only"


def test_rhi_flush_defaults_to_no_activation():
    from ui.canvas_infra.rhi.rhi_present_sync import flush_qrhi_compositor

    param = inspect.signature(flush_qrhi_compositor).parameters["activate"]
    assert param.default is False
