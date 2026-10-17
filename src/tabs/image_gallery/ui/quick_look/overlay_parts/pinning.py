"""QuickLookOverlay pinning — resize re-pins (insets/nav/grip) + sizeHint.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators. ``super()`` becomes an explicit
``TopLevelInWindowOverlay`` call (the sole base) — same resolution.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import TopLevelInWindowOverlay


def _reposition_source_inset(self) -> None:
    # Source/crop inset blocks are absolute children of the preview
    # (bottom-left over the image) — re-pin with every resize, then nav.
    try:
        from tabs.image_gallery.ui.quick_look.insets import reposition_preview_insets
        reposition_preview_insets(self)
    except Exception:
        pass
    # W4 item 6: nav circles are absolute card children — re-pin with
    # every resize.
    try:
        from tabs.image_gallery.ui.quick_look.helpers import reposition_nav_buttons
        reposition_nav_buttons(self)
    except Exception:
        pass


def resizeEvent(self, event):  # noqa: N802
    TopLevelInWindowOverlay.resizeEvent(self, event)
    try:
        self._reposition_source_inset()
    except Exception:
        pass
    # W8: keep the drag handle pinned on overlay (window) resizes.
    try:
        from tabs.image_gallery.ui.quick_look.helpers import reposition_grip
        reposition_grip(self)
    except Exception:
        pass


def sizeHint(self) -> QSize:  # noqa: N802
    # Matches the content floor (1040x680 for three artifact rows).
    return QSize(scaled_px(1040), scaled_px(680))
