from __future__ import annotations

from importlib import import_module

__all__ = [
    "CanvasRenderPlan",
    "RenderIntent",
    "apply_canvas_render_plan",
    "apply_plan_runtime_overlays",
    "apply_render_plan_to_canvas",
    "compute_content_layout",
    "CanvasContentLayout",
    "CanvasTarget",
    "PresentationImageSet",
    "RenderFramePresentation",
    "SnapshotStorePresentation",
]

_EXPORTS = {
    "compute_content_layout": ("ui.canvas_presentation.layout", "compute_content_layout"),
    "CanvasContentLayout": ("ui.canvas_presentation.models", "CanvasContentLayout"),
    "CanvasTarget": ("ui.canvas_presentation.models", "CanvasTarget"),
    "PresentationImageSet": ("ui.canvas_presentation.models", "PresentationImageSet"),
    "RenderFramePresentation": ("ui.canvas_presentation.models", "RenderFramePresentation"),
    "SnapshotStorePresentation": ("ui.canvas_presentation.models", "SnapshotStorePresentation"),
    "CanvasRenderPlan": ("ui.canvas_presentation.plan", "CanvasRenderPlan"),
    "RenderIntent": ("ui.canvas_presentation.render_arch", "RenderIntent"),
    "apply_canvas_render_plan": ("ui.canvas_presentation.plan_applicator", "apply_canvas_render_plan"),
    "apply_plan_runtime_overlays": ("ui.canvas_presentation.plan_applicator", "apply_plan_runtime_overlays"),
    "apply_render_plan_to_canvas": ("ui.canvas_presentation.plan_applicator", "apply_render_plan_to_canvas"),
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
