"""Content identity for the gallery's caches: a digest of the BYTES, not the path.

The bug this closes (owner, 2026-10-27 ``content-identity``): every gallery cache
keyed on ``sha256(path:mtime_ns)``. That key names a *file slot*, not a
*picture*, so two ordinary situations silently lied:

* a file rewritten with its mtime preserved (archive extraction, ``cp -p``,
  some editors) hit the old entry and served the PREVIOUS bytes' thumbnail /
  scorecard / rank;
* the same picture under another name paid the full analysis again, although
  the question to the backend is byte-for-byte the same.

The rule applied here is the one profiling tools use: **mtime is for speed, the
hash is for truth**. ``cache_key_for`` / ``ai_cache._cache_path`` /
``vlm_cache`` / ``jev_cache`` therefore fold a blake2b digest of the file into
their keys whenever one is available (see each module), and this module is the
ONE place that produces it.

Why blake2b-128 through :func:`hashlib.file_digest`: stdlib only (no xxhash /
blake3 dependency), and the reader is streamed by the stdlib — no full-frame
buffer for a large image. ``DIGEST_HEX`` hex chars = 128 bits, which is far past
any collision that could matter for a per-folder cache and short enough to sit
in a filename beside the identity digest.

The INDEX is what makes this affordable. "Compute the digest where the file is
already being read" cannot be honoured by every call site at once (the folder
probe, the thumbnail key and a pair key all ask before anything opened the
file), and re-reading a 20 MB file per open would be a real regression, so the
result is memoized: ``path -> (size, mtime_ns, ctime_ns, digest)`` in memory and
on disk (``<app cache root>/gallery_content_index/index.json`` — resolved through
the app's ONE cache locator, atomic replace, bounded). An UNCHANGED file is
never read twice — the same stat
identity answers from the index, which is exactly the "second call does not open
the file" contract the tests assert.

``ctime_ns`` is part of that stat identity on purpose, and it is the field that
actually fixes the owner's first symptom: restoring ``mtime`` after a rewrite
(``cp -p`` / unzip) leaves ``ctime`` at the moment of the write, so the index
ticks and the bytes are re-read. A plain untouched file keeps all three, so the
extra field costs no reads. The residual boundary is honest and documented: a
rewrite that restores ``mtime`` *and* lands in the same nanosecond *and* keeps
the size is indistinguishable from no write without reading the file on every
call — which is the cost this index exists to avoid.

The disk index is a rebuildable hint, never a source of truth: an unreadable or
corrupt file, a version bump or a lost entry all degrade to "read the bytes
again" (a slower HIT, never a wrong one). Writes are throttled (every
``_FLUSH_PENDING`` new entries or ``_FLUSH_INTERVAL`` seconds) because the whole
dictionary is rewritten each time and a cold 5000-image folder must not rewrite
it 5000 times; losing the tail on a crash costs one re-read next run.

Every public function is total: it never raises, and an unreadable file answers
``""`` — a distinct, logged state, never a fabricated "empty digest" that could
collide with another unreadable file. ``""`` is also what a caller passes to the
key functions to mean "unknown", so the key degrades to the path-keyed form
instead of pretending.

Pure stdlib, no Qt. Safe to call from worker threads and from the UI thread
(the index is lock-guarded and the file read is bounded by one file).
"""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import logging
import os
import threading
import time
from pathlib import Path

