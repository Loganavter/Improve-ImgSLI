"""Resolve host context-menu suppression against feature-declared zones.

Shared canvas code must not branch on feature-specific geometry when deciding
whether a right-click may open a slot/image context menu. Features declare
``CanvasFeatureContextMenuZone`` entries via
``WIDGET_FEATURE.build_context_menu_zones``; this module walks them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .registry import get_canvas_registry
from .widget_contract import CanvasFeatureContextMenuZone


@dataclass(frozen=True, slots=True)
class ContextMenuHitContext:
    store: Any
    canvas: Any
    local_pos: Any
    session_type: str | None


def get_feature_context_menu_zones(
    session_type: str | None,
) -> tuple[CanvasFeatureContextMenuZone, ...]:
    return get_canvas_registry(session_type).get_feature_context_menu_zones()


def is_context_menu_suppressed(ctx: ContextMenuHitContext) -> bool:
    for zone in get_feature_context_menu_zones(ctx.session_type):
        try:
            if zone.suppresses(ctx):
                return True
        except Exception:
            continue
    return False
