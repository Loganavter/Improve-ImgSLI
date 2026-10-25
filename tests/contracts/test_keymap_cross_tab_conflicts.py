"""Cross-tab shared chords are NOT conflicts (keymap / Settings apply / display).

The live binder installs only platform actions plus the ACTIVE tab's actions
(``ActionShortcutBinder.resync`` → ``registry.list_for(active_tab=…)``), so two
tabs may legitimately share ``D`` / ``Ctrl+S``: they never live in one window
scope. Settings used to rank conflicts across ALL tabs instead, so
``image_compare:*`` beat ``multi_compare:*`` alphabetically and the loser was
persisted as an ``""`` override — permanently dead shortcut, surviving restarts
(reproduced on a clean profile by opening Settings and pressing OK without
visiting the Keyboard page).

Four behaviours pinned here:
(a) two tabs owning the same chord leave ``keyboard_overrides`` empty after the
    Settings apply path;
(b) a user's deliberate same-tab ``""`` survives the repair;
(c) a profile already poisoned by the old cross-tab ranking is repaired on the
    next apply;
(d) a genuine same-tab conflict still unbinds the loser — and a platform chord
    still beats a tab chord (the binder scope keeps platform actions).
"""

from __future__ import annotations

from types import SimpleNamespace

from core.state_management.actions import SetKeyboardOverridesAction
from ui.actions.keymap import (
    KeymapDefaultEntry,
    KeymapDefaultsRegistry,
    effective_shortcut_for_id,
    exclusive_overrides,
    normalize_sequence,
)

# The real catalog rows that caused the incident: both tabs ship "D" for the
# divider toggle and "Ctrl+S" for quick save.
TWO_TABS_SHARE_CHORDS = {
    "image_compare.divider.visible": ("D", "image_compare"),
    "multi_compare.divider.visible": ("D", "multi_compare"),
    "image_compare.quick_save": ("Ctrl+S", "image_compare"),
    "multi_compare.quick_save": ("Ctrl+S", "multi_compare"),
}

POISONED_PROFILE = {
    "multi_compare.divider.visible": "",
    "multi_compare.quick_save": "",
}


def _registry_for(defaults_map) -> KeymapDefaultsRegistry:
    registry = KeymapDefaultsRegistry()
    for action_id, (chord, owner_tab) in defaults_map.items():
        registry.register(
            KeymapDefaultEntry(
                action_id=action_id,
                label_key=f"{action_id}.label",
                default_shortcut=chord,
                owner_tab=owner_tab,
            )
        )
    return registry


class _Dispatcher:
    def __init__(self, store) -> None:
        self.store = store
        self.dispatched: list = []

    def dispatch(self, action, **_kwargs) -> None:
        self.dispatched.append(action)
        if isinstance(action, SetKeyboardOverridesAction):
            self.store.settings.keyboard_overrides = dict(action.overrides)


class _Settings:
    def __init__(self, overrides) -> None:
        self.keyboard_overrides = dict(overrides)


class _Store:
    def __init__(self, overrides) -> None:
        self.settings = _Settings(overrides)
        self.dispatcher = _Dispatcher(self)

    def get_dispatcher(self):
        return self.dispatcher


def _apply(defaults_map, *, store_overrides, incoming, monkeypatch):
    """Run the REAL Settings apply path with a pinned defaults catalog.

    ``collect_keymap_defaults`` discovers the tab registry, which is not
    available in every test environment — pinning it (in the collector module
    the apply path imports from) keeps this test about the conflict scope, not
    about tab discovery.
    """
    import plugins.settings.keymap_defaults as keymap_defaults
    from plugins.settings.application_service import SettingsApplicationService

    monkeypatch.setattr(
        keymap_defaults,
        "collect_keymap_defaults",
        lambda: _registry_for(defaults_map),
    )
    store = _Store(store_overrides)
    service = SettingsApplicationService(store, None)
    service._apply_keyboard_overrides(
        SimpleNamespace(keyboard_overrides=dict(incoming))
    )
    return store.settings.keyboard_overrides, store.dispatcher.dispatched


def test_cross_tab_chord_is_not_a_conflict(qapp):
    """(a) pure resolver: no empty override for a chord two tabs both own."""
    assert exclusive_overrides(TWO_TABS_SHARE_CHORDS, {}) == {}


def test_settings_apply_leaves_cross_tab_overrides_empty(qapp, monkeypatch):
    """(a) apply path: OK with an untouched Keyboard page stores nothing."""
    overrides, dispatched = _apply(
        TWO_TABS_SHARE_CHORDS,
        store_overrides={},
        incoming={},
        monkeypatch=monkeypatch,
    )
    assert overrides == {}
    assert dispatched == []


