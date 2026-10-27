# provenance: src/tabs/image_compare/canvas/features/drag_drop_overlay/passes.py:87 @ reconstructed
# rule: raster-logical-tagged
"""RED fixture: a LOGICAL raster tagged with the device pixel ratio.

Reconstructed from the pre-#751 rasterizer (`167b9d820^`): when
`ctx.framebuffer_size` was absent it allocated the raster at the context's
LOGICAL `width`/`height`, and the device size was expected to come from the
painter scale. Tagging that raster with `setDevicePixelRatio` — the shape the
glass-panel readback uses for its DEVICE-pixel readback
(`src/engine/gpu/glass_panel.py:923`) — makes Qt treat the canvas as `size/dpr`,
so the drawing lands in the top-left corner and the rest of the overlay is
empty. That is the same owner report from the other side: the drop zone looked
smaller at a larger interface scale.

The repaired form sizes the raster from `framing.framebuffer_size(host, ctx)`
(device px) and either paints through a painter scale (untagged, negative
fixture `legal_untagged_raster_scale.py`) or tags a device-sized raster.
"""

from __future__ import annotations

from PySide6.QtGui import QImage


def _raster_image(host, ctx):
    width = int(getattr(ctx, "width", 0) or host.width())
    height = int(getattr(ctx, "height", 0) or host.height())
    img = QImage(
        max(1, width),
        max(1, height),
        QImage.Format.Format_RGBA8888_Premultiplied,
    )
    img.setDevicePixelRatio(float(host.devicePixelRatioF()))
    return img
