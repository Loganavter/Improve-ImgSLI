"""Disk cache for Stage 3 VLM results — tie-breaks and compare briefs.

Key = hash(paths+mtime **+ the backend that answered**) like ``ai_cache`` /
``thumbnail_cache`` (sha256 of ``path:mtime_ns``) so edited files invalidate.
One file per pair/tie-break, stored alongside ``gallery_ai_cache`` as
``gallery_vlm_cache``.

WHY the backend is part of the key (invariant I1/I2): the content half alone
named the PICTURE, not the configuration that judged it, so pointing the same
model id at another endpoint (a provider switch — ``services/ai_providers``)
served the PREVIOUS endpoint's verdict/brief as if the new one had answered.
The provider half is ``model`` + the endpoint normalized through the ONE
gallery normalizer (``services/ai_providers._url_key``, also used by
``profile_cache`` / ``ai_cache``) + :data:`VLM_PROMPT_REVISION` (bump it when the
tie-break/brief prompt or its wire contract changes — an answer to a different
question must not be served). Old entries are honest MISSES (the key changed),
never a foreign answer.

The result RECORDS the model the provider actually served (``answered_model``,
from the wire reply). It is provenance only: the KEY stays on the requested
model, because the request chain is what the user configured and the fallback
is a routing detail of that one call.

Pure — no Qt. Cache IO is small JSON, safe to call from worker threads and
from filtering (brief tag search) without UI blocking.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from tabs.image_gallery.models import CompareBrief, TieBreakResult
from tabs.image_gallery.services.ai_providers import _url_key
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Prompt/schema revision of the Stage-3 VLM questions. Bump when
#: ``vlm.TIE_BREAK_PROMPT_TEMPLATE`` / ``COMPARE_BRIEF_PROMPT_TEMPLATE`` (or the
#: answer format they demand) changes: every cached verdict then answered a
#: different question and must be a MISS. Part of both cache keys.
VLM_PROMPT_REVISION = 1

#: The analysis-backend adapter that OWNS this store (ADR 009 wave A4) — see
#: ``services.ai_cache.CACHE_NAMESPACE``. The tie-break / brief answers are the
#: judge's, never a detector's.
CACHE_NAMESPACE = "ai"


def vlm_cache_dir() -> Path:
    from services.io.project_package import cache_kind_dir

    root = cache_kind_dir("gallery_vlm_cache")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _hash_key(parts: list[str]) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _backend_parts(model: str, base_url: str) -> list[str]:
    """The provider half of a key: model + normalized endpoint + prompt revision.

    ``_url_key`` is the gallery's ONE endpoint normalizer, so ``https://h/v1``
    and ``https://h/v1/`` name the same backend while a provider switch does
    not. The defaults (``""``) are for callers with no backend in hand (tests /
    legacy seeds); a production caller always passes the live settings.
    """
    return [
        f"model={str(model or '')}",
        f"base_url={_url_key(base_url)}",
        f"prompt={VLM_PROMPT_REVISION}",
    ]


def _tie_break_key(
    path_a: Path,
    mtime_a: int,
    path_b: Path,
    mtime_b: int,
    source_mtime: int | None = None,
    *,
    model: str = "",
    base_url: str = "",
) -> str:
    # Stable ordering: sort by resolved path string so (a,b) == (b,a)
    a_s = str(Path(path_a).resolve())
    b_s = str(Path(path_b).resolve())
    if a_s > b_s:
        a_s, b_s = b_s, a_s
        mtime_a, mtime_b = mtime_b, mtime_a
    parts = [f"{a_s}:{mtime_a}", f"{b_s}:{mtime_b}"]
    if source_mtime is not None:
        parts.append(f"source:{source_mtime}")
    parts.extend(_backend_parts(model, base_url))
    return _hash_key(parts)


def _brief_key(
    path_a: Path,
    mtime_a: int,
    path_b: Path,
    mtime_b: int,
    *,
    model: str = "",
    base_url: str = "",
) -> str:
    a_s = str(Path(path_a).resolve())
    b_s = str(Path(path_b).resolve())
    if a_s > b_s:
        a_s, b_s = b_s, a_s
        mtime_a, mtime_b = mtime_b, mtime_a
    return _hash_key(
        [f"{a_s}:{mtime_a}", f"{b_s}:{mtime_b}", *_backend_parts(model, base_url)]
    )


def _tie_path(key: str) -> Path:
    return vlm_cache_dir() / f"tie_{key}.json"


def _brief_path(key: str) -> Path:
    return vlm_cache_dir() / f"brief_{key}.json"


# -- tie-break ---------------------------------------------------------

def load_cached_tie_break(
    path_a: Path,
    mtime_a: int,
    path_b: Path,
    mtime_b: int,
    source_mtime: int | None = None,
    *,
    model: str = "",
    base_url: str = "",
) -> TieBreakResult | None:
    key = _tie_break_key(
        path_a, mtime_a, path_b, mtime_b, source_mtime, model=model, base_url=base_url
    )
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
            answered_model=data.get("answered_model", ""),
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
    *,
    model: str = "",
    base_url: str = "",
) -> None:
    key = _tie_break_key(
        path_a, mtime_a, path_b, mtime_b, source_mtime, model=model, base_url=base_url
    )
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
                    "answered_model": getattr(result, "answered_model", ""),
                    "decided_at_iso": result.decided_at_iso,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("VLM tie-break cache write failed %s", p, exc_info=True)


# -- compare brief -----------------------------------------------------

def load_cached_brief(
    path_a: Path,
    mtime_a: int,
    path_b: Path,
    mtime_b: int,
    *,
    model: str = "",
    base_url: str = "",
) -> CompareBrief | None:
    key = _brief_key(path_a, mtime_a, path_b, mtime_b, model=model, base_url=base_url)
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
            answered_model=data.get("answered_model", ""),
        )
    except Exception:
        logger.debug("VLM brief cache read failed %s", p, exc_info=True)
        return None


def save_brief(
    path_a: Path,
    mtime_a: int,
    path_b: Path,
    mtime_b: int,
    result: CompareBrief,
    *,
    model: str = "",
    base_url: str = "",
) -> None:
    key = _brief_key(path_a, mtime_a, path_b, mtime_b, model=model, base_url=base_url)
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
                    "answered_model": getattr(result, "answered_model", ""),
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

    The ``mtime_ns`` lookup is mtime-honoring: when the file still exists on
    disk but its current mtime differs, stale briefs for the old content are
    skipped instead of matching another file's text.

    This is a TEXT SEARCH over every brief on disk, deliberately across
    backends: it answers "does any brief mention this phrase", not "what did the
    current backend answer" (that is :func:`load_cached_brief`, which keys on
    the provider). Each returned record still carries the ``model`` /
    ``answered_model`` that wrote it.
    """
    wanted = str(Path(path).resolve())
    out: list[CompareBrief] = []
    try:
        current_mtime: int | None = Path(path).stat().st_mtime_ns
    except OSError:
        current_mtime = None
    if current_mtime is not None and int(mtime_ns or 0) and current_mtime != int(mtime_ns):
        return out
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
                        answered_model=data.get("answered_model", ""),
                    )
                )
        except Exception:
            continue
    # Also fallback: if brief key was built from sorted order, wanted might match
    # even when pair strings are unresolved symlinks — try containment via hash lookup?
    # Keep fallback: direct key lookup for single-image self? Not needed.
    return out


def clear_default_cache() -> int:
    """Delete every cached tie-break + compare brief; return the count.

    The gallery's "Reset metrics cache" entry point: a cached verdict or brief
    was produced by a paid backend and is a measurement, so a reset that zeroes
    every measurement has to drop it — otherwise the next pass is answered from
    disk and the reset looks like a no-op (owner order 2026-10-22, literal: no
    measurement survives).

    Removes only this module's own ``tie_*.json`` / ``brief_*.json`` files from
    the directory its own :func:`vlm_cache_dir` resolves (the cache root is
    shared with the other gallery stores, so no whole-directory delete). A
    missing directory or an entry that cannot be removed contributes 0; never
    raises.
    """
    try:
        directory = vlm_cache_dir()
    except Exception:
        return 0
    deleted = 0
    for pattern in ("tie_*.json", "brief_*.json"):
        try:
            entries = sorted(Path(directory).glob(pattern))
        except Exception:
            continue
        for path in entries:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                logger.debug("VLM cache entry delete failed %s", path, exc_info=True)
    return deleted
