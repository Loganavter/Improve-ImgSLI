# provenance: src/core/control/capture.py:216 @ dc1ab6ed6^ (parent of the capture-dpr fix)
# rule: primary-screen-grab
"""RED fixture: the live grab asked the PRIMARY screen, not the target's.

Verbatim pre-`dc1ab6ed6` `grab_window` (docstring dropped). On a two-monitor
desktop with mixed scale factors the primary screen answers a different
`availableGeometry`, so the "is the window fully visible" verdict and the pixels
grabbed both belonged to the wrong display.
"""

from __future__ import annotations


def _raster_grab(target):
    try:
        pixmap = target.grab()
    except Exception:
        return None
    try:
        return None if pixmap is None or pixmap.isNull() else pixmap
    except Exception:
        return None


def grab_window(app, target) -> tuple[object, str, int]:
    visible, fully_visible = _target_visible_geometry(app, target)
    if not fully_visible:
        raster = _raster_grab(target)
        if raster is not None:
            return raster, "widget_grab", compose_rhi_frames(target, raster)
    screen = app.primaryScreen() if app is not None else None
    if screen is not None:
        try:
            pixmap = screen.grabWindow(int(target.winId()))
            if pixmap is not None and not pixmap.isNull():
                if not fully_visible:
                    pixmap = _clip_to_visible(pixmap, visible)
                return pixmap, "grabWindow", compose_rhi_frames(target, pixmap)
        except Exception:
            pass
    raster = _raster_grab(target)
    if raster is not None:
        return raster, "widget_grab", compose_rhi_frames(target, raster)
    return None, "", 0


def _target_visible_geometry(app, target):
    try:
        screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return None, True
        return screen.availableGeometry(), True
    except Exception:
        return None, True


def compose_rhi_frames(target, pixmap) -> int:
    return 0


def _clip_to_visible(pixmap, visible):
    return pixmap
