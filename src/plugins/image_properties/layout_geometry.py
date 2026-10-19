"""Image properties dialog content-driven geometry.

Design px live here as plain ints; every resolver below reads the live
``UiScale`` factor **at call time**. The size recipe and the geometry policy
used to consume these numbers raw, so at interface scale 1.25/1.5 the shell
minimum/bounds stayed at design px while the scaled property rows grew — the
table got clipped or crushed ("dialogs stranded at design px" class, plan
``plan-live-appearance-fixes-2026-10-19``). Nothing in this module scales at
import: the working sibling is ``plugins/export/layout_geometry.py``.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
    widget_size_hint as _size_hint,
)
from sli_ui_toolkit.managers import scaled_px

# Design px (unscaled). Resolved through the resolvers below, never at import.
IMAGE_PROPERTIES_MIN_WIDTH = 480
IMAGE_PROPERTIES_MAX_WIDTH = 960
IMAGE_PROPERTIES_MIN_HEIGHT = 360
IMAGE_PROPERTIES_OUTER_MARGIN_PX = 24
IMAGE_PROPERTIES_SCROLL_FOOTER_SPACING_PX = 10
IMAGE_PROPERTIES_HEIGHT_SCREEN_MARGIN_PX = 100
# Property documents can be tall; keep open height comfortable — body scrolls.
IMAGE_PROPERTIES_MAX_CONTENT_HEIGHT_PX = 520


def image_properties_min_dialog_width() -> int:
    return scaled_px(IMAGE_PROPERTIES_MIN_WIDTH)


def image_properties_max_dialog_width() -> int:
    return scaled_px(IMAGE_PROPERTIES_MAX_WIDTH)


def image_properties_min_dialog_height() -> int:
    return scaled_px(IMAGE_PROPERTIES_MIN_HEIGHT)


def image_properties_outer_margin() -> int:
    return scaled_px(IMAGE_PROPERTIES_OUTER_MARGIN_PX)


def image_properties_scroll_footer_spacing() -> int:
    return scaled_px(IMAGE_PROPERTIES_SCROLL_FOOTER_SPACING_PX)


def image_properties_height_screen_margin() -> int:
    return scaled_px(IMAGE_PROPERTIES_HEIGHT_SCREEN_MARGIN_PX)


def image_properties_max_content_height() -> int:
    return scaled_px(IMAGE_PROPERTIES_MAX_CONTENT_HEIGHT_PX)


def image_properties_geometry_policy() -> GeometryApplyPolicy:
    """The dialog's geometry policy, with floor/bounds resolved at THIS call."""
    return GeometryApplyPolicy(
        resize_when_hidden=True,
        update_minimum=True,
        minimum_floor=(
            image_properties_min_dialog_width(),
            image_properties_min_dialog_height(),
        ),
        width_bounds=(
            image_properties_min_dialog_width(),
            image_properties_max_dialog_width(),
        ),
        center_on_parent=True,
        remember_key="image_properties",
    )


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
        content_h = max(
            content_h, min(doc_h, image_properties_max_content_height())
        )

    total_width = (
        max(content_w, footer_w) + image_properties_outer_margin()
    )
    total_height = (
        content_h
        + image_properties_scroll_footer_spacing()
        + footer_h
        + image_properties_outer_margin()
    )

    final_width = clamp(
        total_width,
        minimum=image_properties_min_dialog_width(),
        maximum=image_properties_max_dialog_width(),
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        max(total_height, image_properties_min_dialog_height()),
        margin=image_properties_height_screen_margin(),
    )
    return final_width, final_height


def apply_image_properties_dialog_geometry(dialog) -> None:
    width, height = compute_image_properties_dialog_size(dialog)
    apply_dialog_geometry(
        dialog,
        width,
        height,
        policy=image_properties_geometry_policy(),
    )
    # Restore stretch after any prior measurement / CSD adjustSize.
    _activate_content_layout(dialog)
