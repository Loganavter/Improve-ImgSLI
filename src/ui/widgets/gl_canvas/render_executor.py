from __future__ import annotations

from ui.canvas_infra.scene.gl_pass_contract import RenderPhase, SceneVisibility

PHASE_ORDER: tuple[RenderPhase, ...] = (
    RenderPhase.IMAGE_DECORATION,
    RenderPhase.IMAGE_ANNOTATION,
    RenderPhase.VIEW_ANNOTATION,
    RenderPhase.HUD,
    RenderPhase.DEBUG,
)

def _pass_sort_key(pass_) -> tuple[int, int, int]:
    """Return a sort key using the central stacking policy."""
    phase, priority = pass_.resolved_layer_and_priority()

    try:
        phase_idx = PHASE_ORDER.index(phase)
    except ValueError:
        phase_idx = len(PHASE_ORDER)
    return (phase_idx, int(phase), int(priority))

def iter_ordered_render_passes(passes) -> tuple:
    return tuple(sorted(passes, key=_pass_sort_key))

def _resolve_scene_visibility(ctx) -> SceneVisibility:
    metrics = getattr(ctx, "metrics", None)
    render_metrics = getattr(metrics, "render_metrics", None) if metrics is not None else None
    mode = str(
        getattr(render_metrics, "mode", None)
        or getattr(getattr(ctx, "render_metrics", None), "mode", None)
        or getattr(getattr(ctx, "render_intent", None), "kind", None)
        or "preview"
    )
    if mode == "interactive":
        return SceneVisibility.INTERACTIVE
    if mode == "export":
        return SceneVisibility.EXPORT
    return SceneVisibility.PREVIEW

def execute_render_passes(widget, ctx, passes) -> None:
    current_visibility = _resolve_scene_visibility(ctx)
    for pass_ in iter_ordered_render_passes(passes):
        if not (getattr(pass_, "visibility", SceneVisibility.ALL) & current_visibility):
            continue
        if pass_.should_paint(ctx):
            pass_.paint(widget, ctx)
