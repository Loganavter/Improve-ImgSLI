"""Auto mode selection per folder — pure, no Qt.

Modes:
  FIDELITY        — source hub found (upscale/export batch)
  CAMERA          — photographic, no hub (sharpness / EXIF heuristic)
  BATCH_SYNTHETIC — tight embedding cloud, no hub, non-photo

Stub heuristic (as spec allows):
  if hub -> fidelity
  else if avg sharpness > threshold -> camera
  else batch

Public API:
  Mode enum re-exported (same values as models.Mode)
  select_mode(series_list, items, source_path) -> Mode
  auto_select_mode(...) alias
  detect_mode(...) alias

Explicit deps: no Qt, no hidden lookups.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem, Series

# Re-export Mode so callers can import from services.mode directly.
try:
    from tabs.image_gallery.models import Mode  # type: ignore[no-redef]
except Exception:  # pragma: no cover - fallback if models not yet loaded
    from enum import Enum

    class Mode(str, Enum):  # type: ignore[no-redef]
        FIDELITY = "fidelity"
        CAMERA = "camera"
        BATCH_SYNTHETIC = "batch_synthetic"
else:
    # Ensure the name is available at runtime even for type checkers.
    pass

# Keep local alias for internal use.
_Mode = Mode

_SHARPNESS_THRESHOLD = 120.0
_TIGHT_EMBED_DISTANCE = 0.35

# Sharpness cache: ``_sharpness`` decodes + downscales + runs a pure-Python
# Laplacian per file (~150ms per 8MB PNG) and ``select_mode`` calls it for
# EVERY item on EVERY triage — including warm regroups. Memoize per
# ``(path, mtime_ns, size)`` (same discipline as the clustering signature
# cache); edits miss and recompute. Bounded, immutable float values.
_SHARPNESS_CACHE: dict[tuple[str, int, int], float | None] = {}
_SHARPNESS_CACHE_LIMIT = 4096


def clear_sharpness_cache() -> int:
    """Drop cached sharpness values. Returns entries cleared (tests)."""
    try:
        n = len(_SHARPNESS_CACHE)
    except Exception:
        return 0
    try:
        _SHARPNESS_CACHE.clear()
    except Exception:
        pass
    return n


# EXIF-presence cache: ``_has_exif`` opens + parses every file (~100ms per
# PNG, almost always False) on each ``select_mode`` call. Same key
# discipline as sharpness; edits miss and recompute.
_EXIF_CACHE: dict[tuple[str, int, int], bool] = {}


def _stat_key(path) -> tuple[str, int, int] | None:
    try:
        s = str(path)
        import os

        st = os.stat(s)
        return (s, int(getattr(st, "st_mtime_ns", 0)), int(st.st_size))
    except Exception:
        return None


def exif_for(path) -> bool:
    """Cached EXIF-presence probe for *path* (content-keyed)."""
    key = _stat_key(path)
    if key is None:
        return bool(_has_exif(path))
    try:
        if key in _EXIF_CACHE:
            return bool(_EXIF_CACHE[key])
    except Exception:
        pass
    value = bool(_has_exif(path))
    try:
        if len(_EXIF_CACHE) >= _SHARPNESS_CACHE_LIMIT:
            for old in list(_EXIF_CACHE)[: _SHARPNESS_CACHE_LIMIT // 4]:
                try:
                    del _EXIF_CACHE[old]
                except Exception:
                    pass
        _EXIF_CACHE[key] = value
    except Exception:
        pass
    return value


def sharpness_for(path) -> float | None:
    """Cached Laplacian sharpness for *path* (content-keyed, never shared)."""
    try:
        s = str(path)
    except Exception:
        return _sharpness(path)
    try:
        import os

        st = os.stat(s)
        key = (s, int(getattr(st, "st_mtime_ns", 0)), int(st.st_size))
    except Exception:
        return _sharpness(path)
    try:
        if key in _SHARPNESS_CACHE:
            return _SHARPNESS_CACHE[key]
    except Exception:
        pass
    value = _sharpness(path)
    try:
        if len(_SHARPNESS_CACHE) >= _SHARPNESS_CACHE_LIMIT:
            for old in list(_SHARPNESS_CACHE)[: _SHARPNESS_CACHE_LIMIT // 4]:
                try:
                    del _SHARPNESS_CACHE[old]
                except Exception:
                    pass
        _SHARPNESS_CACHE[key] = value
    except Exception:
        pass
    return value


def _sharpness(path: Path) -> float | None:
    """Laplacian variance sharpness (grayscale). Returns None on failure."""
    try:
        with Image.open(path) as im:
            gray = im.convert("L")
            # Resize large images down for speed: max 512 on longest edge.
            w, h = gray.size
            max_edge = max(w, h)
            if max_edge > 512:
                scale = 512 / max_edge
                nw, nh = int(w * scale), int(h * scale)
                try:
                    resample = Image.Resampling.BILINEAR  # type: ignore[attr-defined]
                except AttributeError:
                    resample = Image.BILINEAR  # type: ignore[attr-defined]
                gray = gray.resize((max(nw, 1), max(nh, 1)), resample)
            # Simple Laplacian kernel variance: use PIL filter then variance via Python.
            # Kernel: [[0,1,0],[1,-4,1],[0,1,0]]
            pixels = list(gray.getdata())
            pw, ph = gray.size
            # Build 2D access quickly: flat list row-major.
            def _at(x: int, y: int) -> int:
                return pixels[y * pw + x]

            # Compute Laplacian response for inner pixels.
            vals: list[float] = []
            for y in range(1, ph - 1):
                for x in range(1, pw - 1):
                    lap = (
                        _at(x, y - 1) + _at(x - 1, y) + _at(x + 1, y) + _at(x, y + 1) - 4 * _at(x, y)
                    )
                    vals.append(float(lap))
            if not vals:
                return 0.0
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            return var
    except Exception:
        return None


def _has_exif(path: Path) -> bool:
    try:
        with Image.open(path) as im:
            exif = None
            # Pillow: _getexif for JPEG/TIFF, getexif for newer.
            if hasattr(im, "getexif"):
                try:
                    exif = im.getexif()
                    if exif and len(exif) > 0:
                        return True
                except Exception:
                    pass
            if hasattr(im, "_getexif"):
                try:
                    exif2 = im._getexif()  # type: ignore[attr-defined]
                    if exif2:
                        return True
                except Exception:
                    pass
            # Also check info dict for exif bytes.
            if getattr(im, "info", None) and "exif" in im.info:
                return True
    except Exception:
        return False
    return False


def _average_sharpness(items: list["GalleryItem"]) -> float | None:
    vals: list[float] = []
    for it in items:
        s = sharpness_for(it.path)
        if s is not None:
            vals.append(s)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _is_tight_embedding_cloud(
    series_list: list["Series"] | None,
    items: list["GalleryItem"] | None,
) -> bool:
    # Heuristic: if we have one dominant series covering >=60% of items
    # and embedding distances are tight, treat as batch-synthetic.
    if not items or len(items) < 3:
        return False
    try:
        from tabs.image_gallery.services.clustering import signature_for as _sig_for
    except Exception:
        return False

    # Quick embedding spread check: compute pairwise distances for sample (max 20 items for speed).
    # Signatures come from the perceptual cache (no re-decode on regroups).
    sample = items[:20]
    vecs: list[list[float]] = []
    for it in sample:
        try:
            vecs.append(list(_sig_for(it.path)[1]))
        except Exception:
            continue
    if len(vecs) < 2:
        return False
    # Compute max distance.
    max_d = 0.0
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            d = 0.0
            a, b = vecs[i], vecs[j]
            for x, y in zip(a, b):
                diff = x - y
                d += diff * diff
            d = d**0.5
            if d > max_d:
                max_d = d
    return max_d <= _TIGHT_EMBED_DISTANCE * 4 and max_d > 0


def select_mode(
    series_list: list["Series"] | None,
    items: list["GalleryItem"] | None,
    source_path: Path | None,
) -> _Mode:
    """Auto-select mode per folder.

    Args:
        series_list: clustering result (may be None).
        items: all gallery items.
        source_path: hub candidate from ``detect_source`` (Path or None).

    Returns:
        Mode enum (FIDELITY / CAMERA / BATCH_SYNTHETIC).
    """
    if source_path is not None:
        return _Mode.FIDELITY

    # Tight embedding cloud check hints batch-synthetic, but camera photos can also be tight
    # (e.g., burst). Use sharpness + EXIF to distinguish.
    if items:
        # If any image has EXIF and sharpness is moderate-high → camera.
        has_exif_any = any(exif_for(it.path) for it in items)
        avg_s = _average_sharpness(items)
        if avg_s is not None and avg_s > _SHARPNESS_THRESHOLD:
            return _Mode.CAMERA
        if has_exif_any and avg_s is not None and avg_s > _SHARPNESS_THRESHOLD * 0.6:
            return _Mode.CAMERA
        # If tight cloud and not camera → batch synthetic.
        if _is_tight_embedding_cloud(series_list, items):
            return _Mode.BATCH_SYNTHETIC
        # Fallback sharpness gate: low sharpness → batch synthetic.
        if avg_s is not None and avg_s <= _SHARPNESS_THRESHOLD * 0.5:
            # Very low sharpness could be synthetic or blurry; default to batch for triage.
            return _Mode.BATCH_SYNTHETIC
        # Default when no hub and moderate sharpness but no EXIF → batch.
        # If we have no signal, prefer CAMERA for photo folders (design says photographic no hub).
        # Use heuristic: if average sharpness above half threshold → camera else batch.
        if avg_s is not None:
            return _Mode.CAMERA if avg_s > _SHARPNESS_THRESHOLD * 0.7 else _Mode.BATCH_SYNTHETIC

    # Fallback.
    return _Mode.BATCH_SYNTHETIC


# Aliases expected by alternative call sites / tests.
auto_select_mode = select_mode
detect_mode = select_mode
