"""Disk pin for VLM-selected metric profiles — plan P2/P3.

Key = ``sha256(sorted(path:mtime_ns) + mode + model + pool ids)`` — an edited
member (mtime), a changed series membership (path), a different mode/model or a
re-shaped pool all invalidate; an unchanged folder-generation is served from
disk with **no second VLM call**.

The AI domain is *explicitly non-deterministic* (the same request may answer
differently on a second identical run): the pin makes one run reproducible — a
folder is profiled once and every later pass over the same paths+mtimes+mode+
model+pool reuses that pinned selection, so flipping between tabs/domains never
re-rolls the dice. This mirrors :mod:`tabs.image_gallery.services.jev_cache`
(one JSON file per key, version-gated, **no TTL**, malformed replies
deliberately **not** pinned) so the gallery keeps ONE cache idiom.

Pure — no Qt, no HTTP. Small JSON IO, safe from worker threads.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from tabs.image_gallery.services.metric_profile import MEASURED_POOL, MetricProfile, mode_id

logger = logging.getLogger("ImproveImgSLI")

#: Bump when the cached record shape changes (old pins stop matching).
PROFILE_CACHE_VERSION = 1

#: Cache directory name, stored alongside the Jev cache directory.
CACHE_DIR_NAME = "gallery_profile_cache"


def profile_cache_dir() -> Path:
    from services.io.project_package import _cache_root

    root = _cache_root() / CACHE_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _item_path(item) -> str:
    try:
        return str(getattr(item, "path", ""))
    except Exception:
        return ""


def _item_mtime(item) -> int:
    try:
        return int(getattr(item, "mtime_ns", 0) or 0)
    except Exception:
        return 0


def profile_cache_key(items, *, mode, model, pool=None) -> str:
    """Stable pin identity: ``sha256(members + mode + model + pool)``.

    Members are sorted by path so the key is independent of the caller's member
    order; the mode is normalized to a registry id (``Mode.FIDELITY`` and
    ``"fidelity"`` pin the same profile); the pool defaults to the immutable
    ``MEASURED_POOL`` so a caller never has to pass it.
    """
    pool_ids = tuple(pool) if pool is not None else MEASURED_POOL
    try:
        ordered = sorted(list(items or ()), key=_item_path)
    except Exception:
        ordered = list(items or ())
    parts = [f"{_item_path(item)}:{_item_mtime(item)}" for item in ordered]
    parts.append(f"mode={mode_id(mode)}")
    parts.append(f"model={str(model or '')}")
    parts.append("pool=" + ",".join(str(p) for p in pool_ids))
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ProfileCache:
    """One-file-per-folder JSON pin for VLM-selected metric profiles.

    ``get`` returns the stored :class:`MetricProfile` or ``None`` on a miss
    (absent/corrupt file, a version mismatch, or an empty axis set — an empty
    profile is not a usable selection). ``put`` stores the full value object so
    a re-read is trivially equal to the fresh one. Transient failures (transport
    error, malformed reply) are deliberately **not** pinned — a later pass may
    retry.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = Path(directory) if directory is not None else None

    def _dir(self) -> Path:
        if self._directory is not None:
            return self._directory
        return profile_cache_dir()

    def _path(self, key: str) -> Path:
        return self._dir() / f"profile_{key}.json"

    def get(self, key: str) -> MetricProfile | None:
        try:
            p = self._path(key)
        except Exception:
            return None
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("profile cache read failed %s", p, exc_info=True)
            return None
        if not isinstance(data, dict):
            return None
        try:
            if int(data.get("version", 0) or 0) != PROFILE_CACHE_VERSION:
                return None
        except Exception:
            return None
        axis_ids = data.get("axis_ids")
        if not isinstance(axis_ids, list):
            return None
        try:
            profile = MetricProfile(
                axis_ids=tuple(str(a) for a in axis_ids),
                mode=data.get("mode", ""),
                source=data.get("source", "vlm"),
                salient_axes=tuple(data.get("salient_axes") or ()),
            )
        except Exception:
            return None
        return profile if profile.axis_ids else None

    def put(self, key: str, profile) -> None:
        if profile is None or not getattr(profile, "axis_ids", ()):
            return
        try:
            p = self._path(key)
        except Exception:
            return
        record = {
            "version": PROFILE_CACHE_VERSION,
            "axis_ids": [str(a) for a in profile.axis_ids],
            "mode": str(getattr(profile, "mode", "") or ""),
            "source": str(getattr(profile, "source", "vlm") or "vlm"),
            "salient_axes": [str(a) for a in (getattr(profile, "salient_axes", ()) or ())],
        }
        try:
            p.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        except OSError:
            logger.debug("profile cache write failed %s", p, exc_info=True)

    def clear(self) -> int:
        """Delete every pin file in this cache's directory; return the count.

        The gallery's "Reset metrics cache" entry point: the VLM selection is
        pinned per folder-generation, so a stale pin would keep serving the old
        axis set to the re-derived pipeline. A missing directory / an
        unreadable entry contributes 0; never raises.
        """
        try:
            directory = self._dir()
        except Exception:
            return 0
        try:
            entries = sorted(Path(directory).glob("profile_*.json"))
        except Exception:
            return 0
        deleted = 0
        for path in entries:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                logger.debug("profile pin delete failed %s", path, exc_info=True)
        return deleted


_default_cache: ProfileCache | None = None


def default_cache() -> ProfileCache:
    """Process-wide default cache (lazy, disk-backed)."""
    global _default_cache
    if _default_cache is None:
        _default_cache = ProfileCache()
    return _default_cache


def clear_default_cache() -> int:
    """Clear the process-wide default cache (drop every disk pin). Never raises."""
    try:
        return int(default_cache().clear())
    except Exception:
        return 0


__all__ = [
    "CACHE_DIR_NAME",
    "PROFILE_CACHE_VERSION",
    "ProfileCache",
    "clear_default_cache",
    "default_cache",
    "profile_cache_dir",
    "profile_cache_key",
]
