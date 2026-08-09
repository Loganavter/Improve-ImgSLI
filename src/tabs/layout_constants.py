"""Shared control-panel layout constants for workspace tabs.

Both ``image_compare`` and ``multi_compare`` build their own per-tab control
rows (save button, magnifier/settings panels, footers) independently. Reuse a
single edge-padding value here instead of each tab picking its own inset, so
controls line up flush with each other from the window edge across tabs.
"""

from __future__ import annotations

CONTROL_EDGE_PADDING_PX = 8
