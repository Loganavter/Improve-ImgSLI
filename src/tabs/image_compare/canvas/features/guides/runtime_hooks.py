from __future__ import annotations

from typing import Any

from domain.qt_adapters import color_to_qcolor

from .state import get_guides_widget_state


def build_guides_render_scene_overrides(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {}
    state = get_guides_widget_state(viewport.view_state)
    return {
        "laser_color": color_to_qcolor(state.color),
        "guides_thickness": int(state.thickness),
        "optimize_laser_smoothing": bool(state.smoothing_enabled),
    }
