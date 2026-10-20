"""Append-only Q/A log for the gallery's Ask AI surface.

The flyout used to keep its answers only in memory (``controller._ask_cache``,
a per-run dict), so nothing survived a restart and there was no history to
show. This module persists every completed answer as one JSONL record under the
app cache dir — ``_cache_root() / "gallery_ask_log"``, the same root
``ai_cache`` / ``vlm_cache`` use (so ``IMGSLI_PROJECT_CACHE`` and the Qt cache
location both apply).

Record shape — fixed keys, always in this order (``RECORD_KEYS``)::

    {"ts": "<ISO-8601 UTC>", "scope_kind": "selection|series|region",
     "scope_label": str, "paths": [str, ...], "question": str,
     "answer": str, "backend": {"model": str, "base_url": str},
     "mode": str, "profile": str, "effort": str, "cache_hit": bool}

``api_key`` is never accepted nor stored: ``backend`` is rebuilt from exactly
model + base_url on every append, so a caller's accidental extra key cannot
reach the file. The profile is the metric-profile identity (its axis ids, in
registry order — the same token ``ai_cache.analysis_cache_identity`` uses).

**One record per completed answer.** Never one per streaming token/chunk — the
controller appends once, from the completion handler. Error paths (routing
stub, not-configured, transport/worker errors) are deliberately NOT recorded:
this is an answer history, not an error journal. A cache REPLAY is an answer
and IS recorded, with ``cache_hit=True`` (so the history shows repeated asks
rather than hiding them).

Bounded, explicitly: the file is capped at ``ASK_LOG_MAX_RECORDS`` (500).
Every :func:`append` calls :func:`trim`, which keeps the newest N *valid* lines
and rewrites the file atomically (``<name>.jsonl.tmp`` + ``os.replace``) — the
bound therefore survives restarts, not just one process. A truncated/corrupt
line is skipped on read and dropped by the next trim; IO/parse failures degrade
to "no record" and never raise into the ask flow.

Read API for a future history UI: :func:`recent` (newest first, optional
scope-path filter, ``limit``) and :func:`count` (the flyout's "N previous
questions" affordance). Pure stdlib — no Qt imports.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ImproveImgSLI")

#: Directory (under the app cache root) and file name of the log.
ASK_LOG_DIRNAME = "gallery_ask_log"
ASK_LOG_FILENAME = "ask_log.jsonl"

#: Hard bound on the persisted history — the newest N records survive.
ASK_LOG_MAX_RECORDS = 500

#: Default page size of :func:`recent`.
ASK_LOG_RECENT_LIMIT = 20

#: Canonical record key order (deterministic JSON on every write).
RECORD_KEYS = (
    "ts",
    "scope_kind",
    "scope_label",
    "paths",
    "question",
    "answer",
    "backend",
    "mode",
    "profile",
    "effort",
    "cache_hit",
)

#: One writer at a time (append + trim rewrite the same file). Re-entrant
#: because ``append`` -> ``trim`` happens on the same thread.
_LOCK = threading.RLock()


def ask_log_dir() -> Path:
    """The log directory (created on demand), under the shared cache root."""
    from services.io.project_package import _cache_root

    root = _cache_root() / ASK_LOG_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def log_path() -> Path:
    """Absolute path of the JSONL log file (not created by this call)."""
    return ask_log_dir() / ASK_LOG_FILENAME


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with a second resolution (stable, sortable)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_text(value) -> str:  # type: ignore[no-untyped-def]
    """``str(value)`` stripped, or ``""`` — never raises."""
    try:
        return str(value or "").strip()
    except Exception:
        return ""


def _clean_paths(paths) -> list[str]:  # type: ignore[no-untyped-def]
    """Deduped, sorted string paths — deterministic and filter-friendly."""
    try:
        seq = list(paths or ())
    except Exception:
        seq = []
    out: list[str] = []
    for raw in seq:
        text = _clean_text(raw)
        if text and text not in out:
            out.append(text)
    return sorted(out)


def make_record(
    *,
    scope_kind="",  # type: ignore[no-untyped-def]
    scope_label="",  # type: ignore[no-untyped-def]
    paths=(),  # type: ignore[no-untyped-def]
    question="",  # type: ignore[no-untyped-def]
    answer="",  # type: ignore[no-untyped-def]
    model="",  # type: ignore[no-untyped-def]
    base_url="",  # type: ignore[no-untyped-def]
    mode="",  # type: ignore[no-untyped-def]
    profile="",  # type: ignore[no-untyped-def]
    effort="",  # type: ignore[no-untyped-def]
    cache_hit: bool = False,
    ts=None,  # type: ignore[no-untyped-def]
) -> dict:
    """Build one record with the canonical shape/order. Never raises.

    ``backend`` carries only ``model`` + ``base_url`` — there is no accepted
    parameter for ``api_key``, and that is deliberate (the log is not a
    credential store).
    """
    return {
        "ts": _clean_text(ts) or _utc_now_iso(),
        "scope_kind": _clean_text(scope_kind),
        "scope_label": _clean_text(scope_label),
        "paths": _clean_paths(paths),
        "question": _clean_text(question),
        "answer": _clean_text(answer),
        "backend": {
            "model": _clean_text(model),
            "base_url": _clean_text(base_url),
        },
        "mode": _clean_text(mode),
        "profile": _clean_text(profile),
        "effort": _clean_text(effort),
        "cache_hit": bool(cache_hit),
    }


def _read_lines(path: Path) -> list[str]:
    """Non-empty lines of ``path`` (``[]`` when missing/unreadable)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        logger.debug("Ask log read failed: %s", path, exc_info=True)
        return []
    return [line for line in text.splitlines() if line.strip()]


