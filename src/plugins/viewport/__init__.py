from __future__ import annotations

from importlib import import_module

__all__ = ["ViewportPlugin"]

def __getattr__(name: str):
    if name != "ViewportPlugin":
        raise AttributeError(name)
    module = import_module("plugins.viewport.plugin")
    value = getattr(module, name)
    globals()[name] = value
    return value
