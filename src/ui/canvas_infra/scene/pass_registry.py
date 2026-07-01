from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from types import ModuleType

from .pass_contract import CanvasRenderPassBase, CanvasRenderPass

_FEATURE_PACKAGES: list[ModuleType] = []


def register_canvas_render_pass_feature_package(package: ModuleType) -> None:
    if package not in _FEATURE_PACKAGES:
        _FEATURE_PACKAGES.append(package)
        get_canvas_render_passes.cache_clear()

@lru_cache(maxsize=1)
def get_canvas_render_pass_bases() -> tuple[CanvasRenderPassBase, ...]:
    """Return all discovered feature GL render passes.

    Auto-discovers ``RENDER_PASSES`` lists from registered tab feature
    packages. Features that do not have a ``passes.py`` are silently skipped.
    """
    passes: list[CanvasRenderPassBase] = []
    for features_pkg in _FEATURE_PACKAGES:
        for module_info in sorted(
            pkgutil.iter_modules(features_pkg.__path__), key=lambda m: m.name
        ):
            if module_info.name.startswith("_"):
                continue
            try:
                module = importlib.import_module(
                    f"{features_pkg.__name__}.{module_info.name}.passes"
                )
            except ModuleNotFoundError:
                continue
            feature_passes = getattr(module, "RENDER_PASSES", None)
            if isinstance(feature_passes, (list, tuple)):
                passes.extend(feature_passes)
    return tuple(passes)


@lru_cache(maxsize=1)
def get_canvas_render_passes() -> tuple[CanvasRenderPass, ...]:
    """Return feature passes that have completed their QRhi port."""
    passes: list[CanvasRenderPass] = []
    for features_pkg in _FEATURE_PACKAGES:
        for module_info in sorted(
            pkgutil.iter_modules(features_pkg.__path__), key=lambda m: m.name
        ):
            if module_info.name.startswith("_"):
                continue
            try:
                module = importlib.import_module(
                    f"{features_pkg.__name__}.{module_info.name}.passes"
                )
            except ModuleNotFoundError:
                continue
            feature_passes = getattr(module, "RENDER_PASSES", None)
            if isinstance(feature_passes, (list, tuple)):
                passes.extend(feature_passes)
    return tuple(passes)
