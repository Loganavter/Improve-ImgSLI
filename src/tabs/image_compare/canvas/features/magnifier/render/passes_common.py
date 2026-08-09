"""Shared uniform-packing helpers for the magnifier's QRhi passes.

Split out of ``passes.py`` so each render pass module only imports the byte-
packing helpers it actually uses, instead of every pass sharing one file.
"""

from __future__ import annotations

import struct

from PySide6.QtGui import QColor

from shared.rendering.uniform_layout import assert_uniform_size
from tabs.image_compare.canvas.features.magnifier.render.shader_layout import (
    ARC_UNIFORM_SIZE,
    BORDER_DISK_UNIFORM_SIZE,
)

_ARC_UNIFORM_FMT = "<16f 2f 2f 4f 4f"
_BORDER_DISK_UNIFORM_FMT = "<16f 2f 2f 4f 4f 4f"
assert_uniform_size(_ARC_UNIFORM_FMT, ARC_UNIFORM_SIZE, label="pack_arc_uniform")
assert_uniform_size(
    _BORDER_DISK_UNIFORM_FMT, BORDER_DISK_UNIFORM_SIZE, label="pack_border_disk_uniform"
)


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
        _ARC_UNIFORM_FMT,
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
        _BORDER_DISK_UNIFORM_FMT,
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
