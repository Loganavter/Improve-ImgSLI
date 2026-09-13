"""Hub / source detection — smallest-resolution centroid member similar to all others.

Pure, no Qt. Explicit deps: takes ``series_list`` and ``items`` as produced
by ``clustering.cluster_items`` / ``folder_scanner.scan_folder``.

Candidate source is the smallest-resolution image whose perceptual hash is
within ``threshold`` of every other image in the folder. This models the
common upscale/export batch where the low-res source is visually near-identical
to its upscales but has far fewer pixels.

Public API:
    detect_source(series_list, items) -> Path | None
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem, Series

_DEFAULT_THRESHOLD = 12


def _image_area(path: Path) -> int:
    try:
        with Image.open(path) as im:
            w, h = im.size
            return int(w) * int(h)
    except Exception:
        # Unreadable → treat as huge so it sorts last (never picked as hub).
        return 10**12


def _phash_for(path: Path) -> int:
    # Local import to avoid circular dep at module load; reuse clustering primitive.
    from tabs.image_gallery.services.clustering import compute_phash

    return compute_phash(path)


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def detect_source(
    series_list: list["Series"] | None,
    items: list["GalleryItem"] | None,
    threshold: int = _DEFAULT_THRESHOLD,
) -> Path | None:
    """Return hub source path or None.

    Args:
        series_list: output of ``cluster_items`` (may be None/empty — global scan still works).
        items: all ``GalleryItem`` for the folder.
        threshold: max hamming distance to be considered "similar".
    """
    if not items:
        return None

    # Build phash cache.
    phashes: dict[Path, int] = {}
    for it in items:
        h = _phash_for(it.path)
        # Unreadable files have hash 0; mark but will be skipped as candidate if area huge.
        phashes[it.path] = h

    # Candidates sorted by area ascending (smallest first).
    # Tie-break by path name for determinism.
    candidates = sorted(items, key=lambda it: (_image_area(it.path), it.path.name.lower()))

    # Helper: max hamming from candidate to all others.
    def _max_hamming(candidate_path: Path, candidate_hash: int) -> int:
        max_d = 0
        for it in items:
            if it.path == candidate_path:
                continue
            other_hash = phashes.get(it.path, 0)
            # If other is unreadable (hash 0 and area huge), skip — it shouldn't veto hub.
            if other_hash == 0 and _image_area(it.path) >= 10**12:
                continue
            d = _hamming(candidate_hash, other_hash)
            if d > max_d:
                max_d = d
                if max_d > threshold:
                    # Early exit.
                    return max_d
        return max_d

    # Prefer candidates that are centroid members of a series when series exist.
    # Build set of centroid-closest members per series (already ranked).
    preferred: set[Path] = set()
    if series_list:
        for ser in series_list:
            if not ser.members:
                continue
            # Rank 1 is closest to centroid (assigned in clustering).
            best = min(ser.members, key=lambda m: (m.rank if m.rank is not None else 999, _image_area(m.path)))
            preferred.add(best.path)

    # Search order: preferred smallest first, then all candidates smallest first.
    # To keep "smallest overall similar wins" we interleave but prioritize preferred
    # only as tie-breaker when areas are close. Simplest: try preferred sorted by area,
    # then fallback to full sorted list (without rechecking preferred).
    tried: set[Path] = set()

    def _try_ordered(order: list["GalleryItem"]) -> Path | None:
        for it in order:
            if it.path in tried:
                continue
            tried.add(it.path)
            # Skip unreadable candidates (area huge).
            if _image_area(it.path) >= 10**12:
                continue
            h = phashes.get(it.path, 0)
            # Uniform images can legitimately have hash 0 but readable; only skip if also unreadable area.
            # If hash 0 but area valid, still allow (white image source scenario).
            max_d = _max_hamming(it.path, h)
            if max_d <= threshold:
                return it.path
        return None

    if preferred:
        pref_items = [it for it in candidates if it.path in preferred]
        found = _try_ordered(pref_items)
        if found is not None:
            return found

    return _try_ordered(candidates)
