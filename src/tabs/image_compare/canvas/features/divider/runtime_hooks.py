from __future__ import annotations

from typing import Any

from domain.qt_adapters import color_to_qcolor

from tabs.image_compare.canvas.features.divider.state.feature_state import get_divider_widget_state


def build_divider_render_scene_overrides(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {}
    view = viewport.view_state
    divider_state = get_divider_widget_state(view)
    diff_mode = str(getattr(view, "diff_mode", "off") or "off")
    single_image_mode = int(getattr(view, "showing_single_image_mode", 0) or 0)
    return {
        "show_divider": bool(
            divider_state.visible and diff_mode == "off" and single_image_mode == 0
        ),
        "divider_color": color_to_qcolor(divider_state.color),
        "divider_thickness": int(divider_state.thickness),
        "filename_divider_thickness": int(divider_state.thickness),
    }
