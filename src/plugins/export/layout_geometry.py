"""Export dialog content-driven geometry."""

from __future__ import annotations

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    HorizontalPaneMinimum,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
    max_visible_widget_width_hint,
    sum_visible_widget_height_hint,
    widget_height_hint,
    widget_width_hint,
)

EXPORT_PREVIEW_MIN_WIDTH = 500
# Soft floor: when height is tight, preview shrinks before form controls.
EXPORT_PREVIEW_MIN_HEIGHT = 160
EXPORT_FORM_MIN_WIDTH = 420
EXPORT_MIN_DIALOG_WIDTH = 640
EXPORT_MAX_DIALOG_WIDTH = 1400
EXPORT_MIN_DIALOG_HEIGHT = 520
EXPORT_MAIN_MARGIN_PX = 24
EXPORT_MAIN_SPACING_PX = 12
EXPORT_FRAME_PADDING_PX = 16
EXPORT_FORM_ROW_SPACING_PX = 10
# Minimum Y gap between filename block and format controls (still expands).
EXPORT_FILENAME_FORMAT_MIN_GAP_PX = 20
EXPORT_HEIGHT_SCREEN_MARGIN_PX = 100

# Non-scroll dialog: lock minimum to computed content so controls cannot be
# crushed (settings keeps a low floor because pages scroll).
EXPORT_GEOMETRY_POLICY = GeometryApplyPolicy(
    resize_when_hidden=True,
    update_minimum=True,
    minimum_floor=(EXPORT_MIN_DIALOG_WIDTH, EXPORT_MIN_DIALOG_HEIGHT),
    width_bounds=(EXPORT_MIN_DIALOG_WIDTH, EXPORT_MAX_DIALOG_WIDTH),
    center_on_parent=True,
    lock_minimum_to_computed=True,
)

# First layout pass after CSD adjustSize: force the computed size even if the
# dialog is already visible (otherwise pixmap sizeHint keeps a huge shell and
# EXPORT_PREVIEW_MIN_WIDTH appears to do nothing).
EXPORT_GEOMETRY_POLICY_INITIAL = GeometryApplyPolicy(
    resize_when_hidden=True,
    update_minimum=True,
    minimum_floor=(EXPORT_MIN_DIALOG_WIDTH, EXPORT_MIN_DIALOG_HEIGHT),
    width_bounds=(EXPORT_MIN_DIALOG_WIDTH, EXPORT_MAX_DIALOG_WIDTH),
    center_on_parent=True,
    lock_minimum_to_computed=True,
    force_resize=True,
)


def _export_form_widgets(dialog) -> list:
    return [
        getattr(dialog, "output_section", None),
        getattr(dialog, "fmt_label", None),
        getattr(dialog, "combo_format", None),
        getattr(dialog, "resolution_row", None),
        getattr(dialog, "quality_row", None),
        getattr(dialog, "png_row", None),
        getattr(dialog, "bg_color_row", None),
        getattr(dialog, "checkbox_include_metadata", None),
        getattr(dialog, "comment_label", None),
        getattr(dialog, "edit_comment", None),
        getattr(dialog, "checkbox_comment_default", None),
        getattr(dialog, "action_bar", None),
    ]


def compute_export_form_width(dialog) -> int:
    form_frame = getattr(dialog, "export_form_frame", None)
    return max(
        EXPORT_FORM_MIN_WIDTH,
        widget_width_hint(form_frame),
        max_visible_widget_width_hint(_export_form_widgets(dialog)),
    )


def compute_export_form_height(dialog) -> int:
    """Stack form rows — never take max of a single row."""
    form_frame = getattr(dialog, "export_form_frame", None)
    stacked = sum_visible_widget_height_hint(
        _export_form_widgets(dialog),
        spacing=EXPORT_FORM_ROW_SPACING_PX,
    )
    frame_hint = widget_height_hint(form_frame)
    return max(stacked, frame_hint) + EXPORT_FRAME_PADDING_PX


