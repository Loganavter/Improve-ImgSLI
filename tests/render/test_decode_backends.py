"""Decode-backend tests: pyvips streaming vs PIL/imagecodecs full-frame bound.

Covers the archived pyvips-streaming plan's Phase 1/4 contract (private improve-imgsli-internal-docs repo):
- `from_path` streams (no MAX_SUPPORTED_IMAGE_DIMENSION bound) when the
  installed libvips can stream the file's format;
- the PIL/imagecodecs fallback always enforces the bound;
- previews use the streaming path when available;
- the per-format capability probe (`pyvips_can_stream`) is consistent.

Environment note: the dev `venv/` resolves pyvips to `pyvips-binary`
(no libjxl), so JXL-specific assertions are written against
`pyvips_can_stream` rather than hardcoding a capability.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image

from core.constants import AppConstants
from shared.image_processing import progressive_loader as pl
from engine.store.tiled_pixel_store import TiledPixelStore


def _write_rgba_png(path: str, width: int, height: int) -> None:
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, :3] = 128
    arr[:, :, 3] = 255
    Image.fromarray(arr, mode="RGBA").save(path, format="PNG")


def _can_stream_any() -> bool:
    """Whether the current env can stream *any* format via pyvips."""
    return pl.PYVIPS_SUPPORTED and bool(pl._vips_suffixes())


def test_pyvips_can_stream_is_per_format(tmp_path):
    png = tmp_path / "a.png"
    _write_rgba_png(str(png), 8, 8)
    # Env-independent: an unknown suffix never streams.
    assert pl.pyvips_can_stream(str(png) + ".qzx") is False
    if not pl.PYVIPS_SUPPORTED:
        assert pl.pyvips_can_stream(str(png)) is False
        return
    # Degrade-tolerant: probe consistency with the installed libvips build,
    # not a hardcoded capability (wheels report different streamable
    # suffixes per platform). Mirrors test_jxl_probe_consistent_with_suffixes.
    assert pl.pyvips_can_stream(str(png)) == (".png" in pl._vips_suffixes())
    if pl.pyvips_can_stream(str(png)):
        return
    # Fallback contract when this build reports png as non-streamable:
    # the PIL/imagecodecs path must enforce the bound.
    big = tmp_path / "big_fallback.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    assert pl.pyvips_can_stream(str(big)) is False
    try:
        TiledPixelStore.from_path(str(big))
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("PIL fallback must enforce MAX_SUPPORTED_IMAGE_DIMENSION")


def test_from_path_streams_oversized_image_when_backend_can(tmp_path):
    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)

    if _can_stream_any():
        store = TiledPixelStore.from_path(str(big))
        try:
            assert store.size == (AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
        finally:
            store.close()
    else:
        try:
            TiledPixelStore.from_path(str(big))
        except pl.ImageSizeLimitError:
            pass
        else:
            raise AssertionError("PIL fallback must enforce MAX_SUPPORTED_IMAGE_DIMENSION")


def test_from_path_enforces_bound_on_non_streamable_extension(tmp_path):
    """A >65536 file whose extension pyvips can't stream must hit the bound
    even when pyvips is installed (the fallback backend is PIL/imagecodecs)."""
    fake = tmp_path / "huge.qzx"
    _write_rgba_png(str(fake), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    assert pl.pyvips_can_stream(str(fake)) is False

    try:
        TiledPixelStore.from_path(str(fake))
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("Non-streamable >65536 file must raise ImageSizeLimitError")


def test_small_image_loads_regardless_of_backend(tmp_path):
    png = tmp_path / "small.png"
    _write_rgba_png(str(png), 64, 48)
    store = TiledPixelStore.from_path(str(png))
    try:
        assert store.size == (64, 48)
        assert store.mode == "RGBA"
    finally:
        store.close()


def test_load_preview_image_bounded_streaming_path(tmp_path):
    from PySide6.QtGui import QImage

    png = tmp_path / "wide.png"
    _write_rgba_png(str(png), 2048, 40)

    preview = pl.load_preview_image(str(png))
    assert isinstance(preview, QImage)
    assert preview.format() == QImage.Format.Format_RGBA8888
    assert max(preview.width(), preview.height()) <= 1024
    assert preview.width() == 1024 or preview.height() == 1024


def test_get_image_dimensions_oversized_with_streaming(tmp_path):
    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    if _can_stream_any():
        assert pl.get_image_dimensions(str(big)) == (
            AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000,
            10,
        )
    else:
        try:
            pl.get_image_dimensions(str(big))
        except pl.ImageSizeLimitError:
            pass
        else:
            raise AssertionError("dimensions probe must enforce the bound without pyvips")


def test_auto_crop_vips_and_pil_agree(tmp_path):
    from shared.image_processing.resize import get_auto_crop_box
    from engine.store.tiled_pixel_store import _find_trim_box_vips

    arr = np.zeros((60, 80, 4), dtype=np.uint8)
    arr[10:50, 20:60, :3] = 200
    arr[10:50, 20:60, 3] = 255
    rgba = Image.fromarray(arr, mode="RGBA")

    vips_box = _find_trim_box_vips(np.asarray(rgba), threshold=15)
    pil_box = get_auto_crop_box(rgba, 15)

    if vips_box is not None:
        assert pil_box is not None, "PIL auto-crop disagreed with vips find_trim"
        assert tuple(int(v) for v in vips_box) == tuple(pil_box)
    # When pyvips is absent vips_box is None and the PIL path is authoritative;
    # nothing to assert there beyond running without error.


def test_forced_pil_fallback_still_enforces_bound(monkeypatch, tmp_path):
    """Force the no-pyvips path even when pyvips is installed, so the PIL
    fallback branch is exercised in every environment."""
    monkeypatch.setattr(pl, "PYVIPS_SUPPORTED", False)
    # monkeypatch (not a bare assignment): the memo is process-wide and a
    # leftover empty frozenset tells every later test that NOTHING streams,
    # sending each decode down the bounded PIL path (measured 2026-10-27).
    monkeypatch.setattr(pl, "_vips_suffixes_cache", frozenset())
    assert pl.pyvips_can_stream("anything.png") is False

    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    try:
        TiledPixelStore.from_path(str(big))
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("PIL fallback must enforce MAX_SUPPORTED_IMAGE_DIMENSION")

    small = tmp_path / "small.png"
    _write_rgba_png(str(small), 32, 24)
    store = TiledPixelStore.from_path(str(small))
    try:
        assert store.size == (32, 24)
    finally:
        store.close()


def test_stream_failure_falls_back_with_bound(monkeypatch, tmp_path):
    """pyvips is installed and the file's format is streamable, but the
    stream attempt itself raises -> the PIL/imagecodecs fallback must still
    enforce MAX_SUPPORTED_IMAGE_DIMENSION."""
    if not _can_stream_any():
        return

    import engine.store.tiled_pixel_store as tps

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated stream failure")

    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    assert pl.pyvips_can_stream(str(big)) is True

    monkeypatch.setattr(tps, "_stream_pyvips_to_memmap", _boom)
    try:
        TiledPixelStore.from_path(str(big))
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("stream-failure fallback must enforce the bound")


def test_jxl_probe_consistent_with_suffixes():
    assert pl.pyvips_can_stream("sample.JXL") == (".jxl" in pl._vips_suffixes())
    assert pl.pyvips_can_stream("sample.jpg") == (".jpg" in pl._vips_suffixes())


# ---------------------------------------------------------------------------
# Task 2 (task-fix-decode-bounds-2026-09-20): JXL dims come from the header,
# and the backend bound fires BEFORE any full-frame decode. The codestream
# prefixes below are real ``cjxl`` output bytes (not synthesised), pinning
# the small/big x square/rect/ratio SizeHeader paths.
# ---------------------------------------------------------------------------

_RAW_SMALL_SQUARE = bytes.fromhex("ff0a4f060013080100")  # 64x64
_RAW_SMALL_RECT = bytes.fromhex("ff0a07c20013080100")  # 16x32 (ratio 0)
_RAW_BIG_RECT = bytes.fromhex("ff0a2802c60c001308")  # 100x70 (ratio 0)
_RAW_BIG_SQUARE = bytes.fromhex("ff0a3a9c1900130801")  # 5000x5000 (ratio 1)
_RAW_BIG_641 = bytes.fromhex("ff0af08e00c5001308")  # 641x479


def _write_jxl(path, payload: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(payload + bytes(64))


def _box(box_type: bytes, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + box_type + payload


def _jxl_container(codestream: bytes, *, progressive: bool = False) -> bytes:
    ftyp = _box(b"ftyp", b"jxl ")
    if progressive:
        return ftyp + _box(b"jxlp", (0).to_bytes(4, "big") + codestream)
    return ftyp + _box(b"jxlc", codestream)


class _BitWriter:
    def __init__(self):
        self._bits: list[int] = []

    def write(self, count: int, value: int) -> None:
        for i in range(count):
            self._bits.append((value >> i) & 1)

    def bytes(self) -> bytes:
        out = bytearray((len(self._bits) + 7) // 8)
        for i, bit in enumerate(self._bits):
            out[i >> 3] |= bit << (i & 7)
        return bytes(out)


def _synth_jxl_codestream(width: int, height: int) -> bytes:
    """Spec-mirror SizeHeader synthesis (encoder selection per libjxl Set)."""
    ratios = ((1, 1), (12, 10), (4, 3), (3, 2), (16, 9), (5, 4), (2, 1))
    ratio = 0
    for index, (num, den) in enumerate(ratios, start=1):
        if width == (height * num) // den and (height * num) % den == 0:
            ratio = index
            break
    small = (
        height <= 256
        and height % 8 == 0
        and (ratio != 0 or (width <= 256 and width % 8 == 0))
    )
    writer = _BitWriter()
    writer.write(8, 0xFF)
    writer.write(8, 0x0A)
    writer.write(1, 1 if small else 0)
    if small:
        writer.write(5, height // 8 - 1)
    else:
        value = height - 1
        widths = (9, 13, 18, 30)
        selector = next(
            s for s in range(4) if value < (1 << widths[s])
        )
        writer.write(2, selector)
        writer.write(widths[selector], value)
    writer.write(3, ratio)
    if ratio == 0:
        if small:
            writer.write(5, width // 8 - 1)
        else:
            value = width - 1
            widths = (9, 13, 18, 30)
            selector = next(
                s for s in range(4) if value < (1 << widths[s])
            )
            writer.write(2, selector)
            writer.write(widths[selector], value)
    return writer.bytes()


def test_jxl_header_dimensions_from_real_cjxl_bytes(tmp_path):
    cases = [
        (_RAW_SMALL_SQUARE, (64, 64)),
        (_RAW_SMALL_RECT, (16, 32)),
        (_RAW_BIG_RECT, (100, 70)),
        (_RAW_BIG_SQUARE, (5000, 5000)),
        (_RAW_BIG_641, (641, 479)),
    ]
    for index, (prefix, dims) in enumerate(cases):
        raw = tmp_path / f"real_raw_{index}.jxl"
        _write_jxl(str(raw), prefix)
        assert pl.read_jxl_header_dimensions(str(raw)) == dims
        boxed = tmp_path / f"real_box_{index}.jxl"
        _write_jxl(str(boxed), _jxl_container(prefix))
        assert pl.read_jxl_header_dimensions(str(boxed)) == dims
        partial = tmp_path / f"real_jxlp_{index}.jxl"
        _write_jxl(str(partial), _jxl_container(prefix, progressive=True))
        assert pl.read_jxl_header_dimensions(str(partial)) == dims


def test_jxl_header_synth_roundtrip(tmp_path):
    for dims in [(8, 8), (256, 256), (257, 257), (70000, 70000), (70000, 100)]:
        stream = _synth_jxl_codestream(*dims)
        path = tmp_path / f"synth_{dims[0]}x{dims[1]}.jxl"
        _write_jxl(str(path), _jxl_container(stream))
        assert pl.read_jxl_header_dimensions(str(path)) == dims


def test_jxl_header_unreadable_returns_none(tmp_path):
    garbage = tmp_path / "garbage.jxl"
    garbage.write_bytes(bytes(128))
    assert pl.read_jxl_header_dimensions(str(garbage)) is None
    truncated = tmp_path / "truncated.jxl"
    truncated.write_bytes(b"\xff\x0a\x28")
    assert pl.read_jxl_header_dimensions(str(truncated)) is None


def _install_fake_imagecodecs(monkeypatch, calls: dict):
    import sys
    import types

    fake = types.ModuleType("imagecodecs")

    def _imread(path):
        calls["n"] += 1
        raise AssertionError("full JXL decode must not run before the bound check")

    fake.imread = _imread
    monkeypatch.setitem(sys.modules, "imagecodecs", fake)
    monkeypatch.setattr(pl, "JXL_SUPPORTED", True)
    monkeypatch.setattr(pl, "PYVIPS_SUPPORTED", False)
    # monkeypatch (not a bare assignment): the memo is process-wide and a
    # leftover empty frozenset tells every later test that NOTHING streams,
    # sending each decode down the bounded PIL path (measured 2026-10-27).
    monkeypatch.setattr(pl, "_vips_suffixes_cache", frozenset())
    return fake


def _oversized_jxl(tmp_path, name="huge.jxl"):
    path = tmp_path / name
    _write_jxl(str(path), _jxl_container(_synth_jxl_codestream(70000, 70000)))
    return str(path)


def test_oversized_jxl_without_pyvips_raises_before_decode(monkeypatch, tmp_path):
    """P0 repro: oversized JXL on a backend without streaming decode must
    raise ImageSizeLimitError from the header — never reach imread (OOM)."""
    calls = {"n": 0}
    _install_fake_imagecodecs(monkeypatch, calls)
    path = _oversized_jxl(tmp_path)

    try:
        pl.load_preview_image(path)
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("oversized JXL preview must raise ImageSizeLimitError")
    assert calls["n"] == 0

    try:
        pl.get_image_dimensions(path)
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("oversized JXL dimensions must raise ImageSizeLimitError")
    assert calls["n"] == 0

    try:
        pl.should_use_progressive_load(path)
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("oversized JXL probe must raise ImageSizeLimitError")


def test_small_jxl_still_decodes_when_bounded(monkeypatch, tmp_path):
    """A bounded JXL still reaches the decoder (the bound gates, not bans)."""
    import numpy as np

    calls = {"n": 0}
    fake = _install_fake_imagecodecs(monkeypatch, calls)
    arr = np.zeros((70, 100, 3), dtype=np.uint8)
    arr[:, :, 0] = 200
    fake.imread = lambda _path: (calls.__setitem__("n", calls["n"] + 1), arr)[1]

    path = tmp_path / "small.jxl"
    _write_jxl(str(path), _jxl_container(_synth_jxl_codestream(100, 70)))
    dims = pl.get_image_dimensions(str(path))
    assert dims == (100, 70)
    assert calls["n"] == 0, "header dims must answer with no decode at all"


def test_autocrop_probe_honors_bound_without_decode(monkeypatch, tmp_path):
    """The autocrop probe must not full-decode an oversized file to look for
    margins; a bounded file still probes normally."""
    import sys
    import types

    import numpy as np

    from shared.image_processing.autocrop import CropService

    calls = {"n": 0}
    fake = types.ModuleType("imagecodecs")

    def _imread(path):
        calls["n"] += 1
        return np.zeros((70, 100, 3), dtype=np.uint8)

    fake.imread = _imread
    monkeypatch.setitem(sys.modules, "imagecodecs", fake)
    monkeypatch.setattr(pl, "PYVIPS_SUPPORTED", False)
    # monkeypatch (not a bare assignment): the memo is process-wide and a
    # leftover empty frozenset tells every later test that NOTHING streams,
    # sending each decode down the bounded PIL path (measured 2026-10-27).
    monkeypatch.setattr(pl, "_vips_suffixes_cache", frozenset())

    huge = _oversized_jxl(tmp_path, name="huge_crop.jxl")
    assert CropService().get(huge) is None
    assert calls["n"] == 0

    small = tmp_path / "small_crop.jxl"
    _write_jxl(str(small), _jxl_container(_synth_jxl_codestream(100, 70)))

    bordered = np.zeros((70, 100, 3), dtype=np.uint8)
    bordered[15:55, 20:80, :] = 200

    def _imread_small(path):
        calls["n"] += 1
        return bordered

    fake.imread = _imread_small
    box = CropService().get(str(small))
    assert box is not None
    left, top, right, bottom = box.to_tuple()
    assert left >= 15 and top >= 10 and right <= 85 and bottom <= 60
    assert calls["n"] == 1


def test_auto_crop_end_to_end_streaming_matches_pil(monkeypatch, tmp_path):
    """Auto-crop through the pyvips streaming path and the PIL fallback must
    agree on the crop box for the same source (the two paths use different
    probes: pyvips thumbnail+find_trim vs the PIL get_auto_crop_box probe)."""
    arr = np.zeros((200, 300, 4), dtype=np.uint8)
    arr[30:170, 40:260, :3] = 180
    arr[30:170, 40:260, 3] = 255
    path = tmp_path / "margins.png"
    Image.fromarray(arr, mode="RGBA").save(str(path), format="PNG")

    if not _can_stream_any():
        store = TiledPixelStore.from_path(str(path), auto_crop=True)
        try:
            assert store.size == (220, 140)
        finally:
            store.close()
        return

    store_stream = TiledPixelStore.from_path(str(path), auto_crop=True)
    try:
        size_stream = store_stream.size
    finally:
        store_stream.close()

    monkeypatch.setattr(pl, "PYVIPS_SUPPORTED", False)
    # monkeypatch (not a bare assignment): the memo is process-wide and a
    # leftover empty frozenset tells every later test that NOTHING streams,
    # sending each decode down the bounded PIL path (measured 2026-10-27).
    monkeypatch.setattr(pl, "_vips_suffixes_cache", frozenset())
    store_pil = TiledPixelStore.from_path(str(path), auto_crop=True)
    try:
        size_pil = store_pil.size
    finally:
        store_pil.close()

    assert size_pil == (220, 140)
    assert size_stream == size_pil