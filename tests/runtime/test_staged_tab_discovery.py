"""Staged tab discovery — bootstrap vs deferred tiers."""

from __future__ import annotations

import pytest

from tabs.registry import TabRegistry


def _fresh_registry() -> TabRegistry:
    TabRegistry._instance = None
    return TabRegistry()


def test_bootstrap_tier_registers_two_tabs():
    registry = _fresh_registry()
    registry.discover(tier="bootstrap")
    types = set(registry.registered_types)

    assert types == {"image_compare", "session_picker"}


def test_deferred_tier_adds_multi_compare():
    registry = _fresh_registry()
    registry.discover(tier="bootstrap")
    registry.discover(tier="deferred")

    assert "multi_compare" in registry.registered_types
    assert registry.get_tab("multi_compare") is not None


def test_discover_without_tier_is_idempotent():
    registry = _fresh_registry()
    registry.discover()
    types_after_first = set(registry.registered_types)
    registry.discover()
    assert set(registry.registered_types) == types_after_first
    assert types_after_first == {
        "image_compare",
        "session_picker",
        "multi_compare",
        "image_gallery",
    }


def test_deferred_tier_is_idempotent():
    registry = _fresh_registry()
    registry.discover(tier="bootstrap")
    registry.discover(tier="deferred")
    count = len(registry.registered_types)
    registry.discover(tier="deferred")
    assert len(registry.registered_types) == count


def test_bootstrap_default_is_reserved_for_session_picker():
    from core.store import INITIAL_WORKSPACE_SESSION_TYPE

    assert INITIAL_WORKSPACE_SESSION_TYPE == "session_picker"
    registry = _fresh_registry()
    registry.discover(tier="bootstrap")
    tab = registry.bootstrap_default_tab()
    assert tab is not None
    assert tab.session_type == "session_picker"


def test_bootstrap_default_rejects_non_session_picker_claimant():
    from tabs.contract import TabContract
    from tabs.registry import TabRegistry

    class _Intruder(TabContract):
        startup_tier = "bootstrap"

        @property
        def session_type(self) -> str:
            return "intruder"

        @property
        def display_name(self) -> str:
            return "Intruder"

        def create_page(self, parent, context):
            return None

        @property
        def is_bootstrap_default(self) -> bool:
            return True

    registry = _fresh_registry()
    registry._tabs["intruder"] = _Intruder()
    with pytest.raises(RuntimeError):
        registry.bootstrap_default_tab()


def test_startup_service_routes_by_capability():
    from tabs.contract import TabContract
    from tabs.registry import TabRegistry

    class _Capable(TabContract):
        startup_tier = "bootstrap"

        @property
        def session_type(self) -> str:
            return "capable"

        @property
        def display_name(self) -> str:
            return "Capable"

        def create_page(self, parent, context):
            return None

        def create_service(self, service_id, *args, **kwargs):
            if service_id == "shell_widget":
                return object()
            return None

    class _Bystander(TabContract):
        startup_tier = "bootstrap"

        @property
        def session_type(self) -> str:
            return "bystander"

        @property
        def display_name(self) -> str:
            return "Bystander"

        def create_page(self, parent, context):
            return None

    registry = _fresh_registry()
    registry._tabs["bystander"] = _Bystander()
    registry._tabs["capable"] = _Capable()
    assert registry.create_startup_service("shell_widget") is not None
    assert registry.create_startup_service("nope") is None


def test_startup_service_returns_none_when_no_tab_answers():
    from tabs.registry import TabRegistry

    registry = _fresh_registry()
    registry.discover(tier="bootstrap")
    assert (
        registry.create_startup_service("no_such_service_anywhere", object())
        is None
    )


def test_image_compare_does_not_claim_bootstrap_default():
    from tabs.registry import TabRegistry

    registry = _fresh_registry()
    registry.discover(tier="bootstrap")
    tab = registry.get_tab("image_compare")
    assert tab is not None
    assert tab.is_bootstrap_default is False
