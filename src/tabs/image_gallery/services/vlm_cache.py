"""Disk cache for Stage 3 VLM results — tie-breaks and compare briefs.

Key = hash(paths+mtime) like ``ai_cache`` / ``thumbnail_cache`` (sha256 of
``path:mtime_ns``) so edited files invalidate. One file per pair/tie-break,
stored alongside ``gallery_ai_cache`` as ``gallery_vlm_cache``.

Pure — no Qt. Cache IO is small JSON, safe to call from worker threads and
from filtering (brief tag search) without UI blocking.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from tabs.image_gallery.models import CompareBrief, TieBreakResult

logger = logging.getLogger("ImproveImgSLI")


def vlm_cache_dir() -> Path:
    from services.io.project_package import _cache_root

    root = _cache_root() / "gallery_vlm_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _hash_key(parts: list[str]) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _tie_break_key(path_a: Path, mtime_a: int, path_b: Path, mtime_b: int, source_mtime: int | None = None) -> str:
    # Stable ordering: sort by resolved path string so (a,b) == (b,a)
    a_s = str(Path(path_a).resolve())
    b_s = str(Path(path_b).resolve())
    if a_s > b_s:
        a_s, b_s = b_s, a_s
        mtime_a, mtime_b = mtime_b, mtime_a
    parts = [f"{a_s}:{mtime_a}", f"{b_s}:{mtime_b}"]
    if source_mtime is not None:
        parts.append(f"source:{source_mtime}")
    return _hash_key(parts)


def _brief_key(path_a: Path, mtime_a: int, path_b: Path, mtime_b: int) -> str:
    a_s = str(Path(path_a).resolve())
    b_s = str(Path(path_b).resolve())
    if a_s > b_s:
        a_s, b_s = b_s, a_s
        mtime_a, mtime_b = mtime_b, mtime_a
    return _hash_key([f"{a_s}:{mtime_a}", f"{b_s}:{mtime_b}"])


def _tie_path(key: str) -> Path:
    return vlm_cache_dir() / f"tie_{key}.json"


def _brief_path(key: str) -> Path:
    return vlm_cache_dir() / f"brief_{key}.json"


# -- tie-break ---------------------------------------------------------

def load_cached_tie_break(
    path_a: Path, mtime_a: int, path_b: Path, mtime_b: int, source_mtime: int | None = None
) -> TieBreakResult | None:
    key = _tie_break_key(path_a, mtime_a, path_b, mtime_b, source_mtime)
    p = _tie_path(key)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return TieBreakResult(
            winner_path=data["winner_path"],
            loser_path=data["loser_path"],
            reason=data.get("reason", ""),
            confidence=float(data.get("confidence", 0.0)),
            model=data.get("model", ""),
            decided_at_iso=data.get("decided_at_iso", ""),
        )
    except Exception:
        logger.debug("VLM tie-break cache read failed %s", p, exc_info=True)
        return None


def save_tie_break(
    path_a: Path,
    mtime_a: int,
    path_b: Path,
    mtime_b: int,
    result: TieBreakResult,
    source_mtime: int | None = None,
) -> None:
    key = _tie_break_key(path_a, mtime_a, path_b, mtime_b, source_mtime)
    p = _tie_path(key)
    try:
        p.write_text(
            json.dumps(
                {
                    "winner_path": result.winner_path,
                    "loser_path": result.loser_path,
                    "reason": result.reason,
                    "confidence": result.confidence,
                    "model": result.model,
                    "decided_at_iso": result.decided_at_iso,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("VLM tie-break cache write failed %s", p, exc_info=True)


# -- compare brief -----------------------------------------------------

def load_cached_brief(
    path_a: Path, mtime_a: int, path_b: Path, mtime_b: int
) -> CompareBrief | None:
    key = _brief_key(path_a, mtime_a, path_b, mtime_b)
    p = _brief_path(key)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        pair = tuple(data.get("pair", ()))
        if len(pair) != 2:
            pair = (str(path_a), str(path_b))
        return CompareBrief(
            pair=(str(pair[0]), str(pair[1])),
            summary=data.get("summary", ""),
            differences=tuple(data.get("differences", ())),
            tags=tuple(data.get("tags", ())),
            model=data.get("model", ""),
            created_at_iso=data.get("created_at_iso", ""),
        )
    except Exception:
        logger.debug("VLM brief cache read failed %s", p, exc_info=True)
        return None


def save_brief(
    path_a: Path, mtime_a: int, path_b: Path, mtime_b: int, result: CompareBrief
) -> None:
    key = _brief_key(path_a, mtime_a, path_b, mtime_b)
    p = _brief_path(key)
    try:
        p.write_text(
            json.dumps(
                {
                    "pair": list(result.pair),
                    "summary": result.summary,
                    "differences": list(result.differences),
                    "tags": list(result.tags),
                    "model": result.model,
                    "created_at_iso": result.created_at_iso,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("VLM brief cache write failed %s", p, exc_info=True)


# -- helpers for filtering (tag search across cached briefs) -----------

def find_briefs_for_path(path: Path, mtime_ns: int) -> list[CompareBrief]:
    """Return all cached briefs that include *path* (any pair containing it).

    Scans ``vlm_cache_dir`` — cheap for typical folder sizes (dozens of briefs).
    Used by filtering to make semantic search hit brief tags even when the
    controller hasn't yet loaded them into ``GalleryItem.vlm_brief``.
    """
    wanted = str(Path(path).resolve())
    out: list[CompareBrief] = []
    try:
        cache_dir = vlm_cache_dir()
    except Exception:
        return out
    for p in cache_dir.glob("brief_*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            pair = tuple(data.get("pair", ()))
            if wanted in tuple(str(Path(s).resolve()) for s in pair if s):
                out.append(
                    CompareBrief(
                        pair=(str(pair[0]), str(pair[1])) if len(pair) == 2 else (wanted, wanted),
                        summary=data.get("summary", ""),
                        differences=tuple(data.get("differences", ())),
                        tags=tuple(data.get("tags", ())),
                        model=data.get("model", ""),
                        created_at_iso=data.get("created_at_iso", ""),
                    )
                )
        except Exception:
            continue
    # Also fallback: if brief key was built from sorted order, wanted might match
    # even when pair strings are unresolved symlinks — try containment via hash lookup?
    # Keep fallback: direct key lookup for single-image self? Not needed.
    return out
