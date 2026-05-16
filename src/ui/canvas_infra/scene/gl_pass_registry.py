from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

import ui.canvas_features as _features_pkg

from .gl_pass_contract import CanvasGLRenderPass

@lru_cache(maxsize=1)
def get_canvas_gl_render_passes() -> tuple[CanvasGLRenderPass, ...]:
    """Return all discovered feature GL render passes.

    Auto-discovers ``GL_RENDER_PASSES`` lists from every
    ``ui.canvas_features.<name>.gl_passes`` module that exists.
    Features that do not have a ``gl_passes.py`` are silently skipped.
    """
    passes: list[CanvasGLRenderPass] = []
    for module_info in sorted(
        pkgutil.iter_modules(_features_pkg.__path__), key=lambda m: m.name
    ):
        if module_info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(
                f"{_features_pkg.__name__}.{module_info.name}.gl_passes"
            )
        except ModuleNotFoundError:
            continue
        feature_passes = getattr(module, "GL_RENDER_PASSES", None)
        if isinstance(feature_passes, (list, tuple)):
            passes.extend(feature_passes)
    return tuple(passes)
