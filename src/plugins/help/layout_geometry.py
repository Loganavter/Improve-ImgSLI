"""Help dialog content-driven geometry."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
)

HELP_MIN_WIDTH = 720
HELP_MAX_WIDTH = 1200
HELP_MIN_HEIGHT = 480
HELP_CONTENT_MIN_WIDTH = 480
HELP_SHELL_PADDING_PX = 48
HELP_SIDEBAR_MIN_WIDTH = 200
HELP_SIDEBAR_DEFAULT_WIDTH = 280
HELP_SIDEBAR_MAX_WIDTH = 420
HELP_NAV_MIN_WIDTH = HELP_SIDEBAR_DEFAULT_WIDTH
HELP_HEIGHT_SCREEN_MARGIN_PX = 100
# Hub/document content can be tall; keep open height comfortable — body scrolls.
HELP_MAX_CONTENT_HEIGHT_PX = 560

HELP_GEOMETRY_POLICY = GeometryApplyPolicy(
    resize_when_hidden=True,
    update_minimum=True,
    minimum_floor=(HELP_MIN_WIDTH, HELP_MIN_HEIGHT),
    width_bounds=(HELP_MIN_WIDTH, HELP_MAX_WIDTH),
    center_on_parent=True,
)


def _visible_help_page(dialog) -> QWidget | None:
    hub = getattr(dialog, "_hub_page", None)
    if hub is not None and not hub.isHidden():
        return hub
    document = getattr(dialog, "_document", None)
    if document is not None and not document.isHidden():
        return document
    return getattr(dialog, "_content_host", None)


def _size_hint(widget: QWidget | None) -> tuple[int, int]:
    """Read intrinsic size without ``adjustSize`` (which collapses live layout)."""
    if widget is None:
        return (0, 0)
    widget.ensurePolished()
    hint = widget.sizeHint()
    return (max(0, hint.width()), max(0, hint.height()))


def compute_help_dialog_size(dialog) -> tuple[int, int]:
    dialog.ensurePolished()
    nav_widget = getattr(dialog, "nav_widget", None)
    back_bar = getattr(dialog, "_back_bar", None)

    nav_width = 0
    if nav_widget is not None and nav_widget.isVisible():
        hint_w, _ = _size_hint(nav_widget)
        splitter = getattr(dialog, "_splitter", None)
        live_w = 0
        if splitter is not None and splitter.sizes():
            live_w = splitter.sizes()[0]
        nav_width = max(
            HELP_SIDEBAR_DEFAULT_WIDTH,
            HELP_NAV_MIN_WIDTH,
            hint_w,
            nav_widget.minimumWidth(),
            live_w,
        )

    # Never call adjustSize on the scroll area or its live page widgets —
    # QScrollArea sizeHint is often 0x0, and adjustSize collapses the viewport
    # (or hub cards) into a blank / tiny pane.
    content_width = HELP_CONTENT_MIN_WIDTH
    content_height = HELP_MIN_HEIGHT
    page = _visible_help_page(dialog)
    if page is not None:
        page_w, page_h = _size_hint(page)
        content_width = max(content_width, page_w)
        content_height = max(
            content_height,
            min(page_h, HELP_MAX_CONTENT_HEIGHT_PX),
        )

    bar_h = _size_hint(back_bar)[1]
    required_width = nav_width + content_width + HELP_SHELL_PADDING_PX
    required_height = content_height + bar_h + HELP_SHELL_PADDING_PX

    final_width = clamp(
        required_width,
        minimum=HELP_MIN_WIDTH,
        maximum=HELP_MAX_WIDTH,
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        max(required_height, HELP_MIN_HEIGHT),
        margin=HELP_HEIGHT_SCREEN_MARGIN_PX,
    )
    return final_width, final_height


def apply_help_dialog_geometry(dialog) -> None:
    width, height = compute_help_dialog_size(dialog)
    apply_dialog_geometry(
        dialog,
        width,
        height,
        policy=HELP_GEOMETRY_POLICY,
    )
