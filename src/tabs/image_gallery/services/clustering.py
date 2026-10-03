"""Perceptual clustering for local triage — pure, no Qt.

Stage 2 Pass 1: perceptual hash (dHash via PIL) + small HSV embedding
→ distance threshold → series = ≥2 members.

Public API expected by the task:
- ``compute_phash(path) -> int``
- ``embedding(path) -> vector``  (list[float] normalized 0..1)
- ``cluster_items(items, threshold) -> list[Series]``

``threshold`` is a hamming distance threshold for the 64-bit dHash.
Embedding is used as a secondary gate (euclidean) and for centroid
computation.  Explicit dependencies only — no Qt, no getattrs.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem, Series


# -- low-level primitives -------------------------------------------------

def compute_phash(path: Path | str) -> int:
    """Return 64-bit dHash (difference hash) for *path*.

    Implementation: 9×8 grayscale resize (LANCZOS) → horizontal diff
    → 64-bit integer. Returns 0 on failure so callers can skip corrupt
    files without raising (pure service, never Qt).
    """
    try:
        p = Path(path)
        with Image.open(p) as im:
            # Handle palette / RGBA etc. → L.
            try:
                im = im.convert("L")
            except Exception:
                im = im.convert("RGB").convert("L")
            # Resize to 9x8 for dHash (9 columns give 8 diffs per row).
            # Pillow ≥10 removed ANTIALIAS; use LANCZOS/BILINEAR fallback.
            try:
                resample = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
            except AttributeError:
                resample = Image.LANCZOS  # type: ignore[attr-defined,attr-defined]
            small = im.resize((9, 8), resample)
            pixels = list(small.getdata())
            # pixels row-major 9*8; for each row compare x vs x+1.
            bits = 0
            idx = 0
            for y in range(8):
                row_start = y * 9
                for x in range(8):
                    left = pixels[row_start + x]
                    right = pixels[row_start + x + 1]
                    bits = (bits << 1) | (1 if left > right else 0)
                    idx += 1
            return bits
    except Exception:
        return 0


def embedding(path: Path | str) -> list[float]:
    """Return small HSV embedding vector for *path*.

    8×8 HSV flatten: resize to 8×8, convert to HSV, flatten channels
    normalized to 0..1 (length 192 = 8*8*3). Pure Python + PIL, no Qt.
    Returns zero vector on failure.
    """
    zero = [0.0] * 192
    try:
        p = Path(path)
        with Image.open(p) as im:
            # Convert to RGB then HSV. PIL HSV: H 0-255, S 0-255, V 0-255.
            try:
                im = im.convert("RGB")
            except Exception:
                return zero
            try:
                resample = Image.Resampling.BILINEAR  # type: ignore[attr-defined]
            except AttributeError:
                try:
                    resample = Image.BILINEAR  # type: ignore[attr-defined]
                except Exception:
                    resample = 0  # type: ignore[assignment]
            small = im.resize((8, 8), resample)
            hsv = small.convert("HSV")
            data = list(hsv.getdata())  # type: ignore[arg-type]
            # data is list of (h,s,v) tuples 0-255.
            vec: list[float] = []
            for h, s, v in data:
                vec.append(h / 255.0)
                vec.append(s / 255.0)
                vec.append(v / 255.0)
            if len(vec) != 192:
                # Pad/truncate defensively.
                vec = (vec + zero)[:192]
            return vec
    except Exception:
        return zero


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _embedding_distance(a: list[float], b: list[float]) -> float:
    # Euclidean distance.
    # Use pure python to avoid mandatory numpy dependency.
    s = 0.0
    for x, y in zip(a, b):
        d = x - y
        s += d * d
    return s ** 0.5


# -- union-find -----------------------------------------------------------

class _DSU:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


# -- clustering -----------------------------------------------------------

# Perceptual-signature cache (Wave E perf): ``compute_phash`` + ``embedding``
# decode + downscale every file (~250ms per 8MB PNG). Re-triage after a
# series move re-reads UNCHANGED files, so memoize per
# ``(path, mtime_ns, size)`` — content edits (new mtime/size) miss and
# recompute. Module-level dict, bounded (evict oldest quarter past 4k
# entries); values are immutable ``(phash, embedding-tuple)`` so callers
# cannot corrupt the cache. Tests reset via ``clear_signature_cache``.
_SIGNATURE_CACHE: dict[tuple[str, int, int], tuple[int, tuple[float, ...]]] = {}
_SIGNATURE_CACHE_LIMIT = 4096


def _stat_key(path) -> tuple[str, int, int]:
    """Cache key for *path*: string + mtime_ns + size (missing → zeros)."""
    try:
        s = str(path)
    except Exception:
        return ("", 0, 0)
    try:
        import os

        st = os.stat(s)
        return (s, int(getattr(st, "st_mtime_ns", 0)), int(st.st_size))
    except Exception:
        return (s, 0, 0)


def clear_signature_cache() -> int:
    """Drop all cached signatures. Returns entries cleared (tests)."""
    try:
        n = len(_SIGNATURE_CACHE)
    except Exception:
        return 0
    try:
        _SIGNATURE_CACHE.clear()
    except Exception:
        pass
    return n


def signature_for(path) -> tuple[int, list[float]]:
    """Cached ``(phash, embedding)`` for *path* (list copy, never shared)."""
    key = _stat_key(path)
    try:
        hit = _SIGNATURE_CACHE.get(key)
    except Exception:
        hit = None
    if hit is not None:
        try:
            return (hit[0], list(hit[1]))
        except Exception:
            pass
    h = compute_phash(path)
    e = embedding(path)
    try:
        if len(_SIGNATURE_CACHE) >= _SIGNATURE_CACHE_LIMIT:
            for old in list(_SIGNATURE_CACHE)[: _SIGNATURE_CACHE_LIMIT // 4]:
                try:
                    del _SIGNATURE_CACHE[old]
                except Exception:
                    pass
        _SIGNATURE_CACHE[key] = (h, tuple(e))
    except Exception:
        pass
    return (h, e)


def cluster_items(items: list["GalleryItem"], threshold: int = 10) -> list["Series"]:
    """Group *items* into series (≥2 members) by phash + embedding distance.

    *threshold* is the maximum hamming distance for dHash (0..64).
    Embedding distance is a secondary gate: if hamming is just above
    threshold but embedding is very close, we still cluster (tight cloud).

    Returns ``list[Series]``; mutates ``GalleryItem.series_id`` / ``rank``
    for convenience (explicit but non-Qt). Corrupt/unreadable files (both
    phash == 0 and embedding is zero vector) are excluded from grouping
    so they become singletons (UNGROUPED).
    """
    from tabs.image_gallery.models import Series  # local import, explicit dep

    if not items:
        return []

    n = len(items)
    # Precompute hashes & embeddings.
    phashes: list[int] = []
    embeddings: list[list[float]] = []
    valid: list[bool] = []
    zero_vec = [0.0] * 192
    for it in items:
        h, e = signature_for(it.path)
        phashes.append(h)
        embeddings.append(e)
        # Valid if we could read at least something: hash non-zero or embedding non-zero,
        # or file actually exists and is non-empty (phash 0 can be valid for uniform image,
        # but embedding zero for uniform gray is not all zeros — uniform gray HSV still has V=~0.5).
        # So treat fully-zero embedding as invalid/currupt. Hash zero alone is ambiguous
        # (all white image gives hash 0). Use embedding check.
        is_zero_embed = e == zero_vec
        # If both hash==0 and embed zero, treat as corrupt/unreadable → invalid.
        if h == 0 and is_zero_embed:
            # Check if file actually exists and PIL could open it: if size==0 file, invalid.
            # For uniform white image, embedding is not zero (V ~1), so not invalid.
            valid.append(False)
        else:
            valid.append(True)

    dsu = _DSU(n)
    # Tight embedding threshold derived from hamming threshold.
    # Empirically: embedding euclidean in 0..~13 (192 dims 0..1). Average random ~5.
    # Map hamming threshold 10 → embedding threshold ~0.6 for 8x8 HSV flatten.
    embed_thresh = 0.55 if threshold >= 10 else 0.4
    # For very small threshold, be stricter.
    for i in range(n):
        if not valid[i]:
            continue
        for j in range(i + 1, n):
            if not valid[j]:
                continue
            ham = _hamming(phashes[i], phashes[j])
            if ham <= threshold:
                dsu.union(i, j)
                continue
            # Secondary: tight embedding cloud → cluster even if hash slightly higher.
            # Only when hash is within 1.5× threshold and embedding is very tight.
            if ham <= threshold + 4:
                ed = _embedding_distance(embeddings[i], embeddings[j])
                if ed <= embed_thresh * 0.7:
                    dsu.union(i, j)
                continue
            # Also if embedding extremely tight (near duplicate via HSV), cluster regardless of hash.
            # This helps for very similar color images where dHash may be sensitive to crop.
            ed = _embedding_distance(embeddings[i], embeddings[j])
            if ed <= 0.25:
                dsu.union(i, j)

    # Gather groups.
    groups: dict[int, list[int]] = {}
    for idx in range(n):
        if not valid[idx]:
            continue
        root = dsu.find(idx)
        groups.setdefault(root, []).append(idx)

    series_list: list["Series"] = []
    sid = 0
    for member_indices in groups.values():
        if len(member_indices) < 2:
            continue
        members = [items[i] for i in member_indices]
        # Centroid = mean embedding vector.
        centroid: list[float] = [0.0] * 192
        for i in member_indices:
            emb = embeddings[i]
            for k in range(192):
                centroid[k] += emb[k]
        cnt = len(member_indices)
        centroid = [c / cnt for c in centroid]
        # phash centroid: majority? Use medoid (member hash closest to others) as representative int.
        # Compute sum hamming to others, pick min.
        best_idx = member_indices[0]
        best_sum = None
        for i in member_indices:
            s = 0
            for j in member_indices:
                if i == j:
                    continue
                s += _hamming(phashes[i], phashes[j])
            if best_sum is None or s < best_sum:
                best_sum = s
                best_idx = i
        phash_centroid = phashes[best_idx]

        sid += 1
        series_id = f"series_{sid}"
        # Assign series_id to members; rank placeholder sorted by distance to centroid.
        # Distance to centroid for ranking (smaller = more central).
        scored: list[tuple[float, "GalleryItem"]] = []
        for i in member_indices:
            d = _embedding_distance(embeddings[i], centroid)
            scored.append((d, items[i]))
        scored.sort(key=lambda x: x[0])
        for rank, (_, m) in enumerate(scored, start=1):
            m.series_id = series_id
            m.rank = rank
            # Store metrics for potential UI (pure dict).
            m.metrics["phash"] = phashes[items.index(m)] if m in items else 0
            m.metrics["embedding_dist_to_centroid"] = scored[rank - 1][0]

        ser = Series(id=series_id, members=members, centroid=centroid, phash_centroid=phash_centroid)
        series_list.append(ser)

    # Reset series_id/rank for singletons (UNGROUPED).
    grouped_paths = {id(m) for s in series_list for m in s.members}
    for it in items:
        if id(it) not in grouped_paths:
            it.series_id = None
            it.rank = None

    # Sort series by size descending then id for stable output.
    series_list.sort(key=lambda s: (-len(s.members), s.id))
    return series_list
