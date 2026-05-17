from __future__ import annotations

from ui.canvas_infra.scene.gl_pass_contract import RenderPhase

PHASE_ORDER: tuple[RenderPhase, ...] = (
    RenderPhase.IMAGE_DECORATION,
    RenderPhase.IMAGE_ANNOTATION,
    RenderPhase.VIEW_ANNOTATION,
    RenderPhase.HUD,
    RenderPhase.DEBUG,
)

def _pass_sort_key(pass_) -> tuple[int, int, int]:
    """Return a sort key using the central stacking policy when available."""
    resolve = getattr(pass_, "resolved_layer_and_priority", None)
    if resolve is not None:
        phase, priority = resolve()
    else:
        phase = getattr(pass_, "layer", RenderPhase.VIEW_ANNOTATION)
        priority = getattr(pass_, "priority", 100)

    try:
        phase_idx = PHASE_ORDER.index(phase)
    except ValueError:
        phase_idx = len(PHASE_ORDER)
    return (phase_idx, int(phase), int(priority))

def iter_ordered_render_passes(passes) -> tuple:
    return tuple(sorted(passes, key=_pass_sort_key))

def execute_render_passes(widget, ctx, passes) -> None:
    is_single_preview = getattr(getattr(ctx, "scene_frame", None), "single_image_preview", False)
    for pass_ in iter_ordered_render_passes(passes):
        if is_single_preview and getattr(pass_, "hide_in_single_preview", True):
            continue
        if pass_.should_paint(ctx):
            pass_.paint(widget, ctx)
