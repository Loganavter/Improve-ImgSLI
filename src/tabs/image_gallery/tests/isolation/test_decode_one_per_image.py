"""One decode per image across the triage pass (clustering + mode).

Owner invariant I2: no redundant image loads. The triage worker runs
``cluster_items`` and then ``select_mode`` over the SAME pool, and each of
those used to open the same file on its own:

* ``clustering.signature_for`` → ``compute_phash`` (``Image.open``) +
  ``embedding`` (``Image.open`` again);
* ``mode._average_sharpness`` → ``_sharpness`` (third ``Image.open``);
* ``mode.select_mode`` → ``exif_for`` → ``_has_exif`` (fourth ``Image.open``,
  header-only but still a separate handle).

Measured BEFORE the shared decode helper: **4 opens per image** for one cold
``cluster_items`` + ``select_mode`` (the plan brief said 3 — it missed the
EXIF-presence probe). After: **1** for the pool sizes covered by the frame
bound (``decode_cache._CACHE_LIMIT``); the fan-out itself is gone, and the
remaining >bound re-decode is a documented memory trade, not a second codec
path per consumer. See ``services/decode_cache.py``.

The parity tests pin the values to the PRE-change formulas copied inline
here, so a "one decode" optimisation cannot silently retune the dHash, the
HSV embedding, the Laplacian sharpness or the EXIF bit.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# -- pre-change math, copied verbatim from the modules at b39032eb ----------
# (independent oracle: never calls the implementation under test)


def _legacy_phash(path) -> int:
    from PIL import Image

    try:
        with Image.open(path) as im:
            try:
                im = im.convert("L")
            except Exception:
                im = im.convert("RGB").convert("L")
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:  # pragma: no cover - Pillow < 10
                resample = Image.LANCZOS
            small = im.resize((9, 8), resample)
            pixels = list(small.getdata())
            bits = 0
            for y in range(8):
                row_start = y * 9
                for x in range(8):
                    left = pixels[row_start + x]
                    right = pixels[row_start + x + 1]
                    bits = (bits << 1) | (1 if left > right else 0)
            return bits
    except Exception:
        return 0


def _legacy_embedding(path) -> list[float]:
    from PIL import Image

    zero = [0.0] * 192
    try:
        with Image.open(path) as im:
            try:
                im = im.convert("RGB")
            except Exception:
                return zero
            try:
                resample = Image.Resampling.BILINEAR
            except AttributeError:  # pragma: no cover - Pillow < 10
                resample = Image.BILINEAR
            small = im.resize((8, 8), resample)
            hsv = small.convert("HSV")
            data = list(hsv.getdata())
            vec: list[float] = []
            for h, s, v in data:
                vec.append(h / 255.0)
                vec.append(s / 255.0)
                vec.append(v / 255.0)
            if len(vec) != 192:
                vec = (vec + zero)[:192]
            return vec
    except Exception:
        return zero


def _legacy_sharpness(path) -> float | None:
    from PIL import Image

    try:
        with Image.open(path) as im:
            gray = im.convert("L")
            w, h = gray.size
            max_edge = max(w, h)
            if max_edge > 512:
                scale = 512 / max_edge
                nw, nh = int(w * scale), int(h * scale)
                try:
                    resample = Image.Resampling.BILINEAR
                except AttributeError:  # pragma: no cover - Pillow < 10
                    resample = Image.BILINEAR
                gray = gray.resize((max(nw, 1), max(nh, 1)), resample)
            pixels = list(gray.getdata())
            pw, ph = gray.size

            def _at(x: int, y: int) -> int:
                return pixels[y * pw + x]

            vals: list[float] = []
            for y in range(1, ph - 1):
                for x in range(1, pw - 1):
                    lap = (
                        _at(x, y - 1)
                        + _at(x - 1, y)
                        + _at(x + 1, y)
                        + _at(x, y + 1)
                        - 4 * _at(x, y)
                    )
                    vals.append(float(lap))
            if not vals:
                return 0.0
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            return var
    except Exception:
        return None


def _legacy_has_exif(path) -> bool:
    from PIL import Image

    try:
        with Image.open(path) as im:
            if hasattr(im, "getexif"):
                try:
                    exif = im.getexif()
                    if exif and len(exif) > 0:
                        return True
                except Exception:
                    pass
            if hasattr(im, "_getexif"):
                try:
                    if im._getexif():
                        return True
                except Exception:
                    pass
            if getattr(im, "info", None) and "exif" in im.info:
                return True
    except Exception:
        return False
    return False


# -- fixtures --------------------------------------------------------------


def _paint(path: Path, size=(96, 72)) -> Path:
    """Deterministic tiny PNG with structure (hashes + Laplacian non-zero)."""
    from PIL import Image

    w, h = size
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7 + y * 3) % 256, (x * 13 + 5) % 256, (y * 11 + 9) % 256)
    im.save(path)
    return path


class _OpenSpy:
    """Counts ``PIL.Image.open`` calls per resolved path (no decode change)."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self._patcher = None

    def start(self):
        from unittest.mock import patch

        import PIL.Image

        real = PIL.Image.open

        def _counted(target, *a, **k):
            try:
                key = str(Path(target).resolve())
            except Exception:
                key = "<other>"
            self.counts[key] = self.counts.get(key, 0) + 1
            return real(target, *a, **k)

        self._patcher = patch.object(PIL.Image, "open", _counted)
        self._patcher.start()
        return self

    def stop(self) -> None:
        if self._patcher is not None:
            self._patcher.stop()
            self._patcher = None

    def opens_for(self, path: Path) -> int:
        return self.counts.get(str(Path(path).resolve()), 0)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _clear_triage_caches() -> None:
    from tabs.image_gallery.services import clustering, decode_cache, mode

    clustering.clear_signature_cache()
    mode.clear_sharpness_cache()
    mode.clear_exif_cache()
    decode_cache.clear()


