"""Settings dialog content-driven geometry."""

from __future__ import annotations

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
    measure_scroll_pages_stack,
)

SETTINGS_MIN_WIDTH = 800
SETTINGS_MAX_WIDTH = 1200
SETTINGS_CONTENT_MARGIN_EXTRA_PX = 40
SETTINGS_SIDEBAR_ROW_HEIGHT_PX = 45
SETTINGS_SIDEBAR_VERTICAL_PADDING_PX = 40
SETTINGS_BOTTOM_CONTROLS_HEIGHT_PX = 80
SETTINGS_HEIGHT_SCREEN_MARGIN_PX = 100
SETTINGS_HEIGHT_EXTRA_PX = 5
# Pages are QScrollArea-backed; do not size the shell to the tallest
# scroll *content* (Keyboard alone is dozens of rows). Cap the viewport
# budget so open height stays comfortable on any monitor.
SETTINGS_MAX_CONTENT_HEIGHT_PX = 520

SETTINGS_GEOMETRY_POLICY = GeometryApplyPolicy(
    resize_when_hidden=True,
    update_minimum=True,
    minimum_floor=(300, 200),
    width_bounds=(SETTINGS_MIN_WIDTH, SETTINGS_MAX_WIDTH),
    center_on_parent=True,
)


def compute_settings_dialog_size(dialog) -> tuple[int, int]:
    dialog.ensurePolished()
    sidebar_width = dialog.sidebar.width()
    content_margins = dialog.content_layout.contentsMargins()
    total_width_margins = (
        content_margins.left()
        + content_margins.right()
        + SETTINGS_CONTENT_MARGIN_EXTRA_PX
    )

    max_content_width, max_content_height = measure_scroll_pages_stack(
        dialog.pages_stack,
        group_widget_cls=getattr(dialog, "_custom_group_widget_cls", None),
    )
    max_content_height = min(max_content_height, SETTINGS_MAX_CONTENT_HEIGHT_PX)

    required_width = sidebar_width + max_content_width + total_width_margins
    final_width = clamp(
        required_width,
        minimum=SETTINGS_MIN_WIDTH,
        maximum=SETTINGS_MAX_WIDTH,
    )

    sidebar_req_height = (
        dialog.sidebar.count() * SETTINGS_SIDEBAR_ROW_HEIGHT_PX
        + SETTINGS_SIDEBAR_VERTICAL_PADDING_PX
    )
    required_height = max(
        sidebar_req_height,
        max_content_height + SETTINGS_BOTTOM_CONTROLS_HEIGHT_PX,
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        required_height + SETTINGS_HEIGHT_EXTRA_PX,
        margin=SETTINGS_HEIGHT_SCREEN_MARGIN_PX,
    )
    return final_width, final_height


def apply_settings_dialog_geometry(dialog) -> None:
    width, height = compute_settings_dialog_size(dialog)
    apply_dialog_geometry(
        dialog,
        width,
        height,
        policy=SETTINGS_GEOMETRY_POLICY,
    )
