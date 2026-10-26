"""Flyout dismissal must not cross windows.

Owner report (2026-10-26): "opening flyouts in the Settings window hides
flyouts even in the InfoHUD — strange that they are connected and the flyout
manager cannot separate windows".

The manager is process-wide, so the only thing standing between two windows'
flyouts is the host show policy. Two holes made it dismiss-everything:

1. Every Settings flyout (a toolkit ``ComboBox`` dropdown, which carries no
   ``flyout_group`` of its own) resolved to ``default``, and ``default`` was
   never configured — so ``GroupShowPolicy._dismiss_targets`` fell through to
   its DISMISS_ALL fallback.
2. The corner HUD chips were only "protected" by not appearing in any dismiss
   set. ``pinned=True`` covers passive paths (outside click / wheel /
   deactivate / anchor move) but ``FlyoutManager.request_show`` checks
   ``pinned`` on the *showing* flyout only; a pinned chip is still a legal
   dismiss target for whatever opens next.

Both are policy facts, so they are asserted here directly, plus one pass
through the real ``FlyoutManager.request_show`` dismiss loop — the closest
thing to the owner's symptom that runs without a window. The structural part
(one ``_active_flyout`` for every top-level) is a toolkit follow-up; the app
tests below must hold either way.
"""

from __future__ import annotations

import pytest

from sli_ui_toolkit.managers import FlyoutManager

from ui.flyout_policy import install_flyout_show_policy


class _FakeFlyout:
    """Structural flyout: the manager only needs isVisible/hide (+pinned)."""

    def __init__(self, group: str | None = None, *, pinned: bool = False,
                 visible: bool = True, window=None) -> None:
        if group is not None:
            self.flyout_group = group
        self.pinned = pinned
        self._visible = visible
        self._window = window

    def isVisible(self) -> bool:  # noqa: N802 - Qt spelling
        return self._visible

    def hide(self) -> None:
        self._visible = False

    def window(self):
        return self._window


class _ScopedWindow:
    """Duck-typed top-level declaring a flyout scope (see SettingsDialog)."""

    flyout_scope_group = "settings"


@pytest.fixture()
def policy():
    manager = FlyoutManager.get_instance()
    previous_policy = manager.show_policy()
    previous_stack = manager.layer_stack()
    previous_registered = set(getattr(manager, "_registered_flyouts", ()))
    previous_active = getattr(manager, "_active_flyout", None)
    try:
        value = install_flyout_show_policy()
        yield value
    finally:
        manager.set_show_policy(previous_policy)
        manager.set_layer_stack(previous_stack)
        manager._registered_flyouts = previous_registered
        manager._active_flyout = previous_active


def test_untagged_default_flyout_does_not_dismiss_info_hud(policy):
    """The Settings-side flyout is untagged -> ``default``; the chip must stay."""
    untagged = _FakeFlyout()  # no flyout_group: the Settings combo dropdown case
    hud = _FakeFlyout("info_hud", pinned=True)

    assert policy.should_dismiss(untagged, hud) is False


def test_settings_window_flyout_does_not_dismiss_hud_chips(policy):
    """A flyout scoped to the Settings window leaves both chips alone."""
    settings_flyout = _FakeFlyout("settings")
    hud = _FakeFlyout("info_hud", pinned=True)
    zoom = _FakeFlyout("zoom_indicator", pinned=True)

    assert policy.should_dismiss(settings_flyout, hud) is False
    assert policy.should_dismiss(settings_flyout, zoom) is False
    # Symmetric: the chips never dismiss anything either.
    assert policy.should_dismiss(hud, settings_flyout) is False
    assert policy.should_dismiss(zoom, hud) is False


def test_no_configured_group_can_dismiss_a_hud_chip(policy):
    """Protection comes from coexistence edges, not from an omission in a list."""
    hud = _FakeFlyout("info_hud", pinned=True)
    zoom = _FakeFlyout("zoom_indicator", pinned=True)
    configured = set()
    for table in ("_group_dismisses", "_group_claim_active", "_group_parent"):
        configured.update(getattr(policy, table, {}) or {})

    assert {"info_hud", "zoom_indicator", "default", "settings"} <= configured
    for group in sorted(configured - {"info_hud", "zoom_indicator"}):
        showing = _FakeFlyout(group)
        assert policy.should_dismiss(showing, hud) is False, group
        assert policy.should_dismiss(showing, zoom) is False, group


def test_exclusive_groups_still_dismiss_each_other(policy):
    """No over-broad exception: the exclusive set keeps its mutual dismissal."""
    listing = _FakeFlyout("unified_list")
    options = _FakeFlyout("options")
    untagged = _FakeFlyout()

    assert policy.should_dismiss(listing, options) is True
    assert policy.should_dismiss(options, listing) is True
    # ``default`` is configured with the same dismiss set, not exempted:
    assert policy.should_dismiss(untagged, options) is True
    assert policy.should_dismiss(options, untagged) is True
    assert policy.should_dismiss(_FakeFlyout("settings"), options) is True


def test_context_menu_still_dismisses_nothing_and_never_claims_active(policy):
    menu = _FakeFlyout("context_menu")
    listing = _FakeFlyout("unified_list")
    hud = _FakeFlyout("info_hud", pinned=True)

    for other in (listing, hud, _FakeFlyout("options"), _FakeFlyout("default")):
        assert policy.should_dismiss(menu, other) is False
        assert policy.should_dismiss(other, menu) is False
    assert policy.should_claim_active(menu, listing) is False


def test_canvas_feature_panel_is_protected_from_the_untagged_group(policy):
    """Feature panels no longer close when an untagged popup opens (same class of bug)."""
    panel = _FakeFlyout("canvas_feature_settings")
    untagged = _FakeFlyout()
    hint = _FakeFlyout("slider_hint")

    assert policy.should_dismiss(untagged, panel) is False
    assert policy.should_dismiss(panel, hint) is False
    assert policy.should_dismiss(untagged, hint) is False


def test_untagged_flyout_of_scoped_window_adopts_its_group(qapp, policy):
    """A group-less toolkit dropdown follows the window that owns it."""
    scoped = _FakeFlyout(window=_ScopedWindow())
    manager = FlyoutManager.get_instance()

    manager.request_show(scoped)

    assert scoped.flyout_group == "settings"


def test_request_show_keeps_hud_chip_visible_when_untagged_flyout_opens(qapp, policy):
    """The owner's symptom, end to end through the real dismiss loop."""
    manager = FlyoutManager.get_instance()
    hud = _FakeFlyout("info_hud", pinned=True)
    manager.request_show(hud)
    assert hud.isVisible()

    settings_dropdown = _FakeFlyout(window=_ScopedWindow())
    manager.request_show(settings_dropdown)

    assert hud.isVisible(), "opening a Settings flyout hid the InfoHUD chip"
    assert settings_dropdown.isVisible()

    # And an untagged flyout of any other window still leaves it alone.
    straggler = _FakeFlyout()
    manager.request_show(straggler)
    assert hud.isVisible()
