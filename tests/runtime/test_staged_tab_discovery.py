"""Staged tab discovery — bootstrap vs deferred tiers."""

from __future__ import annotations

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
    assert types_after_first == {"image_compare", "session_picker", "multi_compare"}


def test_deferred_tier_is_idempotent():
    registry = _fresh_registry()
    registry.discover(tier="bootstrap")
    registry.discover(tier="deferred")
    count = len(registry.registered_types)
    registry.discover(tier="deferred")
    assert len(registry.registered_types) == count
