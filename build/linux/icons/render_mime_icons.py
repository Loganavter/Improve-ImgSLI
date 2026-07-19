#!/usr/bin/env python3
"""Render PSD/XCF-style MIME icons for application/x-improve-imgsli.

Layout: dog-eared document, compact app mark (not the wordmark), ``IMGSLI`` label.
Requires an offscreen Qt platform::

    QT_QPA_PLATFORM=offscreen python3 build/linux/icons/render_mime_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

REPO = Path(__file__).resolve().parents[3]
MARK_PATH = REPO / "src" / "resources" / "icons" / "icon.png"
OUT_DIR = Path(__file__).resolve().parent / "mimetypes"
SIZES = (16, 22, 32, 48, 64, 128, 256)
ICON_NAME = "application-x-improve-imgsli"


def document_path(w: float, h: float, fold: float, radius: float) -> QPainterPath:
    r = radius
    path = QPainterPath()
    path.moveTo(r, 0)
    path.lineTo(w - fold, 0)
    path.lineTo(w, fold)
    path.lineTo(w, h - r)
    path.quadTo(w, h, w - r, h)
    path.lineTo(r, h)
    path.quadTo(0, h, 0, h - r)
    path.lineTo(0, r)
    path.quadTo(0, 0, r, 0)
    path.closeSubpath()
    return path


def fold_path(w: float, fold: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(w - fold, 0)
    path.lineTo(w, fold)
    path.lineTo(w - fold, fold)
    path.closeSubpath()
    return path


def render(mark: QImage, size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    margin = size * 0.07
    page_h = size - 2 * margin
    page_w = page_h / 1.28
    if page_w > size - 2 * margin:
        page_w = size - 2 * margin
        page_h = page_w * 1.28
    x0 = (size - page_w) / 2
    y0 = (size - page_h) / 2
    fold = page_w * 0.22
    radius = max(1.5, page_w * 0.06)

    shadow = document_path(page_w, page_h, fold, radius)
    shadow.translate(x0 + size * 0.015, y0 + size * 0.02)
    p.fillPath(shadow, QColor(0, 0, 0, 48))

    page = document_path(page_w, page_h, fold, radius)
    page.translate(x0, y0)
    p.fillPath(page, QColor(245, 246, 248))
    p.strokePath(page, QPen(QColor(190, 195, 205), max(1.0, size * 0.012)))

    fp = fold_path(page_w, fold)
    fp.translate(x0, y0)
    p.fillPath(fp, QColor(228, 230, 236))
    p.strokePath(fp, QPen(QColor(190, 195, 205), max(0.8, size * 0.01)))

    # Compact mark — leave page chrome visible (GIMP/PSD style, not full-bleed).
    label_h = page_h * (0.16 if size >= 32 else 0.0)
    top_pad = page_h * 0.14
    bottom_pad = page_h * 0.10 + label_h
    avail_h = page_h - top_pad - bottom_pad
    avail_w = page_w * 0.42
    mark_edge = min(avail_w, avail_h)
    scaled = mark.scaled(
        max(1, int(mark_edge)),
        max(1, int(mark_edge)),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    mx = x0 + (page_w - scaled.width()) / 2
    my = y0 + top_pad + (avail_h - scaled.height()) / 2
    p.drawImage(QPointF(mx, my), scaled)

    if size >= 32:
        # Regular face + tiny tracking (~1px @256). Larger AbsoluteSpacing
        # looked sparse; zero/negative read crushed on bold caps.
        font = QFont("Roboto")
        if not font.exactMatch():
            font = QFont("Noto Sans")
        if not font.exactMatch():
            font = QFont("DejaVu Sans")
        font.setWeight(QFont.Weight.Medium)
        font.setStyleStrategy(
            QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
        )
        font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing, max(0.15, size * 0.004)
        )
        font.setPixelSize(max(7, int(page_h * 0.10)))
        p.setFont(font)
        p.setPen(QColor(55, 60, 70))
        text_rect = QRectF(x0, y0 + page_h - label_h - page_h * 0.015, page_w, label_h)
        p.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            "IMGSLI",
        )
    p.end()
    return img


def main() -> int:
    if not MARK_PATH.is_file():
        print(f"missing mark: {MARK_PATH}", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    del app
    mark = QImage(str(MARK_PATH))
    if mark.isNull():
        print(f"failed to load mark: {MARK_PATH}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        out = OUT_DIR / f"{ICON_NAME}-{size}.png"
        if not render(mark, size).save(str(out), "PNG"):
            print(f"failed to write {out}", file=sys.stderr)
            return 1
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
