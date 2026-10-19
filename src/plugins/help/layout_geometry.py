"""Help dialog content-driven geometry.

Design px live here as plain ints; every resolver below reads the live
``UiScale`` factor **at call time**. The size recipe and the geometry policy
used to consume these numbers raw, so at interface scale 1.25/1.5 the window
bracket stayed at design px while the scaled help rows/nav grew ("dialogs
stranded at design px" class, plan ``plan-live-appearance-fixes-2026-10-19``).
Nothing in this module scales at import: the working sibling is
``plugins/export/layout_geometry.py``.

``HELP_SIDEBAR_*`` stay design-space constants because ``plugins/help/dialog.py``
owns their live resolution (it wraps them in ``scaled_px`` at its own use
sites); the resolvers below are for this module's own consumers.
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


def help_min_dialog_width() -> int:
    return scaled_px(HELP_MIN_WIDTH)


def help_max_dialog_width() -> int:
    return scaled_px(HELP_MAX_WIDTH)


def help_min_dialog_height() -> int:
    return scaled_px(HELP_MIN_HEIGHT)


def help_content_min_width() -> int:
    return scaled_px(HELP_CONTENT_MIN_WIDTH)


def help_shell_padding() -> int:
    return scaled_px(HELP_SHELL_PADDING_PX)


def help_sidebar_min_width() -> int:
    return scaled_px(HELP_SIDEBAR_MIN_WIDTH)


def help_sidebar_default_width() -> int:
    return scaled_px(HELP_SIDEBAR_DEFAULT_WIDTH)


def help_sidebar_max_width() -> int:
    return scaled_px(HELP_SIDEBAR_MAX_WIDTH)


def help_nav_min_width() -> int:
    return scaled_px(HELP_NAV_MIN_WIDTH)


def help_height_screen_margin() -> int:
    return scaled_px(HELP_HEIGHT_SCREEN_MARGIN_PX)


def help_max_content_height() -> int:
    return scaled_px(HELP_MAX_CONTENT_HEIGHT_PX)


def help_geometry_policy() -> GeometryApplyPolicy:
    """The dialog's geometry policy, with floor/bounds resolved at THIS call."""
    return GeometryApplyPolicy(
        resize_when_hidden=True,
        update_minimum=True,
        minimum_floor=(help_min_dialog_width(), help_min_dialog_height()),
        width_bounds=(help_min_dialog_width(), help_max_dialog_width()),
        center_on_parent=True,
        remember_key="help",
    )


def _visible_help_page(dialog) -> QWidget | None:
    hub = getattr(dialog, "_hub_page", None)
    if hub is not None and not hub.isHidden():
        return hub
    document = getattr(dialog, "_document", None)
    if document is not None and not document.isHidden():
        return document
    return getattr(dialog, "_content_host", None)


def compute_help_dialog_size(dialog) -> tuple[int, int]:
    dialog.ensurePolished()
    nav_widget = getattr(dialog, "nav_widget", None)
    back_bar = getattr(dialog, "_back_bar", None)

    nav_width = 0
    if nav_widget is not None and getattr(nav_widget, "isVisible", lambda: False)():
        hint_w, _ = _size_hint(nav_widget)
        splitter = getattr(dialog, "_splitter", None)
        live_w = 0
        if splitter is not None and splitter.sizes():
            live_w = splitter.sizes()[0]
        nav_width = max(
            help_sidebar_default_width(),
            help_nav_min_width(),
            hint_w,
            getattr(nav_widget, "minimumWidth", lambda: 0)(),
            live_w,
        )

    # Never call adjustSize on the scroll area or its live page widgets —
    # QScrollArea sizeHint is often 0x0, and adjustSize collapses the viewport
    # (or hub cards) into a blank / tiny pane.
    content_width = help_content_min_width()
    content_height = help_min_dialog_height()
    page = _visible_help_page(dialog)
    if page is not None:
        page_w, page_h = _size_hint(page)
        content_width = max(content_width, page_w)
        content_height = max(
            content_height,
            min(page_h, help_max_content_height()),
        )

    bar_h = _size_hint(back_bar)[1]
    required_width = nav_width + content_width + help_shell_padding()
    required_height = content_height + bar_h + help_shell_padding()

    final_width = clamp(
        required_width,
        minimum=help_min_dialog_width(),
        maximum=help_max_dialog_width(),
    )
    _final_w, final_height = clamp_to_screen(
        final_width,
        max(required_height, help_min_dialog_height()),
        margin=help_height_screen_margin(),
    )
    return final_width, final_height


def apply_help_dialog_geometry(dialog) -> None:
    width, height = compute_help_dialog_size(dialog)
    apply_dialog_geometry(
        dialog,
        width,
        height,
        policy=help_geometry_policy(),
    )
