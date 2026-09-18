"""Persistent disk cache of finished strip thumbnails (P2 wave).

Key = (source paths + mtime + size, autocrop flag, split state, target
size, render scale, snapshot-params hash). The hash is CONSERVATIVE: any
doubt (unstatable source, unhashable snapshot, bad target size) yields
``None`` (a miss) instead of a guess — a wrong thumbnail is worse than a
slow thumbnail, so the cache prefers a miss over a wrong hit.

Value = finished 160x90 PNG bytes (the post-``_finish_thumbnail_image``
cover output). LRU eviction is capped by entry count and total bytes,
ordered by file mtime so it survives restarts.

Cache dir = ``get_log_directory("ImproveImgSLI") + "thumbnails"`` (never
the log dir itself, never raw XDG paths, never ``/tmp``) — same precedent
as ``src/engine/cache/tile_debug.py``. Corrupt/unreadable entries are a
miss (undecodable files are removed so they cost one decode attempt, then
overwritten by the next store); nothing here ever raises into the
thumbnail emit path. No proactive invalidation beyond key conservatism.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import tempfile
import threading

logger = logging.getLogger("ImproveImgSLI")

CACHE_SUBDIR_NAME = "thumbnails"
CACHE_FILE_SUFFIX = ".png"

#: Bump to invalidate every stored entry (key schema change).
KEY_VERSION = "v1"

DEFAULT_MAX_ENTRIES = 512
DEFAULT_MAX_BYTES = 64 * 1024 * 1024

_HEXDIGITS = frozenset("0123456789abcdef")


def default_thumbnail_cache_dir() -> str:
    """``<app-data>/ImproveImgSLI/thumbnails`` — always a subdir, never the
    log dir itself. Raises only if the platform directory is unresolvable
    (callers treat that as cache-unavailable)."""
    from sli_ui_toolkit.core.logging import get_log_directory

    base = get_log_directory("ImproveImgSLI")
    return os.path.join(base, CACHE_SUBDIR_NAME)


def _extract_split_state(snap) -> object:
    """Best-effort split/divider state probe.

    Split position lives inside ``viewport_state``/``settings_state`` (whose
    full reprs are already hashed), so this is belt-and-braces explicitness
    for the key-spec's "split state" component. Returns ``""`` on any doubt
    — the surrounding reprs still carry the information.
    """
    candidates = ("split", "split_state", "split_position", "splitter_state", "divider")
    try:
        for name in candidates:
            try:
                value = getattr(snap, name, None)
            except Exception:
                continue
            if value is not None:
                try:
                    return repr(value)
                except Exception:
                    continue
        for container_attr in ("viewport_state", "settings_state"):
            try:
                container = getattr(snap, container_attr, None)
            except Exception:
                continue
            if isinstance(container, dict):
                for name in candidates:
                    if name in container:
                        try:
                            return repr(container[name])
                        except Exception:
                            continue
            else:
                for name in candidates:
                    try:
                        value = getattr(container, name, None)
                    except Exception:
                        continue
                    if value is not None:
                        try:
                            return repr(value)
                        except Exception:
                            continue
    except Exception:
        pass
    return ""


def hash_snapshot_params(snap) -> str | None:
    """Conservative hash of what identifies snapshot render params.

    Covers timestamp, image paths/names, the full ``viewport_state`` and
    ``settings_state`` reprs (pan/zoom/split/tool values ride along), plus
    the explicit split probe. Returns ``None`` on any doubt (miss).
    """
    try:
        parts: list[str] = []
        try:
            parts.append("timestamp=" + repr(float(getattr(snap, "timestamp", -1.0))))
        except Exception:
            return None
        for attr in ("image1_path", "image2_path", "name1", "name2"):
            try:
                parts.append(attr + "=" + repr(getattr(snap, attr, None)))
            except Exception:
                return None
        for attr in ("viewport_state", "settings_state"):
            try:
                value = getattr(snap, attr, None)
            except Exception:
                return None
            try:
                parts.append(attr + "=" + repr(value))
            except Exception:
                return None
        try:
            parts.append("split=" + repr(_extract_split_state(snap)))
        except Exception:
            return None
        return hashlib.sha256(
            "\x00".join(parts).encode("utf-8", "replace")
        ).hexdigest()
    except Exception:
        return None


def _stat_fingerprint(path: str, attr: str) -> str | None:
    """``"<attr>=<path>\\0mtime=<ns>\\0size=<bytes>"`` — ``None`` on doubt.

    A non-``None`` path that cannot be stat'ed (moved/deleted/unreadable
    source) is doubt, not a key component: without mtime+size two different
    contents could share a key.
    """
    if path is None:
        return attr + "=none"
    if not isinstance(path, (str, os.PathLike)):
        return None
    try:
        path_str = os.fspath(path)
    except Exception:
        return None
    try:
        st = os.stat(path_str)
    except OSError:
        return None
    except Exception:
        return None
    return (
        f"{attr}={path_str}\x00mtime={st.st_mtime_ns}\x00size={st.st_size}"
    )


def thumbnail_cache_key_for_snap(
    snap,
    *,
    auto_crop: bool = False,
    thumbnail_size=(160, 90),
    render_scale: float = 1.0,
) -> str | None:
    """Cache key for ``snap`` — hex digest, or ``None`` on any doubt (miss).

    The autocrop *verdict* needs no separate component: for fixed
    ``(auto_crop, snap)`` inputs the renderer output is deterministic, so
    the flag plus the snapshot hash already pins the verdict down.
    """
    try:
        target_w, target_h = int(thumbnail_size[0]), int(thumbnail_size[1])
    except Exception:
        return None
    if target_w <= 0 or target_h <= 0:
        return None
    try:
        scale = float(render_scale)
    except Exception:
        return None
    snap_hash = hash_snapshot_params(snap)
    if snap_hash is None:
        return None
    try:
        path1 = getattr(snap, "image1_path", None)
    except Exception:
        return None
    try:
        path2 = getattr(snap, "image2_path", None)
    except Exception:
        return None
    fp1 = _stat_fingerprint(path1, "image1_path")
    if fp1 is None:
        return None
    fp2 = _stat_fingerprint(path2, "image2_path")
    if fp2 is None:
        return None
    try:
        raw = "\x00".join(
            [
                KEY_VERSION,
                f"target={target_w}x{target_h}",
                f"autocrop={bool(auto_crop)!r}",
                f"scale={scale!r}",
                snap_hash,
                fp1,
                fp2,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()
    except Exception:
        return None


class ThumbnailDiskCache:
    """LRU disk cache of finished thumbnail PNGs. Never raises to callers.

    ``get``/``put`` swallow every failure (miss / ``False``) so a broken
    cache dir degrades to the no-cache path instead of breaking the strip.
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        if cache_dir is None:
            cache_dir = default_thumbnail_cache_dir()
        self._dir = os.fspath(cache_dir)
        self._max_entries = max(1, int(max_entries))
        self._max_bytes = max(1, int(max_bytes))
        self._lock = threading.Lock()
        try:
            os.makedirs(self._dir, exist_ok=True)
        except Exception:
            logger.debug(
                "Thumbnail disk cache dir unavailable: %s", self._dir, exc_info=True
            )

    @property
    def cache_dir(self) -> str:
        return self._dir

    def _path_for_key(self, key) -> str | None:
        if (
            not isinstance(key, str)
            or len(key) != 64
            or any(c not in _HEXDIGITS for c in key)
        ):
            return None
        return os.path.join(self._dir, key + CACHE_FILE_SUFFIX)

    def get(self, key, *, expected_size=None):
        """Finished PIL image for ``key``, or ``None`` (miss — never raises).

        ``expected_size`` (the request's thumbnail size) rejects corrupt
        entries that decode to the wrong dimensions; the key already binds
        the target size, so a mismatch means corruption.
        """
        try:
            path = self._path_for_key(key)
            if path is None or not os.path.isfile(path):
                return None
            from PIL import Image

            try:
                with Image.open(path) as img:
                    img.load()
                    if expected_size is not None and tuple(img.size) != tuple(
                        expected_size
                    ):
                        return None
                    return img.convert("RGBA")
            except Exception:
                # Undecodable entry: drop it so the next lookup costs one
                # stat instead of another failed decode; the next store
                # overwrites the key. Never propagates.
                with self._lock:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                return None
            finally:
                try:
                    os.utime(path, None)
                except OSError:
                    pass
        except Exception:
            return None

    def put(self, key, pil_image) -> bool:
        """Store finished ``pil_image`` under ``key`` (atomic replace)."""
        try:
            path = self._path_for_key(key)
            if path is None or pil_image is None:
                return False
            size = getattr(pil_image, "size", None)
            if (
                size is None
                or len(size) != 2
                or int(size[0]) <= 0
                or int(size[1]) <= 0
            ):
                return False
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            payload = buf.getvalue()
            if not payload:
                return False
            fd, tmp = tempfile.mkstemp(
                dir=self._dir, prefix=".thumb-", suffix=CACHE_FILE_SUFFIX
            )
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                os.replace(tmp, path)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            self._evict_if_needed()
            return True
        except Exception:
            return False

    def _evict_if_needed(self) -> None:
        """Drop oldest-mtime entries while over count/byte caps."""
        try:
            with self._lock:
                entries: list[tuple[int, str, int]] = []
                total = 0
                try:
                    listing = os.scandir(self._dir)
                except OSError:
                    return
                with listing:
                    for entry in listing:
                        if entry.name.startswith(".") or not entry.name.endswith(
                            CACHE_FILE_SUFFIX
                        ):
                            continue
                        try:
                            st = entry.stat()
                        except OSError:
                            continue
                        entries.append((st.st_mtime_ns, entry.name, st.st_size))
                        total += st.st_size
                entries.sort()
                for _, name, size in list(entries):
                    if len(entries) <= self._max_entries and total <= self._max_bytes:
                        break
                    try:
                        os.remove(os.path.join(self._dir, name))
                    except OSError:
                        continue
                    entries.pop(0)
                    total -= size
        except Exception:
            pass
