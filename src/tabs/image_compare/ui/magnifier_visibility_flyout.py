"""Backward-compatibility re-export.

The canonical location is ``ui.widgets.panel_visibility_flyout``.
This module re-exports for any remaining imports from the old path.
"""

from ui.widgets.panel_visibility_flyout import PanelVisibilityFlyout as MagnifierVisibilityFlyout

__all__ = ["MagnifierVisibilityFlyout"]
