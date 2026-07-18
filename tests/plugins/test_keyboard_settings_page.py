"""Keyboard settings section and binder smoke."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from core.actions.types import ActionDescriptor
from plugins.settings.pages.keyboard import SECTION, _collect_defaults
from plugins.settings.registry import SettingsRegistry
from ui.actions.binder import ActionShortcutBinder
from ui.actions.keymap import KeymapDefaultEntry, keymap_entry_rank, normalize_sequence
from ui.actions.registry import ActionRegistry


def test_keyboard_section_registers():
    registry = SettingsRegistry()
    registry.add(SECTION)
    sections = registry.sections_for(None)
    assert any(s.section_id == "builtin.keyboard" for s in sections)
    assert SECTION.title_key == "settings.keyboard"


def test_keymap_defaults_include_diff_mode_and_ssim_search():
    defaults = {e.action_id: e for e in _collect_defaults().all_entries()}
    assert "image_compare.diff_mode" in defaults
    entry = defaults["image_compare.diff_mode"]
    assert entry.default_shortcut == "H"
    assert keymap_entry_rank(entry, "ssim") is not None
    assert keymap_entry_rank(entry, "difference") is not None
    assert keymap_entry_rank(entry, "magnifier") is None


def test_keymap_entry_rank_matches_find_action_fields():
    entry = KeymapDefaultEntry(
        action_id="probe.mode",
        label_key="image_compare.action.diff_mode",
        default_shortcut="H",
        description_key="tooltip.change_diff_mode",
        search_keys=("image_compare.action.diff_ssim",),
        search_terms=("ssim",),
    )
    assert keymap_entry_rank(entry, "ssim") is not None
    assert keymap_entry_rank(entry, "probe.mode") is not None
    assert keymap_entry_rank(entry, "H") is not None
    assert keymap_entry_rank(entry, "change difference") is not None
    assert keymap_entry_rank(entry, "nope-xyz") is None
    # Extra terms (group title / effective chord) participate like palette aliases.
    assert (
        keymap_entry_rank(
            entry, "image compare", extra_search_terms=("Image Compare",)
        )
        is not None
    )


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
