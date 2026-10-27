# provenance: src/tabs/image_gallery/ui/quick_look/overlay_build/icons.py:51 @ reconstructed
# rule: ratio-hardcoded
"""RED fixture: a raster planted with a hardcoded ratio of 2.

Reconstructed from the incident class in
`src/tabs/image_gallery/ui/card/context_menu/icons.py` and
`.../overlay_build/icons.py` (@ 230431a52), whose fixed form asks the SOURCE:

    out = QPixmap(pm.size())
    out.setDevicePixelRatio(pm.devicePixelRatio())

Hardcoding 2 instead of asking is invisible on the 2x host where it was written
and wrong on a 1x or 1.5x one: at DPR=1 the copy is drawn at half size, at 1.5
it is 33% too big.
"""

from __future__ import annotations

from PySide6.QtGui import QPixmap


def _copy_icon(pm: QPixmap) -> QPixmap:
    out = QPixmap(pm.size())
    out.setDevicePixelRatio(2)
    return out