from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Hex chars kept from the blake2b digest — 128 bits (see the module docstring
#: for why truncating the stdlib's 512-bit blake2b is how "blake2b-128" is
#: spelled here: :func:`hashlib.file_digest` takes a constructor NAME, and the
#: named blake2b constructor has no digest_size argument).
DIGEST_HEX = 32

#: Entries kept in the index. It is a hint keyed by an absolute path, so the
#: bound only decides how many folders are remembered between runs; eviction is
#: FIFO (oldest insertion first) and costs a re-read, never correctness.
INDEX_LIMIT = 4096

#: On-disk shape version. Bumped only for an incompatible entry shape; a stale
#: version is dropped wholesale (rebuild = re-read once), never migrated.
INDEX_VERSION = 1

#: Write the whole dictionary at most this often / after this many new entries.
_FLUSH_INTERVAL = 2.0
_FLUSH_PENDING = 64

#: Cache kind directory (under the app's ONE cache root — see
#: ``services.io.project_package.cache_kind_dir``) and the file inside it. The
#: root is derived from ``core.log_names.APP_NAME``, never a hard-coded product
#: name, and it already honours ``XDG_CACHE_HOME`` / ``IMGSLI_PROJECT_CACHE``
#: plus the pre-rename carry-forward, so this store needs no path policy of its
#: own.
_CACHE_KIND = "gallery_content_index"
_INDEX_NAME = "index.json"

#: Opened through this seam so a test can prove "an unchanged file is not read
#: again" by replacing it with a counter that fails on use, instead of trusting
#: a timing measurement.
_open = builtins.open

_LOCK = threading.RLock()
#: absolute path -> (size, mtime_ns, ctime_ns, digest)
_INDEX: dict[str, tuple[int, int, int, str]] = {}
_LOADED = False
_HITS = 0
_MISSES = 0
_PENDING = 0
_LAST_FLUSH = 0.0


# -- paths / index ------------------------------------------------------


def index_path() -> Path:
    """Where the digest index lives: ``<app cache root>/gallery_content_index/index.json``.

    Resolved through ``services.io.project_package.cache_kind_dir`` — the ONE
    cache locator the gallery's other stores use — so the index follows
    ``XDG_CACHE_HOME`` / ``IMGSLI_PROJECT_CACHE`` and the product's current name
    without a second path policy here. It is resolved on every call (not cached)
    so a test can redirect it and re-resolution can never leak a stale root
    between runs of one process.
    """
    from services.io.project_package import cache_kind_dir

    return cache_kind_dir(_CACHE_KIND) / _INDEX_NAME


def _resolve(path) -> str:  # type: ignore[no-untyped-def]
    """Absolute, symlink-free path string; ``""`` when it cannot be formed."""
    try:
        return os.path.realpath(os.fspath(path))
    except Exception:
        return ""


def _name(resolved: str) -> str:
    """Bare file name for a log line (the full path is noise in the log)."""
    try:
        return os.path.basename(resolved) or resolved
    except Exception:
        return resolved


def _ensure_loaded() -> None:
    """Load the disk index once per process; a failure is simply "no index"."""
    global _LOADED
    with _LOCK:
        if _LOADED:
            return
        # Set before the IO so a failing/corrupt file is not retried on every
        # digest call (the cost of a lost index is one re-read, not a spin).
        _LOADED = True
        try:
            raw = index_path().read_text(encoding="utf-8")
        except OSError:
            return
        except Exception:
            logger.debug("content identity index unreadable", exc_info=True)
            return
        try:
            data = json.loads(raw)
        except Exception:
            logger.debug("content identity index is not JSON — rebuilding", exc_info=True)
            return
        if not isinstance(data, dict):
            return
        try:
            version = int(data.get("version", 0) or 0)
        except Exception:
            version = 0
        if version != INDEX_VERSION:
            return
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return
        for key, value in entries.items():
            try:
                size, mtime_ns, ctime_ns, digest = value
                if not isinstance(digest, str) or not digest:
                    continue
                _INDEX[str(key)] = (
                    int(size),
                    int(mtime_ns),
                    int(ctime_ns),
                    digest,
                )
            except Exception:
                continue
            if len(_INDEX) >= INDEX_LIMIT:
                break


def _persist(*, force: bool = False) -> None:
    """Atomically write the index (throttled — see the module docstring)."""
    global _PENDING, _LAST_FLUSH
    with _LOCK:
        if not force and (
            _PENDING < _FLUSH_PENDING and (time.monotonic() - _LAST_FLUSH) < _FLUSH_INTERVAL
        ):
            return
        _PENDING = 0
        _LAST_FLUSH = time.monotonic()
        entries = {key: list(value) for key, value in _INDEX.items()}
    target = index_path()
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": INDEX_VERSION, "digest": "blake2b-128", "entries": entries},
            separators=(",", ":"),
        )
        with _open(tmp, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, target)
    except Exception:
        logger.debug("content identity index write failed %s", target, exc_info=True)
        try:
            tmp.unlink()
        except OSError:
            pass


def _remember(resolved: str, size: int, mtime_ns: int, ctime_ns: int, digest: str) -> None:
    """Store one entry (FIFO-bounded) and queue the throttled write."""
    global _PENDING
    with _LOCK:
        if resolved not in _INDEX and len(_INDEX) >= INDEX_LIMIT:
            try:
                _INDEX.pop(next(iter(_INDEX)), None)
            except Exception:
                pass
        _INDEX[resolved] = (int(size), int(mtime_ns), int(ctime_ns), digest)
        _PENDING += 1
    _persist()


# -- the digest ----------------------------------------------------------


def digest_of_bytes(data: bytes) -> str:
    """Digest of an in-memory payload (blake2b-128 hex, ``DIGEST_HEX`` chars).

    The one-shot twin of :func:`file_digest`, for callers that already hold the
    bytes (a synthetic test image, a re-encoded normalised frame). It runs the
    SAME ``file_digest`` over a ``BytesIO``, so the two can never drift apart —
    a caller may compare one against the other. Never raises: a non-bytes value
    answers ``""``.
    """
    try:
        return hashlib.file_digest(io.BytesIO(bytes(data)), "blake2b").hexdigest()[
            :DIGEST_HEX
        ]
    except Exception:
        return ""


