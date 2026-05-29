"""Canonical input-session owner IDs.

These string IDs identify who currently drives a canvas input session. The
shared session service and each feature's ``gestures.py`` must agree on the
exact values — if they diverge, the session service silently never sees the
owner and the gesture stops working. They are defined once here so no module
re-declares them.
"""

from __future__ import annotations

KEYBOARD_MOVE_OWNER = "keyboard_move"
CAPTURE_DRAG_OWNER = "capture_drag"
SPLIT_DRAG_OWNER = "split_drag"
INTERNAL_SPLIT_DRAG_OWNER = "internal_split_drag"
