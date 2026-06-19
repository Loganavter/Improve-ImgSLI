"""UI inspector controller selects widgets only via Shift+LeftClick.

Dogma source: docs/dev/UI_INSPECTOR.md.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from devtools.ui_inspector import controller as controller_module
from devtools.ui_inspector.controller import UiInspectorController

_APP = None


class _ThemeManagerProbe:
    _dark_palette = {}
    _light_palette = {}
    _qss_paths = ()

    def is_dark(self):
        return False


class _MousePress:
    def __init__(self, modifiers=Qt.KeyboardModifier.NoModifier):
        self._modifiers = modifiers

    def button(self):
        return Qt.MouseButton.LeftButton

    def modifiers(self):
        return self._modifiers

    def globalPosition(self):
        return QPointF(40, 40)


def _app():
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def test_controller_requires_shift_left_click(monkeypatch):
    app = _app()
    main = QWidget()
    target = QLabel("Target", main)
    target.setGeometry(QRect(10, 10, 80, 24))

    inspector = UiInspectorController(app, main, _ThemeManagerProbe())
    try:
        called = False

        def _widget_at(_pos: QPoint):
            nonlocal called
            called = True
            return target

        monkeypatch.setattr(
            controller_module.QApplication,
            "widgetAt",
            staticmethod(_widget_at),
        )

        assert inspector._handle_mouse_press(_MousePress()) is False
        assert called is False
        assert inspector._current_widget is None
    finally:
        inspector.shutdown()


def test_controller_can_inspect_plugin_top_level_window(monkeypatch):
    app = _app()
    main = QWidget()
    plugin_window = QWidget()
    target = QLabel("Plugin target", plugin_window)
    target.setObjectName("pluginTarget")
    target.setGeometry(QRect(10, 10, 90, 24))

    inspector = UiInspectorController(app, main, _ThemeManagerProbe())
    try:
        monkeypatch.setattr(
            controller_module.QApplication,
            "widgetAt",
            staticmethod(lambda _pos: target),
        )

        event = _MousePress(Qt.KeyboardModifier.ShiftModifier)

        assert inspector._handle_mouse_press(event) is True
        assert inspector._current_widget is target
        assert plugin_window in inspector._overlays
        assert main not in inspector._overlays
    finally:
        inspector.shutdown()
