"""Video editor dialog geometry derived from export/settings content."""

from __future__ import annotations

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    HorizontalPaneMinimum,
    apply_dialog_geometry,
    clamp,
    tab_widget_intrinsic_width,
    widget_width_hint,
)

MIN_VIDEO_EDITOR_PREVIEW_WIDTH = 240
MIN_VIDEO_EDITOR_PREVIEW_HEIGHT = 135
MIN_VIDEO_EDITOR_SETTINGS_WIDTH = 350
MAX_VIDEO_EDITOR_SETTINGS_WIDTH = 650
VIDEO_EDITOR_TOP_MARGIN_PX = 20
VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX = 10
# ``content_layout`` around TopTabHost in ``build_settings_panel`` (12 + 12).
VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX = 24
MIN_VIDEO_EDITOR_DIALOG_HEIGHT = 600

VIDEO_EDITOR_GEOMETRY_POLICY = GeometryApplyPolicy(
    resize_when_hidden=False,
    update_minimum=True,
    minimum_floor=(0, MIN_VIDEO_EDITOR_DIALOG_HEIGHT),
    width_bounds=None,
    center_on_parent=False,
)


def _tabs_required_panel_width(dialog) -> int:
    """Tab strip width plus the horizontal margins of its parent layout."""
    tabs = getattr(dialog, "tabs", None)
    width = tab_widget_intrinsic_width(tabs)
    if tabs is None:
        return width

    parent = tabs.parentWidget() if hasattr(tabs, "parentWidget") else None
    layout = parent.layout() if parent is not None else None
    if layout is not None:
        margins = layout.contentsMargins()
        width += int(margins.left()) + int(margins.right())
    else:
        width += VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX
    return width


def compute_settings_panel_width(dialog) -> int:
    static_width = widget_width_hint(getattr(dialog, "settings_static_container", None))
    tabs_width = _tabs_required_panel_width(dialog)
    export_width = widget_width_hint(getattr(dialog, "btn_export", None))

    optimal = max(
        MIN_VIDEO_EDITOR_SETTINGS_WIDTH,
        static_width,
        tabs_width,
        export_width,
    )
    return clamp(
        optimal,
        minimum=MIN_VIDEO_EDITOR_SETTINGS_WIDTH,
        maximum=MAX_VIDEO_EDITOR_SETTINGS_WIDTH,
    )


def compute_minimum_dialog_width(settings_width: int) -> int:
    return HorizontalPaneMinimum(
        left_min=MIN_VIDEO_EDITOR_PREVIEW_WIDTH,
        spacing=VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX,
        right_min=settings_width,
        outer_margins=VIDEO_EDITOR_TOP_MARGIN_PX,
    ).total_width()


def apply_top_row_geometry(dialog) -> int:
    settings_width = compute_settings_panel_width(dialog)
    dialog.settings_panel.setMinimumWidth(MIN_VIDEO_EDITOR_SETTINGS_WIDTH)
    dialog.settings_panel.setFixedWidth(settings_width)

    min_dialog_width = compute_minimum_dialog_width(settings_width)
    current_min = dialog.minimumSize()
    min_dialog_height = max(current_min.height(), MIN_VIDEO_EDITOR_DIALOG_HEIGHT)
    apply_dialog_geometry(
        dialog,
        min_dialog_width,
        min_dialog_height,
        policy=VIDEO_EDITOR_GEOMETRY_POLICY,
    )
    return settings_width
