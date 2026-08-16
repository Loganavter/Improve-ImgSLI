"""Shared window-edge padding for workspace control rows.

Both workspace tabs (``image_compare``, ``multi_compare``) and plugins
(``settings``, ``help``, …) build control rows / footers that must line up
flush with each other from the window edge. Keep the single design-px value
here instead of each consumer picking its own inset; all callers resolve it
through ``control_edge_padding()`` so it scales with ``UiScale``.
"""

from __future__ import annotations

from sli_ui_toolkit.managers import scaled_px

CONTROL_EDGE_PADDING_PX = 8


def control_edge_padding() -> int:
    """Horizontal window-edge padding for control rows, in live (scaled) px."""
    return scaled_px(CONTROL_EDGE_PADDING_PX)
