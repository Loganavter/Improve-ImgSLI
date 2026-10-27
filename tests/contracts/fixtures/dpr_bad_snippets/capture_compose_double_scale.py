# provenance: src/core/control/capture.py:118 @ 230431a52^ (parent of #755)
# rule: double-scale
"""RED fixture: the live capture multiplied the DPR twice.

Verbatim (docstring trimmed) from the pre-#755 `compose_rhi_frames`. The
`QPixmap` is a `grabWindow` result and therefore ALREADY carries
`devicePixelRatio == 2` on a HiDPI host, so its painter works in
device-independent coordinates — and every coordinate below is then multiplied
by `dpr` on top. Measured on a real painter: a canvas meant for device
`(200,100)-(600,300)` landed at `(400,200)-(1198,598)`.
"""

from __future__ import annotations


def compose_rhi_frames(target, pixmap) -> int:
    from PySide6.QtCore import QPoint, QRectF
    from PySide6.QtGui import QPainter

    try:
        dpr = float(pixmap.devicePixelRatio() or 1.0)
    except Exception:
        dpr = 1.0
    try:
        on_grab = QRectF(0.0, 0.0, float(pixmap.width()), float(pixmap.height()))
    except Exception:
        return 0
    painter = None
    painted = 0
    for widget in target.findChildren(object):
        width = int(widget.width())
        height = int(widget.height())
        frame = widget.grabFramebuffer()
        anchor = target.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
        rect = QRectF(
            float(anchor.x()) * dpr,
            float(anchor.y()) * dpr,
            float(width) * dpr,
            float(height) * dpr,
        )
        if not rect.intersects(on_grab):
            continue
        if painter is None:
            painter = QPainter(pixmap)
        painter.drawImage(rect, frame)
        painted += 1
    if painter is not None:
        painter.end()
    return painted
