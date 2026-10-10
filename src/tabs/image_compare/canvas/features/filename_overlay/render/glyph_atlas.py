"""Glyph atlas for the filename_overlay text pass (variant C1).

Per-glyph **antialiased coverage** atlas (NOT a signed-distance field): each
glyph is rasterized once per ``(font key, pixel_size, dpr, weight)`` at
``_SUPERSAMPLE`` x device resolution and CPU-downscaled to device resolution,
so the stored coverage carries genuine sub-pixel area information (0..1 alpha
edge gradient). This is the glass-panel text-mask technique
(``docs/legacy/rendering/glass-panel-text-vibrancy-plan.md`` bugs 9/13): a flat
1x QPainter render tops out at weak/near-binary coverage; supersample +
downscale gives a real gradient. The shader samples the coverage directly
(``alpha = tex``), so there is no SDF decode/threshold that could saturate to
0/1.

Ownership note (contract): this module is under ``src/tabs`` and must not
allocate a QRhi texture -- ``render/gpu_resources.py`` owns the QRhi texture.
This module only builds the CPU image + slot metadata.

F5 BOUNDARY (C1): WHAT STAYS -- the shared per-glyph coverage atlas + per-glyph
quads (built CPU-side here, uploaded by ``gpu_resources``) has no image in
``TexturedOverlayShell`` (one fullscreen quad over one texture). INVALIDATION --
re-open the verdict if the shell gains a shared glyph atlas + per-glyph quad
stream.

C1 limitation: one face only -- printable ASCII 32..126 plus the horizontal
ellipsis U+2026 (what ``QFontMetrics.elidedText`` inserts on truncation).
Other missing code points (CJK, emoji, combining marks) return ``None`` from
``glyph_for`` and are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen

# Supersample factor for the per-glyph coverage raster (matches the glass-HUD
# text-mask supersample). The CPU downscale to device res is the source of the
# antialiased edge gradient -- see module docstring.
_SUPERSAMPLE = 4

# Cheaper supersample used while a settings slider is being dragged
# (interactive render mode): a weight/size drag changes the atlas key every
# tick, and a full 4x rebuild is ~40-120 ms per tick. 2x keeps the drag
# responsive; the settled frame rebuilds at the full ``_SUPERSAMPLE``.
_INTERACTIVE_SUPERSAMPLE = 2

# Printable ASCII plus the horizontal ellipsis U+2026 -- the elision glyph
# ``QFontMetrics.elidedText`` appends when a filename is truncated to the label
# box. Without it the elided string's tail glyph is dropped (hard cut, no "...").
_CHARSET = "".join(chr(c) for c in range(32, 127)) + "\u2026"
_ATLAS_WIDTH = 512
_PAD_FRACTION = 0.25
_MIN_PAD = 3.0
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
    coverage: np.ndarray | None
    advance_px: float
    bearing_px: tuple[float, float]
    x: int = 0
    y: int = 0


class GlyphAtlas:
    """Shelf-packed antialiased coverage atlas for one face / pixel size / dpr / weight.

    ``ensure`` rebuilds only when the ``(font key, pixel_size, dpr, weight)``
    tuple changes, so a split drag (which changes the elided string, not the
    font) never touches the CPU here. ``image`` is the RGBA8 atlas (R = alpha
    coverage, A = coverage too); ``gpu_resources`` owns the QRhi texture.
    """

    def __init__(self, rhi) -> None:
        self._rhi = rhi
        self._key: tuple | None = None
        self.image: QImage | None = None
        self.width = 0
        self.height = 0
        self.pad_px = 0.0
        # Kept for interface compatibility; unused by the coverage atlas.
        self.sdf_range_px = 0.0
        self._slots: dict[str, GlyphSlot] = {}

    def ensure(
        self,
        font: QFont,
        pixel_size: int,
        dpr: float,
        weight: int = 0,
        supersample: int = _SUPERSAMPLE,
    ) -> bool:
        """Build/refresh the atlas; no-op (``False``) when the key is unchanged."""
        ss = max(1, int(supersample))
        key = (
            font.key(),
            int(pixel_size),
            round(max(1.0, float(dpr)), 3),
            int(weight),
            ss,
        )
        if key == self._key:
            return False
        self._key = key
        self._build(font, int(pixel_size), max(1.0, float(dpr)), int(weight), ss)
        return True

    def glyph_for(self, ch: str) -> GlyphSlot | None:
        return self._slots.get(ch)

    def reset(self) -> None:
        self._key = None
        self.image = None
        self.width = 0
        self.height = 0
        self._slots = {}

    def _build(
        self, font: QFont, pixel_size: int, dpr: float, weight: int, supersample: int
    ) -> None:
        pixel_size = max(1, pixel_size)
        dev_font = QFont(font)
        dev_font.setPixelSize(max(1, int(round(pixel_size * dpr))))
        metrics = QFontMetrics(dev_font)

        pad_logical = max(_MIN_PAD, round(pixel_size * _PAD_FRACTION))
        pad_dev = max(1, int(round(pad_logical * dpr)))
        self.pad_px = pad_logical
        # Synthetic bold stroke width (device px), same formula as the retired
        # CPU raster: stroke_px = pixel_size * weight / 500.
        stroke_dev = float(pixel_size) * float(weight) / 500.0 * dpr

        tiles: list[_Tile] = []
        for ch in _CHARSET:
            path = QPainterPath()
            path.addText(0.0, 0.0, dev_font, ch)
            # Glyph outlines are non-zero-winding; QPainterPath defaults to
            # OddEvenFill, which punches holes where contours overlap (the "f"
            # crossbar/stem, "e" bar, "a" bowl junction). Force WindingFill.
            path.setFillRule(Qt.FillRule.WindingFill)
            br = path.boundingRect()
            advance = float(metrics.horizontalAdvance(ch)) / dpr
            if br.width() <= 0.0 or br.height() <= 0.0:
                # Advance-only glyph (space and friends): no ink tile, but the
                # pen must still move -- otherwise words collapse into one run
                # ("Original Tom" -> "OriginalTom").
                if advance > 0.0:
                    tiles.append(
                        _Tile(
                            ch=ch,
                            w=0,
                            h=0,
                            coverage=None,
                            advance_px=advance,
                            bearing_px=(0.0, 0.0),
                        )
                    )
                continue
            w = int(np.ceil(br.width())) + 2 * pad_dev
            h = int(np.ceil(br.height())) + 2 * pad_dev
            coverage = _render_coverage(
                path, br, w, h, pad_dev, stroke_dev, supersample
            )
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

        self._pack(tiles, dpr)

    def _pack(self, tiles: list[_Tile], dpr: float) -> None:
        ink = [t for t in tiles if t.w > 0 and t.h > 0]
        ink.sort(key=lambda t: (-t.h, t.ch))
        x = _GUTTER
        y = _GUTTER
        row_h = 0
        for tile in ink:
            if x + tile.w + _GUTTER > _ATLAS_WIDTH:
                x = _GUTTER
                y += row_h + _GUTTER
                row_h = 0
            tile.x = x
            tile.y = y
            x += tile.w + _GUTTER
            row_h = max(row_h, tile.h)
        atlas_h = max(1, y + row_h + _GUTTER)

        atlas = np.zeros((atlas_h, _ATLAS_WIDTH, 4), dtype=np.uint8)
        self._slots = {}
        for tile in ink:
            cov_u8 = np.round(tile.coverage * 255.0).astype(np.uint8)
            x0, y0 = tile.x, tile.y
            atlas[y0 : y0 + tile.h, x0 : x0 + tile.w, 0] = cov_u8
            atlas[y0 : y0 + tile.h, x0 : x0 + tile.w, 3] = cov_u8
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
        # Advance-only glyphs (space etc.): a slot with no uv/tile so pack_run
        # still moves the pen without emitting a quad.
        for tile in tiles:
            if tile.w <= 0 or tile.h <= 0:
                self._slots[tile.ch] = GlyphSlot(
                    uv=(0.0, 0.0, 0.0, 0.0),
                    advance_px=tile.advance_px,
                    bearing_px=(0.0, 0.0),
                    size_px=(0.0, 0.0),
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


def _downscale_lanczos(img: QImage, w: int, h: int) -> QImage:
    """Downscale ``img`` to ``w x h`` with a real multi-tap filter.

    PIL LANCZOS when available (matches ``draw_text_bold_supersampled``);
    Qt's SmoothTransformation otherwise (mushier but always present).
    """
    try:
        from PIL import Image

        rgba = img.convertToFormat(QImage.Format.Format_RGBA8888)
        pil = Image.frombytes(
            "RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits())
        )
        pil = pil.resize((w, h), Image.Resampling.LANCZOS)
        raw = pil.tobytes("raw", "RGBA")
        return QImage(
            raw, w, h, w * 4, QImage.Format.Format_RGBA8888
        ).copy()
    except Exception:
        return img.scaled(
            w,
            h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )


def _render_coverage(
    path: QPainterPath,
    br,
    w: int,
    h: int,
    pad_dev: int,
    stroke_dev: float,
    supersample: int = _SUPERSAMPLE,
) -> np.ndarray:
    """Rasterize one glyph to antialiased coverage (device px), supersampled.

    Renders at ``supersample`` x then downscales to ``w x h`` (LANCZOS), so
    each output pixel is a genuine area average -- the glass-HUD text-mask fix
    for weak/near-binary 1x coverage.
    """
    ss = max(1, int(supersample))
    big_w, big_h = max(1, w * ss), max(1, h * ss)
    img = QImage(big_w, big_h, QImage.Format.Format_RGBA8888)
    img.fill(0)
    painter = QPainter(img)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(float(ss), float(ss))
        painter.translate(float(pad_dev) - br.x(), float(pad_dev) - br.y())
        color = QColor(255, 255, 255, 255)
        if stroke_dev > 0.0:
            pen = QPen(color, stroke_dev)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(color)
            painter.drawPath(path)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)
    finally:
        painter.end()
    small = _downscale_lanczos(img, w, h)
    raw = np.frombuffer(small.constBits(), dtype=np.uint8).reshape(h, w, 4)
    return raw[..., 3].astype(np.float64) / 255.0
