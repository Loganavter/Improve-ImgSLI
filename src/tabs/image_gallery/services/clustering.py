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

Audit-Meta: pattern=perceptual-signature size=521 reason="one signature contract: the dHash, the HSV embedding and the shared decode frame must agree, because the 2026-10-26 backend-isolation W5a wave removed a duplicate open by making all three read ONE decoded image. Splitting the primitives out lets a later edit reintroduce the second decode (measured: 4 opens per image) or make the hash and the embedding describe different pixels; the module stays a single ~60-line math block over one frame."
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from tabs.image_gallery.services import decode_cache

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem, Series


# -- low-level primitives -------------------------------------------------

def _phash_from_image(im) -> int:
    """dHash over an already-decoded frame (no file I/O)."""
    try:
        # Handle palette / RGBA etc. → L.
        try:
            gray = im.convert("L")
        except Exception:
            gray = im.convert("RGB").convert("L")
        # Resize to 9x8 for dHash (9 columns give 8 diffs per row).
        # Pillow ≥10 removed ANTIALIAS; use LANCZOS/BILINEAR fallback.
        try:
            resample = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
        except AttributeError:
            resample = Image.LANCZOS  # type: ignore[attr-defined,attr-defined]
        small = gray.resize((9, 8), resample)
        pixels = list(small.getdata())
        # pixels row-major 9*8; for each row compare x vs x+1.
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


def compute_phash(path: Path | str) -> int:
    """Return 64-bit dHash (difference hash) for *path*.

    Implementation: 9×8 grayscale resize (LANCZOS) → horizontal diff
    → 64-bit integer. Returns 0 on failure so callers can skip corrupt
    files without raising (pure service, never Qt).

    Decodes through ``services.decode_cache`` so the matching
    ``embedding`` call on the same file reuses this one open (I2).
    """
    im = decode_cache.decode_image(path)
    if im is None:
        return 0
    return _phash_from_image(im)


def _embedding_from_image(im) -> list[float]:
    """HSV embedding over an already-decoded frame (no file I/O)."""
    zero = [0.0] * 192
    try:
        # Convert to RGB then HSV. PIL HSV: H 0-255, S 0-255, V 0-255.
        try:
            rgb = im.convert("RGB")
        except Exception:
            return zero
        try:
            resample = Image.Resampling.BILINEAR  # type: ignore[attr-defined]
        except AttributeError:
            try:
                resample = Image.BILINEAR  # type: ignore[attr-defined]
            except Exception:
                resample = 0  # type: ignore[assignment]
        small = rgb.resize((8, 8), resample)
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


def embedding(path: Path | str) -> list[float]:
    """Return small HSV embedding vector for *path*.

    8×8 HSV flatten: resize to 8×8, convert to HSV, flatten channels
    normalized to 0..1 (length 192 = 8*8*3). Pure Python + PIL, no Qt.
    Returns zero vector on failure.

    Decodes through ``services.decode_cache`` so ``compute_phash`` on the
    same file reuses that one open (I2).
    """
    im = decode_cache.decode_image(path)
    if im is None:
        return [0.0] * 192
    return _embedding_from_image(im)


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

# Perceptual-signature cache: ``compute_phash`` + ``embedding`` decode +
# downscale every file (~250ms per 8MB PNG); re-triage re-reads UNCHANGED
# files, so memoize per ``(path, mtime_ns, size)`` (edits miss/recompute).
# Bounded module dict (evict oldest quarter past 4k); immutable values.
# Tests reset via ``clear_signature_cache``.
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
    """Cached ``(phash, embedding)`` for *path* (list copy, never shared).

    ``compute_phash`` + ``embedding`` each decode through the shared
    ``services.decode_cache`` frame, so the pair costs ONE ``Image.open``
    per file (I2), not two.
    """
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


def signatures_cached(paths) -> bool:
    """True when every path is cached (regroup without decode).

    Lets callers pick a synchronous regroup over a worker hop. Stat reads
    only — never decodes.
    """
    try:
        items = list(paths or [])
    except Exception:
        return False
    if not items:
        return False
    try:
        for p in items:
            path = getattr(p, "path", p)
            if _stat_key(path) not in _SIGNATURE_CACHE:
                return False
        return True
    except Exception:
        return False


