"""App-level color picker suite.

Product-owned (picker integration is not a toolkit concern): the dialog, the
recents shelf, the swatch button, and the value-field formatting logic live
together here. External consumers import from this package's public names.
"""

from __future__ import annotations

from ui.widgets.color.picker_dialog import ColorPickerDialog
from ui.widgets.color.recents import (
    RECENT_COLORS_CAP,
    RecentColorsRow,
    RecentColorsStore,
    color_to_hex_string,
    parse_hex_color,
)
from ui.widgets.color.swatch import ColorSwatch
from ui.widgets.color.value_format import (
    ValueFormat,
    color_format_label,
    color_value_has_alpha,
    format_color_value,
    next_color_format,
    parse_color_value,
)

__all__ = [
    "ColorPickerDialog",
    "ColorSwatch",
    "RECENT_COLORS_CAP",
    "RecentColorsRow",
    "RecentColorsStore",
    "ValueFormat",
    "color_format_label",
    "color_to_hex_string",
    "color_value_has_alpha",
    "format_color_value",
    "next_color_format",
    "parse_color_value",
    "parse_hex_color",
]