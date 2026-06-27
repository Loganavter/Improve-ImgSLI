"""Platform-facing helpers exposed to tabs.

This module is the official seam through which tab code can access generic
host-side utilities (dialog decoration, app-wide styling hooks, etc.) without
importing platform-private modules (``shared_toolkit``, ``resources.*``,
``ui.*``). The tab-isolation contract test allows tabs to import from
``tabs.*``, so re-exporting these helpers here keeps the dependency direction
correct: tab → tabs.host_helpers → platform.

Only generic, tab-agnostic helpers belong here. Anything specific to a single
tab must live inside that tab's own package.
"""

from __future__ import annotations

from shared_toolkit.ui.decorate_dialog import decorate_dialog


__all__ = ["decorate_dialog"]
