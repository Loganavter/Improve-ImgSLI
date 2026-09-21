"""Chrome shortcut three-side consistency (binder / keymap / Settings display).

Side 1 — live binder (``ActionShortcutBinder``). Side 2 — stored overrides
(``exclusive_overrides`` / ``steal_chord_in_overrides``). Side 3 — Settings
display (``effective_shortcut_for_id`` + ``resolve_chord_winners``). All
three rank through ``binding_priority`` so every conflict has one winner.
"""

from __future__ import annotations

from core.actions.types import ActionDescriptor
from ui.actions.binder import ActionShortcutBinder
from ui.actions.keymap import (
    aliases_for,
    binding_priority,
    exclusive_overrides,
    effective_shortcut_for_id,
    normalize_sequence,
    resolve_chord_winners,
)


def _noop() -> None:
    return None


def _action(action_id, shortcut, owner_tab=None):
    return ActionDescriptor(
        action_id=action_id,
        label_key=f"{action_id}.label",
        owner_tab=owner_tab,
        shortcut=shortcut,
        run=_noop,
    )


def test_shared_priority_orders_platform_before_tab():
    assert binding_priority("platform.settings", owner_tab=None) < binding_priority(
        "platform.x", owner_tab=None
    )
    assert binding_priority("platform.x", owner_tab=None) < binding_priority(
        "image_compare.x", owner_tab="image_compare"
    )


def test_three_sides_agree_on_conflict_winner(qapp):
    """Binder claim == keymap winner == Settings display chord."""
    from PySide6.QtWidgets import QWidget

    from ui.actions.registry import ActionRegistry

    registry = ActionRegistry()
    # Registration order deliberately disagrees with priority: the tab action
    # registers first, but the platform action must still win.
    registry.register(_action("image_compare.save", "Ctrl+S", "image_compare"))
    registry.register(_action("platform.save_project", "Ctrl+S"))

    defaults = {
        "image_compare.save": ("Ctrl+S", "image_compare"),
        "platform.save_project": ("Ctrl+S", None),
    }
    fixed = exclusive_overrides(defaults, {})
    assert fixed.get("image_compare.save") == ""
    assert "platform.save_project" not in fixed

    winners = resolve_chord_winners(defaults, fixed)
    chord = normalize_sequence("Ctrl+S")
    assert winners[chord] == "platform.save_project"

    window = QWidget()
    try:
        binder = ActionShortcutBinder()
        binder.resync(window, registry=registry, overrides=fixed, active_tab="image_compare")
        assert binder._claimed[chord] == "platform.save_project"
        # Settings display: winner keeps its chord, loser shows unbound.
        assert (
            effective_shortcut_for_id(
                "platform.save_project", default="Ctrl+S", overrides=fixed
            )
            == chord
        )
        assert (
            effective_shortcut_for_id(
                "image_compare.save", default="Ctrl+S", overrides=fixed
            )
            is None
        )
    finally:
        window.deleteLater()


def test_ctrl_y_alias_registered_and_visible_to_conflicts(qapp):
    """Ctrl+Y is a redo alias: winners map it, primaries beat it."""
    from PySide6.QtWidgets import QWidget

    from ui.actions.registry import ActionRegistry

    assert "Ctrl+Y" in [
        normalize_sequence(raw) for raw in ("Ctrl+Y",) if raw
    ]
    assert normalize_sequence("Ctrl+Y") in aliases_for("platform.redo")

    defaults = {
        "platform.redo": ("Ctrl+Shift+Z", None),
        "platform.custom": ("Ctrl+Y", None),
    }
    winners = resolve_chord_winners(defaults, {})
    # A primary holder outranks the alias holder on the same chord.
    assert winners[normalize_sequence("Ctrl+Y")] == "platform.custom"
    assert winners[normalize_sequence("Ctrl+Shift+Z")] == "platform.redo"

    # Alias installs when the chord is otherwise free.
    registry = ActionRegistry()
    registry.register(_action("platform.redo", "Ctrl+Shift+Z"))
    window = QWidget()
    try:
        binder = ActionShortcutBinder()
        binder.resync(window, registry=registry, overrides={}, active_tab=None)
        assert binder._claimed[normalize_sequence("Ctrl+Shift+Z")] == "platform.redo"
        assert binder._claimed[normalize_sequence("Ctrl+Y")] == "platform.redo"
    finally:
        window.deleteLater()


def test_redo_descriptor_exposes_ctrl_y_search_terms():
    """Registry + keymap rows expose the alias so conflict UIs see it."""
    from ui.actions.platform import (
        contribute_platform_keymap_defaults,
        register_platform_actions,
    )
    from ui.actions.keymap import KeymapDefaultsRegistry
    from ui.actions.registry import ActionRegistry

    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        undo=_noop,
        redo=_noop,
        registry=registry,
    )
    redo = registry.get("platform.redo")
    assert redo is not None
    assert "Ctrl+Y" in (tuple(getattr(redo, "search_terms", ()) or ()))

    keymap = KeymapDefaultsRegistry()
    contribute_platform_keymap_defaults(keymap)
    entry = next(
        e for e in keymap.all_entries() if e.action_id == "platform.redo"
    )
    assert "Ctrl+Y" in tuple(entry.search_terms or ())


