"""Quick-look preview zoom — pure helpers (no Qt widgets).

Wheel-zoom for the single-quad canvas: centered, ``ZOOM_MIN..ZOOM_MAX``,
``ZOOM_STEP`` per wheel notch. Split from ``preview_canvas.py`` (500-line
contract gate). All functions total and fail-open (``None`` = keep current).

``ViewportState`` is the ONE zoom/pan holder: the main preview canvas owns
an instance and the source inset canvas binds to the SAME object
(``QuickLookCanvasWidget.bind_view``), so both views transform identically —
zooming/panning either surface moves both. Pure Python (observers are plain
callables, no Qt types), so the state stays testable and the widgets stay
the only place that paints.
"""

from __future__ import annotations

ZOOM_MIN = 1.0
ZOOM_MAX = 8.0
ZOOM_STEP = 1.15


class ViewportState:
    """Shared ``(zoom, pan_x, pan_y)`` state for every view of one frame.

    ``plan-gallery-ql-source-canvas``: the source inset is a second engine
    canvas, not a pixmap; one viewport state must drive both views. The
    canvas widget owns one per source and ``bind_view`` makes another widget
    subscribe to it, so a wheel/drag on either writes the same numbers.
    Listeners are notified after an actual change; all accessors are total.
    """

    __slots__ = ("_zoom", "_pan_x", "_pan_y", "_listeners")

    def __init__(self, zoom: float = 1.0, pan_x: float = 0.0, pan_y: float = 0.0) -> None:
        self._listeners: list = []
        self._zoom = self._num(zoom, 1.0)
        self._pan_x = self._num(pan_x, 0.0)
        self._pan_y = self._num(pan_y, 0.0)

    @staticmethod
    def _num(value, fallback: float) -> float:
        try:
            return float(value)
        except Exception:
            return float(fallback)

    @property
    def zoom(self) -> float:
        return self._zoom

    @zoom.setter
    def zoom(self, value) -> None:
        z = self._num(value, self._zoom)
        if z == self._zoom:
            return
        self._zoom = z
        self._notify()

    @property
    def pan_x(self) -> float:
        return self._pan_x

    @pan_x.setter
    def pan_x(self, value) -> None:
        p = self._num(value, self._pan_x)
        if p == self._pan_x:
            return
        self._pan_x = p
        self._notify()

    @property
    def pan_y(self) -> float:
        return self._pan_y

    @pan_y.setter
    def pan_y(self, value) -> None:
        p = self._num(value, self._pan_y)
        if p == self._pan_y:
            return
        self._pan_y = p
        self._notify()

    @property
    def view(self) -> tuple[float, float, float]:
        return (self._zoom, self._pan_x, self._pan_y)

    def subscribe(self, callback) -> None:
        """Register a repaint observer (idempotent, fail-open)."""
        try:
            if callback not in self._listeners:
                self._listeners.append(callback)
        except Exception:
            pass

    def unsubscribe(self, callback) -> None:
        try:
            self._listeners.remove(callback)
        except Exception:
            pass

    def _notify(self) -> None:
        for callback in tuple(self._listeners):
            try:
                callback()
            except Exception:
                pass

    def set_view(self, zoom, pan_x, pan_y, *, notify: bool = True) -> bool:
        """Assign all three axes at once; True when the view actually changed."""
        z = self._num(zoom, self._zoom)
        px = self._num(pan_x, self._pan_x)
        py = self._num(pan_y, self._pan_y)
        if (z, px, py) == (self._zoom, self._pan_x, self._pan_y):
            return False
        self._zoom, self._pan_x, self._pan_y = z, px, py
        if notify:
            self._notify()
        return True

    def reset(self, *, notify: bool = True) -> bool:
        """Back to the identity view (context change / new pair)."""
        return self.set_view(ZOOM_MIN, 0.0, 0.0, notify=notify)


def step_zoom(zoom: float, delta_y: float) -> float:
    """Next zoom for a wheel delta (positive = in). Clamped, never raises."""
    try:
        z = float(zoom)
    except Exception:
        z = ZOOM_MIN
    try:
        factor = ZOOM_STEP if float(delta_y) > 0 else 1.0 / ZOOM_STEP
    except Exception:
        return z
    return max(ZOOM_MIN, min(ZOOM_MAX, z * factor))


