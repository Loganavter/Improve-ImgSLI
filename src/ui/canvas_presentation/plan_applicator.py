from __future__ import annotations

from .composition import CompositionPlan, resolve_composition
from .plan import CanvasRenderPlan


def _call_tab_canvas_service(service_id: str, *args, **kwargs):
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    return registry.create_service(service_id, *args, **kwargs)


def apply_plan_runtime_overlays(canvas, plan: CanvasRenderPlan) -> None:
    """Compatibility wrapper; the active tab owns plan/runtime overlay behavior."""
    return _call_tab_canvas_service("canvas_plan_runtime_overlays", canvas, plan)


def _sync_geometry_state(canvas, store) -> None:
    """Compatibility wrapper; the active tab owns geometry-state synchronization."""
    return _call_tab_canvas_service("canvas_sync_geometry_state", canvas, store)


def apply_canvas_render_plan(
    canvas,
    plan: CanvasRenderPlan,
    *,
    store=None,
    clip_overlays_to_image_bounds: bool = False,
) -> None:
    """
    Unified canvas configurator.

    Composition plans are resolved in the shared presentation layer. Legacy
    image-compare render-plan application belongs to the image_compare tab and
    is reached through a tab service boundary.
    """
    if plan.composition_root is not None:
        _apply_composition_plan(canvas, plan)
        return
    _call_tab_canvas_service(
        "canvas_legacy_render_plan",
        canvas,
        plan,
        store=store,
        clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
    )


def apply_render_plan_to_canvas(canvas, plan: CanvasRenderPlan) -> None:
    """Snapshot / export / preview path: thin wrapper around apply_canvas_render_plan."""
    apply_canvas_render_plan(canvas, plan)


def _apply_composition_plan(canvas, plan: CanvasRenderPlan) -> None:
    """Resolve the composition tree and stash it on the canvas.

    Composition-aware backends read ``canvas._active_composition`` and dispatch
    their own draw calls.
    """
    composition = plan.composition_plan
    if composition is None:
        composition = CompositionPlan(
            root=plan.composition_root,
            canvas_w=int(plan.canvas_w),
            canvas_h=int(plan.canvas_h),
            fill_rgba=plan.fill_rgba,
        )
    resolved = resolve_composition(composition)
    canvas._active_render_plan = plan
    canvas._active_composition = resolved
