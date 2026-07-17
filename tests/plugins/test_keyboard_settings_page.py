"""Keyboard settings section and binder smoke."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from core.actions.types import ActionDescriptor
from plugins.settings.pages.keyboard import SECTION
from plugins.settings.registry import SettingsRegistry
from ui.actions.binder import ActionShortcutBinder
from ui.actions.keymap import normalize_sequence
from ui.actions.registry import ActionRegistry


def test_keyboard_section_registers():
    registry = SettingsRegistry()
    registry.add(SECTION)
    sections = registry.sections_for(None)
    assert any(s.section_id == "builtin.keyboard" for s in sections)
    assert SECTION.title_key == "settings.keyboard"


def test_binder_first_wins_and_invokes(qtbot):
    window = QWidget()
    qtbot.addWidget(window)
    window.show()

    ran: list[str] = []
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="probe.first",
            label_key="menu.settings",
            shortcut="Ctrl+Shift+P",
            run=lambda: ran.append("first"),
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="probe.second",
            label_key="menu.quit",
            shortcut="Ctrl+Shift+P",
            run=lambda: ran.append("second"),
        )
    )

    binder = ActionShortcutBinder()
    binder.resync(window, registry=registry, overrides={}, active_tab=None)
    assert len(binder._shortcuts) == 1
    assert binder._claimed[normalize_sequence("Ctrl+Shift+P")] == "probe.first"

    binder._shortcuts[0].activated.emit()
    qtbot.wait(20)
    assert ran == ["first"]
