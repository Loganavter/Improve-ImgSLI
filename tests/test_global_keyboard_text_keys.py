"""The overlay-movement route must not swallow keys typed into a focused field.

``GlobalKeyboardHandler.should_route_globally`` sends W/A/S/D/Q/E and Space to
the canvas overlay. A toolkit ComboBox is a painted ``Button`` (not a
``QLineEdit``), so the old type-based text-input check missed it and typing
``deepseek`` into a focused model list delivered only ``p``/``k``. The widget
now opts in through ``acceptsTextKeys()``; these tests pin the routing decision
at the handler, which is where the keys were lost.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget

from events.app_event import keyboard as keyboard_module
from events.app_event.keyboard import GlobalKeyboardHandler, widget_accepts_text_keys
from sli_ui_toolkit.widgets import ComboBox


@pytest.fixture
def handler():
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            interaction_state=SimpleNamespace(space_bar_pressed=False)
        )
    )
    return GlobalKeyboardHandler(
        store=store,
        presenter_provider=lambda: None,
        movement_controller=SimpleNamespace(start=lambda: None, stop=lambda: None),
        keyboard_state=SimpleNamespace(),
    )


def _key(key: Qt.Key) -> QKeyEvent:
    text = {
        Qt.Key.Key_D: "d",
        Qt.Key.Key_E: "e",
        Qt.Key.Key_S: "s",
        Qt.Key.Key_W: "w",
    }.get(key, "")
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)


def _route(handler, focused, key):
    """Ask the decision with ``focused`` standing in for the live focus widget."""
    tab = SimpleNamespace(owns_widget=lambda _w: False)
    registry = SimpleNamespace(get_active_tab=lambda: tab)
    with patch.object(keyboard_module, "get_shared_tab_registry", lambda: registry), patch.object(
        keyboard_module, "focused_widget", lambda: focused
    ):
        return handler.should_route_globally(_key(key), SimpleNamespace())


def test_overlay_keys_are_still_global_for_a_plain_widget(handler):
    plain = QWidget()
    for key in (Qt.Key.Key_D, Qt.Key.Key_E, Qt.Key.Key_S, Qt.Key.Key_W):
        assert _route(handler, plain, key) is True


def test_overlay_keys_are_not_stolen_from_a_typing_combobox(handler, qtbot):
    combo = ComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["deepseek-r1", "deepseek-v3", "other"])
    assert widget_accepts_text_keys(combo) is True
    for key in (Qt.Key.Key_D, Qt.Key.Key_E, Qt.Key.Key_S, Qt.Key.Key_W):
        assert _route(handler, combo, key) is False


def test_space_is_not_stolen_from_a_typing_combobox(handler, qtbot):
    combo = ComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["a", "b"])
    space = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ")
    tab = SimpleNamespace(owns_widget=lambda _w: False)
    registry = SimpleNamespace(get_active_tab=lambda: tab)
    with patch.object(keyboard_module, "get_shared_tab_registry", lambda: registry), patch.object(
        keyboard_module, "focused_widget", lambda: combo
    ):
        assert handler.should_route_globally(space, SimpleNamespace()) is False


def test_a_combobox_with_typing_disabled_does_not_hold_the_overlay_keys(handler, qtbot):
    combo = ComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["a", "b"])
    combo.setSearchEnabled(False)
    assert widget_accepts_text_keys(combo) is False
    assert _route(handler, combo, Qt.Key.Key_D) is True


def test_native_editors_and_a_disabled_combobox(handler, qtbot):
    line = QLineEdit()
    qtbot.addWidget(line)
    assert widget_accepts_text_keys(line) is True
    assert _route(handler, line, Qt.Key.Key_D) is False

    combo = ComboBox()
    qtbot.addWidget(combo)
    combo.addItems(["a"])
    combo.setEnabled(False)
    assert widget_accepts_text_keys(combo) is False
