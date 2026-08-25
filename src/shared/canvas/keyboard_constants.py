"""Shared keyboard pan/zoom constants — single source for B9.

Both ``tabs.image_compare.canvas.interaction`` and
``tabs.multi_compare.canvas.interaction`` duplicated the same key sets and
nudge fraction. Bodies differ legitimately, only constants are shared.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

KEY_PAN = {
    Qt.Key.Key_Left,
    Qt.Key.Key_Right,
    Qt.Key.Key_Up,
    Qt.Key.Key_Down,
}

KEY_ZOOM_IN = {
    Qt.Key.Key_Plus,
    Qt.Key.Key_Equal,
}

KEY_ZOOM_OUT = {
    Qt.Key.Key_Minus,
}

# Pan nudge as fraction of widget width/height per arrow press; scaled by zoom
# so a nudge stays a fixed *screen* distance.
KEY_PAN_NUDGE = 0.05
