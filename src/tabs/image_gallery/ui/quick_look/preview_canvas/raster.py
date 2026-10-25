"""Quick-look canvas: frame raster + wheel/mouse pan-zoom interaction.

Split from ``preview_canvas.py`` (plan-gallery-split-2026-10-17, Part C2).
Bodies moved verbatim; names and signatures unchanged. Plain functions
take the canvas widget as their first argument (``CODE_PATTERNS.md`` --
thin owner + module functions).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt

from engine.store.tiled_pixel_store import pixel_source_size

# Decode caps owned by services/decode_policy.py (single home); the alias
# keeps the historic ``_DECODE_EDGE_CAP`` name used below.
from tabs.image_gallery.services.decode_policy import (
    PREVIEW_FULL_DECODE_EDGE as _DECODE_EDGE_CAP,
    exceeds_edge,
)
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


# -- frame raster -----------------------------------------------------------


def _raster_frame(self, target) -> tuple[int, int, bytes] | None:
    """Frame raster, never presenting nothing.

    Wraps ``_compute_raster_frame``: any miss (unbuilt LOD level, empty
    composition, decode failure) reuses the last good frame instead of
    returning ``None``. A partial tiled frame is not ``covered`` while it
    streams, so a ``None`` here would leave the QRhiWidget presenting no
    pass at all — a see-through hole (``qrhiwidget-cant-alpha-blend`` /
    "no pinned coarse level → holes by construction"). Stale beats a hole;
    the frame cache is invalidated on source change, so the reused frame
    is always the same image. Never raises.
    """
    try:
        frame = self._compute_raster_frame(target)
    except Exception:
        logger.debug("QuickLook preview: raster failed open", exc_info=True)
        frame = None
    if frame is not None:
        return frame
    return self._frame_bytes


def _compute_raster_frame(self, target) -> tuple[int, int, bytes] | None:
    """Compute the frame raster: single ResolvedLayer → cache → crop."""
    try:
        composition = self._active_composition
        layers = getattr(composition, "layers", ()) or ()
        if not layers:
            return None
        source = getattr(layers[0], "image", None)
        if source is None:
            return None
        src_w, src_h = pixel_source_size(source)
        if src_w <= 0 or src_h <= 0:
            return None
        try:
            size = target.pixelSize()
            fb_w, fb_h = max(1, int(size.width())), max(1, int(size.height()))
        except Exception:
            return None
        try:  # last live fb for the lazy need computation (no behavior change).
            self._last_fb = (int(fb_w), int(fb_h))
        except Exception:
            pass
        try:
            generation = int(getattr(source, "generation", 0))
        except Exception:
            generation = 0
        key = (id(source), generation, int(src_w), int(src_h), fb_w, fb_h,
               round(self._zoom, 4), round(self._pan_x, 4), round(self._pan_y, 4),
               self._ql_levels_token())
        if key == self._frame_key and self._frame_bytes is not None:
            return self._frame_bytes
        full = self._decoded_image(source, src_w, src_h)
        if full is None or full.isNull():
            return None
        try:
            lod = self._lod_frame(full, fb_w, fb_h)
        except Exception:
            lod = None
        if lod is not None:
            frame = lod
        else:
            try:
                from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame
            except Exception:
                return None
            frame = zoomed_frame(full, fb_w, fb_h, self._zoom, self._pan_x, self._pan_y)
        if frame is None:
            return None
        self._frame_key = key
        self._frame_bytes = frame
        return frame
    except Exception:
        logger.debug("QuickLook preview: raster failed open", exc_info=True)
        return None


def _decoded_image(self, source, src_w: int, src_h: int) -> QImage | None:
    """Host image via the frozen pyramid seam (bounded, no full frame).

    Samples the held (coarse, edge-capped by the host) store verbatim
    through ``PyramidPixelStore.best_pixels`` — ``read_array`` only, so
    no full-frame materialize and no second cache. Miss (stale/unbuilt
    level, unreadable box) fails closed to None; the frame is skipped
    and the QLabel fallback owns the pane.
    """
    try:
        from engine.store.pyramid_pixel_store import PyramidPixelStore
    except Exception:
        return None
    try:
        w, h = int(src_w), int(src_h)
        if w <= 0 or h <= 0:
            return None
        pyramid = PyramidPixelStore(source)
        try:
            image = pyramid.best_pixels((0, 0, w, h), 1.0)
        finally:
            try:
                pyramid.close()  # derived levels only; base owned by host
            except Exception:
                pass
    except Exception:
        return None
    if image is None or image.isNull():
        return None
    try:
        # Never hold a 40k host image for a ~640px pane: downscale once.
        if exceeds_edge(image.width(), image.height(), _DECODE_EDGE_CAP):
            small = image.scaled(
                _DECODE_EDGE_CAP,
                _DECODE_EDGE_CAP,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if small is not None and not small.isNull():
                image = small
    except Exception:
        pass
    return image


def _lod_frame(self, full, fb_w: int, fb_h: int) -> tuple[int, int, bytes] | None:
    """Zoomed frame from the demand pyramid's best level (None = use coarse).

    Same window as ``zoomed_frame`` — pan math comes from the shared
    ``preview_zoom._axis``, so the crop agrees with the coarse path by
    construction — but pixels come from ``PyramidPixelStore.best_pixels``
    (shared ``select_level`` LOD: display-px per full-res px picks the
    level) instead of a CPU-upscaled coarse. Active ONLY past 1.0x with
    a live pyramid; every miss fails closed to None and the caller
    falls back to today's path bit-identically. Never raises.
    """
    try:
        try:
            z = float(getattr(self, "_zoom", 1.0))
        except Exception:
            return None
        if not z > 1.0 + 1e-9:
            return None  # no-zoom path stays bit-identical (coarse only).
        try:
            pyr = getattr(self, "_ql_pyramid", None)
            full_store = getattr(self, "_ql_full_store", None)
            if pyr is None or full_store is None:
                return None
            if not bool(getattr(pyr, "valid", False)):
                return None
            if not bool(getattr(full_store, "is_open", False)):
                return None
        except Exception:
            return None
        try:
            cw, ch = int(full.width()), int(full.height())
            fb_w, fb_h = int(fb_w), int(fb_h)
            if cw <= 0 or ch <= 0 or fb_w <= 0 or fb_h <= 0:
                return None
            fw, fh = pixel_source_size(full_store)
            fw, fh = int(fw), int(fh)
            if fw <= 0 or fh <= 0:
                return None
        except Exception:
            return None
        try:  # visible window in coarse-dest px (zoomed_frame geometry).
            scale = min(float(fb_w) / float(cw), float(fb_h) / float(ch)) * z
            if not scale > 0:
                return None
            dest_w = max(1, int(round(cw * scale)))
            dest_h = max(1, int(round(ch * scale)))
            from tabs.image_gallery.ui.quick_look.preview_zoom import _axis

            try:
                px, py = float(self._pan_x), float(self._pan_y)
            except Exception:
                px, py = 0.0, 0.0
            dx, sx, cw2 = _axis(dest_w, fb_w, px)
            dy, sy, ch2 = _axis(dest_h, fb_h, py)
            if cw2 <= 0 or ch2 <= 0:
                return None
        except Exception:
            return None
        try:  # dest px → coarse px → full-res px (best_pixels clamps too).
            import math

            rx, ry = float(fw) / float(cw), float(fh) / float(ch)
            left = max(0, int(math.floor(sx / scale * rx)))
            top = max(0, int(math.floor(sy / scale * ry)))
            right = min(fw, int(math.ceil((sx + cw2) / scale * rx)))
            bottom = min(fh, int(math.ceil((sy + ch2) / scale * ry)))
            if right <= left or bottom <= top:
                return None
            dest_scale = min(float(fb_w) / float(fw), float(fb_h) / float(fh)) * z
            img = pyr.best_pixels((left, top, right, bottom), dest_scale)
        except Exception:
            return None
        try:
            _bad = img is None or img.isNull()
        except Exception:
            _bad = True
        if _bad:
            return None
        try:  # blit the level crop onto the fb window (zoomed_frame tail).
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage, QPainter

            scaled = img.scaled(
                int(cw2), int(ch2),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if scaled is None or scaled.isNull():
                return None
            canvas = QImage(fb_w, fb_h, QImage.Format.Format_RGBA8888_Premultiplied)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            try:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(int(dx), int(dy), scaled, 0, 0, int(cw2), int(ch2))
            finally:
                painter.end()
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
        logger.debug("QuickLook preview: LOD raster failed open", exc_info=True)
        return None


def wheelEvent(self, event) -> None:  # noqa: N802
    """Wheel = cursor-anchored zoom (MC parity); floor snaps pan to origin."""
    try:
        from tabs.image_gallery.ui.quick_look.preview_zoom import wheel_zoom_pan

        pos = event.position()
        got = wheel_zoom_pan(
            getattr(self, "_zoom", 1.0), getattr(self, "_pan_x", 0.0),
            getattr(self, "_pan_y", 0.0), event.angleDelta().y(),
            float(pos.x()) / max(1, int(self.width())),
            float(pos.y()) / max(1, int(self.height())),
        )
        if got is not None:
            try:
                from tabs.image_gallery.ui.quick_look.preview_zoom import clamp_pan

                _dims = getattr(self, "_ql_probe_dims", None)
                if _dims is not None:
                    got = (
                        got[0],
                        *clamp_pan(
                            got[1], got[2], _dims[0], _dims[1],
                            max(1, int(self.width())), max(1, int(self.height())),
                            got[0],
                        ),
                    )
            except Exception:
                pass
            self.set_view(*got)
            self._frame_key = None
            self.update()
        event.accept()
    except Exception:
        pass
    try:  # zoom past 1.0 demands the full pyramid (dwell covers 1.0).
        if float(getattr(self, "_zoom", 1.0)) > 1.0:
            self._maybe_demand_build("zoom")
            try:  # zoom bypasses dwell for the staged tiled kick too.
                self._fire_ql_tiled_pending()
            except Exception:
                pass
    except Exception:
        pass


def mousePressEvent(self, event) -> None:  # noqa: N802
    try:
        from PySide6.QtCore import Qt as _Qt

        if event.button() == _Qt.MouseButton.MiddleButton:
            pos = event.position()
            self._drag_last = (float(pos.x()), float(pos.y()))
            self.setCursor(_Qt.CursorShape.ClosedHandCursor)
        super(type(self), self).mousePressEvent(event)
    except Exception:
        pass


def mouseMoveEvent(self, event) -> None:  # noqa: N802
    try:
        last = getattr(self, "_drag_last", None)
        if last is not None:
            from tabs.image_gallery.ui.quick_look.preview_zoom import drag_pan

            pos = event.position()
            got = drag_pan(
                getattr(self, "_pan_x", 0.0), getattr(self, "_pan_y", 0.0),
                float(pos.x()) - last[0], float(pos.y()) - last[1],
                max(1, int(self.width())), max(1, int(self.height())),
                getattr(self, "_zoom", 1.0),
            )
            if got is not None:
                try:
                    from tabs.image_gallery.ui.quick_look.preview_zoom import clamp_pan

                    _dims = getattr(self, "_ql_probe_dims", None)
                    if _dims is not None:
                        got = clamp_pan(
                            got[0], got[1], _dims[0], _dims[1],
                            max(1, int(self.width())), max(1, int(self.height())),
                            getattr(self, "_zoom", 1.0),
                        )
                except Exception:
                    pass
                self.set_view(self._zoom, got[0], got[1])
                self._frame_key = None
                self.update()
            self._drag_last = (float(pos.x()), float(pos.y()))
        super(type(self), self).mouseMoveEvent(event)
    except Exception:
        pass


def mouseReleaseEvent(self, event) -> None:  # noqa: N802
    try:
        from PySide6.QtCore import Qt as _Qt

        if event.button() == _Qt.MouseButton.MiddleButton:
            self._drag_last = None
            self.setCursor(_Qt.CursorShape.ArrowCursor)
        super(type(self), self).mouseReleaseEvent(event)
    except Exception:
        pass
