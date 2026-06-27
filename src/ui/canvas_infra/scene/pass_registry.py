from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

import ui.canvas_features as _features_pkg

from .pass_contract import CanvasRenderPassBase, CanvasRenderPass


@lru_cache(maxsize=1)
def get_canvas_render_passes() -> tuple[CanvasRenderPassBase, ...]:
    """Return all discovered feature GL render passes.

    Auto-discovers ``RENDER_PASSES`` lists from every
    ``ui.canvas_features.<name>.passes`` module that exists.
    Features that do not have a ``passes.py`` are silently skipped.
    """
    passes: list[CanvasRenderPassBase] = []
    for module_info in sorted(
        pkgutil.iter_modules(_features_pkg.__path__), key=lambda m: m.name
    ):
        if module_info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(
                f"{_features_pkg.__name__}.{module_info.name}.passes"
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
    for module_info in sorted(
        pkgutil.iter_modules(_features_pkg.__path__), key=lambda m: m.name
    ):
        if module_info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(
                f"{_features_pkg.__name__}.{module_info.name}.passes"
            )
        except ModuleNotFoundError:
            continue
        feature_passes = getattr(module, "RENDER_PASSES", None)
        if isinstance(feature_passes, (list, tuple)):
            passes.extend(feature_passes)
    return tuple(passes)
