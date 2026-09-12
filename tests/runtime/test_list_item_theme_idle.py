"""List row idle background must blend with the panel, not read as hover.

Regression 1: the light theme's ``list_item.background.normal`` (#f7f7f7)
was a visible grey patch on the white flyout panel — idle rows looked
hovered. Idle must match the panel background so only hover/current rows
stand out (same contract as the dark theme and the toolkit FLUENT
palette).

Regression 2: the dark theme's ``list_item.background.hover`` (#424242)
was only 4% lighter than the panel (#383838) — hovering a row was
visually indistinguishable from idle. The hover fill must be clearly
darker/lighter than the panel in both themes.
"""

from __future__ import annotations

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE


def _luma(color) -> int:
    return color.red() + color.green() + color.blue()


def test_idle_list_item_matches_panel_background():
    # ``flyout.background`` was unified into ``surface.background`` (toolkit
    # ThemeManager ALIAS); the panel token is now ``surface.background``.
    for palette in (LIGHT_THEME_PALETTE, DARK_THEME_PALETTE):
        assert palette["list_item.background.normal"] == palette["surface.background"]
        assert (
            palette["list_item.background.normal"]
            != palette["list_item.background.hover"]
        )


def test_hover_fill_is_clearly_distinct_from_panel():
    for palette in (LIGHT_THEME_PALETTE, DARK_THEME_PALETTE):
        panel = palette["surface.background"]
        hover = palette["list_item.background.hover"]
        # At least ~7% channel shift: the old dark hover (4%) read as idle.
        assert abs(_luma(hover) - _luma(panel)) >= 55
