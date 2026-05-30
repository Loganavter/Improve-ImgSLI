from __future__ import annotations

from core.store import Store
from plugins.video_editor.services.video_export_models import GlobalCanvasBounds
from shared.rendering import NormalizedBounds, resolve_virtual_canvas_layout
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_commands_by_id


def calculate_still_snapshot_bounds(snap, image1, image2) -> GlobalCanvasBounds:
    base_w = max(
        1,
        int(getattr(image1, "width", 0) or 0),
        int(getattr(image2, "width", 0) or 0),
    )
    base_h = max(
        1,
        int(getattr(image1, "height", 0) or 0),
        int(getattr(image2, "height", 0) or 0),
    )

    temp_store = Store()
    temp_store.viewport = snap.viewport_state.clone()
    temp_store.settings = snap.settings_state.freeze_for_export()
    temp_store.viewport.session_data.image_state.image1 = image1
    temp_store.viewport.session_data.image_state.image2 = image2
    temp_store.document.full_res_image1 = image1
    temp_store.document.full_res_image2 = image2
    temp_store.viewport.geometry_state.pixmap_width = base_w
    temp_store.viewport.geometry_state.pixmap_height = base_h

    requirements = []
    for build_requirement in get_canvas_feature_commands_by_id(
        "render.layout_requirement"
    ):
        requirement = build_requirement(
            temp_store,
            drawing_width=base_w,
            drawing_height=base_h,
        )
        if requirement is not None:
            requirements.append(requirement)

    if requirements:
        layout = resolve_virtual_canvas_layout(requirements)
        pad_left, pad_right, pad_top, pad_bottom = layout.resolve_padding_pixels(
            base_width=base_w,
            base_height=base_h,
        )
        canvas_bounds = layout.canvas_bounds
    else:
        pad_left, pad_right, pad_top, pad_bottom = (0, 0, 0, 0)
        canvas_bounds = NormalizedBounds.unit()

    return GlobalCanvasBounds(
        pad_left=pad_left,
        pad_right=pad_right,
        pad_top=pad_top,
        pad_bottom=pad_bottom,
        base_width=base_w,
        base_height=base_h,
        canvas_x_min=float(canvas_bounds.x_min),
        canvas_x_max=float(canvas_bounds.x_max),
        canvas_y_min=float(canvas_bounds.y_min),
        canvas_y_max=float(canvas_bounds.y_max),
    )
