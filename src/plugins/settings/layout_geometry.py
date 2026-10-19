"""Settings dialog content-driven geometry.

Design px live here as plain ints; every resolver below reads the live
``UiScale`` factor **at call time**. These numbers used to be consumed raw,
so at interface scale 1.25/1.5 the declared floor/bounds stayed at design px
while the dialog's rows (which do scale) grew — the shell bracketed content
that no longer fit ("dialogs stranded at design px" class, plan
``plan-live-appearance-fixes-2026-10-19``). Nothing in this module scales at
import: the working sibling is ``plugins/export/layout_geometry.py``.
"""

from __future__ import annotations

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
    measure_scroll_pages_stack,
)
from sli_ui_toolkit.managers import scaled_px

# Design px (unscaled). Resolved through the resolvers below, never at import.
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
# Resizability floor, not a content-fit guarantee (pages scroll): low by
# design, but it still has to bracket the scaled chrome at factor > 1.
SETTINGS_FLOOR_WIDTH_PX = 300
SETTINGS_FLOOR_HEIGHT_PX = 200


def settings_min_dialog_width() -> int:
    return scaled_px(SETTINGS_MIN_WIDTH)


def settings_max_dialog_width() -> int:
    return scaled_px(SETTINGS_MAX_WIDTH)


def settings_content_margin_extra() -> int:
    return scaled_px(SETTINGS_CONTENT_MARGIN_EXTRA_PX)


def settings_sidebar_row_height() -> int:
    return scaled_px(SETTINGS_SIDEBAR_ROW_HEIGHT_PX)


def settings_sidebar_vertical_padding() -> int:
    return scaled_px(SETTINGS_SIDEBAR_VERTICAL_PADDING_PX)


def settings_bottom_controls_height() -> int:
    return scaled_px(SETTINGS_BOTTOM_CONTROLS_HEIGHT_PX)


def settings_height_screen_margin() -> int:
    return scaled_px(SETTINGS_HEIGHT_SCREEN_MARGIN_PX)


def settings_height_extra() -> int:
    return scaled_px(SETTINGS_HEIGHT_EXTRA_PX)


def settings_max_content_height() -> int:
    return scaled_px(SETTINGS_MAX_CONTENT_HEIGHT_PX)


def settings_minimum_floor() -> tuple[int, int]:
    return (scaled_px(SETTINGS_FLOOR_WIDTH_PX), scaled_px(SETTINGS_FLOOR_HEIGHT_PX))


def settings_geometry_policy() -> GeometryApplyPolicy:
    """The dialog's geometry policy, with floor/bounds resolved at THIS call."""
    return GeometryApplyPolicy(
        resize_when_hidden=True,
        update_minimum=True,
        minimum_floor=settings_minimum_floor(),
        width_bounds=(settings_min_dialog_width(), settings_max_dialog_width()),
        center_on_parent=True,
        remember_key="settings",
    )


def compute_settings_dialog_size(dialog) -> tuple[int, int]:
    dialog.ensurePolished()
    sidebar_width = dialog.sidebar.width()
    content_margins = dialog.content_layout.contentsMargins()
    total_width_margins = (
        content_margins.left()
        + content_margins.right()
        + settings_content_margin_extra()
    )

    max_content_width, max_content_height = measure_scroll_pages_stack(
        dialog.pages_stack,
        group_widget_cls=getattr(dialog, "_custom_group_widget_cls", None),
    )
    max_content_height = min(max_content_height, settings_max_content_height())

    required_width = sidebar_width + max_content_width + total_width_margins
    final_width = clamp(
        required_width,
        minimum=settings_min_dialog_width(),
        maximum=settings_max_dialog_width(),
    )

    sidebar_req_height = (
        dialog.sidebar.count() * settings_sidebar_row_height()
        + settings_sidebar_vertical_padding()
    )
    required_height = max(
        sidebar_req_height,
        max_content_height + settings_bottom_controls_height(),
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        required_height + settings_height_extra(),
        margin=settings_height_screen_margin(),
    )
    return final_width, final_height


def apply_settings_dialog_geometry(dialog) -> None:
    width, height = compute_settings_dialog_size(dialog)
    apply_dialog_geometry(
        dialog,
        width,
        height,
        policy=settings_geometry_policy(),
    )
