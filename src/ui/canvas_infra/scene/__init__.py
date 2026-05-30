from __future__ import annotations

_EXPORT_MODULES = {
    "CanvasSceneApplyContext": ".context",
    "CanvasSceneBuildContext": ".context",
    "CanvasFeatureZOrder": ".feature_contract",
    "CanvasSceneFeature": ".feature_contract",
    "CanvasSceneObject": ".models",
    "CanvasSceneGraph": ".models",
    "CanvasStackHint": ".stacking",
    "CanvasStackLayer": ".stacking",
    "CanvasStackRole": ".stacking",
    "SCENE_APPLIERS": ".pipeline",
    "SCENE_HIT_TESTERS": ".pipeline",
    "SCENE_OVERLAY_BUILDERS": ".pipeline",
    "SCENE_PRIMARY_BUILDERS": ".pipeline",
    "apply_scene_to_canvas": ".apply",
    "build_canvas_scene": ".builder",
    "find_scene_object_at_position": ".hit_test",
    "get_canvas_scene_features": ".feature_registry",
    "resolve_pick_order": ".stacking",
    "resolve_render_order": ".stacking",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module = import_module(module_name, __name__)
    return getattr(module, name)