def test_withdraw_drops_binder_shortcuts(qapp):
    """Catalog withdraw resyncs the binder — no stale chords keep firing."""
    from PySide6.QtWidgets import QWidget

    from ui.actions.dialog_contribute import withdraw_dialog_search_actions
    from ui.actions.registry import ActionRegistry

    registry = ActionRegistry()
    registry.register(_action("image_compare.export_dialog.quality", "Ctrl+E", "image_compare"))
    window = QWidget()
    try:
        binder = ActionShortcutBinder()
        binder.resync(window, registry=registry, overrides={}, active_tab="image_compare")
        assert normalize_sequence("Ctrl+E") in binder._claimed
        # Withdraw through a throwaway binder seeded with the same claim:
        # drop_prefix is the no-window path withdraw uses.
        binder.drop_prefix("image_compare.export_dialog.")
        assert normalize_sequence("Ctrl+E") not in binder._claimed

        # Full withdraw path (registry + binder drop) with an explicit binder.
        from ui.actions import binder as binder_module

        registry.register(
            _action("image_compare.export_dialog.quality", "Ctrl+E", "image_compare")
        )
        old_singleton = binder_module._binder
        binder_module._binder = binder
        try:
            binder.resync(
                window, registry=registry, overrides={}, active_tab="image_compare"
            )
            assert normalize_sequence("Ctrl+E") in binder._claimed
            withdraw_dialog_search_actions(
                "image_compare.export_dialog.", registry=registry
            )
            assert registry.get("image_compare.export_dialog.quality") is None
            assert normalize_sequence("Ctrl+E") not in binder._claimed
        finally:
            binder_module._binder = old_singleton
    finally:
        window.deleteLater()


def test_unresolvable_groups_register_no_dead_rows(qapp):
    """Groups with no widget register nothing — no noop rows."""
    from PySide6.QtWidgets import QWidget

    from ui.actions.dialog_contribute import contribute_dialog_search_actions
    from ui.actions.registry import ActionRegistry
    from ui.actions.search_index import SearchGroup, SearchIndex

    dialog = QWidget()
    try:
        member = QWidget(dialog)
        index = SearchIndex.of(
            SearchGroup.of("dlg.ghost_group", "dlg.ghost_member"),
            SearchGroup.of("dlg.live_group", "dlg.live_member"),
        )
        # Only the live member is tagged; the ghost group has no widget and
        # no resolvable member either.
        from ui.actions.search_index import PROP_MEMBER

        member.setProperty(PROP_MEMBER, "dlg.live_member")
        registry = ActionRegistry()
        registered = contribute_dialog_search_actions(
            dialog,
            index=index,
            prefix="dlg.test.",
            owner_tab="image_compare",
            topic="test",
            breadcrumb=("menu.file",),
            registry=registry,
        )
        assert "dlg.test.group.dlg.ghost_group" not in registered
        assert registry.get("dlg.test.group.dlg.ghost_group") is None
        live_group_id = "dlg.test.group.dlg.live_group"
        assert live_group_id in registered
        live_member_id = f"{live_group_id}.dlg.live_member"
        assert live_member_id in registered
        for action in registry.all_actions():
            assert callable(action.run)
            assert action.target is not None
            assert action.target.widget is not None
    finally:
        dialog.deleteLater()


def test_breadcrumb_fallback_has_no_raw_keys():
    from ui.actions.registry import action_breadcrumb_text

    bare = ActionDescriptor(action_id="platform.mystery", label_key="x.label")
    crumb = action_breadcrumb_text(bare)
    assert crumb
    assert "." not in crumb

    odd = ActionDescriptor(
        action_id="platform.odd",
        label_key="x.label",
        breadcrumb=("menu.file", "totally.missing_segment_key"),
    )
    crumb_odd = action_breadcrumb_text(odd)
    assert "totally.missing_segment_key" not in crumb_odd
    assert " ▸ " in crumb_odd


def test_explicit_override_store_beats_walk():
    from ui.actions.palette.common import (
        clear_keyboard_overrides_for_tests,
        current_keyboard_overrides,
        set_keyboard_overrides,
    )

    try:
        set_keyboard_overrides({"platform.save_project": "Ctrl+S"})
        assert current_keyboard_overrides() == {"platform.save_project": "Ctrl+S"}
        set_keyboard_overrides({})
        assert current_keyboard_overrides() == {}
    finally:
        clear_keyboard_overrides_for_tests()
    # Fail-open fallback without a published store.
    assert current_keyboard_overrides() == {}


def test_tr_action_humanizes_missing_keys():
    from ui.actions.palette.common import tr_action

    text = tr_action("totally.missing_label_key", "totally.missing_label_key")
    assert "." not in text
    assert text
