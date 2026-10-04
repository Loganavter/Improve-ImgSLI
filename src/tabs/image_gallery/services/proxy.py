"""Shared bounded proxy decodes for gallery Stage-2 analyses.

Phase-1 proxy sharing: artifact + fidelity + camera stages used to fully
decode every image themselves (artifacts opens item+source per item,
fidelity opens item+source per item, camera opens 3x per item — source
re-decoded N times per stage). All three stages now consume one shared
bounded proxy per file (longest edge <= ``PROXY_MAX_EDGE``) built here:

- cold path: ONE full decode per item total; the source decoded ONCE total
  (in-memory cache shared across items and stages);
- warm path (proxy cached): ZERO decodes — ``proxy_for`` serves the cached
  image without touching ``Image.open``.

Fail-closed identity: the cache key is ``(resolved path, mtime_ns, size)``
so an edited file misses and recomputes; proxies are never shared between
different paths. Cached images are read-only inputs — stage entry points
must never mutate or close them (detectors only ``resize``/``convert``,
which return new images).

Pure + Qt-free (safe for ``GenericWorker``); no Store/EventBus writes.

INTERFACE: ``PROXY_MAX_EDGE``, ``Proxy``, ``proxy_for``,
``clear_proxy_cache``, ``run_proxy_stages_sync``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger("ImproveImgSLI")

#: Longest edge of a shared proxy. Matches the fidelity SSIM cap
#: (``services/fidelity_metrics._SSIM_MAX_EDGE``) so the SSIM engine sees
#: exactly the pixels it would have capped to itself; every other consumer
#: caps further down (512 / 64) and is resolution-insensitive past that.
PROXY_MAX_EDGE = 1024

_PROXY_CACHE_LIMIT = 256


class Proxy(NamedTuple):
    """One shared bounded decode: RGB pixels + original full-res size."""

    image: object  # PIL.Image.Image in RGB, longest edge <= PROXY_MAX_EDGE
    size: tuple[int, int]  # original (w, h) BEFORE the proxy downscale


_PROXY_CACHE: dict[tuple[str, int, int], Proxy] = {}


def clear_proxy_cache() -> int:
    """Drop cached proxies. Returns entries cleared (tests)."""
    try:
        n = len(_PROXY_CACHE)
    except Exception:
        return 0
    try:
        _PROXY_CACHE.clear()
    except Exception:
        pass
    return n


def _stat_key(path: Path) -> tuple[str, int, int] | None:
    """Content key for *path*: (resolved, mtime_ns, size); None on miss."""
    try:
        resolved = str(Path(path).resolve())
        st = os.stat(resolved)
        return (resolved, int(getattr(st, "st_mtime_ns", 0)), int(st.st_size))
    except Exception:
        return None


def _build_proxy(path: Path) -> Proxy | None:
    """Decode *path* once, normalize to RGB, downscale to PROXY_MAX_EDGE."""
    try:
        from PIL import Image as _Image
    except Exception:
        return None
    try:
        with _Image.open(path) as im:
            try:
                orig = (int(im.size[0]), int(im.size[1]))
            except Exception:
                orig = (0, 0)
            try:
                rgb = im.convert("RGB")
            except Exception:
                return None
            try:
                w, h = rgb.size
                m = max(w, h)
                if m > PROXY_MAX_EDGE and m > 0:
                    scale = PROXY_MAX_EDGE / m
                    try:
                        resample = _Image.Resampling.BILINEAR  # type: ignore[attr-defined]
                    except AttributeError:
                        resample = _Image.BILINEAR  # type: ignore[attr-defined]
                    rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))), resample)
            except Exception:
                pass
            try:
                rgb.load()
            except Exception:
                pass
            # convert/resize detach from the file handle — safe past close.
            return Proxy(image=rgb, size=orig)
    except Exception:
        logger.debug("proxy: decode failed for %s", path, exc_info=True)
        return None


def proxy_for(path: Path | str) -> Proxy | None:
    """Shared bounded proxy for *path* (cached; None when unreadable).

    Cold: exactly one ``Image.open`` for a readable file. Warm: no decode
    at all — the cached proxy is returned as-is (callers must not mutate
    or close it).
    """
    try:
        p = Path(path)
    except Exception:
        return None
    key = _stat_key(p)
    if key is None:
        return None
    try:
        hit = _PROXY_CACHE.get(key)
    except Exception:
        hit = None
    if hit is not None:
        return hit
    proxy = _build_proxy(p)
    if proxy is None:
        return None
    try:
        if len(_PROXY_CACHE) >= _PROXY_CACHE_LIMIT:
            for old in list(_PROXY_CACHE)[: _PROXY_CACHE_LIMIT // 4]:
                try:
                    del _PROXY_CACHE[old]
                except Exception:
                    pass
        _PROXY_CACHE[key] = proxy
    except Exception:
        pass
    return proxy


def run_proxy_stages_sync(
    items: list,
    source_path: Path | str | None,
    *,
    include_camera: bool = False,
) -> dict[str, dict]:
    """Single-pass Stage-2 worker body for ``GenericWorker``.

    Builds each item proxy ONCE and the source proxy ONCE, then runs the
    artifact catalog + fidelity metrics (+ camera scalars when
    ``include_camera``) over the shared bytes. Returns
    ``{str(item.path): {"artifacts": {...}, "fidelity": {...},
    "camera": {...}}}`` — stage dicts present only when that stage was
    requested and measurable (fail-closed per item, path-keyed, never
    copied between items). The controller still owns delivery (wave B).
    """
    from tabs.image_gallery.services.artifacts import analyze_images
    from tabs.image_gallery.services.camera_metrics import measure_camera_from_image
    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_from_images

    out: dict[str, dict] = {}
    try:
        src_proxy = proxy_for(source_path) if source_path is not None else None
    except Exception:
        src_proxy = None
    for it in items or []:
        try:
            own = Path(getattr(it, "path"))
        except Exception:
            continue
        key = str(own)
        entry: dict = {}
        try:
            proxy = proxy_for(own)
        except Exception:
            proxy = None
        if proxy is None:
            out[key] = entry
            continue
        try:
            src_img = src_proxy.image if src_proxy is not None else None
            if src_proxy is not None:
                try:
                    same = Path(source_path).resolve() == own.resolve()  # type: ignore[arg-type]
                except Exception:
                    same = False
                if same:
                    src_img = None  # same-file pair: detectors run sourceless
            entry["artifacts"] = analyze_images(proxy.image, src_img)
        except Exception:
            logger.debug("proxy batch: artifacts failed for %s", own, exc_info=True)
        if source_path is not None and src_proxy is not None:
            try:
                try:
                    same = Path(source_path).resolve() == own.resolve()  # type: ignore[arg-type]
                except Exception:
                    same = False
                if same:
                    # Same-file pair: identity scores, no engine call
                    # (mirrors compute_fidelity_metrics path equality).
                    entry["fidelity"] = {"ssim": 1.0, "hf_ratio": 0.0, "delta_e": 0.0, "upscale_factor": 1}
                else:
                    entry["fidelity"] = compute_fidelity_from_images(
                        proxy.image,
                        src_proxy.image,
                        item_size=proxy.size,
                        source_size=src_proxy.size,
                    )
            except Exception:
                logger.debug("proxy batch: fidelity failed for %s", own, exc_info=True)
        if include_camera:
            try:
                entry["camera"] = measure_camera_from_image(proxy.image)
            except Exception:
                logger.debug("proxy batch: camera failed for %s", own, exc_info=True)
        out[key] = entry
    return out
