from __future__ import annotations

from importlib import import_module

__all__ = [
    "apply_store_to_gl_canvas",
    "build_live_store_presentation",
    "build_render_frame_presentation",
    "build_snapshot_store_presentation",
    "CanvasRenderPlan",
    "BaseImagePrimitive",
    "CaptureRingPrimitive",
    "DividerPrimitive",
    "FilenameOverlayPrimitive",
    "GuideLinePrimitive",
    "RenderIntent",
    "RenderList",
    "ResolvedCanvasStyle",
    "SceneFrame",
    "apply_canvas_render_plan",
    "apply_plan_runtime_overlays",
    "apply_render_plan_to_canvas",
    "build_canvas_plan",
    "compute_canvas_plan",
    "compute_content_layout",
    "CanvasContentLayout",
    "CanvasTarget",
    "PresentationImageSet",
    "RenderFramePresentation",
    "SnapshotStorePresentation",
]

_EXPORTS = {
    "apply_store_to_gl_canvas": ("ui.canvas_presentation.gl_surface", "apply_store_to_gl_canvas"),
    "compute_content_layout": ("ui.canvas_presentation.layout", "compute_content_layout"),
    "CanvasContentLayout": ("ui.canvas_presentation.models", "CanvasContentLayout"),
    "CanvasTarget": ("ui.canvas_presentation.models", "CanvasTarget"),
    "PresentationImageSet": ("ui.canvas_presentation.models", "PresentationImageSet"),
    "RenderFramePresentation": ("ui.canvas_presentation.models", "RenderFramePresentation"),
    "SnapshotStorePresentation": ("ui.canvas_presentation.models", "SnapshotStorePresentation"),
    "CanvasRenderPlan": ("ui.canvas_presentation.plan", "CanvasRenderPlan"),
    "BaseImagePrimitive": ("ui.canvas_presentation.render_arch", "BaseImagePrimitive"),
    "CaptureRingPrimitive": ("ui.canvas_presentation.render_arch", "CaptureRingPrimitive"),
    "DividerPrimitive": ("ui.canvas_presentation.render_arch", "DividerPrimitive"),
    "FilenameOverlayPrimitive": ("ui.canvas_presentation.render_arch", "FilenameOverlayPrimitive"),
    "GuideLinePrimitive": ("ui.canvas_presentation.render_arch", "GuideLinePrimitive"),
    "RenderIntent": ("ui.canvas_presentation.render_arch", "RenderIntent"),
    "RenderList": ("ui.canvas_presentation.render_arch", "RenderList"),
    "ResolvedCanvasStyle": ("ui.canvas_presentation.render_arch", "ResolvedCanvasStyle"),
    "SceneFrame": ("ui.canvas_presentation.render_arch", "SceneFrame"),
    "apply_canvas_render_plan": ("ui.canvas_presentation.plan_applicator", "apply_canvas_render_plan"),
    "apply_plan_runtime_overlays": ("ui.canvas_presentation.plan_applicator", "apply_plan_runtime_overlays"),
    "apply_render_plan_to_canvas": ("ui.canvas_presentation.plan_applicator", "apply_render_plan_to_canvas"),
    "build_canvas_plan": ("ui.canvas_presentation.plan_builder", "build_canvas_plan"),
    "build_live_store_presentation": ("ui.canvas_presentation.plan_builder", "build_live_store_presentation"),
    "build_render_frame_presentation": ("ui.canvas_presentation.plan_builder", "build_render_frame_presentation"),
    "build_snapshot_store_presentation": ("ui.canvas_presentation.plan_builder", "build_snapshot_store_presentation"),
    "compute_canvas_plan": ("ui.canvas_presentation.plan_builder", "compute_canvas_plan"),
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
