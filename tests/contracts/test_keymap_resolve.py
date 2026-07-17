"""Keymap resolve — defaults, overrides, unbound, PortableText normalize."""

from __future__ import annotations

from core.actions.types import ActionDescriptor
from ui.actions.keymap import (
    chord_conflicts,
    effective_shortcut,
    effective_shortcut_for_id,
    normalize_sequence,
)


def test_normalize_empty_and_simple():
    assert normalize_sequence("") == ""
    assert normalize_sequence(None) == ""
    assert normalize_sequence("ctrl+s") == normalize_sequence("Ctrl+S")


def test_effective_uses_default_when_override_missing():
    action = ActionDescriptor(
        action_id="platform.find_action",
        label_key="menu.find_action",
        shortcut="Ctrl+Shift+P",
    )
    assert effective_shortcut(action, {}) == normalize_sequence("Ctrl+Shift+P")


def test_effective_override_and_unbound():
    action = ActionDescriptor(
        action_id="platform.find_action",
        label_key="menu.find_action",
        shortcut="Ctrl+Shift+P",
    )
    assert effective_shortcut(
        action, {"platform.find_action": "Ctrl+P"}
    ) == normalize_sequence("Ctrl+P")
    assert effective_shortcut(action, {"platform.find_action": ""}) is None


def test_effective_shortcut_for_id():
    assert (
        effective_shortcut_for_id("a", default="Ctrl+S", overrides={})
        == normalize_sequence("Ctrl+S")
    )
    assert effective_shortcut_for_id("a", default="Ctrl+S", overrides={"a": ""}) is None


def test_chord_conflicts():
    conflicts = chord_conflicts(
        {
            "a": "Ctrl+S",
            "b": "Ctrl+S",
            "c": "Ctrl+O",
            "d": "",
        }
    )
    chord = normalize_sequence("Ctrl+S")
    assert chord in conflicts
    assert set(conflicts[chord]) == {"a", "b"}
