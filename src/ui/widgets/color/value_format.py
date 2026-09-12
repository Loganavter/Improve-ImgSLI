"""Color value formatting for the picker's single editable value field.

The color picker shows the current color as one text value whose format can
be cycled (``HEX`` -> ``RGB`` -> ``HSL`` -> ...) via a small button next to
the field. Formatting and parsing live app-side (not in the toolkit) because
the exact alpha round-trip semantics are a product concern.

Supported formats:

- ``HEX``: ``#RRGGBB`` / ``#RRGGBBAA`` (the storage format, see
  ``color_picker_recents``).
- ``RGB``: ``rgb(R, G, B)`` / ``rgba(R, G, B, A)``.
- ``HSL``: ``hsl(H, S%, L%)`` / ``hsla(H, S%, L%, A%)``.

Every channel is an integer; alpha is 0-255 in all formats so the value
round-trips exactly. Parsing additionally accepts CSS-float (0-1) and
percent alpha tokens so pasted ``rgba()`` / ``hsla()`` text from other
tools still works.
"""

from __future__ import annotations

import re
from enum import IntEnum

from PySide6.QtGui import QColor

from ui.widgets.color.recents import color_to_hex_string, parse_hex_color


class ValueFormat(IntEnum):
    """Identifiers for the value formats the picker field can display."""

    HEX = 0
    RGB = 1
    HSL = 2


_CYCLE_ORDER = (ValueFormat.HEX, ValueFormat.RGB, ValueFormat.HSL)


def next_color_format(fmt: ValueFormat) -> ValueFormat:
    """Next format in the cycle order (``HEX`` wraps back to the start)."""
    index = _CYCLE_ORDER.index(fmt)
    return _CYCLE_ORDER[(index + 1) % len(_CYCLE_ORDER)]


def color_format_label(fmt: ValueFormat) -> str:
    """Short uppercase button label, e.g. ``"HEX"`` / ``"RGB"`` / ``"HSL"``."""
    return fmt.name


def format_color_value(color: QColor, fmt: ValueFormat, *, include_alpha: bool) -> str:
    """Render ``color`` in ``fmt``.

    ``include_alpha`` mirrors the hex-field convention: alpha appears only
    when it is enabled *and* differs from opaque.
    """
    if fmt is ValueFormat.HEX:
        return color_to_hex_string(color, include_alpha=include_alpha)
    show_alpha = include_alpha and color.alpha() < 255
    if fmt is ValueFormat.RGB:
        if show_alpha:
            return (
                f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"
            )
        return f"rgb({color.red()}, {color.green()}, {color.blue()})"
    h, s, l, _a = color.getHslF()
    hue_deg = 0 if h < 0 else int(round(h * 360.0)) % 360
    sat_pct = int(round(s * 100.0))
    light_pct = int(round(l * 100.0))
    if show_alpha:
        return f"hsla({hue_deg}, {sat_pct}%, {light_pct}%, {color.alpha()})"
    return f"hsl({hue_deg}, {sat_pct}%, {light_pct}%)"


def parse_color_value(text: str, fmt: ValueFormat) -> QColor | None:
    """Parse a value field string in ``fmt`` back into a ``QColor``.

    Returns ``None`` for anything that does not parse. Alpha, when present,
    is applied; callers that want to ignore it decide via
    ``color_value_has_alpha``.
    """
    body = str(text or "").strip()
    if fmt is ValueFormat.HEX:
        return parse_hex_color(body)
    if fmt is ValueFormat.RGB:
        match = _RGB_RE.match(body)
        if match is None:
            return None
        channels = [int(_clamp(int(match.group(i)), 0, 255)) for i in (1, 2, 3)]
        color = QColor(*channels)
        alpha_token = match.group(4)
    else:
        match = _HSL_RE.match(body)
        if match is None:
            return None
        hue_deg = int(round(float(match.group(1)) % 360.0))
        sat_frac = _clamp(float(match.group(2)), 0, 100) / 100.0
        light_frac = _clamp(float(match.group(3)), 0, 100) / 100.0
        color = QColor.fromHslF(hue_deg / 360.0, sat_frac, light_frac)
        alpha_token = match.group(4)
    if alpha_token is not None:
        color.setAlpha(_parse_alpha_token(alpha_token))
    return color if color.isValid() else None


def color_value_has_alpha(text: str, fmt: ValueFormat) -> bool:
    """Whether ``text`` carries an explicit alpha component in ``fmt``."""
    body = str(text or "").strip()
    if fmt is ValueFormat.HEX:
        return len(body.lstrip("#")) == 8
    if fmt is ValueFormat.RGB:
        match = _RGB_RE.match(body)
    else:
        match = _HSL_RE.match(body)
    return match is not None and match.group(4) is not None


def _clamp(value: float, lo: int, hi: int) -> float:
    return max(lo, min(hi, value))


def _parse_alpha_token(token: str) -> int:
    token = token.strip()
    is_percent = token.endswith("%")
    value = float(token.rstrip("%"))
    if is_percent:
        scaled = value * 255.0 / 100.0
    elif "." in token:
        scaled = value * 255.0  # CSS float alpha, 0-1
    else:
        scaled = value  # integer alpha, 0-255
    return int(round(max(0.0, min(255.0, scaled))))


# ``rgb(R, G, B)`` / ``rgba(R, G, B, A)`` — alpha may be int 0-255, CSS
# float 0-1, or percent (the ``%`` stays inside the capture group so the
# parser can tell percent tokens apart from plain integers).
_RGB_RE = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*"
    r"(?:,\s*([0-9]*\.?[0-9]+\s*%?)\s*)?\)",
    re.IGNORECASE,
)

# ``hsl(H, S%, L%)`` / ``hsla(H, S%, L%, A%)`` — S/L may omit the percent
# sign; hue may exceed 359 (normalized); alpha as in RGB above.
_HSL_RE = re.compile(
    r"hsla?\(\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*%?\s*,\s*"
    r"([0-9]*\.?[0-9]+)\s*%?\s*(?:,\s*([0-9]*\.?[0-9]+\s*%?)\s*)?\)",
    re.IGNORECASE,
)