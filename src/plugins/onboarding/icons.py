"""Demo icons for onboarding slides — shared app assets, not tab icons."""

from __future__ import annotations

from enum import Enum


class DemoIcon(Enum):
    """Filenames match shared toolbar icons under the app asset pack."""

    VERTICAL_SPLIT = "vertical_split.svg"
    HORIZONTAL_SPLIT = "horizontal_split.svg"
    DIVIDER_VISIBLE = "divider_visible.svg"
    DIVIDER_HIDDEN = "divider_hidden.svg"
    DIVIDER_COLOR = "divider_color.svg"
    DIVIDER_WIDTH = "divider_width.svg"