def _valid_json_line(line: str) -> bool:
    try:
        return isinstance(json.loads(line), dict)
    except Exception:
        return False


def trim(max_records: int | None = None) -> int:
    """Keep only the newest ``max_records`` valid lines; return how many went.

    Atomic (temp file + ``os.replace``) so a crash mid-trim cannot leave a
    half-written log. Corrupt/truncated lines are dropped whenever a trim runs
    (they are also skipped on read). Never raises; a missing log returns 0.
    """
    try:
        keep = int(ASK_LOG_MAX_RECORDS if max_records is None else max_records)
    except Exception:
        keep = ASK_LOG_MAX_RECORDS
    keep = max(0, keep)
    try:
        path = log_path()
    except Exception:
        return 0
    with _LOCK:
        lines = _read_lines(path)
        valid = [line for line in lines if _valid_json_line(line)]
        dropped = len(lines) - min(len(valid), keep)
        if len(valid) <= keep and len(lines) == len(valid):
            return 0
        kept = valid[-keep:] if keep else []
        try:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(
                "".join(line + "\n" for line in kept), encoding="utf-8"
            )
            os.replace(tmp, path)
        except OSError:
            logger.debug("Ask log trim failed: %s", path, exc_info=True)
            return 0
        return dropped


def append(record: dict, *, max_records: int | None = None) -> bool:
    """Append one already-built record, then trim to the bound.

    The stored object is rebuilt from ``RECORD_KEYS`` — notably ``backend`` is
    reduced to ``model`` / ``base_url``, so an ``api_key`` smuggled into the
    mapping never reaches the file. Never raises; True on a successful write.
    """
    if not isinstance(record, dict):
        return False
    try:
        backend = record.get("backend")
        backend = backend if isinstance(backend, dict) else {}
        payload = {
            "ts": _clean_text(record.get("ts")) or _utc_now_iso(),
            "scope_kind": _clean_text(record.get("scope_kind")),
            "scope_label": _clean_text(record.get("scope_label")),
            "paths": _clean_paths(record.get("paths")),
            "question": _clean_text(record.get("question")),
            "answer": _clean_text(record.get("answer")),
            "backend": {
                "model": _clean_text(backend.get("model")),
                "base_url": _clean_text(backend.get("base_url")),
            },
            "mode": _clean_text(record.get("mode")),
            "profile": _clean_text(record.get("profile")),
            "effort": _clean_text(record.get("effort")),
            "cache_hit": bool(record.get("cache_hit", False)),
        }
        line = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False
        )
        path = log_path()
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:
        logger.debug("Ask log append failed", exc_info=True)
        return False
    trim(max_records=max_records)
    return True


def append_answer(**kwargs) -> dict | None:  # type: ignore[no-untyped-def]
    """Build + append one answer record; the record, or ``None`` on failure.

    Convenience over :func:`make_record` + :func:`append` for the completion
    path. Keyword arguments are exactly ``make_record``'s.
    """
    try:
        record = make_record(**kwargs)
    except Exception:
        return None
    return record if append(record) else None


def read_all() -> list[dict]:
    """Every valid record, oldest → newest (corrupt lines skipped)."""
    try:
        path = log_path()
    except Exception:
        return []
    records: list[dict] = []
    for line in _read_lines(path):
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def _scope_matches(record: dict, wanted: set[str]) -> bool:
    try:
        paths = {str(p) for p in (record.get("paths") or ())}
    except Exception:
        return False
    return bool(paths & wanted)


def recent(scope_paths=None, limit: int | None = None) -> list[dict]:  # type: ignore[no-untyped-def]
    """The newest records first, optionally filtered by scope paths.

    ``scope_paths`` matches a record when the two path sets intersect (a series
    record matches any of its members; ``None``/empty means "the whole log").
    ``limit`` defaults to :data:`ASK_LOG_RECENT_LIMIT`; ``<= 0`` yields ``[]``.
    Never raises.
    """
    try:
        page = int(ASK_LOG_RECENT_LIMIT if limit is None else limit)
    except Exception:
        page = ASK_LOG_RECENT_LIMIT
    if page <= 0:
        return []
    records = read_all()
    wanted: set[str] = set()
    if scope_paths is not None:
        try:
            wanted = {
                str(p) for p in scope_paths if _clean_text(p)
            }
        except Exception:
            wanted = set()
    if wanted:
        records = [record for record in records if _scope_matches(record, wanted)]
    return list(reversed(records))[:page]


def count(scope_paths=None) -> int:  # type: ignore[no-untyped-def]
    """How many records the log holds for ``scope_paths`` (all when ``None``).

    Backs the flyout's "N previous questions" line. Never raises.
    """
    try:
        return len(recent(scope_paths=scope_paths, limit=ASK_LOG_MAX_RECORDS))
    except Exception:
        return 0


__all__ = [
    "ASK_LOG_DIRNAME",
    "ASK_LOG_FILENAME",
    "ASK_LOG_MAX_RECORDS",
    "ASK_LOG_RECENT_LIMIT",
    "RECORD_KEYS",
    "append",
    "append_answer",
    "ask_log_dir",
    "count",
    "log_path",
    "make_record",
    "read_all",
    "recent",
    "trim",
]
