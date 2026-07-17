"""Image properties dialog content-driven geometry."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
)

IMAGE_PROPERTIES_MIN_WIDTH = 480
IMAGE_PROPERTIES_MAX_WIDTH = 960
IMAGE_PROPERTIES_MIN_HEIGHT = 360
IMAGE_PROPERTIES_OUTER_MARGIN_PX = 24
IMAGE_PROPERTIES_SCROLL_FOOTER_SPACING_PX = 10
IMAGE_PROPERTIES_HEIGHT_SCREEN_MARGIN_PX = 100

IMAGE_PROPERTIES_GEOMETRY_POLICY = GeometryApplyPolicy(
    resize_when_hidden=True,
    update_minimum=True,
    minimum_floor=(IMAGE_PROPERTIES_MIN_WIDTH, IMAGE_PROPERTIES_MIN_HEIGHT),
    width_bounds=(IMAGE_PROPERTIES_MIN_WIDTH, IMAGE_PROPERTIES_MAX_WIDTH),
    center_on_parent=True,
)


def _size_hint(widget: QWidget | None) -> tuple[int, int]:
    """Read intrinsic size without ``adjustSize``.

    Calling ``adjustSize`` on live section frames / scroll content freezes each
    child to its sizeHint geometry and breaks the parent VBox stretch until the
    next user resize — first open then looks like overlapping group headers.
    """
    if widget is None:
        return (0, 0)
    widget.ensurePolished()
    hint = widget.sizeHint()
    return (max(0, hint.width()), max(0, hint.height()))


def _activate_content_layout(dialog) -> None:
    content = getattr(dialog, "properties_scroll_content", None)
    if content is None:
        return
    layout = content.layout()
    if layout is None:
        return
    layout.invalidate()
    layout.activate()
    content.updateGeometry()


def compute_image_properties_dialog_size(dialog) -> tuple[int, int]:
    dialog.ensurePolished()
    section_frames = getattr(dialog, "properties_section_frames", ()) or ()
    scroll_content = getattr(dialog, "properties_scroll_content", None)
    actions = getattr(dialog, "properties_actions", None)

    content_w, content_h = _size_hint(scroll_content)
    footer_w, footer_h = _size_hint(actions)

    if section_frames:
        section_widths = []
        sections_height = 0
        for frame in section_frames:
            fw, fh = _size_hint(frame)
            section_widths.append(fw)
            sections_height += fh
        gaps = max(0, len(section_frames) - 1) * IMAGE_PROPERTIES_SCROLL_FOOTER_SPACING_PX
        content_w = max(content_w, max(section_widths))
        content_h = max(content_h, sections_height + gaps)

    total_width = max(content_w, footer_w) + IMAGE_PROPERTIES_OUTER_MARGIN_PX
    total_height = (
        content_h
        + IMAGE_PROPERTIES_SCROLL_FOOTER_SPACING_PX
        + footer_h
        + IMAGE_PROPERTIES_OUTER_MARGIN_PX
    )

    final_width = clamp(
        total_width,
        minimum=IMAGE_PROPERTIES_MIN_WIDTH,
        maximum=IMAGE_PROPERTIES_MAX_WIDTH,
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        max(total_height, IMAGE_PROPERTIES_MIN_HEIGHT),
        margin=IMAGE_PROPERTIES_HEIGHT_SCREEN_MARGIN_PX,
    )
    return final_width, final_height


def apply_image_properties_dialog_geometry(dialog) -> None:
    width, height = compute_image_properties_dialog_size(dialog)
    apply_dialog_geometry(
        dialog,
        width,
        height,
        policy=IMAGE_PROPERTIES_GEOMETRY_POLICY,
    )
    # Restore stretch after any prior measurement / CSD adjustSize.
    _activate_content_layout(dialog)
