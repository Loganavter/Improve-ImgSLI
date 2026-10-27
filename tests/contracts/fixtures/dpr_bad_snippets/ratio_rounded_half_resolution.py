# provenance: src/ui/main_window/runtime.py:92 @ b59e846de (parent)
# rule: ratio-rounded
"""RED fixture: the device size was rounded from the RATIO itself.

Reconstructed from the defect `b59e846de` fixed: `_freeze_rhi_surfaces` passed
the widget's LOGICAL `size()` to `setFixedColorBufferSize(pixelSize)`, so at
DPR=2 the opt-in resize shield pinned a half-resolution buffer and Qt upscaled
it — the blur the shield exists to avoid. The same mistake written as a ratio
cast (`int(dpr)`) is this fixture: 1.25/1.5 collapse to 1, so the buffer is
allocated at the wrong geometry on every fractional-DPI host.

The repaired form is in the same file today (`_rhi_device_pixel_size`: prefer
`renderTarget().pixelSize()`, else `round(logical * devicePixelRatioF())`).
"""

from __future__ import annotations


def _rhi_device_pixel_size(rhi, logical_size):
    try:
        dpr = int(rhi.devicePixelRatioF())
    except Exception:
        dpr = 1
    return (logical_size[0] * dpr, logical_size[1] * dpr)
