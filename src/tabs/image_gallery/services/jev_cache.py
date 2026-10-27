"""Disk cache + pin for the Jev (TypeSafe System One) series rank.

Key = ``sha256(paths + mtimes + content digests + endpoint + canonical payload)``
— an edited file (mtime), a rewritten-in-place file whose mtime was restored
(content digest, ``content_digest``), a changed series membership (path), a
re-pointed provider (endpoint) or a changed measured vector (payload) all
invalidate; a byte-identical re-run is served from disk with **no second HTTP
call**.

WHY the endpoint is part of the key (invariant I1/I2): the payload carries the
constant ``jev_client.JEV_MODEL``, so with the key stopping at
paths+mtimes+payload the same model id on ANOTHER endpoint (a provider switch —
``services/ai_providers``) reused the previous endpoint's pinned order. The
endpoint is normalized with the ONE gallery normalizer
(``ai_providers._url_key``): two spellings of one provider share a pin.

The AI domain is *explicitly non-deterministic* (plan
``plan-gallery-rank-backends-2026-10-15`` §Risks): the model is free to answer
differently on a second identical request. The cache is the *pin* that makes a
single run reproducible — a series is ranked once and every later pass over the
same paths+mtimes+payload reuses that pinned answer, including a pinned
"abstained" (Noul / low confidence), so flipping the domain back and forth never
re-rolls the dice.

Pure — no Qt. Small JSON IO, safe from worker threads. Mirrors
:mod:`tabs.image_gallery.services.vlm_cache` (key = hash+mtimes, one file per
result) so the gallery has one cache idiom, not two.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: The analysis-backend adapter that OWNS this store (ADR 009 wave A4) — see
#: ``services.ai_cache.CACHE_NAMESPACE``.
CACHE_NAMESPACE = "ai"

#: Bump when the cached record shape changes (old pins stop matching).
JEV_CACHE_VERSION = 1

#: Cache directory name, stored alongside ``gallery_vlm_cache``.
CACHE_DIR_NAME = "gallery_jev_cache"


def jev_cache_dir() -> Path:
    from services.io.project_package import cache_kind_dir

    root = cache_kind_dir(CACHE_DIR_NAME)
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


def rank_cache_key(items, payload: dict, *, base_url: str = "") -> str:
    """Stable key for one series rank: ``hash(paths + mtimes + digests + endpoint + payload)``.

    The payload alone is not enough: its aliases (``img_N``) are opaque, so the
    on-disk path/mtime identity must be folded in explicitly. Members are sorted
    by path so the key is independent of the caller's member order; the payload
    is canonicalised with ``sort_keys`` so a re-built-but-equal payload matches.

    Each member also carries its CONTENT digest (``content_digest``, ``""`` for
    an unreadable file): a rank is a measurement of pictures, so a rewrite that
    restored the mtime (unzip / ``cp -p``) must not reuse the previous bytes'
    order. Untouched files answer from the digest index, so a series is not
    re-read on every pass.

    ``base_url`` is the ENDPOINT that answered (the model id in the payload is a
    constant, ``jev_client.JEV_MODEL``), normalized through the gallery's ONE
    normalizer ``ai_providers._url_key``: two spellings of one provider share a
    pin, a provider switch is a MISS instead of serving the old endpoint's
    order. The ``""`` default is for storeless callers/tests; production passes
    the live settings.
    """
    from tabs.image_gallery.services import content_digest
    from tabs.image_gallery.services.ai_providers import _url_key

    parts: list[str] = []
    try:
        ordered = sorted(list(items or ()), key=_item_path)
    except Exception:
        ordered = list(items or ())
    for item in ordered:
        path = _item_path(item)
        mtime = _item_mtime(item)
        try:
            digest = content_digest.file_digest(path, mtime_ns=mtime) if path else ""
        except Exception:
            digest = ""
        parts.append(f"{path}:{mtime}:{digest}")
    parts.append(f"base_url={_url_key(base_url)}")
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        canonical = repr(payload)
    parts.append(canonical)
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class JevRankCache:
    """One-file-per-series JSON pin for Jev ranks.

    ``get`` returns the stored record (``{"ranks": {...} | None,
    "reason": str | None}``) or ``None`` on a miss. ``put`` stores either a
    decisive ``ranks`` mapping or an explicit abstain (``ranks=None`` plus the
    reason) so a re-run is stable. Transient failures (HTTP error, malformed
    body) are deliberately **not** pinned — a later pass may retry.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = Path(directory) if directory is not None else None

    def _dir(self) -> Path:
        if self._directory is not None:
            return self._directory
        return jev_cache_dir()

    def _path(self, key: str) -> Path:
        return self._dir() / f"rank_{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            p = self._path(key)
        except Exception:
            return None
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("jev rank cache read failed %s", p, exc_info=True)
            return None
        if not isinstance(data, dict):
            return None
        if int(data.get("version", 0) or 0) != JEV_CACHE_VERSION:
            return None
        ranks = data.get("ranks")
        if ranks is not None and not isinstance(ranks, dict):
            return None
        clean: dict[str, int] = {}
        if isinstance(ranks, dict):
            for path, rank in ranks.items():
                try:
                    clean[str(path)] = int(rank)
                except Exception:
                    continue
        return {"ranks": (clean if ranks is not None else None), "reason": data.get("reason")}

    def put(self, key: str, ranks: dict[str, int] | None, *, reason: str | None = None) -> None:
        try:
            p = self._path(key)
        except Exception:
            return
        record = {
            "version": JEV_CACHE_VERSION,
            "ranks": (dict(ranks) if ranks is not None else None),
            "reason": reason,
        }
        try:
            p.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        except OSError:
            logger.debug("jev rank cache write failed %s", p, exc_info=True)


_default_cache: JevRankCache | None = None


def default_cache() -> JevRankCache:
    """Process-wide default cache (lazy, disk-backed)."""
    global _default_cache
    if _default_cache is None:
        _default_cache = JevRankCache()
    return _default_cache


def clear_default_cache() -> int:
    """Delete every pin in the default cache directory; return the count.

    The gallery's "Reset metrics cache" entry point: a pinned Jev order is a
    measured decision, so a reset that zeroes every measurement has to drop it
    — otherwise the next pass over the same paths+mtimes+payload is served the
    SAME ranks with no second call, i.e. the reset looks like a no-op (owner
    order 2026-10-22, literal: no measurement survives).

    Only this module's own ``rank_*.json`` files are unlinked: the resolved
    directory can hold unrelated entries (the cache root is shared), so a
    whole-directory delete is not an option. A missing directory or an entry
    that cannot be removed contributes 0; never raises.
    """
    try:
        directory = jev_cache_dir()
    except Exception:
        return 0
    try:
        entries = sorted(Path(directory).glob("rank_*.json"))
    except Exception:
        return 0
    deleted = 0
    for path in entries:
        try:
            path.unlink()
            deleted += 1
        except OSError:
            logger.debug("jev rank pin delete failed %s", path, exc_info=True)
    return deleted


__all__ = [
    "CACHE_DIR_NAME",
    "JEV_CACHE_VERSION",
    "JevRankCache",
    "clear_default_cache",
    "default_cache",
    "jev_cache_dir",
    "rank_cache_key",
]
