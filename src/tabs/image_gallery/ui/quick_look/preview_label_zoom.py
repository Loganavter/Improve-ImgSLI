"""Quick-look QLabel fallback zoom — plain functions (no owner state).

Wheel-zoom + LMB/Middle-drag pan for the raster fallback label, reusing
the pure ``preview_zoom`` helpers so the fallback feels exactly like the
GPU canvas (same ``ZOOM_MIN..ZOOM_MAX`` idiom, same cursor-anchored
math). Split from ``preview.py`` (500-line contract gate); state stays
on the overlay (``_label_zoom/_label_pan_x/_label_pan_y/_label_drag``).

The canvas path resets its view per source (``set_source``); the label
path mirrors that via ``reset_label_zoom`` from
``_populate_preview_label``. At 1.0x every handler is a no-op so label
clicks keep their old behavior (swallowed by the card veil guard).
"""

from __future__ import annotations


def reset_label_zoom(overlay) -> None:
    """Reset the fallback view to whole-frame (never raises)."""
    for attr, val in (
        ("_label_zoom", 1.0),
        ("_label_pan_x", 0.0),
        ("_label_pan_y", 0.0),
        ("_label_drag", None),
    ):
        try:
            setattr(overlay, attr, val)
        except Exception:
            pass


def _view(overlay) -> tuple[float, float, float]:
    try:
        zoom = float(getattr(overlay, "_label_zoom", 1.0) or 1.0)
    except Exception:
        zoom = 1.0
    try:
        px = float(getattr(overlay, "_label_pan_x", 0.0) or 0.0)
    except Exception:
        px = 0.0
    try:
        py = float(getattr(overlay, "_label_pan_y", 0.0) or 0.0)
    except Exception:
        py = 0.0
    return zoom, px, py


def _has_full(overlay) -> bool:
    try:
        full = getattr(overlay, "_preview_full", None)
        return full is not None and not full.isNull()
    except Exception:
        return False


def label_wheel(overlay, delta_y, mx, my) -> bool:
    """Cursor-anchored wheel zoom on the fallback label.

    Returns True when the view changed (caller accepts the event).
    No-op (False) without a stashed preview or on a below-epsilon tick.
    """
    if not _has_full(overlay):
        return False
    try:
        from tabs.image_gallery.ui.quick_look.preview_zoom import wheel_zoom_pan
    except Exception:
        return False
    try:
        zoom, px, py = _view(overlay)
        got = wheel_zoom_pan(zoom, px, py, delta_y, mx, my)
    except Exception:
        return False
    if got is None:
        return False
    try:
        overlay._label_zoom, overlay._label_pan_x, overlay._label_pan_y = got
    except Exception:
        return False
    try:
        from tabs.image_gallery.ui.quick_look.preview import _rescale_preview_to_host

        _rescale_preview_to_host(overlay)
    except Exception:
        pass
    return True


def label_press(overlay, x, y, button) -> bool:
    """Start a fallback pan drag (zoomed only). True = panning started."""
    try:
        zoom, _, _ = _view(overlay)
        if zoom <= 1.0 + 1e-9:
            return False
        from PySide6.QtCore import Qt

        if button not in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            return False
    except Exception:
        return False
    try:
        overlay._label_drag = (float(x), float(y))
    except Exception:
        return False
    try:
        from PySide6.QtCore import Qt as _Qt

        label = getattr(overlay, "_preview_label", None)
        if label is not None:
            label.setCursor(_Qt.CursorShape.ClosedHandCursor)
    except Exception:
        pass
    return True


def label_move(overlay, x, y, w, h) -> bool:
    """Continue a fallback pan drag. True = view changed."""
    try:
        last = getattr(overlay, "_label_drag", None)
    except Exception:
        return False
    if last is None:
        return False
    try:
        from tabs.image_gallery.ui.quick_look.preview_zoom import drag_pan

        zoom, px, py = _view(overlay)
        got = drag_pan(px, py, float(x) - last[0], float(y) - last[1], w, h, zoom)
    except Exception:
        return False
    try:
        overlay._label_drag = (float(x), float(y))
    except Exception:
        pass
    if got is None:
        return False
    try:
        overlay._label_pan_x, overlay._label_pan_y = got
    except Exception:
        return False
    try:
        from tabs.image_gallery.ui.quick_look.preview import _rescale_preview_to_host

        _rescale_preview_to_host(overlay)
    except Exception:
        pass
    return True


def label_release(overlay) -> None:
    """End a fallback pan drag (never raises, never consumes)."""
    try:
        overlay._label_drag = None
    except Exception:
        pass
    try:
        from PySide6.QtCore import Qt as _Qt

        label = getattr(overlay, "_preview_label", None)
        if label is not None:
            label.setCursor(_Qt.CursorShape.ArrowCursor)
    except Exception:
        pass


def _axis_pix(dest: int, target: int, pan: float) -> tuple[int, int, int]:
    """(draw_pos, src_off, size): center if smaller, else pan-crop.

    Pixmap mirror of ``preview_zoom._axis`` (kept local: no private
    cross-module import, same clamp math so canvas/label agree pixel-exact).
    """
    try:
        if dest <= target:
            return max(0, (target - dest) // 2), 0, max(0, dest)
        s = (dest - target) / 2.0 - float(pan) * dest
        return 0, int(round(max(0.0, min(float(dest - target), s)))), target
    except Exception:
        return 0, 0, max(0, target)


def zoomed_label_pixmap(full, tw: int, th: int, zoom: float, pan_x: float = 0.0, pan_y: float = 0.0):
    """Contain-fit ``full`` into ``tw`` x ``th``, magnified + panned.

    QPixmap twin of ``preview_zoom.zoomed_frame`` (raster instead of
    bytes): fit first (whole image at 1.0), scale by zoom, crop the
    ``tw`` x ``th`` window around ``pan``. Returns a ``QPixmap`` or
    None. Never raises.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPainter, QPixmap
    except Exception:
        return None
    try:
        src_w, src_h = int(full.width()), int(full.height())
        tw, th = int(tw), int(th)
        if src_w <= 0 or src_h <= 0 or tw <= 0 or th <= 0:
            return None
        try:
            from tabs.image_gallery.ui.quick_look.preview_zoom import ZOOM_MAX, ZOOM_MIN

            z = max(ZOOM_MIN, min(ZOOM_MAX, float(zoom)))
        except Exception:
            z = 1.0
        scale = min(float(tw) / float(src_w), float(th) / float(src_h)) * z
        if not scale > 0:
            return None
        dest_w = max(1, int(round(src_w * scale)))
        dest_h = max(1, int(round(src_h * scale)))
        try:
            scaled = full.scaled(
                dest_w,
                dest_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            return None
        if scaled is None or scaled.isNull():
            return None
        try:
            px, py = float(pan_x), float(pan_y)
        except Exception:
            px, py = 0.0, 0.0
        dw, dh = int(scaled.width()), int(scaled.height())
        dx, sx, cw = _axis_pix(dw, tw, px)
        dy, sy, ch = _axis_pix(dh, th, py)
        try:
            canvas = QPixmap(tw, th)
            canvas.fill(Qt.GlobalColor.transparent)
        except Exception:
            return None
        try:
            painter = QPainter(canvas)
            try:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawPixmap(dx, dy, scaled, sx, sy, cw, ch)
            finally:
                painter.end()
        except Exception:
            return None
        return canvas
    except Exception:
        return None
