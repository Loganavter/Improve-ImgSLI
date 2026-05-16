from __future__ import annotations

from importlib import import_module

__all__ = [
    "AnalysisRuntime",
    "CachedDiffService",
    "CoreUpdateDispatcher",
    "MetricsService",
    "UIUpdateDispatcher",
]

_EXPORTS = {
    "CachedDiffService": ("plugins.analysis.services.cached_diff", "CachedDiffService"),
    "MetricsService": ("plugins.analysis.services.metrics", "MetricsService"),
    "AnalysisRuntime": ("plugins.analysis.services.runtime", "AnalysisRuntime"),
    "CoreUpdateDispatcher": ("plugins.analysis.services.runtime", "CoreUpdateDispatcher"),
    "UIUpdateDispatcher": ("plugins.analysis.services.runtime", "UIUpdateDispatcher"),
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
