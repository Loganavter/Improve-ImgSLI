"""Image properties dialog content-driven geometry."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
    widget_size_hint as _size_hint,
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
    remember_key="image_properties",
)


IMAGE_PROPERTIES_MAX_CONTENT_HEIGHT_PX = 520


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
    document = getattr(dialog, "properties_document", None)
    scroll_content = getattr(dialog, "properties_scroll_content", None)
    actions = getattr(dialog, "properties_actions", None)

    content_w, content_h = _size_hint(scroll_content)
    footer_w, footer_h = _size_hint(actions)

    if document is not None:
        doc_w, doc_h = _size_hint(document)
        content_w = max(content_w, doc_w)
        content_h = max(content_h, min(doc_h, IMAGE_PROPERTIES_MAX_CONTENT_HEIGHT_PX))

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