def cluster_items(items: list["GalleryItem"], threshold: int = 10) -> list["Series"]:
    """Group *items* into series (≥2 members) by phash + embedding distance.

    *threshold* is the maximum hamming distance for dHash (0..64).
    Embedding distance is a secondary gate: if hamming is just above
    threshold but embedding is very close, we still cluster (tight cloud).

    Returns ``list[Series]``; mutates ``GalleryItem.series_id`` and the
    ``phash`` / ``embedding_dist_to_centroid`` metrics for convenience
    (explicit but non-Qt). Rank is intentionally NOT assigned here — it comes
    from the measured metric fusion (``services.rank_fusion``) in the
    controller. Files no backend could DECODE are excluded from grouping so they
    become singletons (UNGROUPED); that is the decode's answer, not an inference
    from a zero hash (an all-black image is readable and hashes to 0).
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
        # Readable-ness is the DECODE's answer, never a property of the signature.
        # The old rule inferred "corrupt" from ``h == 0 and e == zero_vec``, and an
        # ALL-BLACK image satisfies both (a uniform picture hashes to 0 and its HSV
        # value channel is 0 everywhere) — so a perfectly readable frame was dropped
        # from its own series as if no backend could read it (measured 2026-10-28).
        # ``decode_image`` is the marker ``decode_cache`` already returns None from,
        # and it is a cache HIT here: ``signature_for`` just decoded the same file.
        valid.append(decode_cache.decode_image(it.path) is not None)

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
        # series_id + centroid distance (still backs ``typicality``); rank is
        # owned by the measured fusion (plan-gallery-rank-backends-2026-10-15).
        for i in member_indices:
            m = items[i]
            m.series_id = series_id
            # Store metrics for potential UI (pure dict).
            m.metrics["phash"] = phashes[i] if 0 <= i < len(phashes) else 0
            m.metrics["embedding_dist_to_centroid"] = _embedding_distance(
                embeddings[i], centroid
            )

        ser = Series(id=series_id, members=members, centroid=centroid, phash_centroid=phash_centroid)
        series_list.append(ser)

    # Singletons stay UNGROUPED (series_id cleared); rank is owned by the
    # controller's fusion pass, never by clustering.
    grouped_paths = {id(m) for s in series_list for m in s.members}
    for it in items:
        if id(it) not in grouped_paths:
            it.series_id = None

    # Sort series by size descending then id for stable output.
    series_list.sort(key=lambda s: (-len(s.members), s.id))
    return series_list


# -- Wave S1 attach support (pure, no Qt; existing functions untouched) ------


def _embed_threshold_for(threshold: int) -> float:
    """Embedding gate mirroring ``cluster_items``' secondary gate."""
    try:
        t = int(threshold)
    except Exception:
        t = 10
    return 0.55 if t >= 10 else 0.4


def series_centroids(series) -> dict:
    """Map series id → centroid vector (mean embedding).

    Reuses the stored ``Series.centroid`` when present; entries without
    one (plain member lists, or ``Series`` with ``centroid=None``)
    recompute the mean embedding of their members via the cached
    ``signature_for`` path. Series with no members or no usable centroid
    are skipped. Pure (no Qt).
    """
    out: dict = {}
    try:
        entries = list(series or [])
    except Exception:
        return {}
    for entry in entries:
        try:
            if hasattr(entry, "members"):
                members = list(getattr(entry, "members", None) or [])
                try:
                    sid = getattr(entry, "id", None)
                except Exception:
                    sid = None
                try:
                    stored = getattr(entry, "centroid", None)
                except Exception:
                    stored = None
            elif isinstance(entry, (list, tuple)):
                members = list(entry)
                sid = None
                stored = None
            else:
                continue
            if sid is None and members:
                try:
                    sid = getattr(members[0], "series_id", None)
                except Exception:
                    sid = None
            if sid is None:
                continue
            try:
                sid_s = str(sid)
            except Exception:
                continue
            if stored:
                try:
                    out[sid_s] = [float(v) for v in stored]
                    continue
                except Exception:
                    pass
            # No stored centroid: mean embedding over members (cached).
            acc: list[float] | None = None
            count = 0
            for m in members:
                try:
                    _, emb = signature_for(getattr(m, "path"))
                except Exception:
                    continue
                try:
                    if acc is None:
                        acc = [0.0] * len(emb)
                    for i, v in enumerate(emb):
                        if i < len(acc):
                            acc[i] += float(v)
                    count += 1
                except Exception:
                    continue
            if acc is not None and count > 0:
                out[sid_s] = [v / count for v in acc]
        except Exception:
            continue
    return out


def nearest_series_id(signature, centroids: dict, threshold: int = 10):
    """Nearest centroid id for *signature* (embedding vector) or None.

    Embedding-distance gate mirrors ``cluster_items``' secondary gate
    (``0.55`` for ``threshold >= 10`` else ``0.4``): the closest
    centroid at or inside the gate wins (ties → smallest id); anything
    farther attaches to nothing (None). Pure (no Qt, no I/O).
    """
    try:
        vec = [float(v) for v in (signature or [])]
    except Exception:
        return None
    if not vec:
        return None
    try:
        items = list((centroids or {}).items())
    except Exception:
        return None
    gate = _embed_threshold_for(threshold)
    best_id = None
    best_d: float | None = None
    for sid, centroid in items:
        try:
            c = [float(v) for v in (centroid or [])]
        except Exception:
            continue
        if not c:
            continue
        try:
            d = _embedding_distance(vec, c)
        except Exception:
            continue
        if best_d is None or d < best_d or (d == best_d and str(sid) < str(best_id)):
            best_d = d
            best_id = sid
    if best_d is None or best_d > gate:
        return None
    try:
        return str(best_id)
    except Exception:
        return None
