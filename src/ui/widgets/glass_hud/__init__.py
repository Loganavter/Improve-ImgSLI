"""App-level glass HUD suite — pinned corner chips over the canvas.

Shared frosted-glass flyout base (``GlassHUD``), its composited sprite
blitter (``panel_display``), and the two concrete HUD chips (``InfoHUD``,
``ZoomIndicator``). External consumers import from this package's public
names.
"""

from __future__ import annotations

from ui.widgets.glass_hud.hud import GlassHUD
from ui.widgets.glass_hud.info import InfoHUD
from ui.widgets.glass_hud.panel_display import (
    GlassPanelDisplayWidget,
    GlassPanelDisplayWidgetCpu,
    GlassPanelDisplayWidgetRhi,
    create_glass_panel_display_widget,
)
from ui.widgets.glass_hud.zoom import ZoomIndicator

__all__ = [
    "GlassHUD",
    "GlassPanelDisplayWidget",
    "GlassPanelDisplayWidgetCpu",
    "GlassPanelDisplayWidgetRhi",
    "InfoHUD",
    "ZoomIndicator",
    "create_glass_panel_display_widget",
]