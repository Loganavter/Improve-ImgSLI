"""Legacy render-plan application call surface (thin owner).

Whole-owner rule (engine-migration C3): the implementation lives in
``engine.cache.display_tier_service`` (legacy-plan impl); this module keeps
same-signature thin delegators that bind the tab collaborators (feature
registry, render-scene builder, first-frame debug, Store action
construction) into hook bundles. No logic lives here — service entry
points and the preview-contract monkeypatch surface (``registry``,
``_setup_store_bindings``, ``_apply_overlays``, ``_resolve_clip_flag``)
keep their import paths while the single live implementation sits behind
the service boundary.
"""

from __future__ import annotations

from engine.cache import display_tier_service as _service
from engine.cache.display_tier_service import (
    LegacyPlanHooks,
    LegacyPlanSteps,
)
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.canvas.scene import build_render_scene
from tabs.image_compare.first_frame_debug import ic_first_frame_debug


def _tier_hooks():
    from tabs.image_compare.canvas.texture_parts.base_images import tier_hooks

    return tier_hooks()


def _make_geometry_actions(cw: int, ch: int, cx: int, cy: int) -> list:
    """Construct (not dispatch) the Store geometry actions (tab adaptation)."""
    from core.state_management.geometry_actions import (
        SetImageDisplayRectAction,
        SetPixmapDimensionsAction,
    )
    from domain.types import Rect

    return [
        SetPixmapDimensionsAction(width=cw, height=ch),
        SetImageDisplayRectAction(rect=Rect(cx, cy, cw, ch)),
    ]


def _commit_geometry_attrs(geometry_state, cw: int, ch: int, cx: int, cy: int) -> None:
    """Dispatch-failure fallback (tab adaptation — Store-owned setattr)."""
    from domain.types import Rect

    setattr(geometry_state, "pixmap_width", cw)
    setattr(geometry_state, "pixmap_height", ch)
    setattr(geometry_state, "image_display_rect_on_label", Rect(cx, cy, cw, ch))


def _plan_hooks() -> LegacyPlanHooks:
    reg = registry  # read the module global per call so tab tests can monkeypatch it
    return LegacyPlanHooks(
        debug=lambda canvas, msg, *args: ic_first_frame_debug(canvas, msg, *args),
        tier=_tier_hooks(),
        apply_feature_plan_runtime_overlays=lambda canvas, plan: reg().apply_feature_plan_runtime_overlays(
            canvas, plan
        ),
        apply_feature_live_runtime_overlays=lambda store, canvas: reg().apply_feature_live_runtime_overlays(
            store, canvas
        ),
        get_feature_command=lambda alias: reg().get_feature_command_by_alias(alias),
        build_render_scene=lambda store, **kwargs: build_render_scene(store, **kwargs),
        make_geometry_actions=_make_geometry_actions,
        commit_geometry_attrs=_commit_geometry_attrs,
    )


def _plan_steps() -> LegacyPlanSteps:
    # Lazy global resolution so monkeypatching this module's step functions
    # keeps intercepting the full/scene-only paths (preview contracts).
    return LegacyPlanSteps(
        resolve_clip_flag=lambda *args: _resolve_clip_flag(*args),
        setup_store_bindings=lambda *args, **kwargs: _setup_store_bindings(
            *args, **kwargs
        ),
        apply_overlays=lambda *args, **kwargs: _apply_overlays(*args, **kwargs),
    )


def _refresh_live_content_rect(canvas, state, plan) -> None:
    return _service.refresh_live_content_rect(canvas, state, plan)


def _compute_inner_content_rect(state, plan):
    return _service.compute_inner_content_rect(state, plan)


def _apply_plan_letterbox_from_clip(canvas, plan) -> None:
    return _service.apply_plan_letterbox_from_clip(canvas, plan)


def apply_plan_runtime_overlays(canvas, plan) -> None:
    return _service.apply_plan_runtime_overlays(canvas, plan, hooks=_plan_hooks())


def sync_geometry_state(canvas, store) -> None:
    return _service.sync_geometry_state(canvas, store, hooks=_plan_hooks())


def _resolve_clip_flag(store, clip_overlays_to_image_bounds: bool, plan) -> bool:
    return _service.resolve_clip_flag(store, clip_overlays_to_image_bounds, plan)


def _setup_store_bindings(canvas, plan, *, store, clip_flag: bool) -> None:
    return _service.setup_store_bindings(
        canvas, plan, store=store, clip_flag=clip_flag, hooks=_plan_hooks()
    )


def _apply_overlays(canvas, plan, *, store) -> None:
    return _service.apply_overlays(canvas, plan, store=store, hooks=_plan_hooks())


def apply_canvas_render_plan(
    canvas,
    plan,
    *,
    store=None,
    clip_overlays_to_image_bounds: bool = False,
) -> None:
    return _service.apply_canvas_render_plan(
        canvas,
        plan,
        store=store,
        clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
        hooks=_plan_hooks(),
        steps=_plan_steps(),
    )


def _apply_plan_full(
    canvas,
    plan,
    *,
    store,
    clip_overlays_to_image_bounds: bool,
) -> None:
    return _service.apply_plan_full(
        canvas,
        plan,
        store=store,
        clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
        hooks=_plan_hooks(),
        steps=_plan_steps(),
    )


def _apply_plan_scene_only(
    canvas,
    plan,
    *,
    store,
    clip_overlays_to_image_bounds: bool,
) -> None:
    return _service.apply_plan_scene_only(
        canvas,
        plan,
        store=store,
        clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
        hooks=_plan_hooks(),
        steps=_plan_steps(),
    )
