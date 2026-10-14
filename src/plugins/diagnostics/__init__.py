"""Local-first diagnostics / crash-report plugin.

Builds a redacted report of an unhandled failure (or on demand) and lets the
user **Copy / Save… / Open issue**. Nothing is uploaded automatically — see
``docs/dev/PLUGINS.md`` and the plugin ``plugin.py`` docstring.
"""

from __future__ import annotations

from importlib import import_module

__all__ = ["DiagnosticsPlugin"]


def __getattr__(name: str):
    if name != "DiagnosticsPlugin":
        raise AttributeError(name)
    module = import_module("plugins.diagnostics.plugin")
    value = getattr(module, name)
    globals()[name] = value
    return value
