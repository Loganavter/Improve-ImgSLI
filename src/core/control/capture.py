"""Live capture: grab a running surface (window/chrome + canvas frames).

Split out of ``core/control/discovery.py`` (2026-10-17) when the canvas
compositing pushed that module past the 500-line audit limit — the same
reason ``FILE_SIZE_POLICY.md`` splits any growing module. Discovery keeps
the surface lookup (``resolve_capture_target``) and the socket/pointer
plumbing; this module owns what a grab *is*.

The live grab is two layers plus one correction:

1. the X-level window grab (``QScreen.grabWindow``) or the widget raster
   (``QWidget.grab``) — chrome, cards, thumbnails;
2. the correction: a presenting ``QRhiWidget`` canvas owns a swapchain
   surface that is part of **neither** grab path, so a capture used to
   show whatever raster layer sat behind the canvas (the cover plate, the
   panel) — which reads as "the canvas is blank/broken". The canvas does
   know its own last frame (``QRhiWidget.grabFramebuffer``), so that frame
   is painted in at the canvas's geometry (``compose_rhi_frames``).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .discovery import MethodError, resolve_capture_target


def compose_rhi_frames(target: Any, pixmap: Any) -> int:
    """Paint the visible ``QRhiWidget`` canvases into *pixmap* (live grabs).

    A presenting canvas owns a swapchain surface that is part of neither
    ``QScreen.grabWindow`` nor ``QWidget.grab`` — the live capture used to
    show whatever raster layer sat behind the canvas (the cover plate, or
    the window background), which reads as "the canvas is blank/broken".
    The canvas itself still knows its last frame
    (``QRhiWidget.grabFramebuffer``), so the honest capture is the window
    raster plus each visible canvas painted at its own geometry.

    Returns how many canvases were painted (0 = nothing to add). Canvases
    are looked up from *target*'s top-level window, not from *target*
    itself: the Quick Look canvas lives in an in-window overlay parented to
    the window, so a tab-page grab would otherwise miss the very canvas
    the caller is looking at. Only canvases whose rect actually lands on
    the grab are painted; a canvas that is hidden, has not rendered yet,
    cannot hand its frame over, or returns a null image is skipped rather
    than failing the capture — the grab stays useful either way and never
    raises.
    """
    try:
        from PySide6.QtCore import QPoint, QRectF
        from PySide6.QtGui import QPainter
    except Exception:
        return 0
    try:
        from PySide6.QtWidgets import QRhiWidget
    except Exception:
        return 0
    root = target
    try:
        window = target.window()
        if window is not None:
            root = window
    except Exception:
        root = target
    try:
        widgets = root.findChildren(QRhiWidget)
    except Exception:
        return 0
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
    try:
        for widget in widgets:
            try:
                if not widget.isVisible():
                    continue
                width = int(widget.width())
                height = int(widget.height())
                if width <= 0 or height <= 0:
                    continue
                frame = widget.grabFramebuffer()
                if frame is None or frame.isNull():
                    continue
                # mapTo(target, ...) only promises ancestors; go through the
                # screen so a canvas under a sibling/overlay still lands right.
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
            except Exception:
                continue
    finally:
        if painter is not None:
            try:
                painter.end()
            except Exception:
                pass
    return painted


def _target_visible_geometry(app: Any, target: Any) -> tuple[Any, bool]:
    """(*target*-local on-screen rect, fully_visible) — fail-open to (None, True).

    A window that is not fully inside the display has **no pixels** outside
    it: an X grab returns black there, which a reader mistakes for a broken
    widget (live 2026-10-17: the private Xvfb was smaller than the app
    window, and the black landed on the toolbar/footer exactly where a real
    defect would look). Never raises.
    """
    try:
        from PySide6.QtCore import QPoint, QRect

        screen = app.primaryScreen() if app is not None else None
        if screen is None:
            return None, True
        available = screen.availableGeometry()
        origin = target.mapToGlobal(QPoint(0, 0))
        local = QRect(0, 0, int(target.width()), int(target.height()))
        on_screen = QRect(
            int(available.x()) - int(origin.x()),
            int(available.y()) - int(origin.y()),
            int(available.width()),
            int(available.height()),
        )
        visible = local.intersected(on_screen)
        return visible, bool(local.isValid() and visible == local)
    except Exception:
        return None, True


def _raster_grab(target: Any) -> Any:
    """Qt-rendered grab of *target* (whole widget tree, display-independent)."""
    try:
        pixmap = target.grab()
    except Exception:
        return None
    try:
        return None if pixmap is None or pixmap.isNull() else pixmap
    except Exception:
        return None


def grab_window(app: Any, target: Any) -> tuple[Any, str, int]:
    """Live grab: the widget raster or the X window, + the canvas frames.

    Order is deliberate. A target that is **not fully on screen** is tried
    with the Qt raster first: ``QWidget.grab`` renders the widget tree with
    no X server involved, so the whole window has content, while the X grab
    of the same window returns black for the off-screen part (see
    ``_target_visible_geometry``). A fully visible target keeps the X grab
    (real screen pixels). Either way the canvas frames are composed in (the
    swapchain surface is in neither grab path — see ``compose_rhi_frames``).
    When only the X grab is possible and it is partly off screen, the
    pixmap is clipped to its visible part so black is never presented as
    content.
    """
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


def _clip_to_visible(pixmap: Any, visible: Any) -> Any:
    """Clip a grab to its on-screen rect (no black presented as content)."""
    if visible is None:
        return pixmap
    try:
        if visible.isValid() and not visible.isEmpty():
            return pixmap.copy(visible)
    except Exception:
        pass
    return pixmap


def capture_live_png(app: Any, window: Any, what: Any, out_dir: Any) -> dict[str, Any]:
    """Grab the live window/tab into *out_dir* and report what was produced."""
    if str(what or "") == "screen":
        # TEMP REPRO INSTRUMENT (not for commit): whole-screen grab.
        screen = app.primaryScreen() if app is not None else None
        if screen is not None:
            try:
                pm = screen.grabWindow(0)
                if pm is not None and not pm.isNull():
                    path = Path(out_dir) / f"live-capture-screen-{time.strftime('%Y%m%d-%H%M%S')}.png"
                    pm.save(str(path), "PNG")
                    return {"path": str(path), "what": "screen", "method": "screen_grab",
                            "size": [pm.width(), pm.height()], "rhi_layers": 0}
            except Exception as exc:
                return {"path": "", "what": "screen", "method": "screen_grab_failed",
                        "size": [0, 0], "rhi_layers": 0, "error": str(exc)}
    target, label = resolve_capture_target(app, window, what)
    if target is None:
        raise MethodError(
            "no live window to capture",
            "pass what=<tab> (see list_surfaces) or focus a window first",
        )
    pixmap, method, rhi_layers = grab_window(app, target)
    if pixmap is None:
        raise MethodError(
            f"could not grab {label}",
            "run on a real display (a private Xvfb), not the offscreen platform",
        )
    path = Path(out_dir) / f"live-capture-{label}-{time.strftime('%Y%m%d-%H%M%S')}.png"
    if not pixmap.save(str(path), "PNG"):
        raise MethodError(
            f"could not write {path}", "check IMGSLI_MCP_ARTIFACTS is writable"
        )
    return {
        "path": str(path),
        "what": label,
        "method": method,
        "size": [pixmap.width(), pixmap.height()],
        # How many live canvas frames were composited on top of the raster
        # grab; 0 means the captured widget had no presenting canvas.
        "rhi_layers": int(rhi_layers),
    }