def file_digest(path, *, size: int | None = None, mtime_ns: int | None = None) -> str:  # type: ignore[no-untyped-def]
    """Content digest of *path* — ``""`` when the bytes cannot be read.

    ``size`` / ``mtime_ns`` exist so a caller that already scanned the folder
    can express the version it is keying on WITHOUT this function having to
    invent one. They are deliberately not trusted for freshness: the on-disk
    stat is what the index compares against, because a scan's mtime is already
    stale the moment a file is rewritten mid-run, and skipping the stat on a
    remembered mtime is exactly the hole (``path:mtime``) this module closes.

    An unchanged file never re-reads its bytes: the index answers from
    ``(size, mtime_ns, ctime_ns)``, which is what keeps "identity by content"
    from turning into "read every file on every open".

    The one log line that matters is the content change: the same path, a
    different digest. It is emitted once per rewrite and names the file only —
    the cache entries keyed on the old digest are now unreachable (they stay on
    disk until the gallery's "Reset metrics cache" drops them).
    """
    del size, mtime_ns  # hints only — see the docstring
    resolved = _resolve(path)
    if not resolved:
        return ""
    try:
        st = os.stat(resolved)
        stat_size = int(getattr(st, "st_size", 0) or 0)
        stat_mtime = int(getattr(st, "st_mtime_ns", 0) or 0)
        stat_ctime = int(getattr(st, "st_ctime_ns", 0) or 0)
    except OSError:
        # A missing file is not an error worth a line: every cache path asks
        # about files that may have been deleted since the scan, and the answer
        # ("" = unknown) is the correct, stable one.
        return ""
    except Exception:
        logger.debug("content identity: cannot stat %s", _name(resolved), exc_info=True)
        return ""

    global _HITS, _MISSES
    _ensure_loaded()
    with _LOCK:
        entry = _INDEX.get(resolved)
    if (
        entry is not None
        and entry[0] == stat_size
        and entry[1] == stat_mtime
        and entry[2] == stat_ctime
    ):
        with _LOCK:
            _HITS += 1
        return entry[3]

    with _LOCK:
        _MISSES += 1
    try:
        with _open(resolved, "rb") as handle:
            digest = hashlib.file_digest(handle, "blake2b").hexdigest()[:DIGEST_HEX]
    except Exception:
        # Explicit, not "empty digest": an unreadable file has NO identity, and
        # the callers' keys fall back to the path-keyed form (never to a value
        # another unreadable file could share).
        logger.info("cache identity: %s unreadable — no content digest", _name(resolved))
        return ""

    digest = digest.lower()
    changed = entry is not None and bool(entry[3]) and entry[3] != digest
    _remember(resolved, stat_size, stat_mtime, stat_ctime or 0, digest)
    if changed:
        logger.info(
            "cache identity: %s content changed — entries dropped", _name(resolved)
        )
    return digest


def forget(path) -> None:  # type: ignore[no-untyped-def]
    """Drop *path*'s index entry (its next digest is re-read, never re-used)."""
    resolved = _resolve(path)
    if not resolved:
        return
    _ensure_loaded()
    with _LOCK:
        removed = _INDEX.pop(resolved, None) is not None
    if removed:
        _persist(force=True)


def index_stats() -> dict:
    """``{"entries": n, "hits": n, "misses": n}`` for the live process.

    ``hits`` = answered from the index (no filesystem read), ``misses`` = the
    file had to be read (or could not be), cumulative since import. Read by the
    tests and by the UI inspector; never raises.
    """
    try:
        _ensure_loaded()
    except Exception:
        pass
    with _LOCK:
        return {"entries": len(_INDEX), "hits": _HITS, "misses": _MISSES}


def _reset_state(*, drop_disk: bool = False) -> None:
    """Forget the in-memory index and counters — a fresh-process simulation.

    Tests only: the process is expected to keep one index for its lifetime.
    ``drop_disk`` also removes the file, so a test can prove the index is
    actually written and re-read instead of surviving in memory.
    """
    global _LOADED, _HITS, _MISSES, _PENDING, _LAST_FLUSH
    with _LOCK:
        _INDEX.clear()
        _LOADED = False
        _HITS = 0
        _MISSES = 0
        _PENDING = 0
        _LAST_FLUSH = 0.0
    if drop_disk:
        try:
            index_path().unlink()
        except OSError:
            pass


__all__ = [
    "DIGEST_HEX",
    "INDEX_LIMIT",
    "digest_of_bytes",
    "file_digest",
    "forget",
    "index_path",
    "index_stats",
]
