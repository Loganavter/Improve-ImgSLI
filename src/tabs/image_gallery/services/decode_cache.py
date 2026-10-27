"""One decoded frame per file for the triage pass — pure, process-local.

Cold triage used to open each file FOUR times: ``clustering.compute_phash``,
``clustering.embedding``, ``mode._sharpness`` and ``mode._has_exif`` each
called ``Image.open`` themselves. The triage worker (``triage_run``) runs
``cluster_items`` and then ``select_mode`` over the SAME pool, so all four
consumers now share one decoded frame (owner invariant I2: no redundant
image loads). Two ``convert`` calls on that frame are cheaper than a second
codec run.

Key: ``(resolved path, st_mtime_ns, st_size)`` — an edit (new mtime or
size) never serves the old pixels. No content digest here, deliberately: this
cache holds a DECODED FRAME in memory for one triage pass, so producing the
digest would have to read the same bytes a second time before the decoder does
— the opposite of what this cache exists for (``(path, mtime_ns, size)`` is the
cheap stat identity, and a frame never outlives the process, so a rewrite cannot
hide behind it across runs; the result caches are the ones that need
``content_digest``). Bounded LRU (4 frames): one decoded frame
is the working set of the sequential triage worker. The catch that comes with
a frame bound: ``cluster_items`` and ``select_mode`` are two FULL passes over
the pool, so a pool larger than the bound keeps the frames of its last 4
files and the mode pass re-decodes the overflow (measured: 4 opens/item
before, 1 for pools <= bound, 3 for a 6-item pool). Raising the bound trades
memory 1:1 for that overflow; a real fix for huge cold folders is a single
per-item probe pass, not a bigger frame cache. A miss simply decodes again,
so the bound is a memory cap, never a correctness surface. Process-local by
design: no cross-process cache, no implicit invalidation.

EXIF orientation is applied ONCE here (``ImageOps.exif_transpose``), so a
rotated photo is measured in display orientation. ``exif_present`` is
recorded from the RAW frame BEFORE the transpose moves/strips the
orientation tag, keeping ``mode.exif_for``'s pre-change answer.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any

from PIL import Image, ImageOps

#: Sequential triage worker: one item's signature + mode probes fit together.
_CACHE_LIMIT = 4

_LOCK = threading.RLock()
_CACHE: "OrderedDict[tuple[str, int, int], tuple[Any, bool]]" = OrderedDict()


def _key(path) -> tuple[str, int, int] | None:
    """Stat key for *path*; None when it cannot be resolved/statted."""
    try:
        resolved = os.path.realpath(os.fspath(path))
        st = os.stat(resolved)
        return (resolved, int(getattr(st, "st_mtime_ns", 0)), int(st.st_size))
    except Exception:
        return None


def _raw_has_exif(im) -> bool:
    """Mirrors ``mode._has_exif`` on the RAW frame (before transpose)."""
    try:
        if hasattr(im, "getexif"):
            try:
                exif = im.getexif()
                if exif and len(exif) > 0:
                    return True
            except Exception:
                pass
        if hasattr(im, "_getexif"):
            try:
                if im._getexif():  # type: ignore[attr-defined]
                    return True
            except Exception:
                pass
        if getattr(im, "info", None) and "exif" in im.info:
            return True
    except Exception:
        pass
    return False


def _load(path) -> tuple[Any, bool] | None:
    """Decode *path* once: orientation-applied frame + raw EXIF bit."""
    try:
        with Image.open(path) as raw:
            exif = _raw_has_exif(raw)
            try:
                image = ImageOps.exif_transpose(raw)
            except Exception:
                image = None
            if image is None:  # defensive: in_place=False always returns a copy
                image = raw.copy()
            image.load()
            return (image, exif)
    except Exception:
        return None


def _store(key: tuple[str, int, int], image, exif: bool) -> None:
    with _LOCK:
        _CACHE[key] = (image, exif)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_LIMIT:
            _CACHE.popitem(last=False)


def decode_image(path):
    """Shared decoded frame for *path* (read-only — callers never mutate it).

    Returns None when the file is unreadable; callers keep their existing
    fail-closed values (0 hash / zero vector / None sharpness / False EXIF).
    """
    key = _key(path)
    if key is not None:
        with _LOCK:
            hit = _CACHE.get(key)
            if hit is not None:
                _CACHE.move_to_end(key)
                return hit[0]
    loaded = _load(path)
    if loaded is None:
        return None
    image, exif = loaded
    if key is not None:
        _store(key, image, exif)
    return image


def exif_present(path) -> bool | None:
    """Cached EXIF-presence bit for *path* from the SAME decode (None = unreadable)."""
    key = _key(path)
    if key is not None:
        with _LOCK:
            hit = _CACHE.get(key)
            if hit is not None:
                _CACHE.move_to_end(key)
                return hit[1]
    loaded = _load(path)
    if loaded is None:
        return None
    image, exif = loaded
    if key is not None:
        _store(key, image, exif)
    return exif


def clear() -> int:
    """Drop every cached frame. Returns entries cleared (tests)."""
    with _LOCK:
        n = len(_CACHE)
        _CACHE.clear()
    return n


__all__ = ["decode_image", "exif_present", "clear"]
