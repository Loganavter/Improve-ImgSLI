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

Units (the 2026-10-27 defect, both halves): everything Qt hands back — a
``QScreen.grabWindow`` pixmap, a ``QWidget.grab()`` pixmap,
``QRhiWidget.grabFramebuffer()`` — is DEVICE pixels, while widget geometry and
the coordinate system of a ``QPainter`` on a pixmap carrying a
``devicePixelRatio`` are LOGICAL. So the DPR is applied exactly once, by the
object that owns it: a painter target rect stays logical
(``compose_rhi_frames``), a logical crop of a grab is scaled by the grab's own
DPR (``_clip_to_visible``), and sizes that mean one of the two say so in their
name (``_device_independent_size``, ``_device_pixel_ratio``).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .discovery import MethodError, resolve_capture_target


def _device_pixel_ratio(pixmap: Any) -> float:
    """The grab's own device px per logical px; ``1.0`` when it cannot answer."""
    try:
        return float(pixmap.devicePixelRatio() or 1.0)
    except Exception:
        return 1.0


def _device_independent_size(pixmap: Any) -> tuple[float, float]:
    """(*pixmap*'s size in LOGICAL px) — the space a ``QPainter`` on it uses.

    ``QPixmap.width()/height()`` are DEVICE pixels, while a ``QPainter`` on a
    pixmap that carries a ``devicePixelRatio`` paints in device-INDEPENDENT
    coordinates. Comparing the two ("is this canvas on the grab?") or scaling a
    logical rect by the DPR before drawing mixes the two spaces — the
    2026-10-27 defect: a canvas meant for device ``(200,100)-(600,300)`` at
    DPR=2 landed in ``(400,200)-(1198,598)``.
    """
    try:
        size = pixmap.deviceIndependentSize()
        return float(size.width()), float(size.height())
    except Exception:
        pass
    try:
        dpr = _device_pixel_ratio(pixmap)
        return float(pixmap.width()) / dpr, float(pixmap.height()) / dpr
    except Exception:
        return 0.0, 0.0


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

    Units: the widget geometry below (``anchor``/``width``/``height``) and the
    painter's coordinate system on *pixmap* are both LOGICAL, so the target
    rect is built from logical numbers only; the pixmap's own
    ``devicePixelRatio`` (and the frame's, which ``drawImage`` absorbs) applies
    the DPR exactly once. The grab rect comes from
    ``deviceIndependentSize()`` for the same reason — ``width()`` is device px.
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
    grab_width_logical, grab_height_logical = _device_independent_size(pixmap)
    if grab_width_logical <= 0.0 or grab_height_logical <= 0.0:
        return 0
    on_grab = QRectF(0.0, 0.0, grab_width_logical, grab_height_logical)
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
                # LOGICAL rect: the painter already applies the pixmap's DPR.
                rect_logical = QRectF(
                    float(anchor.x()),
                    float(anchor.y()),
                    float(width),
                    float(height),
                )
                if not rect_logical.intersects(on_grab):
                    continue
                if painter is None:
                    painter = QPainter(pixmap)
                # ``drawImage(QRectF, QImage)`` scales the DEVICE-pixel frame
                # into this logical rect, so the frame is handed over as is.
                painter.drawImage(rect_logical, frame)
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


def _target_screen(app: Any, target: Any) -> Any:
    """The screen *target* is on — not the application's primary screen.

    Both grab paths ask for the **target's** display. On a two-monitor desktop
    with different scale factors the primary screen answers a different
    ``availableGeometry`` (a false "fully visible" verdict) and grabs the wrong
    screen's pixels, so the visible-rect clip and the grab disagree with the
    window. The platform window Qt actually put on that display is the honest
    answer (``windowHandle().screen()``); a widget still answers ``screen()``;
    a duck-typed target that answers neither keeps the primary-screen fallback
    (the pre-2026-10-27 behaviour), so a stub or an unmapped widget still works.
    """
    try:
        handle = target.windowHandle()
    except Exception:
        handle = None
    if handle is not None:
        try:
            screen = handle.screen()
        except Exception:
            screen = None
        if screen is not None:
            return screen
    try:
        screen = target.screen()
    except Exception:
        screen = None
    if screen is not None:
        return screen
    try:
        return app.primaryScreen() if app is not None else None
    except Exception:
        return None


def _target_visible_geometry(app: Any, target: Any) -> tuple[Any, bool]:
    """(*target*-local LOGICAL on-screen rect, fully_visible) — fail-open.

    A window that is not fully inside the display has **no pixels** outside
    it: an X grab returns black there, which a reader mistakes for a broken
    widget (live 2026-10-17: the private Xvfb was smaller than the app
    window, and the black landed on the toolbar/footer exactly where a real
    defect would look). Never raises.

    Both rects are LOGICAL (widget coordinates): the caller that crops a
    device-pixel grab scales them by the grab's own DPR (``_clip_to_visible``).
    """
    try:
        from PySide6.QtCore import QPoint, QRect

        screen = _target_screen(app, target)
        if screen is None:
            return None, True
        available = screen.availableGeometry()
        origin = target.mapToGlobal(QPoint(0, 0))
        local_logical = QRect(0, 0, int(target.width()), int(target.height()))
        on_screen_logical = QRect(
            int(available.x()) - int(origin.x()),
            int(available.y()) - int(origin.y()),
            int(available.width()),
            int(available.height()),
        )
        visible_logical = local_logical.intersected(on_screen_logical)
        return visible_logical, bool(
            local_logical.isValid() and visible_logical == local_logical
        )
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

    Units: *visible* from ``_target_visible_geometry`` is LOGICAL; the X grab
    is DEVICE pixels. The grab asks the target's own screen (see
    ``_target_screen``) and ``_clip_to_visible`` does the DPR conversion.
    """
    visible, fully_visible = _target_visible_geometry(app, target)
    if not fully_visible:
        raster = _raster_grab(target)
        if raster is not None:
            return raster, "widget_grab", compose_rhi_frames(target, raster)
    screen = _target_screen(app, target)
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


def _clip_to_visible(pixmap: Any, visible_logical: Any) -> Any:
    """Clip a grab to its on-screen rect (no black presented as content).

    *visible_logical* comes from ``_target_visible_geometry`` and is LOGICAL;
    a ``QScreen.grabWindow`` pixmap is DEVICE pixels. The crop rect is therefore
    scaled by the pixmap's own ``devicePixelRatio``: slicing the logical rect
    straight out of a DPR=2 grab returned the top-left 1/DPR² of the window
    (measured 2026-10-27: a 2560x1600 grab with a 1280x700 visible rect came
    back 1280x700 instead of 2560x1400).
    """
    if visible_logical is None:
        return pixmap
    try:
        from PySide6.QtCore import QRect

        if not visible_logical.isValid() or visible_logical.isEmpty():
            return pixmap
        dpr = _device_pixel_ratio(pixmap)
        visible_device = QRect(
            int(round(visible_logical.x() * dpr)),
            int(round(visible_logical.y() * dpr)),
            int(round(visible_logical.width() * dpr)),
            int(round(visible_logical.height() * dpr)),
        )
        clipped = pixmap.copy(visible_device)
        if clipped is None or clipped.isNull():
            return pixmap
        return clipped
    except Exception:
        pass
    return pixmap


def capture_live_png(app: Any, window: Any, what: Any, out_dir: Any) -> dict[str, Any]:
    """Grab the live window/tab into *out_dir* and report what was produced."""
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
        # The PNG's own pixels, i.e. DEVICE px (a DPR=2 grab is twice its
        # logical size); a caller comparing it to widget geometry must divide
        # by the pixmap's devicePixelRatio.
        "size": [pixmap.width(), pixmap.height()],
        # How many live canvas frames were composited on top of the raster
        # grab; 0 means the captured widget had no presenting canvas.
        "rhi_layers": int(rhi_layers),
    }
