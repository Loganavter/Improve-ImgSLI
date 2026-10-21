"""
Central stacking policy for the canvas scene system.

This module is the SINGLE source of truth for all stacking order decisions.
Features declare a semantic ``CanvasStackRole`` instead of hardcoding numeric
layer/priority pairs.  The policy resolves roles to concrete ordering for:

- QRhi render passes (role -> RenderPhase, priority)
- Scene objects      (role -> CanvasStackLayer, priority)

To change the draw order of any element, edit the tables in this module.
Feature code should never contain raw stacking numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from .pass_contract import RenderPhase

class CanvasStackLayer(IntEnum):
    ALWAYS_BOTTOM = 0
    UNDERLAY = 10
    OBJECT = 20
    OBJECT_ACTIVE = 30
    OVERLAY = 40
    FOREGROUND = 50
    HUD = 60
    DEBUG = 70
    ALWAYS_TOP = 100

class CanvasStackRole(IntEnum):
    """
    Semantic roles for canvas elements.

    Every QRhi render pass and scene object should declare one of these roles
    instead of a raw ``(layer, priority)`` pair.  The central policy tables
    below map roles to concrete ordering.
    """

    UNDERLAY_SPLIT = 10
    IMAGE_OVERLAY_FRAME = 15
    IMAGE_OVERLAY_CONTENT = 20
    ANNOTATION_RING = 30
    ANNOTATION_BORDER = 35
    ANNOTATION_GUIDE = 40
    HUD_LABEL = 50
    TRANSIENT_PREVIEW = 55
    HUD_INTERACTION_OVERLAY = 57
    INTERACTION_HANDLE = 60
    DEBUG_VIS = 70

_RENDER_PASS_ORDER: dict[CanvasStackRole, tuple[RenderPhase, int]] = {
    CanvasStackRole.UNDERLAY_SPLIT:        (RenderPhase.IMAGE_DECORATION, 10),
    CanvasStackRole.ANNOTATION_GUIDE:      (RenderPhase.IMAGE_ANNOTATION, 60),
    CanvasStackRole.ANNOTATION_RING:       (RenderPhase.IMAGE_ANNOTATION, 70),
    CanvasStackRole.IMAGE_OVERLAY_FRAME:   (RenderPhase.IMAGE_ANNOTATION, 90),
    CanvasStackRole.IMAGE_OVERLAY_CONTENT: (RenderPhase.IMAGE_ANNOTATION, 100),
    CanvasStackRole.ANNOTATION_BORDER:     (RenderPhase.VIEW_ANNOTATION, 15),
    CanvasStackRole.HUD_LABEL:             (RenderPhase.HUD, 100),
    CanvasStackRole.TRANSIENT_PREVIEW:     (RenderPhase.HUD, 50),
    CanvasStackRole.HUD_INTERACTION_OVERLAY: (RenderPhase.HUD, 150),
    CanvasStackRole.INTERACTION_HANDLE:    (RenderPhase.VIEW_ANNOTATION, 50),
    CanvasStackRole.DEBUG_VIS:             (RenderPhase.DEBUG, 10),
}


def resolve_render_pass_order(role: CanvasStackRole) -> tuple[RenderPhase, int]:
    """Resolve a semantic role to concrete ``(RenderPhase, priority)``.

    ``__getitem__``, deliberately: a member without a row must raise
    ``KeyError`` at the first frame instead of drawing at a silent default
    (a default hides a missing declaration forever — see the C1 gate).
    """
    return _RENDER_PASS_ORDER[role]


_SCENE_OBJECT_ORDER: dict[CanvasStackRole, tuple[CanvasStackLayer, int]] = {
    CanvasStackRole.UNDERLAY_SPLIT:        (CanvasStackLayer.UNDERLAY, 0),
    CanvasStackRole.ANNOTATION_GUIDE:      (CanvasStackLayer.OBJECT, -20),
    CanvasStackRole.ANNOTATION_RING:       (CanvasStackLayer.OBJECT, -10),
    CanvasStackRole.IMAGE_OVERLAY_FRAME:   (CanvasStackLayer.OBJECT, -5),
    CanvasStackRole.IMAGE_OVERLAY_CONTENT: (CanvasStackLayer.OBJECT, 0),
    CanvasStackRole.ANNOTATION_BORDER:     (CanvasStackLayer.OVERLAY, 5),
    CanvasStackRole.HUD_LABEL:             (CanvasStackLayer.HUD, 0),
    CanvasStackRole.HUD_INTERACTION_OVERLAY: (CanvasStackLayer.HUD, 10),
    CanvasStackRole.TRANSIENT_PREVIEW:     (CanvasStackLayer.FOREGROUND, 0),
    CanvasStackRole.INTERACTION_HANDLE:    (CanvasStackLayer.FOREGROUND, 10),
    CanvasStackRole.DEBUG_VIS:             (CanvasStackLayer.DEBUG, 0),
}


def resolve_scene_object_order(role: CanvasStackRole) -> tuple[CanvasStackLayer, int]:
    """Resolve a semantic role to concrete ``(CanvasStackLayer, priority)``.

    ``__getitem__``, deliberately: a member without a row must raise
    ``KeyError`` at the first frame instead of sharing the default pair with
    ``IMAGE_OVERLAY_CONTENT`` (the collision this wave removed).
    """
    return _SCENE_OBJECT_ORDER[role]


@dataclass(frozen=True)
class CanvasStackHint:
    layer: CanvasStackLayer = CanvasStackLayer.OBJECT
    priority: int = 0
    always_on_top: bool = False
    always_on_bottom: bool = False
    selectable_when_hidden: bool = False
    active_bias: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)
