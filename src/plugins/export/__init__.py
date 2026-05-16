from __future__ import annotations

from importlib import import_module

__all__ = ["ExportPlugin"]

def __getattr__(name: str):
    if name != "ExportPlugin":
        raise AttributeError(name)
    module = import_module("plugins.export.plugin")
    value = getattr(module, name)
    globals()[name] = value
    return value
