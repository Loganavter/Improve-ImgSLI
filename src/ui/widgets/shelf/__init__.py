"""Shared shelf widget and infrastructure.

``ShelfWidget`` is the base class for all shelf-style panels
(session picker recent shelf, color picker recent shelf, etc.).

Subpackages provide reusable building blocks:
- ``layout`` — geometry constants and calculations
- ``selection`` — card selection helpers
- ``corner_cover`` — viewport corner overlay
- ``empty_drop_zone`` — empty-state drop target
- ``relative_time`` — timestamp formatting
"""

from ui.widgets.shelf.widget import (  # noqa: F401
    OpaqueFillHost,
    PANEL_RADIUS,
    SHELF_MARGIN_BOTTOM,
    SHELF_MARGIN_LEFT,
    SHELF_MARGIN_RIGHT,
    SHELF_MARGIN_TOP,
    SHELF_SPACING,
    ShelfWidget,
    apply_opaque_widget_fill,
)

__all__ = [
    "OpaqueFillHost",
    "PANEL_RADIUS",
    "SHELF_MARGIN_BOTTOM",
    "SHELF_MARGIN_LEFT",
    "SHELF_MARGIN_RIGHT",
    "SHELF_MARGIN_TOP",
    "SHELF_SPACING",
    "ShelfWidget",
    "apply_opaque_widget_fill",
]
