"""One chord, one action per tab — the keybinding invariant.

Owner requirement 2026-10-25: inside a tab a key/chord may belong to exactly
ONE action. This is a hard invariant, not the binder's "first chord wins, skip
the loser" degradation: a duplicate that ships or that a user could produce in
Settings → Keyboard is a defect, and it must be *detectable* (strict gate for
tests/CI) and *named* (production verification) instead of silently resolving.

Scope model mirrors ``ActionShortcutBinder.resync`` (and
``ui.actions.keymap.shared_scope``): the binder installs platform actions plus
the ACTIVE tab's actions, so

* platform-vs-tab on one chord **is** a collision (they are live together);
* two different tabs on one chord is **not** — they are never live together
  (pinned separately by ``test_keymap_cross_tab_conflicts.py``).

The shipped-catalog test below is the gate for agents: adding an action whose
default chord is already taken inside its tab fails here, before the duplicate
can reach the binder, Settings, or a profile.
"""

from __future__ import annotations

import logging

import pytest

from core.log_names import APP_LOGGER_NAME
from ui.actions import keymap
from ui.actions.keymap import (
    KeymapDefaultEntry,
    KeymapDefaultsRegistry,
    steal_chord_in_overrides,
)
from ui.actions.keymap_uniqueness import (
    BindingCollisionError,
    assert_unique_bindings,
    assert_unique_bindings_all_scopes,
    binding_scopes,
    collisions_in_all_scopes,
    duplicate_bindings,
    scope_bindings,
    verify_unique_or_log,
)

# tiny catalog: platform + two tabs, with one deliberate same-tab collision
CATALOG = {
    "platform.find_action": ("Ctrl+Shift+P", None),
    "platform.settings": ("Ctrl+,", None),
    "image_compare.diff_mode": ("H", "image_compare"),
    "image_compare.divider.visible": ("D", "image_compare"),
    "image_compare.quick_save": ("Ctrl+S", "image_compare"),
    "multi_compare.divider.visible": ("D", "multi_compare"),
    "multi_compare.quick_save": ("Ctrl+S", "multi_compare"),
    "multi_compare.layout": ("Ctrl+1", "multi_compare"),
}


def _shipped_defaults() -> dict[str, tuple[str | None, str | None]]:
    """The real catalog as Settings sees it (metadata, no live widgets)."""
    from plugins.settings.keymap_defaults import collect_keymap_defaults

    registry = collect_keymap_defaults()
    return {
        entry.action_id: (entry.default_shortcut, entry.owner_tab)
        for entry in registry.all_entries()
    }


# -- shipped catalog (the gate) ----------------------------------------------


def test_shipped_catalog_has_one_action_per_chord_in_every_tab():
    defaults = _shipped_defaults()
    assert defaults, "keymap defaults catalog is empty — the gate would be vacuous"
    # AssertionError-free means: for every tab scope (platform + that tab),
    # and for every platform-only scope, no chord has two installable holders.
    assert_unique_bindings_all_scopes(defaults)


def test_shipped_catalog_scopes_cover_platform_and_each_tab():
    defaults = _shipped_defaults()
    scopes = binding_scopes(defaults)
    assert scopes[0] is None  # platform-only scope
    owners = {owner for _default, owner in defaults.values() if owner}
    assert set(scopes[1:]) == owners
    # Every scope resolves to a binding map (no accidental KeyError/regression).
    for tab in scopes:
        assert isinstance(scope_bindings(defaults, tab=tab), dict)


# -- scope semantics ---------------------------------------------------------


def test_same_chord_in_two_tabs_is_not_a_collision():
    assert duplicate_bindings(CATALOG, tab="image_compare") == {}
    assert duplicate_bindings(CATALOG, tab="multi_compare") == {}
    assert collisions_in_all_scopes(CATALOG) == ()


def test_platform_and_tab_sharing_a_chord_is_a_collision_in_that_tab():
    catalog = dict(CATALOG)
    catalog["multi_compare.find"] = ("Ctrl+Shift+P", "multi_compare")
    duplicates = duplicate_bindings(catalog, tab="multi_compare")
    assert duplicates == {"Ctrl+Shift+P": ("platform.find_action", "multi_compare.find")}
    # The other tab never sees the platform action paired with its own rows.
    assert duplicate_bindings(catalog, tab="image_compare") == {}
    with pytest.raises(BindingCollisionError) as excinfo:
        assert_unique_bindings_all_scopes(catalog)
    assert "Ctrl+Shift+P" in str(excinfo.value)
    assert "multi_compare.find" in str(excinfo.value)


def test_two_actions_of_one_tab_on_one_chord_is_a_collision():
    catalog = dict(CATALOG)
    catalog["multi_compare.layout_b"] = ("Ctrl+1", "multi_compare")
    assert duplicate_bindings(catalog, tab="multi_compare") == {
        "Ctrl+1": ("multi_compare.layout", "multi_compare.layout_b")
    }
    with pytest.raises(BindingCollisionError):
        assert_unique_bindings(catalog, tab="multi_compare")


def test_override_can_create_and_remove_a_collision():
    catalog = dict(CATALOG)
    # unbound → no holder, no collision
    assert duplicate_bindings(
        catalog, {"multi_compare.layout": ""}, tab="multi_compare"
    ) == {}
    # a user override onto another action's chord → collision
    collided = duplicate_bindings(
        catalog, {"multi_compare.layout": "Ctrl+S"}, tab="multi_compare"
    )
    assert collided == {"Ctrl+S": ("multi_compare.quick_save", "multi_compare.layout")}
    with pytest.raises(BindingCollisionError):
        assert_unique_bindings(
            catalog, {"multi_compare.layout": "Ctrl+S"}, tab="multi_compare"
        )


