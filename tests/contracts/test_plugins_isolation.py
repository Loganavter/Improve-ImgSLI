"""Plugin isolation dogma.

  * a plugin must NOT import a canvas feature directly
  * a plugin must NOT reach into another plugin's internals
    (controller / presenter / state / dialog) — cross-plugin communication
    goes via events / services / plugin_coordinator

Dogma source: docs/dev/CANVAS_FEATURES.md (no feature imports in plugins/)
and docs/dev/ARCHITECTURE.md (plugin decoupling).
"""

from __future__ import annotations

import re

import pytest

from ._framework import iter_py, list_plugins, module_imports, rel

PLUGINS = list_plugins()
PLUGIN_IDS = [p.name for p in PLUGINS]

_CANVAS_FEATURE_RE = re.compile(
    r"(?:src\.)?ui\.canvas_features\.([a-zA-Z_]\w*)"
)
_CROSS_PLUGIN_RE = re.compile(r"plugins\.([^.]+)\.(.+)")
_FORBIDDEN_INTERNALS = ("controller", "presenter", "state", "dialog")

@pytest.mark.parametrize("plugin", PLUGINS, ids=PLUGIN_IDS)
def test_plugin_does_not_import_canvas_features_directly(plugin):
    leaks: list[str] = []
    for py in iter_py(plugin):
        for module, lineno in module_imports(py):
            m = _CANVAS_FEATURE_RE.match(module)
            if m and not m.group(1).startswith("_"):
                leaks.append(
                    f"{rel(py)}:{lineno} imports canvas feature "
                    f"'{m.group(1)}' (use capability aliases)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)

@pytest.mark.parametrize("plugin", PLUGINS, ids=PLUGIN_IDS)
def test_plugin_does_not_import_other_plugins_internals(plugin):
    leaks: list[str] = []
    for py in iter_py(plugin):
        for module, lineno in module_imports(py):
            m = _CROSS_PLUGIN_RE.match(module)
            if not m:
                continue
            other, tail = m.group(1), m.group(2)
            if other == plugin.name:
                continue
            head = tail.split(".")[0]
            if head in _FORBIDDEN_INTERNALS:
                leaks.append(
                    f"{rel(py)}:{lineno} imports '{head}' of plugin "
                    f"'{other}' (use events/services/coordinator)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)
