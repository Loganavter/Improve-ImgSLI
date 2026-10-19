"""Video editor dialog geometry derived from export/settings content.

Every value here is authored in DESIGN px and resolved through ``scaled_px``
at use time — never at import. The module-level ``*_PX`` constants are the
design values; ``video_editor_geometry_policy()`` is built per call so its
height floor follows a live ``UiScale`` change instead of freezing at the
factor of the first import.
"""

from __future__ import annotations

from tabs.host_helpers import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
)
from tabs.image_compare.plugins.video_editor.geometry_helpers import (
    clamp,
    tab_widget_intrinsic_width,
    widget_width_hint,
)
from sli_ui_toolkit.managers import scaled_px

MIN_VIDEO_EDITOR_PREVIEW_WIDTH_PX = 240
MIN_VIDEO_EDITOR_PREVIEW_HEIGHT_PX = 135
MIN_VIDEO_EDITOR_SETTINGS_WIDTH_PX = 350
MAX_VIDEO_EDITOR_SETTINGS_WIDTH_PX = 650
VIDEO_EDITOR_TOP_MARGIN_PX = 20
VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX = 10
# ``content_layout`` around TopTabHost in ``build_settings_panel`` (12 + 12).
VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX = 24
MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX = 600


def video_editor_geometry_policy() -> GeometryApplyPolicy:
    """Apply policy for the top-row geometry pass, built per call.

    ``minimum_floor`` resolves its design-px height through ``scaled_px`` here
    rather than being frozen into a module-level policy at import.
    """
    return GeometryApplyPolicy(
        resize_when_hidden=False,
        update_minimum=True,
        minimum_floor=(0, scaled_px(MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX)),
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
        width += scaled_px(VIDEO_EDITOR_TABS_CONTENT_H_MARGINS_PX)
    return width


def compute_settings_panel_width(dialog) -> int:
    minimum = scaled_px(MIN_VIDEO_EDITOR_SETTINGS_WIDTH_PX)
    maximum = scaled_px(MAX_VIDEO_EDITOR_SETTINGS_WIDTH_PX)
    static_width = widget_width_hint(getattr(dialog, "settings_static_container", None))
    tabs_width = _tabs_required_panel_width(dialog)
    export_width = widget_width_hint(getattr(dialog, "btn_export", None))

    optimal = max(minimum, static_width, tabs_width, export_width)
    return clamp(optimal, minimum=minimum, maximum=maximum)


def _pane_row_min_width(
    *,
    left_min: int,
    spacing: int,
    right_min: int,
    outer_margins: int = 0,
) -> int:
    """Minimum width of a left|right pane row: outer + left + spacing + right.

    Kept local on purpose: the shared ``HorizontalPaneMinimum`` is a
    platform-internal layout primitive and is deliberately NOT re-exported
    through ``tabs.host_helpers`` (the tab-isolation seam). A tab that needs
    this trivial sum owns it.
    """
    return outer_margins + left_min + spacing + right_min


def compute_minimum_dialog_width(settings_width: int) -> int:
    return _pane_row_min_width(
        left_min=scaled_px(MIN_VIDEO_EDITOR_PREVIEW_WIDTH_PX),
        spacing=scaled_px(VIDEO_EDITOR_TOP_HORIZONTAL_SPACING_PX),
        right_min=settings_width,
        outer_margins=scaled_px(VIDEO_EDITOR_TOP_MARGIN_PX),
    )


def apply_top_row_geometry(dialog) -> int:
    settings_width = compute_settings_panel_width(dialog)
    dialog.settings_panel.setMinimumWidth(scaled_px(MIN_VIDEO_EDITOR_SETTINGS_WIDTH_PX))
    dialog.settings_panel.setFixedWidth(settings_width)

    min_dialog_width = compute_minimum_dialog_width(settings_width)
    current_min = dialog.minimumSize()
    min_dialog_height = max(
        current_min.height(), scaled_px(MIN_VIDEO_EDITOR_DIALOG_HEIGHT_PX)
    )
    apply_dialog_geometry(
        dialog,
        min_dialog_width,
        min_dialog_height,
        policy=video_editor_geometry_policy(),
    )
    return settings_width