def test_user_same_tab_unbind_survives_apply(qapp, monkeypatch):
    """(b) a deliberate same-tab ``""`` is not "repaired" away."""
    defaults = {
        "image_compare.save": ("Ctrl+S", "image_compare"),
        "image_compare.quick_save": ("Ctrl+S", "image_compare"),
        "multi_compare.text_settings": ("T", "multi_compare"),
    }
    incoming = {
        # User unbound the loser of a genuine same-tab conflict…
        "image_compare.quick_save": "",
        # …and unbound an action whose chord only it owns.
        "multi_compare.text_settings": "",
    }
    overrides, _dispatched = _apply(
        defaults, store_overrides={}, incoming=incoming, monkeypatch=monkeypatch
    )
    assert overrides == incoming


def test_poisoned_profile_is_repaired_on_apply(qapp, monkeypatch):
    """(c) the next OK drops legacy cross-tab unbinds and persists the repair."""
    overrides, dispatched = _apply(
        TWO_TABS_SHARE_CHORDS,
        store_overrides=POISONED_PROFILE,
        incoming=POISONED_PROFILE,
        monkeypatch=monkeypatch,
    )
    assert overrides == {}
    assert len(dispatched) == 1
    assert isinstance(dispatched[0], SetKeyboardOverridesAction)


def test_repair_legacy_cross_tab_unbounds_is_pure():
    """(c) the repair helper itself: drops cross-tab, keeps same-tab, no mutation."""
    from ui.actions.keymap import repair_legacy_cross_tab_unbounds

    defaults = {
        **TWO_TABS_SHARE_CHORDS,
        "image_compare.save": ("Ctrl+Shift+S", "image_compare"),
        "image_compare.save_as": ("Ctrl+Shift+S", "image_compare"),
    }
    overrides = {
        **POISONED_PROFILE,
        "image_compare.save_as": "",
    }
    before = dict(overrides)

    repaired = repair_legacy_cross_tab_unbounds(defaults, overrides)

    assert overrides == before  # pure: caller's dict untouched
    assert repaired == {"image_compare.save_as": ""}

    # A cross-tab share where the action ALSO has a same-tab rival on that
    # chord is a genuine same-tab conflict — the user's "" must stay.
    same_tab_rival = {
        **TWO_TABS_SHARE_CHORDS,
        "multi_compare.overlay.visible": ("D", "multi_compare"),
    }
    assert repair_legacy_cross_tab_unbounds(
        same_tab_rival, {"multi_compare.divider.visible": ""}
    ) == {"multi_compare.divider.visible": ""}


def test_same_tab_conflict_still_unbinds_loser(qapp, monkeypatch):
    """(d) two actions of ONE tab still lose to one winner."""
    defaults = {
        "image_compare.save": ("Ctrl+S", "image_compare"),
        "image_compare.quick_save": ("Ctrl+S", "image_compare"),
    }
    overrides, _dispatched = _apply(
        defaults, store_overrides={}, incoming={}, monkeypatch=monkeypatch
    )
    # binding_priority ranks "…quick_save" before "…save", so quick_save wins.
    assert overrides == {"image_compare.save": ""}
    assert (
        effective_shortcut_for_id(
            "image_compare.quick_save", default="Ctrl+S", overrides=overrides
        )
        == normalize_sequence("Ctrl+S")
    )


def test_platform_chord_still_outranks_tab_chord(qapp, monkeypatch):
    """(4) platform actions live in every tab scope, so they still win."""
    defaults = {
        "platform.save_project": ("Ctrl+S", None),
        "image_compare.quick_save": ("Ctrl+S", "image_compare"),
    }
    overrides, _dispatched = _apply(
        defaults, store_overrides={}, incoming={}, monkeypatch=monkeypatch
    )
    assert overrides == {"image_compare.quick_save": ""}
    assert (
        effective_shortcut_for_id(
            "platform.save_project", default="Ctrl+S", overrides=overrides
        )
        == normalize_sequence("Ctrl+S")
    )


def test_keyboard_page_shows_cross_tab_share_as_active(qapp):
    """(3) both owners display their chord; neither row falls back to "—"."""
    from ui.actions.keymap import repair_legacy_cross_tab_unbounds

    # The exact composition Settings → Keyboard ``build`` uses.
    displayed = exclusive_overrides(
        TWO_TABS_SHARE_CHORDS,
        repair_legacy_cross_tab_unbounds(TWO_TABS_SHARE_CHORDS, POISONED_PROFILE),
    )
    for action_id, chord in (
        ("image_compare.divider.visible", "D"),
        ("multi_compare.divider.visible", "D"),
        ("image_compare.quick_save", "Ctrl+S"),
        ("multi_compare.quick_save", "Ctrl+S"),
    ):
        assert (
            effective_shortcut_for_id(
                action_id,
                default=chord,
                overrides=displayed,
            )
            == normalize_sequence(chord)
        ), action_id


def test_keyboard_page_build_applies_the_repair():
    """(3) wiring: the page composes the repair, not only the raw overrides."""
    import inspect

    from plugins.settings.pages.keyboard import build

    source = inspect.getsource(build)
    assert "repair_legacy_cross_tab_unbounds" in source
