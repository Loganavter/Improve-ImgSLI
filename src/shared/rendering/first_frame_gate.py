"""Shared first-frame present gate for QRhi canvases.

Both canvas tabs must wait for the same number of recorded presents before
declaring the first frame "on screen": on Wayland/Vulkan the compositor keeps
showing the untouched (transparent) subsurface for several recorded presents,
and only a later present actually reaches the display. If
``firstFrameRendered`` fires earlier, the startup placeholder lifts while the
canvas is still a see-through hole.

Kept in one place so the two tabs stay in sync (each canvas aliases
``_first_visual_present_count``/``_FIRST_PRESENT_SETTLE_COUNT`` to these).
"""

from __future__ import annotations

# Empirically the first present that reaches the display on Wayland/Vulkan is
# around the 4th recorded one; 10 keeps a generous margin so the placeholder
# never lifts onto a transparent surface. The settle count must be >= the
# visual count, otherwise the settle-flush chain stops before the emit point.
FIRST_PRESENT_SETTLE_COUNT = 10


def first_visual_present_count() -> int:
    """Presents required before first-frame signals are emitted."""
    return FIRST_PRESENT_SETTLE_COUNT


def first_present_settle_count() -> int:
    """Presents that get a compositor settle kick after recording."""
    return FIRST_PRESENT_SETTLE_COUNT
