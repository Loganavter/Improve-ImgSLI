"""Glyph atlas + signed-distance field for the filename_overlay text pass (C1).

Variant C1 replaces the per-string CPU raster + 4x supersample + GPU Lanczos
downsample of variant A with a single-channel signed-distance-field atlas:
every glyph is rasterized once per ``(font key, pixel_size, dpr)`` into a
shelf-packed atlas, converted to a signed distance field (negative inside,
positive outside, ``0.5`` == the glyph edge once normalized), and sampled by
per-glyph quads in ``shaders/filename_overlay.frag``. Resolution-independent
AA comes from the SDF threshold, so there is no supersample stage and no
per-drag raster at all.

Ownership note (contract): this module is under ``src/tabs`` and must not
allocate a QRhi texture -- ``tests/contracts/test_no_direct_texture_alloc.py``
/ ``test_no_private_grid.py`` pin the tab texture owners, and
``render/gpu_resources.py`` (an allowed owner) owns the QRhi texture/sampler.
This module only builds the CPU image + slot metadata; the caller uploads it.
F5 BOUNDARY (C1): the shared atlas + per-glyph quads has no image in
``TexturedOverlayShell`` (one fullscreen quad over one texture) -- the full
verdict prose lives on ``FilenameOverlayPass`` / ``render/gpu_resources.py``.

C1 limitation: one face only -- ASCII 32..126. Missing code points (CJK,
emoji, combining marks) return ``None`` from ``slot_for`` and are skipped, not
fallback-rendered.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath

try:  # scipy is not declared in requirements-gui.txt yet; keep a numpy fallback.
    from scipy.ndimage import distance_transform_edt as _scipy_edt
except Exception:  # pragma: no cover - exercised only where scipy is absent
    _scipy_edt = None

# Printable ASCII -- the C1 charset (see module docstring).
_CHARSET = "".join(chr(c) for c in range(32, 127))
_ATLAS_WIDTH = 512
_SDF_PAD_FRACTION = 0.4
_SDF_MIN_PAD = 4.0
_GUTTER = 2


@dataclass(frozen=True, slots=True)
class GlyphSlot:
    """Where one glyph lives in the atlas + its pen metrics (logical px)."""

    uv: tuple[float, float, float, float]
    advance_px: float
    bearing_px: tuple[float, float]
    size_px: tuple[float, float]


@dataclass(slots=True)
class _Tile:
    ch: str
    w: int
    h: int
    coverage: np.ndarray
    advance_px: float
    bearing_px: tuple[float, float]
    x: int = 0
    y: int = 0


def _distance_to(target: np.ndarray) -> np.ndarray:
    """Distance (px) from every cell to the nearest ``True`` cell.

    scipy's exact EDT when present; otherwise a two-pass chamfer 3-4
    approximation (good enough for SDF AA, and keeps the app importable where
    scipy is not installed).
    """
    if _scipy_edt is not None:
        # scipy measures distance to the nearest *zero*: invert the mask so it
        # measures distance to the nearest True (our "target") cell.
        return _scipy_edt(~target)
    h, w = target.shape
    inf = 1.0e9
    d = np.where(target, 0.0, inf)
    for y in range(h):
        row = d[y]
        prev = d[y - 1] if y > 0 else None
        for x in range(w):
            best = row[x]
            if prev is not None:
                best = min(best, prev[x] + 1.0)
                if x > 0:
                    best = min(best, prev[x - 1] + 1.41421356)
                if x < w - 1:
                    best = min(best, prev[x + 1] + 1.41421356)
            if x > 0:
                best = min(best, row[x - 1] + 1.0)
            row[x] = best
    for y in range(h - 1, -1, -1):
        row = d[y]
        nxt = d[y + 1] if y < h - 1 else None
        for x in range(w - 1, -1, -1):
            best = row[x]
            if nxt is not None:
                best = min(best, nxt[x] + 1.0)
                if x < w - 1:
                    best = min(best, nxt[x + 1] + 1.41421356)
                if x > 0:
                    best = min(best, nxt[x - 1] + 1.41421356)
            if x < w - 1:
                best = min(best, row[x + 1] + 1.0)
            row[x] = best
    return d


def _signed_distance(coverage: np.ndarray, pad_px: float) -> np.ndarray:
    """Signed distance in px: negative inside the glyph, positive outside."""
    inside = coverage > 0.5
    if not inside.any():
        return np.full(coverage.shape, pad_px, dtype=np.float64)
    if inside.all():
        return np.full(coverage.shape, -pad_px, dtype=np.float64)
    return _distance_to(inside) - _distance_to(~inside)


class GlyphAtlas:
    """Shelf-packed SDF atlas for one font face / pixel size / dpr.

    ``ensure`` rebuilds only when the ``(font key, pixel_size, dpr)`` triple
    changes, so a split drag (which changes the elided string, not the font)
    never touches the CPU here. ``image`` is the RGBA8 SDF atlas (R = distance,
    A = 255 inside a glyph tile / 0 elsewhere); ``gpu_resources`` owns the
    QRhi texture built from it.
    """

    def __init__(self, rhi) -> None:
        self._rhi = rhi
        self._key: tuple | None = None
        self.image: QImage | None = None
        self.width = 0
        self.height = 0
        self.pad_px = 0.0
        self.sdf_range_px = 0.0
        self._slots: dict[str, GlyphSlot] = {}

    def ensure(self, font: QFont, pixel_size: int, dpr: float) -> bool:
        """Build/refresh the atlas; no-op (``False``) when the key is unchanged."""
        key = (font.key(), int(pixel_size), round(max(1.0, float(dpr)), 3))
        if key == self._key:
            return False
        self._key = key
        self._build(font, int(pixel_size), max(1.0, float(dpr)))
        return True

    def slot_for(self, ch: str) -> GlyphSlot | None:
        return self._slots.get(ch)

    def reset(self) -> None:
        self._key = None
        self.image = None
        self.width = 0
        self.height = 0
        self._slots = {}

    def _build(self, font: QFont, pixel_size: int, dpr: float) -> None:
        pixel_size = max(1, pixel_size)
        dev_font = QFont(font)
        dev_font.setPixelSize(max(1, int(round(pixel_size * dpr))))
        metrics = QFontMetrics(dev_font)

        pad_logical = max(_SDF_MIN_PAD, round(pixel_size * _SDF_PAD_FRACTION))
        pad_dev = max(1, int(round(pad_logical * dpr)))
        self.pad_px = pad_logical
        self.sdf_range_px = 2.0 * pad_logical

        tiles: list[_Tile] = []
        for ch in _CHARSET:
            path = QPainterPath()
            path.addText(0.0, 0.0, dev_font, ch)
            br = path.boundingRect()
            advance = float(metrics.horizontalAdvance(ch)) / dpr
            if br.width() <= 0.0 or br.height() <= 0.0:
                continue
            w = int(np.ceil(br.width())) + 2 * pad_dev
            h = int(np.ceil(br.height())) + 2 * pad_dev
            coverage = _render_coverage(path, br, w, h, pad_dev)
            bearing = (br.x() / dpr - pad_logical, br.y() / dpr - pad_logical)
            tiles.append(
                _Tile(
                    ch=ch,
                    w=w,
                    h=h,
                    coverage=coverage,
                    advance_px=advance,
                    bearing_px=(float(bearing[0]), float(bearing[1])),
                )
            )

        self._pack(tiles, pad_dev, dpr)

    def _pack(self, tiles: list[_Tile], pad_dev: int, dpr: float) -> None:
        tiles.sort(key=lambda t: (-t.h, t.ch))
        x = _GUTTER
        y = _GUTTER
        row_h = 0
        for tile in tiles:
            if x + tile.w + _GUTTER > _ATLAS_WIDTH:
                x = _GUTTER
                y += row_h + _GUTTER
                row_h = 0
            tile.x = x
            tile.y = y
            x += tile.w + _GUTTER
            row_h = max(row_h, tile.h)
        atlas_h = max(1, y + row_h + _GUTTER)

        atlas = np.full((atlas_h, _ATLAS_WIDTH, 4), 0, dtype=np.uint8)
        atlas[..., 0] = 255  # default = far outside (edge 0.5 -> 1.0)
        self._slots = {}
        sdf_range = self.sdf_range_px
        for tile in tiles:
            # EDT distances are in device px; normalize to logical px so the
            # shader's sdf_range (logical) decodes cleanly.
            sd = _signed_distance(tile.coverage, float(pad_dev)) / dpr
            tex = np.clip(0.5 + sd / sdf_range, 0.0, 1.0)
            tex_u8 = np.round(tex * 255.0).astype(np.uint8)
            x0, y0 = tile.x, tile.y
            atlas[y0 : y0 + tile.h, x0 : x0 + tile.w, 0] = tex_u8
            atlas[y0 : y0 + tile.h, x0 : x0 + tile.w, 3] = 255
            u0 = x0 / _ATLAS_WIDTH
            v0 = y0 / atlas_h
            u1 = (x0 + tile.w) / _ATLAS_WIDTH
            v1 = (y0 + tile.h) / atlas_h
            self._slots[tile.ch] = GlyphSlot(
                uv=(u0, v0, u1, v1),
                advance_px=tile.advance_px,
                bearing_px=tile.bearing_px,
                size_px=(tile.w / dpr, tile.h / dpr),
            )

        self.width = _ATLAS_WIDTH
        self.height = atlas_h
        self.image = QImage(
            atlas.tobytes(),
            _ATLAS_WIDTH,
            atlas_h,
            _ATLAS_WIDTH * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()


def _render_coverage(
    path: QPainterPath, br, w: int, h: int, pad_dev: int
) -> np.ndarray:
    """Rasterize one glyph path to an alpha coverage array (device px)."""
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(0)
    painter = QPainter(img)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(float(pad_dev) - br.x(), float(pad_dev) - br.y())
        painter.setPen(QColor(255, 255, 255, 255))
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawPath(path)
    finally:
        painter.end()
    raw = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, w, 4)
    return raw[..., 3].astype(np.float64) / 255.0
