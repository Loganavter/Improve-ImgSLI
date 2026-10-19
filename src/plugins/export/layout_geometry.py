"""Export dialog content-driven geometry.

Design px live here as plain ints; every resolver below reads the live
``UiScale`` factor **at call time**. They used to be module-level
``scaled_px(...)`` constants, which are evaluated once at import and frozen at
that factor — so a later interface-scale change left the export dialog at its
old design size while the rest of the UI moved (the "dialogs stranded at
design px" class, plan ``plan-live-appearance-fixes-2026-10-19``). Nothing in
this module scales at import any more.
"""

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
from sli_ui_toolkit.managers import scaled_px

# Design px (unscaled). Resolved through the resolvers below, never at import.
_PREVIEW_MIN_WIDTH_PX = 500
# Soft floor: when height is tight, preview shrinks before form controls.
_PREVIEW_MIN_HEIGHT_PX = 160
_FORM_MIN_WIDTH_PX = 420
_MIN_DIALOG_WIDTH_PX = 640
_MAX_DIALOG_WIDTH_PX = 1400
_MIN_DIALOG_HEIGHT_PX = 520
_MAIN_MARGIN_PX = 24
_MAIN_SPACING_PX = 12
_FRAME_PADDING_PX = 16
_FORM_ROW_SPACING_PX = 10
# Minimum Y gap between filename block and format controls (still expands).
_FILENAME_FORMAT_MIN_GAP_PX = 20
_HEIGHT_SCREEN_MARGIN_PX = 100


def export_preview_min_width() -> int:
    return scaled_px(_PREVIEW_MIN_WIDTH_PX)


def export_preview_min_height() -> int:
    return scaled_px(_PREVIEW_MIN_HEIGHT_PX)


def export_form_min_width() -> int:
    return scaled_px(_FORM_MIN_WIDTH_PX)


def export_min_dialog_width() -> int:
    return scaled_px(_MIN_DIALOG_WIDTH_PX)


def export_max_dialog_width() -> int:
    return scaled_px(_MAX_DIALOG_WIDTH_PX)


def export_min_dialog_height() -> int:
    return scaled_px(_MIN_DIALOG_HEIGHT_PX)


def export_main_margin() -> int:
    return scaled_px(_MAIN_MARGIN_PX)


def export_main_spacing() -> int:
    return scaled_px(_MAIN_SPACING_PX)


def export_frame_padding() -> int:
    return scaled_px(_FRAME_PADDING_PX)


def export_form_row_spacing() -> int:
    return scaled_px(_FORM_ROW_SPACING_PX)


def export_filename_format_min_gap() -> int:
    return scaled_px(_FILENAME_FORMAT_MIN_GAP_PX)


def export_height_screen_margin() -> int:
    return scaled_px(_HEIGHT_SCREEN_MARGIN_PX)


def export_geometry_policy(*, force_resize: bool = False) -> GeometryApplyPolicy:
    """The dialog's geometry policy, with floor/bounds resolved at THIS call.

    Non-scroll dialog: lock the minimum to the computed content so controls
    cannot be crushed (settings keeps a low floor because pages scroll).
    ``force_resize`` is the first-layout pass after CSD ``adjustSize``: force
    the computed size even if the dialog is already visible (otherwise a
    pixmap sizeHint keeps a huge shell and ``export_preview_min_width()``
    appears to do nothing).
    """
    return GeometryApplyPolicy(
        resize_when_hidden=True,
        update_minimum=True,
        minimum_floor=(export_min_dialog_width(), export_min_dialog_height()),
        width_bounds=(export_min_dialog_width(), export_max_dialog_width()),
        center_on_parent=True,
        lock_minimum_to_computed=True,
        force_resize=force_resize,
        remember_key="export",
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
        export_form_min_width(),
        widget_width_hint(form_frame),
        max_visible_widget_width_hint(_export_form_widgets(dialog)),
    )


def compute_export_form_height(dialog) -> int:
    """Stack form rows — never take max of a single row."""
    form_frame = getattr(dialog, "export_form_frame", None)
    stacked = sum_visible_widget_height_hint(
        _export_form_widgets(dialog),
        spacing=export_form_row_spacing(),
    )
    frame_hint = widget_height_hint(form_frame)
    return max(stacked, frame_hint) + export_frame_padding()


def compute_export_dialog_size(dialog) -> tuple[int, int]:
    dialog.ensurePolished()

    # Do not use export_preview_frame / preview_label width hints — a scaled
    # QPixmap makes QLabel.sizeHint() track the current (large) preview and
    # locks the dialog minimum around 300–700px.
    preview_width = max(
        export_preview_min_width(),
        widget_width_hint(getattr(dialog, "export_preview_title", None)),
    )
    preview_height = max(
        export_preview_min_height()
        + widget_height_hint(getattr(dialog, "export_preview_title", None))
        + export_frame_padding(),
        export_preview_min_height() + export_frame_padding(),
    )

    form_width = compute_export_form_width(dialog)
    form_height = compute_export_form_height(dialog)

    title_bar = getattr(dialog, "_csd_title_bar", None)
    title_bar_height = widget_height_hint(title_bar)

    total_width = HorizontalPaneMinimum(
        left_min=preview_width + export_frame_padding(),
        spacing=export_main_spacing(),
        right_min=form_width + export_frame_padding(),
        outer_margins=export_main_margin(),
    ).total_width()
    total_height = (
        max(preview_height, form_height)
        + export_main_margin()
        + title_bar_height
    )

    final_width = clamp(
        total_width,
        minimum=export_min_dialog_width(),
        maximum=export_max_dialog_width(),
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        max(total_height, export_min_dialog_height()),
        margin=export_height_screen_margin(),
    )
    return final_width, final_height


def apply_export_dialog_geometry(dialog, *, force_resize: bool = False) -> None:
    from PySide6.QtWidgets import QSizePolicy

    preview = getattr(dialog, "export_preview_frame", None)
    if preview is not None:
        preview.setMinimumWidth(export_preview_min_width())
        preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

    preview_label = getattr(dialog, "preview_label", None)
    if preview_label is not None:
        preview_label.setMinimumSize(
            export_preview_min_width(), export_preview_min_height()
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
    policy = export_geometry_policy(force_resize=force_resize)
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