def compute_export_dialog_size(dialog) -> tuple[int, int]:
    dialog.ensurePolished()

    # Do not use export_preview_frame / preview_label width hints — a scaled
    # QPixmap makes QLabel.sizeHint() track the current (large) preview and
    # locks the dialog minimum around 300–700px.
    preview_width = max(
        EXPORT_PREVIEW_MIN_WIDTH,
        widget_width_hint(getattr(dialog, "export_preview_title", None)),
    )
    preview_height = max(
        EXPORT_PREVIEW_MIN_HEIGHT
        + widget_height_hint(getattr(dialog, "export_preview_title", None))
        + EXPORT_FRAME_PADDING_PX,
        EXPORT_PREVIEW_MIN_HEIGHT + EXPORT_FRAME_PADDING_PX,
    )

    form_width = compute_export_form_width(dialog)
    form_height = compute_export_form_height(dialog)

    title_bar = getattr(dialog, "_csd_title_bar", None)
    title_bar_height = widget_height_hint(title_bar)

    total_width = HorizontalPaneMinimum(
        left_min=preview_width + EXPORT_FRAME_PADDING_PX,
        spacing=EXPORT_MAIN_SPACING_PX,
        right_min=form_width + EXPORT_FRAME_PADDING_PX,
        outer_margins=EXPORT_MAIN_MARGIN_PX,
    ).total_width()
    total_height = (
        max(preview_height, form_height)
        + EXPORT_MAIN_MARGIN_PX
        + title_bar_height
    )

    final_width = clamp(
        total_width,
        minimum=EXPORT_MIN_DIALOG_WIDTH,
        maximum=EXPORT_MAX_DIALOG_WIDTH,
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        max(total_height, EXPORT_MIN_DIALOG_HEIGHT),
        margin=EXPORT_HEIGHT_SCREEN_MARGIN_PX,
    )
    return final_width, final_height


def apply_export_dialog_geometry(dialog, *, force_resize: bool = False) -> None:
    from PySide6.QtWidgets import QSizePolicy

    preview = getattr(dialog, "export_preview_frame", None)
    if preview is not None:
        preview.setMinimumWidth(EXPORT_PREVIEW_MIN_WIDTH)
        preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

    preview_label = getattr(dialog, "preview_label", None)
    if preview_label is not None:
        preview_label.setMinimumSize(
            EXPORT_PREVIEW_MIN_WIDTH, EXPORT_PREVIEW_MIN_HEIGHT
        )

    form = getattr(dialog, "export_form_frame", None)
    if form is not None:
        form.setMinimumWidth(compute_export_form_width(dialog))
        # Do not pin form to an absolute content height. A hard minimum makes
        # the form overflow the dialog when CSD resize ignores Qt mins, which
        # clips OK/Cancel at the bottom. Layout-driven Minimum + locked
        # children (path section, action bar) + stretch absorbs squeeze.
        form.setMinimumHeight(0)
        form.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )

    output_section = getattr(dialog, "output_section", None)
    lock_min = getattr(output_section, "lock_content_minimum_height", None)
    if callable(lock_min):
        lock_min()
    elif output_section is not None:
        output_section.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        output_section.setMinimumHeight(
            max(
                output_section.minimumHeight(),
                widget_height_hint(output_section),
            )
        )

    action_bar = getattr(dialog, "action_bar", None)
    lock_action = getattr(action_bar, "lock_content_minimum_height", None)
    if callable(lock_action):
        lock_action()
    elif action_bar is not None:
        action_bar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        action_bar.setMinimumHeight(
            max(action_bar.minimumHeight(), widget_height_hint(action_bar))
        )

    width, height = compute_export_dialog_size(dialog)
    policy = (
        EXPORT_GEOMETRY_POLICY_INITIAL if force_resize else EXPORT_GEOMETRY_POLICY
    )
    apply_dialog_geometry(
        dialog,
        width,
        height,
        policy=policy,
    )

    # Wayland/X11 CSD resize often ignores QWidget minimumSize; pin the
    # QWindow hint too when a handle already exists (post-show).
    handle = dialog.windowHandle() if hasattr(dialog, "windowHandle") else None
    if handle is not None:
        handle.setMinimumSize(dialog.minimumSize())
