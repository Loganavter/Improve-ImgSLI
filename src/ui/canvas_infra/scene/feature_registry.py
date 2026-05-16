from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

import ui.canvas_features as features_pkg

from .feature_contract import CanvasSceneFeature

@lru_cache(maxsize=1)
def get_canvas_scene_features() -> tuple[CanvasSceneFeature, ...]:
    features: list[CanvasSceneFeature] = []
    for module_info in sorted(pkgutil.iter_modules(features_pkg.__path__), key=lambda item: item.name):
        if module_info.name.startswith("_"):
            continue
        module = None
        try:
            module = importlib.import_module(
                f"{features_pkg.__name__}.{module_info.name}.manifest"
            )
        except ModuleNotFoundError as exc:
            if exc.name != f"{features_pkg.__name__}.{module_info.name}.manifest":
                raise
        if module is None:
            try:
                module = importlib.import_module(
                    f"{features_pkg.__name__}.{module_info.name}.feature"
                )
            except ModuleNotFoundError as exc:
                if exc.name == f"{features_pkg.__name__}.{module_info.name}.feature":
                    continue
                raise
        feature = getattr(module, "FEATURE", None)
        if isinstance(feature, CanvasSceneFeature):
            features.append(feature)
    return tuple(features)
