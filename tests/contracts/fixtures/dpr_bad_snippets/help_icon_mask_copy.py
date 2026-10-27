# provenance: src/plugins/help/icons.py:94 @ 230431a52
# rule: ratio-dropped-on-copy
"""RED fixture: a new raster built from another raster's size, ratio dropped.

Verbatim `_mask_pixmap` from the current tree. `QPixmap(source.size())` copies
the DEVICE size and gets `devicePixelRatio() == 1.0`, while `source` may carry
2.0 — the copy would then be drawn at half size in the top-left corner. It is
allowlisted in the tree because `QIcon.pixmap(QSize)` returns ratio 1.0 even at
`QT_SCALE_FACTOR=2` (measured), so today the two agree; the shape is one
`QPixmap(source.size())` call away from the shipped gallery defect.

The sibling that was fixed (#302, `tabs/image_gallery/ui/card/context_menu/
icons.py`) copies the ratio explicitly:

    out = QPixmap(pm.size())
    out.setDevicePixelRatio(pm.devicePixelRatio())
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap


def _mask_pixmap(source: QPixmap, color: QColor) -> QPixmap:
    """Return *source*'s alpha silhouette filled with *color*."""
    masked = QPixmap(source.size())
    masked.fill(Qt.GlobalColor.transparent)
    painter = QPainter(masked)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(masked.rect(), color)
    painter.end()
    return masked
