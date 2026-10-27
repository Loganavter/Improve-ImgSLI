# provenance: src/core/control/capture.py:196 @ 230431a52^ (parent of #755)
# rule: geometry-device-copy
"""RED fixture: a LOGICAL rect sliced straight out of a DEVICE-pixel grab.

Verbatim pre-#755 `_clip_to_visible`. `QScreen.grabWindow` answers device pixels
while the visible rect is widget-logical, so `copy(visible)` kept the top-left
`1/DPR²` of the window — measured 2026-10-27: a 2560x1600 grab with a 1280x700
visible rect came back 1280x700.

The catalog test loads this file and RUNS it, so the behavioural rule
`geometry-device-copy` has a falsification story: the current implementation
must keep 2560x1400 while this snippet still returns 1280x700.
"""

from __future__ import annotations


def _clip_to_visible(pixmap, visible):
    """Clip a grab to its on-screen rect (no black presented as content)."""
    if visible is None:
        return pixmap
    try:
        if visible.isValid() and not visible.isEmpty():
            return pixmap.copy(visible)
    except Exception:
        pass
    return pixmap
