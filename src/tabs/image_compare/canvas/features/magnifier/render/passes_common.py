"""Shared uniform-packing helpers for the magnifier's QRhi passes.

Split out of ``passes.py`` so each render pass module only imports the byte-
packing helpers it actually uses, instead of every pass sharing one file.
"""

from __future__ import annotations

import struct

from PySide6.QtGui import QColor


def ensure_qcolor(c) -> QColor:
    if isinstance(c, QColor):
        return c
    r = int(
        getattr(c, "r", 255) if hasattr(c, "r") else getattr(c, "red", lambda: 255)()
    )
    g = int(
        getattr(c, "g", 255) if hasattr(c, "g") else getattr(c, "green", lambda: 255)()
    )
    b = int(
        getattr(c, "b", 255) if hasattr(c, "b") else getattr(c, "blue", lambda: 255)()
    )
    a = int(
        getattr(c, "a", 255) if hasattr(c, "a") else getattr(c, "alpha", lambda: 255)()
    )
    return QColor(r, g, b, a)


def pack_arc_uniform(
    matrix: tuple[float, ...],
    width: float,
    height: float,
    center_x: float,
    center_y: float,
    radius_px: float,
    line_width_px: float,
    start_angle_deg: float,
    span_angle_deg: float,
    color: QColor,
) -> bytes:
    return struct.pack(
        "<16f 2f 2f 4f 4f",
        *matrix,
        width,
        height,
        center_x,
        center_y,
        radius_px,
        line_width_px,
        start_angle_deg,
        span_angle_deg,
        color.redF(),
        color.greenF(),
        color.blueF(),
        color.alphaF(),
    )


def pack_border_disk_uniform(
    matrix: tuple[float, ...],
    width: float,
    height: float,
    center_x: float,
    center_y: float,
    radius_px: float,
    border_width_px: float,
    color: QColor,
) -> bytes:
    return struct.pack(
        "<16f 2f 2f 4f 4f 4f",
        *matrix,
        width,
        height,
        center_x,
        center_y,
        radius_px,
        border_width_px,
        0.0,
        0.0,
        color.redF(),
        color.greenF(),
        color.blueF(),
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
