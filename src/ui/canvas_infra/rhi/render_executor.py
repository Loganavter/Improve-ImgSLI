from __future__ import annotations

from ui.canvas_infra.scene.pass_contract import RenderPhase, SceneVisibility
from ui.canvas_infra.rhi.render_common import should_render_blank_white

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
    render_metrics = (
        getattr(metrics, "render_metrics", None) if metrics is not None else None
    )
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
    for pass_ in iter_active_render_passes(ctx, passes):
        pass_.paint(widget, ctx)


def iter_active_render_passes(ctx, passes) -> tuple:
    current_visibility = _resolve_scene_visibility(ctx)
    blank_white = should_render_blank_white(getattr(ctx, "scene_frame", None))
    active = []
    for pass_ in iter_ordered_render_passes(passes):
        if not _visibility_matches(
            getattr(pass_, "visibility", SceneVisibility.ALL),
            current_visibility,
        ):
            continue
        if blank_white and getattr(pass_, "requires_content", True):
            continue
        if pass_.should_paint(ctx):
            active.append(pass_)
    return tuple(active)


def _visibility_matches(pass_visibility, current_visibility: SceneVisibility) -> bool:
    """True when a pass declaring *pass_visibility* paints in *current_visibility*.

    Both sides must be ``SceneVisibility`` flags: a wrong-typed value raises
    ``TypeError`` from ``&`` instead of silently matching by member name. A
    name-string fallback made ``_visibility_matches("interactive", PREVIEW)``
    return a verdict, so a caller that passed a string (or a list, or ``None``)
    painted or skipped every frame without an error — the wrong frame, on the
    user, instead of a failure at the seam.
    """
    return bool(pass_visibility & current_visibility)