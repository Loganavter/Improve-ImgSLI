"""16-bit PNG streaming must keep opaque alpha (ic-right-image-vanish-2026-09-19).

Root cause of the vanish: ``_stream_pyvips_to_memmap`` did ``bandjoin(255)``
while the image was still ``ushort`` (16-bit source), then scaled with
``(img / 257).cast("uchar")`` — alpha ``255 / 257 -> 0``. The store ended up
fully transparent with healthy-looking RGB, so every CPU probe stayed green
(sized uploads, non-blank RGB, split/instance match) while live canvas, loupe
and export all rendered white. Previews survived because the PIL/thumbnail
path joins alpha in the 8-bit domain.
"""

import os
import struct
import zlib

import numpy as np
import pytest

pyvips = pytest.importorskip("pyvips")

from engine.store.tiled_pixel_store import _stream_pyvips_to_memmap


def _write_16bit_rgb_png(path, w=24, h=16):
    """Minimal stdlib 16-bit RGB PNG writer (bit depth 16, color type 2).

    Samples are ``v * 257`` so the correct 16->8-bit scale (``/ 257``) lands
    exactly on ``v``.
    """

    def chunk(typ: bytes, data: bytes) -> bytes:
        out = struct.pack(">I", len(data)) + typ + data
        out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)
    raw = b"".join(
        b"\x00"
        + b"".join(
            struct.pack(">HHH", x * 257, y * 257, 128 * 257) for x in range(w)
        )
        for y in range(h)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as fh:
        fh.write(png)


def test_stream_16bit_png_keeps_opaque_alpha(tmp_path):
    src = tmp_path / "sixteen.png"
    _write_16bit_rgb_png(src)
    w, h = 24, 16

    memmap, spill_path, out_w, out_h = _stream_pyvips_to_memmap(
        os.fspath(src), os.fspath(tmp_path)
    )
    try:
        assert (out_w, out_h) == (w, h)
        arr = np.asarray(memmap)
        assert arr.shape == (h, w, 4)
        # Alpha must be opaque everywhere — 0 here rendered the whole
        # right slot white (live, loupe, export) with all CPU probes green.
        assert arr[..., 3].min() == 255
        assert arr[..., 3].max() == 255
        # RGB must be the correctly scaled content, not low-byte truncation.
        assert arr[5, 7, 0] == 7
        assert arr[5, 7, 1] == 5
        assert arr[5, 7, 2] == 128
    finally:
        memmap.flush()
        try:
            memmap._mmap.close()  # noqa: SLF001 — release file for unlink
        except Exception:
            pass
        del memmap
        try:
            os.remove(spill_path)
        except OSError:
            pass


def test_stream_16bit_png_end_to_end_from_path(tmp_path):
    from engine.store.tiled_pixel_store import TiledPixelStore

    src = tmp_path / "sixteen.png"
    _write_16bit_rgb_png(src)

    store = TiledPixelStore.from_path(os.fspath(src), tmp_dir=os.fspath(tmp_path))
    try:
        assert (store.width, store.height) == (24, 16)
        arr = np.asarray(store.crop((0, 0, 24, 16)))
        assert arr.shape == (16, 24, 4)
        assert arr[..., 3].min() == 255
        assert arr[5, 7, 0] == 7
        assert arr[5, 7, 1] == 5
    finally:
        store.close()
