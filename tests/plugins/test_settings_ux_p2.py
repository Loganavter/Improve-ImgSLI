"""Settings UX P2: loud notifier, combo selection signals, group-scoped
member resolution, duplicate section log, stable export ids, help badge.

Covers ``task-fix-settings-ux-p2-2026-09-20``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWidget

from ui.actions.search_index import PROP_MEMBER


@pytest.fixture()
def _qapp_qt(qapp):
    return qapp


# --- notifier: None-bus loud + delivery guarantee ---------------------------


def _notifier(**kwargs):
    from plugins.settings.notifier import SettingsUpdateNotifier

    return SettingsUpdateNotifier(SimpleNamespace(), **kwargs)


def test_request_core_update_without_channels_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        _notifier().request_core_update()
    assert any("no event_bus" in r.message for r in caplog.records)


def test_request_core_update_prefers_bus_then_signal():
    from plugins.settings.events import SettingsUIModeChangedEvent  # noqa: F401

    emitted: list = []
    bus = SimpleNamespace(emit=emitted.append)
    _notifier(event_bus=bus).request_core_update()
    assert len(emitted) == 1

    signaled: list = []
    _notifier(update_requested_signal=SimpleNamespace(emit=lambda: signaled.append(1))).request_core_update()
    assert signaled == [1]


def test_emit_ui_mode_changed_without_bus_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        _notifier().emit_ui_mode_changed("expert")
    assert any("emit_ui_mode_changed" in r.message for r in caplog.records)


# --- translations: combo preserves selection or signals reset ----------------


class _Combo:
    def __init__(self, values, current):
        self._values = list(values)
        self._current = current
        self.index = 0

    def currentData(self):
        return self._current

    def clear(self):
        self._values = []

    def addItem(self, text, key=None, userData=None):
        self._values.append(userData if userData is not None else key)

    def findData(self, value):
        try:
            return self._values.index(value)
        except ValueError:
            return -1

    def setCurrentIndex(self, index):
        self.index = index


def test_restore_combo_selection_preserves(caplog):
    from plugins.settings.translations import _restore_combo_selection

    combo = _Combo(["a", "b"], "b")
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        _restore_combo_selection(combo, "b", "combo_x")
    assert combo.index == 1
    assert not caplog.records


def test_restore_combo_selection_warns_on_reset(caplog):
    from plugins.settings.translations import _restore_combo_selection

    combo = _Combo(["a"], "b")
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        _restore_combo_selection(combo, "b", "combo_x")
    assert any("combo_x" in r.message and "lost selection" in r.message for r in caplog.records)


def test_restore_combo_selection_none_is_quiet(caplog):
    from plugins.settings.translations import _restore_combo_selection

    combo = _Combo(["a"], None)
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        _restore_combo_selection(combo, None, "combo_x")
    assert not caplog.records


# --- member resolution: group-scoped + robust control match ------------------


def _tagged(parent, key):
    w = QWidget(parent)
    w.setProperty(PROP_MEMBER, key)
    return w


def test_resolve_member_group_scoped(qapp):
    from plugins.settings.member_resolve import resolve_member_widget

    dialog = QWidget()
    group_box = QWidget(dialog)
    in_group = _tagged(group_box, "m.key")
    _tagged(dialog, "m.key")  # same key outside the group
    dialog.group_widget_for = lambda _key: group_box
    assert resolve_member_widget(dialog, "g", "m.key") is in_group


def test_resolve_member_missing_in_group_returns_none(qapp):
    """Group exists but holds no such member → None (no cross-group leak)."""
    from plugins.settings.member_resolve import (
        activate_member_in_dialog,
        resolve_member_widget,
    )

    dialog = QWidget()
    group_box = QWidget(dialog)
    _tagged(dialog, "m.key")  # only outside the group
    dialog.group_widget_for = lambda _key: group_box
    assert resolve_member_widget(dialog, "g", "m.key") is None
    assert activate_member_in_dialog(dialog, "g", "m.key") is False


def test_resolve_member_falls_back_when_group_missing(qapp):
    from plugins.settings.member_resolve import resolve_member_widget

    dialog = QWidget()
    outside = _tagged(dialog, "m.key")
    dialog.group_widget_for = lambda _key: None
    assert resolve_member_widget(dialog, "g", "m.key") is outside


class _ExclusiveButton:
    """Radio-like control without isCheckable() and without 'radio' in name."""

    def __init__(self):
        self.checked = False

    def autoExclusive(self):
        return True

    def isChecked(self):
        return self.checked

    def setChecked(self, value):
        self.checked = bool(value)


class _PlainCheck:
    def __init__(self):
        self.checked = False

    def isChecked(self):
        return self.checked

    def setChecked(self, value):
        self.checked = bool(value)


def test_activate_member_control_exclusive_structural():
    from plugins.settings.member_resolve import activate_member_control

    radio = _ExclusiveButton()
    assert activate_member_control(radio) is True
    assert radio.checked is True


def test_activate_member_control_checkbox_toggles():
    from plugins.settings.member_resolve import activate_member_control

    check = _PlainCheck()
    assert activate_member_control(check) is True
    assert check.checked is True
    assert activate_member_control(check) is True
    assert check.checked is False


# --- registry: duplicate section logged ---------------------------------------


def _make_dup_section(owner: str = "ic"):
    from plugins.settings.registry import SettingsSection
    from ui.icon_manager import AppIcon

    def _build(_dialog, _ctx):
        return None

    return SettingsSection(
        section_id="dup",
        title_key="t",
        icon=AppIcon.SETTINGS,
        build=_build,
        owner_tab=owner,
        order=40,
    )


def test_registry_identical_reinstall_is_silent(caplog):
    from plugins.settings.registry import SettingsRegistry

    registry = SettingsRegistry()
    first = _make_dup_section()
    second = _make_dup_section()  # fresh instance, same content (startup 3x path)
    registry.add(first)
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        registry.add(second)
    assert not any(
        r.levelno >= logging.WARNING and "duplicate section_id" in r.message
        for r in caplog.records
    )
    assert registry.all_sections() == [first]


def test_registry_conflicting_redefinition_warns(caplog):
    from plugins.settings.registry import SettingsRegistry

    registry = SettingsRegistry()
    registry.add(_make_dup_section(owner="ic"))
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        registry.add(_make_dup_section(owner="other"))
    assert any("duplicate section_id" in r.message for r in caplog.records)
    assert registry.all_sections()[0].owner_tab == "ic"


# --- export: stable action ids -------------------------------------------------


def test_export_dialog_action_ids_stable_across_owners(qapp):
    from plugins.export.actions import (
        _EXPORT_DIALOG_PREFIX,
        contribute_export_dialog_actions,
        withdraw_export_dialog_actions,
    )
    from ui.actions.registry import ActionRegistry

    assert _EXPORT_DIALOG_PREFIX == "export_dialog."

    def _ids_for(owner):
        from plugins.export.search import OUTPUT

        registry = ActionRegistry()
        dialog = QWidget()
        btn = QWidget(dialog)
        OUTPUT.tag_member(btn, "button.browse")
        contribute_export_dialog_actions(dialog, registry=registry, owner_tab=owner)
        try:
            return sorted(a.action_id for a in registry.all_actions())
        finally:
            withdraw_export_dialog_actions(registry=registry, owner_tab=owner)
            dialog.deleteLater()

    ids_a = _ids_for("image_compare")
    ids_b = _ids_for("multi_compare")
    assert ids_a and ids_a == ids_b
    assert all(i.startswith("export_dialog.") for i in ids_a)


# --- help: fallback badge on untranslated help ---------------------------------


def test_help_fallback_badge_on_untranslated_title():
    from plugins.help.labels import FALLBACK_BADGE, node_title
    from plugins.help.tree import HelpNode

    node = HelpNode(
        node_id="x",
        kind="page",
        title="Raw Title",
        body="x.md",
        title_key="nope.missing.key.xyz",
    )
    assert node_title(node, "ru") == f"Raw Title{FALLBACK_BADGE}"


def test_help_translated_title_has_no_badge():
    from plugins.help.labels import FALLBACK_BADGE, node_title
    from plugins.help.tree import HelpNode

    node = HelpNode(
        node_id="x",
        kind="page",
        title="OK",
        body="x.md",
        title_key="common.ok",
    )
    text = node_title(node, "ru")
    assert text == "ОК"
    assert FALLBACK_BADGE not in text


def test_help_fallback_badge_on_untranslated_description():
    from plugins.help.labels import FALLBACK_BADGE, node_description
    from plugins.help.tree import HelpNode

    node = HelpNode(
        node_id="x",
        kind="page",
        title="T",
        description="Raw desc",
        body="x.md",
        description_key="nope.missing.key.xyz",
    )
    assert node_description(node, "ru") == f"Raw desc{FALLBACK_BADGE}"
