from __future__ import annotations

from importlib import import_module

__all__ = ["ComparisonPlugin"]

def __getattr__(name: str):
    if name != "ComparisonPlugin":
        raise AttributeError(name)
    module = import_module("plugins.comparison.plugin")
    value = getattr(module, name)
    globals()[name] = value
    return value
