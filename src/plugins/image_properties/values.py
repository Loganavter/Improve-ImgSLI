"""Presentation formatting of property values (bytes, ratio, DPI, EXIF).

Split out of ``service.py`` when the panel grew the first-frame notice and that
module reached the file-size policy limit (``docs/dev/FILE_SIZE_POLICY.md``).
Pure functions only: no Pillow, no Qt, no panel state — they turn a raw value
into the string the table cell shows, and nothing else.
"""

from __future__ import annotations

import math
from typing import Any


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if abs(value) < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.2f} {unit}"


def format_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "-"
    divisor = math.gcd(width, height)
    simplified = f"{width // divisor}:{height // divisor}"
    decimal = width / height
    return f"{simplified} ({decimal:.3f})"


def format_dpi(dpi: Any) -> str:
    if isinstance(dpi, tuple) and len(dpi) >= 2:
        return f"{stringify(dpi[0])} x {stringify(dpi[1])}"
    return stringify(dpi)


def normalize_exif_value(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace").strip("\x00")
        except Exception:
            return repr(value)
    if isinstance(value, tuple):
        return tuple(normalize_exif_value(item) for item in value)
    return value


def stringify(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple):
        return " x ".join(stringify(item) for item in value)
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if isinstance(numerator, int) and isinstance(denominator, int) and denominator:
        if numerator > denominator:
            return f"{numerator / denominator:g}"
        return f"{numerator}/{denominator}"
    return str(value)
