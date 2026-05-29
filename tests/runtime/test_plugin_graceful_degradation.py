"""Plugins/features degrade gracefully when absent.

  * Plugin discovery over an empty ``plugins/`` set must not raise — the app
    should boot with zero plugins.
  * Looking up a capability alias that no feature provides must return ``None``
    (a quiet, checkable miss) rather than raising — callers branch on ``None``.

Dogma source: docs/dev/ARCHITECTURE.md §Graceful degradation.
"""

from __future__ import annotations

import core.plugin_system.registry as registry_mod
from core.plugin_system.registry import PluginRegistry
from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_command_by_alias,
)

def test_discovery_with_no_plugins_returns_empty(monkeypatch):
    monkeypatch.setattr(registry_mod, "get_registered_plugins", lambda: [])
    monkeypatch.setattr(PluginRegistry, "_scan_package", lambda self, name: None)

    registry = PluginRegistry(app_context=object())
    created = registry.discover_plugins()

    assert list(created) == []
    assert list(registry.all_plugins()) == []

def test_discovery_swallows_missing_package(monkeypatch):
    monkeypatch.setattr(registry_mod, "get_registered_plugins", lambda: [])

    def _raise_import(name):
        raise ImportError(name)

    monkeypatch.setattr(registry_mod.importlib, "import_module", _raise_import)

    registry = PluginRegistry(app_context=object())
    # Missing 'plugins'/'tabs' packages must not propagate.
    assert list(registry.discover_plugins()) == []

def test_unknown_alias_resolves_to_none():
    assert get_canvas_feature_command_by_alias("does.not.exist.alias") is None

def test_get_plugin_missing_returns_none():
    registry = PluginRegistry(app_context=object())
    assert registry.get_plugin("nonexistent") is None
