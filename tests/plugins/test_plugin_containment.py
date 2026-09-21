"""Plugin load containment: one bad plugin must not abort the tier.

Regression tests for task-fix-plugin-containment-2026-09-20:
- broad per-entry import guard in discovery (bad module skipped),
- per-plugin try/except in register_plugins (throwing plugin skipped),
- duplicate session_type isolated (first registration kept),
- command dispatch rejects private/dunder names (trust boundary),
- activate() without an initialized context is skipped, not half-wired.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

sys.path.insert(0, "src")

from core.plugin_coordinator import PluginCoordinator
from core.plugin_system.interfaces import ISessionPlugin
from core.plugin_system.plugin import Plugin, PluginState
from core.plugin_system.registry import PluginRegistry
from core.session_blueprints import SessionBlueprint


class _GoodPlugin(Plugin):
    def initialize(self, context: Any) -> None:
        super().initialize(context)

    def public_command(self) -> str:
        return "ok"


class _ThrowingPlugin(Plugin):
    def initialize(self, context: Any) -> None:
        raise RuntimeError("boom in initialize")


class _SessionPlugin(Plugin, ISessionPlugin):
    def __init__(self, owner: str, session_type: str):
        super().__init__()
        self._owner = owner
        self._session_type = session_type

    def initialize(self, context: Any) -> None:
        super().initialize(context)

    def get_session_blueprints(self):
        return (
            SessionBlueprint(
                session_type=self._session_type,
                plugin_name=self._owner,
            ),
        )


class _ExplodingBlueprintPlugin(Plugin, ISessionPlugin):
    def initialize(self, context: Any) -> None:
        super().initialize(context)

    def get_session_blueprints(self):
        raise RuntimeError("boom in blueprints")


def _coordinator() -> PluginCoordinator:
    return PluginCoordinator(event_bus=None)


def test_register_plugins_skips_throwing_plugin():
    coord = _coordinator()
    good = _GoodPlugin()
    good._plugin_meta = {"name": "contain-good"}
    bad = _ThrowingPlugin()
    bad._plugin_meta = {"name": "contain-bad"}
    good2 = _GoodPlugin()
    good2._plugin_meta = {"name": "contain-good2"}

    # Must not raise; good plugins on both sides still register.
    coord.register_plugins([good, bad, good2])
    assert coord.get_plugin("contain-good") is good
    assert coord.get_plugin("contain-good2") is good2


def test_duplicate_session_type_isolated_first_wins():
    coord = _coordinator()
    first = _SessionPlugin("contain-first", "contain_dup_type")
    first._plugin_meta = {"name": "contain-first"}
    second = _SessionPlugin("contain-second", "contain_dup_type")
    second._plugin_meta = {"name": "contain-second"}
    third = _SessionPlugin("contain-third", "contain_other_type")
    third._plugin_meta = {"name": "contain-third"}

    # Must not raise; the duplicate is skipped, the rest are kept.
    coord.register_plugins([first, second, third])
    blueprint = coord.get_session_blueprint("contain_dup_type")
    assert blueprint is not None
    assert blueprint.plugin_name == "contain-first"
    assert coord.get_session_blueprint("contain_other_type") is not None
    assert coord.get_plugin("contain-second") is not None


def test_exploding_blueprints_do_not_abort_registration():
    coord = _coordinator()
    bad = _ExplodingBlueprintPlugin()
    bad._plugin_meta = {"name": "contain-blueprint-bad"}
    good = _GoodPlugin()
    good._plugin_meta = {"name": "contain-blueprint-good"}

    coord.register_plugins([bad, good])
    assert coord.get_plugin("contain-blueprint-good") is good


def test_execute_command_rejects_private_names():
    coord = _coordinator()
    plugin = _GoodPlugin()
    plugin._plugin_meta = {"name": "contain-cmd"}
    coord.register_plugin(plugin)

    assert coord.execute_command("contain-cmd", "public_command") == "ok"
    with pytest.raises(AttributeError):
        coord.execute_command("contain-cmd", "_set_state")
    with pytest.raises(AttributeError):
        coord.execute_command("contain-cmd", "__class__")


def test_activate_requires_initialized_context():
    plugin = _GoodPlugin()
    plugin.activate()
    assert plugin._state is PluginState.CREATED

    plugin.initialize(object())
    plugin.activate()
    assert plugin._state is PluginState.ACTIVE


def test_import_guard_skips_bad_module():
    registry = PluginRegistry.__new__(PluginRegistry)
    # Must not raise for a module that cannot be imported at all.
    registry._import_plugin_module("plugins.nonexistent_broken_module_xyz")

    # A module that raises a non-ImportError at import time is also contained.
    mod = types.ModuleType("contain_broken_mod_xyz")
    mod.__path__ = []  # type: ignore[attr-defined]

    class _FailLoader:
        @staticmethod
        def exec_module(module):
            raise RuntimeError("boom at module top level")

    import importlib.abc
    import importlib.machinery

    class _Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "contain_broken_mod_xyz":
                loader = _FailLoader()
                return importlib.machinery.ModuleSpec(name, loader)
            return None

    finder = _Finder()
    sys.meta_path.insert(0, finder)
    try:
        registry._import_plugin_module("contain_broken_mod_xyz")
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("contain_broken_mod_xyz", None)
    assert "contain_broken_mod_xyz" not in sys.modules


def test_throwing_constructor_does_not_abort_discovery(monkeypatch):
    import core.plugin_system.registry as registry_mod

    class _ExplodingCtor(Plugin):
        _plugin_meta = {"name": "contain-ctor-bad", "startup_tier": "deferred"}

        def __init__(self):
            raise RuntimeError("boom in constructor")

        def initialize(self, context: Any) -> None:
            super().initialize(context)

    class _FineCtor(Plugin):
        _plugin_meta = {"name": "contain-ctor-good", "startup_tier": "deferred"}

        def initialize(self, context: Any) -> None:
            super().initialize(context)

    monkeypatch.setattr(
        registry_mod, "get_registered_plugins", lambda: (_ExplodingCtor, _FineCtor)
    )
    monkeypatch.setattr(
        registry_mod, "plugin_modules_for_tier", lambda tier: ()
    )
    registry = PluginRegistry.__new__(PluginRegistry)
    registry._plugins = {}
    registry._discovered_tiers = set()

    created = list(registry.discover_plugins(tier="deferred"))
    assert [p._plugin_meta["name"] for p in created] == ["contain-ctor-good"]
