from __future__ import annotations

from importlib import import_module

__all__ = ["AnalysisPlugin"]

def __getattr__(name: str):
    if name != "AnalysisPlugin":
        raise AttributeError(name)
    module = import_module("plugins.analysis.plugin")
    value = getattr(module, name)
    globals()[name] = value
    return value
