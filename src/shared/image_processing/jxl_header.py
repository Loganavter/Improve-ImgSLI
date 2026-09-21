"""JXL header-only dimensions (decode-bounds enforcement without a full decode).

The PIL/imagecodecs full-frame path must enforce MAX_SUPPORTED_IMAGE_DIMENSION
BEFORE allocating a decode buffer (an oversized JXL otherwise OOMs inside
``imagecodecs.imread`` ahead of any post-decode check). PIL reads other
formats' dims header-only via ``Image.open``; JXL needs its own probe:
first a PIL header attempt (works when a JXL plugin is registered), then a
bounded parse of the JXL codestream SizeHeader (ISO/IEC 18181-1 § SizeHeader,
cross-checked byte-for-byte against ``cjxl`` output for 18 files covering
the small/big x square/rect/ratio paths). Only the file prefix (64 KiB) is
ever read — never a full-frame decode.
"""

from __future__ import annotations

import os

from PIL import Image

_JXL_SIGNATURE = b"\xFF\x0A"
_JXL_FTYP_BRAND = b"jxl "
_JXL_HEADER_PREFIX_CAP = 65536

# Fixed aspect ratios indexed by SizeHeader ``ratio`` (1..7); ratio 0 means
# the width is stored explicitly. Order per the spec table.
_JXL_FIXED_RATIOS = ((1, 1), (12, 10), (4, 3), (3, 2), (16, 9), (5, 4), (2, 1))

# U32 width tables for the non-small SizeHeader dims: selector -> bit width.
_JXL_U32_WIDTHS = (9, 13, 18, 30)


class _JxlBitReader:
    """LSB-first bit reader over a bounded prefix (raises on exhaustion)."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, count: int) -> int:
        if count < 0:
            raise ValueError("negative bit count")
        if self._pos + count > len(self._data) * 8:
            raise ValueError("JXL header truncated")
        value = 0
        for i in range(count):
            byte = self._data[self._pos >> 3]
            value |= ((byte >> (self._pos & 7)) & 1) << i
            self._pos += 1
        return value


def _locate_jxl_codestream(prefix: bytes) -> int | None:
    """Offset of the JXL codestream (``FF 0A``) within ``prefix``.

    Handles raw codestreams (signature at 0) and BMFF containers (``ftyp``
    brand ``jxl `` followed by ``jxlc`` / first ``jxlp`` box). ``None`` when
    the prefix holds neither.
    """
    if prefix[:2] == _JXL_SIGNATURE:
        return 0
    if len(prefix) < 12 or prefix[4:8] != b"ftyp" or prefix[8:12] != _JXL_FTYP_BRAND:
        return None
    offset = 12
    while offset + 8 <= len(prefix):
        box_size = int.from_bytes(prefix[offset:offset + 4], "big")
        box_type = prefix[offset + 4:offset + 8]
        header = 8
        if box_size == 1:
            if offset + 16 > len(prefix):
                return None
            box_size = int.from_bytes(prefix[offset + 8:offset + 16], "big")
            header = 16
        elif box_size == 0:
            box_size = len(prefix) - offset
        if box_size < header:
            return None
        if box_type == b"jxlc":
            return offset + header
        if box_type == b"jxlp":
            # 4-byte jxlp_index precedes the codestream bytes.
            return offset + header + 4
        if box_size == 0:
            break
        offset += box_size
    return None


def _parse_jxl_codestream_size(prefix: bytes, offset: int) -> tuple[int, int] | None:
    """Parse SizeHeader at ``offset`` (past the signature). ``None`` on anomaly."""
    reader = _JxlBitReader(prefix[offset:])
    if reader.read(16) != 0x0AFF:
        return None
    small = reader.read(1)
    if small:
        height = (reader.read(5) + 1) * 8
    else:
        height = 1 + reader.read(_JXL_U32_WIDTHS[reader.read(2)])
    ratio = reader.read(3)
    if ratio == 0:
        if small:
            width = (reader.read(5) + 1) * 8
        else:
            width = 1 + reader.read(_JXL_U32_WIDTHS[reader.read(2)])
    elif 1 <= ratio <= len(_JXL_FIXED_RATIOS):
        num, den = _JXL_FIXED_RATIOS[ratio - 1]
        width = (int(height) * num) // den
    else:
        return None
    if not (0 < width <= 0xFFFFFFFF and 0 < height <= 0xFFFFFFFF):
        return None
    return (int(width), int(height))


def read_jxl_header_dimensions(path: str | os.PathLike) -> tuple[int, int] | None:
    """Header-only JXL dimensions, or ``None`` when unreadable.

    Tries a PIL header open first (no pixel decode), then the bounded
    codestream parse. Never performs a full-frame decode: oversized files
    stay cheap to reject.
    """
    path_str = os.fspath(path)
    try:
        with Image.open(path_str) as img:
            width, height = int(img.size[0]), int(img.size[1])
            if width > 0 and height > 0:
                return (width, height)
    except Exception:
        pass
    try:
        with open(path_str, "rb") as handle:
            prefix = handle.read(_JXL_HEADER_PREFIX_CAP)
    except OSError:
        return None
    try:
        offset = _locate_jxl_codestream(prefix)
        if offset is None:
            return None
        return _parse_jxl_codestream_size(prefix, offset)
    except (ValueError, IndexError):
        return None
