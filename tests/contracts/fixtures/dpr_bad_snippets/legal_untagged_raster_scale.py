# provenance: src/tabs/multi_compare/canvas/features/drag_drop_overlay/passes.py:106 @ 230431a52
# rule: none
"""LEGAL fixture: a device-sized raster with an UNTAGGED painter.

Verbatim shape from the current multi_compare rasterizer. The raster is
allocated from `ctx.framebuffer_size` (device px) and carries no
devicePixelRatio, so `painter.scale(dpr, dpr)` is the ONE application of the
ratio that maps logical paint coordinates onto the device raster. Flagging it as
`double-scale` would be wrong: nothing below the painter is dpr-aware.

This fixture exists so the `double-scale` detector cannot be a substring alarm:
it must stay silent here and fire on `capture_compose_double_scale.py`, where
the painter target DOES carry a ratio.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter


def _raster_image(host, ctx):
    fb_w, fb_h = ctx.framebuffer_size
    img = QImage(
        max(1, int(fb_w)),
        max(1, int(fb_h)),
        QImage.Format.Format_RGBA8888_Premultiplied,
    )
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    dpr = max(1.0, float(host.devicePixelRatioF()))
    painter.save()
    painter.scale(dpr, dpr)
    painter.restore()
    painter.end()
    return img