# -- the invariant ---------------------------------------------------------


def test_triage_decodes_each_image_once(tmp_path) -> None:
    """cluster_items + select_mode open each file exactly ONCE (cold pool).

    Pool size is ``decode_cache._CACHE_LIMIT`` (4): the shared frame survives
    from the clustering pass into the mode pass. ``cluster_items`` and
    ``select_mode`` are two FULL passes over the pool, so a pool larger than
    the frame bound re-decodes its overflow in the second pass — that is the
    documented memory cap, not a fan-out (see ``services/decode_cache.py``).
    """
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.services import clustering, mode

    paths = [
        _paint(tmp_path / f"{i}.png", size=(96 + 8 * i, 72)) for i in range(4)
    ]
    items = [
        GalleryItem(path=p, mtime_ns=p.stat().st_mtime_ns) for p in paths
    ]

    _clear_triage_caches()
    spy = _OpenSpy().start()
    try:
        series = clustering.cluster_items(items)
        mode.select_mode(series, items, None)
    finally:
        spy.stop()

    for p in paths:
        assert spy.opens_for(p) == 1, (p.name, spy.counts)
    assert spy.total == len(paths)

    # Warm regroup: signatures + sharpness + EXIF are all cached, so a second
    # triage pass over the same files opens NOTHING.
    spy = _OpenSpy().start()
    try:
        series = clustering.cluster_items(items)
        mode.select_mode(series, items, None)
    finally:
        spy.stop()
    assert spy.total == 0, spy.counts


def test_new_mtime_misses_decode_cache(tmp_path) -> None:
    """A changed mtime is a different key: never serve the old frame."""
    from tabs.image_gallery.services import decode_cache

    p = _paint(tmp_path / "m.png")
    decode_cache.clear()
    spy = _OpenSpy().start()
    try:
        first = decode_cache.decode_image(p)
        again = decode_cache.decode_image(p)
        assert first is not None and again is first  # same cached frame
        assert spy.opens_for(p) == 1

        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        third = decode_cache.decode_image(p)
    finally:
        spy.stop()

    assert third is not None and third is not first
    assert spy.opens_for(p) == 2


# -- parity with the pre-change formulas -----------------------------------


def test_signature_parity_with_pre_change_math(tmp_path) -> None:
    from tabs.image_gallery.services import clustering, decode_cache

    # 640x480 exercises the >512 sharpness downscale path as well.
    p = _paint(tmp_path / "parity.png", size=(640, 480))
    clustering.clear_signature_cache()
    decode_cache.clear()

    phash, emb = clustering.signature_for(p)

    assert phash == _legacy_phash(p)
    assert emb == _legacy_embedding(p)  # exact floats: same frame, same math


def test_sharpness_and_exif_parity_with_pre_change_math(tmp_path) -> None:
    from tabs.image_gallery.services import decode_cache, mode

    p = _paint(tmp_path / "parity_sharp.png", size=(640, 480))
    mode.clear_sharpness_cache()
    mode.clear_exif_cache()
    decode_cache.clear()

    assert mode.sharpness_for(p) == _legacy_sharpness(p)
    assert mode.exif_for(p) is _legacy_has_exif(p)


def test_failure_paths_still_degrade(tmp_path) -> None:
    """Unreadable files keep today's 0 / zero-vector / None / False contract."""
    from tabs.image_gallery.services import clustering, decode_cache, mode

    p = tmp_path / "broken.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    clustering.clear_signature_cache()
    mode.clear_sharpness_cache()
    mode.clear_exif_cache()
    decode_cache.clear()

    assert clustering.signature_for(p) == (0, [0.0] * 192)
    assert mode.sharpness_for(p) is None
    assert mode.exif_for(p) is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