def wheel_zoom_pan(zoom, pan_x, pan_y, delta_y, mx, my):  # type: ignore[no-untyped-def]
    """Cursor-anchored wheel zoom (engine viewport parity, clamped 1..8).

    ``mx``/``my`` are normalized cursor coords (0..1). The content point
    under the cursor stays put; at the zoom floor pan snaps to origin
    (whole frame is in view — a leftover offset would fake a shift).
    Returns ``(zoom, pan_x, pan_y)`` or ``None`` when nothing changes.
    """
    try:
        cur = max(ZOOM_MIN, min(ZOOM_MAX, float(zoom)))
        px, py = float(pan_x), float(pan_y)
        notches = float(delta_y) / 120.0
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, cur * (1.1**notches)))
        if abs(new_zoom - cur) <= 1e-6:
            return None
        if new_zoom <= ZOOM_MIN + 1e-9:
            return (ZOOM_MIN, 0.0, 0.0)
        out = []
        for m, p in ((float(mx), px), (float(my), py)):
            uv = (m - 0.5) / max(cur, 1e-6) + 0.5 - p
            uv = max(0.0, min(1.0, uv))
            out.append(0.5 - uv + (m - 0.5) / new_zoom)
        return (new_zoom, out[0], out[1])
    except Exception:
        return None


def drag_pan(pan_x, pan_y, dx_px, dy_px, w, h, zoom):  # type: ignore[no-untyped-def]
    """LMB drag: image follows the cursor (engine parity, pan unrestricted).

    The delta itself is unclamped — callers pass the result through
    :func:`clamp_pan` so the viewport never shows void.
    """
    try:
        z = max(float(zoom), 1e-6)
        w, h = float(w), float(h)
        if w <= 0 or h <= 0:
            return None
        return (float(pan_x) + float(dx_px) / (w * z),
                float(pan_y) + float(dy_px) / (h * z))
    except Exception:
        return None


def clamp_pan(pan_x, pan_y, src_w, src_h, fb_w, fb_h, zoom):  # type: ignore[no-untyped-def]
    """Cover-range clamp: the viewport never shows void past the image.

    At/below the zoom floor the fitted frame is fully in view, so pan is
    forced to the origin (a leftover offset would fake a shift). Zoomed
    in, each axis clamps to ``|pan| <= (dest-fb)/(2*dest)`` — the exact
    range where the ``_axis`` crop stays fully covered; axes where the
    fitted frame is smaller than the viewport center instead (pan 0).
    Fail-open: bad inputs return the inputs unchanged.
    """
    try:
        px, py = float(pan_x), float(pan_y)
        sw, sh = float(src_w), float(src_h)
        fw, fh = float(fb_w), float(fb_h)
        if not (sw > 0 and sh > 0 and fw > 0 and fh > 0):
            return (pan_x, pan_y)
        z = max(ZOOM_MIN, min(ZOOM_MAX, float(zoom)))
        scale = min(fw / sw, fh / sh) * z
        if not scale > 0:
            return (pan_x, pan_y)
        out = []
        for p, dest, fb in ((px, sw * scale, fw), (py, sh * scale, fh)):
            if dest <= fb:
                out.append(0.0)
            else:
                r = (dest - fb) / (2.0 * dest)
                out.append(max(-r, min(r, p)))
        return (out[0], out[1])
    except Exception:
        return (pan_x, pan_y)


