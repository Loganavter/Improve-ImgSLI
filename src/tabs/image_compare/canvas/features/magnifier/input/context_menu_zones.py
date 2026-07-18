"""Magnifier context-menu suppression zones.

Declares territory where the host must not open a slot/image context menu.
Shared canvas code walks these via ``context_menu_zones.is_context_menu_suppressed``
— no magnifier literals in the canvas widget.
"""

from __future__ import annotations

from domain.types import Point
from ui.canvas_infra.scene.context_menu_zones import ContextMenuHitContext
from ui.canvas_infra.scene.widget_contract import CanvasFeatureContextMenuZone

from tabs.image_compare.canvas.features.magnifier.geometry.hit_test import (
    find_magnifier_at_position,
)
from tabs.image_compare.canvas.features.magnifier.scene.objects import MagnifierSceneObject


def _scene_from_canvas(canvas) -> object | None:
    state = getattr(canvas, "runtime_state", None)
    return getattr(state, "_canvas_scene_graph", None) if state is not None else None


def _suppresses_combined_overlay(ctx: ContextMenuHitContext) -> bool:
    """Combined magnifier overlay owns RMB for internal-split drag — no host menu."""
    scene = _scene_from_canvas(ctx.canvas)
    if scene is None:
        return False
    pos = ctx.local_pos
    point = Point(float(pos.x()), float(pos.y()))
    match = find_magnifier_at_position(scene, point)
    return (
        isinstance(match, MagnifierSceneObject)
        and bool(match.is_combined)
        and bool(getattr(match, "visible", True))
    )


def build_magnifier_context_menu_zones() -> tuple[CanvasFeatureContextMenuZone, ...]:
    return (
        CanvasFeatureContextMenuZone(
            zone_id="magnifier.combined_overlay",
            suppresses=_suppresses_combined_overlay,
            priority=10,
            owner="magnifier",
        ),
    )