def test_alias_chords_participate_in_the_invariant(monkeypatch):
    """An alias chord is a claim like a primary one (e.g. redo's Ctrl+Y)."""
    monkeypatch.setitem(
        keymap.ACTION_ALIAS_CHORDS, "multi_compare.layout", ("Ctrl+1", "Ctrl+2")
    )
    catalog = dict(CATALOG)
    catalog["multi_compare.divider.visible"] = ("Ctrl+2", "multi_compare")
    assert duplicate_bindings(catalog, tab="multi_compare") == {
        "Ctrl+2": ("multi_compare.divider.visible", "multi_compare.layout")
    }
    with pytest.raises(BindingCollisionError):
        assert_unique_bindings_all_scopes(catalog)


def test_primary_only_check_ignores_aliases(monkeypatch):
    """``include_aliases=False`` is the resolver's view (aliases never steal)."""
    monkeypatch.setitem(
        keymap.ACTION_ALIAS_CHORDS, "multi_compare.layout", ("Ctrl+2",)
    )
    catalog = dict(CATALOG)
    catalog["multi_compare.divider.visible"] = ("Ctrl+2", "multi_compare")
    assert duplicate_bindings(catalog, tab="multi_compare", include_aliases=False) == {}
    assert_unique_bindings_all_scopes(catalog, include_aliases=False)


# -- production verification (loud, never fatal) -----------------------------


def test_verify_logs_each_collision_and_returns_it(caplog):
    catalog = dict(CATALOG)
    catalog["multi_compare.layout_b"] = ("Ctrl+1", "multi_compare")
    with caplog.at_level(logging.ERROR, logger=APP_LOGGER_NAME):
        collisions = verify_unique_or_log(catalog, source="probe")
    assert [c.chord for c in collisions] == ["Ctrl+1"]
    assert collisions[0].tab == "multi_compare"
    assert collisions[0].action_ids == ("multi_compare.layout", "multi_compare.layout_b")
    message = "\n".join(record.getMessage() for record in caplog.records)
    assert "probe" in message and "Ctrl+1" in message
    assert "multi_compare.layout_b" in message


def test_verify_is_silent_on_a_clean_map(caplog):
    with caplog.at_level(logging.ERROR, logger=APP_LOGGER_NAME):
        assert verify_unique_or_log(CATALOG, source="probe") == ()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# -- the Settings capture path ------------------------------------------------


def test_settings_capture_leaves_one_holder_per_chord():
    """A capture is a steal: the loser is unbound, never a second holder."""
    defaults = _shipped_defaults()
    # Pick a real same-tab holder pair out of the catalog.
    pair = next(
        (
            (a, b)
            for a, (chord_a, owner) in defaults.items()
            if owner and chord_a
            for b, (chord_b, owner_b) in defaults.items()
            if b != a and owner_b == owner and chord_b and chord_b != chord_a
        ),
        None,
    )
    assert pair is not None, "catalog has no same-tab action pair to test with"
    winner, loser = pair
    chord = defaults[loser][0]

    overrides = steal_chord_in_overrides(
        action_id=winner, chord=chord, defaults=defaults, overrides={}
    )

    assert overrides.get(loser) == ""  # explicitly unbound, not silently kept
    assert_unique_bindings_all_scopes(defaults, overrides)
    # And the requested chord is now the winner's effective one.
    holders = scope_bindings(
        defaults, overrides, tab=defaults[winner][1]
    ).get(keymap.normalize_sequence(chord))
    assert holders == (winner,)


def test_settings_capture_onto_a_platform_chord_keeps_one_holder():
    """A deliberate capture outranks scope — still exactly one holder per tab.

    ``exclusive_overrides(prefer_action_id=…)`` lets the action the user just
    typed a chord for win everywhere (that is what makes an intentional
    reassignment possible at all). The invariant is preserved either way: the
    platform action is explicitly unbound instead of quietly keeping the chord
    in every tab.
    """
    defaults = _shipped_defaults()
    platform_chord = next(
        chord for _aid, (chord, owner) in defaults.items() if owner is None and chord
    )
    tab_action = next(aid for aid, (_chord, owner) in defaults.items() if owner)
    tab = defaults[tab_action][1]

    overrides = steal_chord_in_overrides(
        action_id=tab_action,
        chord=platform_chord,
        defaults=defaults,
        overrides={},
    )

    assert_unique_bindings_all_scopes(defaults, overrides)
    holders = scope_bindings(
        defaults, overrides, tab=tab
    )[keymap.normalize_sequence(platform_chord)]
    assert holders == (tab_action,)
    # No scope may end with two holders: the other tab sees neither action
    # (the old platform holder is unbound, the thief is not installed there),
    # so "at most one" is the invariant, not "exactly one".
    for scope in binding_scopes(defaults):
        per_scope = scope_bindings(defaults, overrides, tab=scope)
        assert len(per_scope.get(keymap.normalize_sequence(platform_chord), ())) <= 1


def test_keymap_defaults_registry_roundtrip_keeps_metadata_only():
    """The Settings catalog is metadata: no runnable targets leak into it."""
    registry = KeymapDefaultsRegistry()
    registry.register(
        KeymapDefaultEntry(
            action_id="probe.a",
            label_key="probe.a.label",
            default_shortcut="Ctrl+Alt+A",
            owner_tab="multi_compare",
        )
    )
    entry = registry.all_entries()[0]
    assert entry.default_shortcut == "Ctrl+Alt+A"
    assert not hasattr(entry, "run")
