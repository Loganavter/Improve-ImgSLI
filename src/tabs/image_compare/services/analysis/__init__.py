from __future__ import annotations

from importlib import import_module

__all__ = [
    "AnalysisRuntime",
    "CachedDiffService",
    "CoreUpdateDispatcher",
    "MetricsService",
    "UIUpdateDispatcher",
]

_PKG = "tabs.image_compare.services.analysis"

_EXPORTS = {
    "CachedDiffService": (f"{_PKG}.cached_diff", "CachedDiffService"),
    "MetricsService": (f"{_PKG}.metrics", "MetricsService"),
    "AnalysisRuntime": (f"{_PKG}.runtime", "AnalysisRuntime"),
    "CoreUpdateDispatcher": (f"{_PKG}.runtime", "CoreUpdateDispatcher"),
    "UIUpdateDispatcher": (f"{_PKG}.runtime", "UIUpdateDispatcher"),
}

def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
