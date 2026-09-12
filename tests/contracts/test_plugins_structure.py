"""Plugin structural dogma.

Each plugin folder under ``src/plugins/`` must:
  * have a ``plugin.py`` entry point
  * use ``@plugin(name="...")`` decorator
  * inherit ``Plugin`` from ``core.plugin_system``
  * decorator name matches folder name (and is unique across plugins)

Dogma source: docs/dev/ARCHITECTURE.md (Plugins section) + core/plugin_system
contract.
"""

from __future__ import annotations

import re

import pytest

from ._framework import list_plugins, read, rel

PLUGINS = list_plugins()
PLUGIN_IDS = [p.name for p in PLUGINS]

_DECORATOR_NAME_RE = re.compile(
    r"@plugin\s*\(\s*name\s*=\s*['\"]([^'\"]+)['\"]"
)

@pytest.mark.parametrize("plugin", PLUGINS, ids=PLUGIN_IDS)
def test_plugin_has_entry_point(plugin):
    assert (plugin / "plugin.py").exists(), (
        f"plugin '{plugin.name}' must have a plugin.py entry point at "
        f"{rel(plugin)}"
    )

@pytest.mark.parametrize("plugin", PLUGINS, ids=PLUGIN_IDS)
def test_plugin_uses_decorator_and_base(plugin):
    plugin_py = plugin / "plugin.py"
    if not plugin_py.exists():
        pytest.skip("no plugin.py")
    text = read(plugin_py)
    assert "@plugin" in text, (
        f"plugin '{plugin.name}' must use @plugin(...) decorator"
    )
    assert "Plugin" in text and "core.plugin_system" in text, (
        f"plugin '{plugin.name}' must import Plugin from core.plugin_system"
    )

@pytest.mark.parametrize("plugin", PLUGINS, ids=PLUGIN_IDS)
def test_plugin_decorator_name_matches_folder(plugin):
    plugin_py = plugin / "plugin.py"
    if not plugin_py.exists():
        pytest.skip("no plugin.py")
    m = _DECORATOR_NAME_RE.search(read(plugin_py))
    assert m is not None, (
        f"plugin '{plugin.name}' @plugin decorator must declare name="
    )
    assert m.group(1) == plugin.name, (
        f"plugin folder '{plugin.name}' declares name='{m.group(1)}'"
    )

def test_plugin_names_are_unique():
    seen: dict[str, str] = {}
    dups: list[str] = []
    for plugin in PLUGINS:
        plugin_py = plugin / "plugin.py"
        if not plugin_py.exists():
            continue
        m = _DECORATOR_NAME_RE.search(read(plugin_py))
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            dups.append(f"'{name}' in {plugin.name} and {seen[name]}")
        else:
            seen[name] = plugin.name
    assert not dups, "duplicate plugin names: " + "; ".join(dups)