def _axis(dest: int, fb: int, pan: float) -> tuple[int, int, int]:
    """(draw_pos, src_off, size): center if smaller, else pan-crop."""
    try:
        if dest <= fb:
            return max(0, (fb - dest) // 2), 0, max(0, dest)
        s = (dest - fb) / 2.0 - float(pan) * dest
        return 0, int(round(max(0.0, min(float(dest - fb), s)))), fb
    except Exception:
        return 0, 0, max(0, fb)


def widget_rect_to_normalized(
    rect, src_w, src_h, fb_w, fb_h, zoom: float = 1.0, pan_x: float = 0.0, pan_y: float = 0.0
):
    """Inverse of :func:`zoomed_frame`: a framebuffer-space rect → image space.

    Returns ``(left, top, right, bottom)`` as fractions of the source image
    (0..1), clamped to the image, or ``None`` when the inputs are degenerate or
    the rect collapses to zero area. Pure; never raises.
    """
    try:
        sw, sh = float(src_w), float(src_h)
        fw, fh = float(fb_w), float(fb_h)
        if not (sw > 0 and sh > 0 and fw > 0 and fh > 0):
            return None
        try:
            z = max(ZOOM_MIN, min(ZOOM_MAX, float(zoom)))
        except Exception:
            z = ZOOM_MIN
        scale = min(fw / sw, fh / sh) * z
        if not scale > 0:
            return None
        dest_w = max(1, int(round(sw * scale)))
        dest_h = max(1, int(round(sh * scale)))
        dx, sx, _cw = _axis(dest_w, int(fw), float(pan_x))
        dy, sy, _ch = _axis(dest_h, int(fh), float(pan_y))
        x0, y0, x1, y1 = (float(v) for v in rect)
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        nx0 = ((x0 - dx) + sx) / scale
        nx1 = ((x1 - dx) + sx) / scale
        ny0 = ((y0 - dy) + sy) / scale
        ny1 = ((y1 - dy) + sy) / scale
        nx0 = max(0.0, min(sw, nx0))
        nx1 = max(0.0, min(sw, nx1))
        ny0 = max(0.0, min(sh, ny0))
        ny1 = max(0.0, min(sh, ny1))
        if nx1 - nx0 <= 0 or ny1 - ny0 <= 0:
            return None
        return (nx0 / sw, ny0 / sh, nx1 / sw, ny1 / sh)
    except Exception:
        return None


def zoomed_frame(full, fb_w: int, fb_h: int, zoom: float, pan_x: float = 0.0, pan_y: float = 0.0):  # type: ignore[no-untyped-def]
    """Contain-fit ``full`` onto ``fb_w`` x ``fb_h``, magnified + panned.

    Fit first (whole image at 1.0), scale by zoom, crop the ``fb`` window
    around ``pan`` (crop origin = centered origin minus pan in dest px,
    clamped). Axes below framebuffer size center instead. Returns
    ``(w, h, bytes)`` or ``None``. Transparent margins at 1.0 (GPU clear
    shows through); zoomed crops fully covered.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage, QPainter
    except Exception:
        return None
    try:
        src_w, src_h = int(full.width()), int(full.height())
        fb_w, fb_h = int(fb_w), int(fb_h)
        if src_w <= 0 or src_h <= 0 or fb_w <= 0 or fb_h <= 0:
            return None
        try:
            z = max(ZOOM_MIN, min(ZOOM_MAX, float(zoom)))
        except Exception:
            z = ZOOM_MIN
        scale = min(float(fb_w) / float(src_w), float(fb_h) / float(src_h)) * z
        if not (scale > 0):
            return None
        dest_w = max(1, int(round(src_w * scale)))
        dest_h = max(1, int(round(src_h * scale)))
        try:
            scaled = full.scaled(
                dest_w, dest_h,
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
        dx, sx, cw = _axis(dw, fb_w, px)
        dy, sy, ch = _axis(dh, fb_h, py)
        try:
            canvas = QImage(fb_w, fb_h, QImage.Format.Format_RGBA8888_Premultiplied)
            canvas.fill(Qt.GlobalColor.transparent)
        except Exception:
            return None
        try:
            painter = QPainter(canvas)
            try:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(dx, dy, scaled, sx, sy, cw, ch)
            finally:
                painter.end()
        except Exception:
            return None
        try:
            premult = canvas.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
            stride = fb_w * 4
            raw = bytes(premult.constBits())
            row_stride = int(premult.bytesPerLine())
            if row_stride == stride:
                pixels = raw[: stride * fb_h]
            else:
                pixels = b"".join(
                    raw[y * row_stride: y * row_stride + stride] for y in range(fb_h)
                )
            if len(pixels) != stride * fb_h:
                return None
            return (fb_w, fb_h, pixels)
        except Exception:
            return None
    except Exception:
        return None
