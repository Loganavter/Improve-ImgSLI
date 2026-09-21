"""Host-owned embedded pixel-cache registry — single process-wide dict.

Logically owned by PipelineCache (tabs embedded tier) — ALLOWED, physically lives in
``shared`` so host code (``services.io.project_io``,
``shared.image_processing.pixel_cache_loader``) can use it without importing
``tabs`` (see ``tests/contracts/test_ui_tab_sandbox.py``).

This is the single source for embedded pixel-cache storage after Phase 1
(8→1). The former registry shim is removed; this module is the
host-safe interface. PipelineCache aliases ``_cache`` directly (tabs may
import shared, not the reverse).

Content identity (CONTENT IDENTITY law): the dict key stays the plain path
string for back-compat with direct ``_cache`` readers, but every entry
carries a validation sidecar (``_meta``) — media mtime/size at register
time plus the crop box the buffer was saved with. ``lookup`` (and
``lookup_detail``) stat the media file now and:

- mtime/size mismatch → the file was replaced: the stale entry is evicted
  and the lookup misses LOUDLY (``replaced-file``) instead of serving
  wrong dims/content;
- crop requested (``crop_box`` given) but the entry's crop is unknown or
  different → miss LOUDLY (``crop-unverifiable`` / ``crop-mismatch``)
  instead of serving wrongly-cropped pixels.

Legacy entries (registered before the sidecar existed, or written directly
into ``_cache``) adopt the current stat as their baseline on first
validated lookup — future replaces are still caught.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.image_processing.autocrop.debug import autocrop_debug
from shared.image_processing.autocrop.model import SkipReason, file_stat

_cache: dict[str, tuple[str, int, int]] = {}

#: Lookup status vocabulary for ``lookup_detail`` (grep-friendly).
STATUS_HIT = "hit"
STATUS_HIT_UNVALIDATED = "hit-unvalidated"
STATUS_MISS_ABSENT = "miss-absent"
STATUS_MISS_REPLACED_FILE = "miss-replaced-file"
STATUS_MISS_CROP_MISMATCH = "miss-crop-mismatch"
STATUS_MISS_CROP_UNVERIFIABLE = "miss-crop-unverifiable"

_UNSET: object = object()


@dataclass
class EntryMeta:
    """Validation sidecar for one ``_cache`` entry."""

    mtime_ns: int | None
    file_size: int | None
    # Crop box (left, top, right, bottom, in source pixels) the buffer was
    # saved with; ``crop_known=False`` means unknown (legacy/project entry
    # registered without crop info) — not the same as a known boxless save.
    crop_box: tuple[int, int, int, int] | None = None
    crop_known: bool = False


_meta: dict[str, EntryMeta] = {}


def _coerce_box(box) -> tuple[int, int, int, int] | None:
    if box is None:
        return None
    try:
        left, top, right, bottom = box
        return (int(left), int(top), int(right), int(bottom))
    except (TypeError, ValueError):
        return None


def register(
    media_path: str,
    cache_path: str,
    width: int,
    height: int,
    *,
    mtime_ns: int | None = None,
    file_size: int | None = None,
    crop_box=None,
    crop_known: bool = False,
) -> None:
    """Register an extracted buffer. Extra identity inputs are optional so
    existing 4-arg callers (project_io, PipelineCache helper) keep working;
    when mtime/size are omitted they are statted now (best effort)."""
    key = str(media_path)
    _cache[key] = (str(cache_path), int(width), int(height))
    if mtime_ns is None or file_size is None:
        current_mtime, current_size = file_stat(key)
        if mtime_ns is None:
            mtime_ns = current_mtime
        if file_size is None:
            file_size = current_size
    coerced = _coerce_box(crop_box)
    _meta[key] = EntryMeta(
        mtime_ns=mtime_ns,
        file_size=file_size,
        crop_box=coerced,
        crop_known=bool(crop_known) or coerced is not None,
    )


def lookup(
    media_path: str,
    *,
    mtime_ns: int | None = None,
    file_size: int | None = None,
    crop_box=_UNSET,
    validate_stat: bool = True,
) -> tuple[str, int, int] | None:
    """Validated lookup — same 3-tuple shape as before, or None on any miss.

    ``crop_box`` left at the ``_UNSET`` default means "no crop requested"
    (legacy/project callers): served as before. Passing an explicit box
    (including None = "I want boxless") requires the entry's recorded crop
    to match, else a loud miss. Stat validation evicts replaced-file
    entries instead of serving them.
    """
    detail = lookup_detail(
        media_path,
        mtime_ns=mtime_ns,
        file_size=file_size,
        crop_box=crop_box,
        validate_stat=validate_stat,
    )
    return detail.entry


@dataclass(frozen=True)
class LookupDetail:
    entry: tuple[str, int, int] | None
    status: str


def lookup_detail(
    media_path: str,
    *,
    mtime_ns: int | None = None,
    file_size: int | None = None,
    crop_box=_UNSET,
    validate_stat: bool = True,
) -> LookupDetail:
    key = str(media_path)
    entry = _cache.get(key)
    if entry is None:
        return LookupDetail(None, STATUS_MISS_ABSENT)
    if not validate_stat:
        return LookupDetail(entry, STATUS_HIT_UNVALIDATED)

    if mtime_ns is None or file_size is None:
        current_mtime, current_size = file_stat(key)
        if mtime_ns is None:
            mtime_ns = current_mtime
        if file_size is None:
            file_size = current_size

    meta = _meta.get(key)
    if meta is None:
        # Legacy entry (or direct _cache write): adopt the current stat as
        # baseline so future replaces are caught; crop unknown.
        if mtime_ns is not None or file_size is not None:
            _meta[key] = EntryMeta(mtime_ns=mtime_ns, file_size=file_size)
            meta = _meta[key]
        else:
            # Media file itself is stat-less (missing/rewritten member path):
            # cannot validate — serve as before, say so.
            return LookupDetail(entry, STATUS_HIT_UNVALIDATED)
    else:
        # Baseline exists: a stat change means the file was replaced.
        if (
            meta.mtime_ns is not None
            and mtime_ns is not None
            and (meta.mtime_ns, meta.file_size) != (mtime_ns, file_size)
        ) or (
            meta.mtime_ns is None
            and meta.file_size is not None
            and file_size is not None
            and meta.file_size != file_size
        ):
            _cache.pop(key, None)
            _meta.pop(key, None)
            autocrop_debug(
                "embedded verdict=SKIP reason=%s path=%s "
                "registered=(mtime=%s,size=%s) current=(mtime=%s,size=%s)",
                SkipReason.REPLACED_FILE,
                key, meta.mtime_ns, meta.file_size, mtime_ns, file_size,
            )
            return LookupDetail(None, STATUS_MISS_REPLACED_FILE)

    if crop_box is _UNSET:
        return LookupDetail(entry, STATUS_HIT)
    requested = _coerce_box(crop_box)
    meta = _meta.get(key)
    if meta is None:
        # Unstatable media with no baseline (returned unvalidated above is
        # the only such path) — without crop state, unverifiable.
        autocrop_debug(
            "embedded verdict=SKIP reason=crop-unverifiable path=%s "
            "requested_box=%s (no entry state at all)",
            key, requested,
        )
        return LookupDetail(None, STATUS_MISS_CROP_UNVERIFIABLE)
    if not meta.crop_known:
        autocrop_debug(
            "embedded verdict=SKIP reason=crop-unverifiable path=%s "
            "requested_box=%s (entry recorded no crop state)",
            key, requested,
        )
        return LookupDetail(None, STATUS_MISS_CROP_UNVERIFIABLE)
    if meta.crop_box != requested:
        autocrop_debug(
            "embedded verdict=SKIP reason=crop-mismatch path=%s "
            "recorded_box=%s requested_box=%s",
            key, meta.crop_box, requested,
        )
        return LookupDetail(None, STATUS_MISS_CROP_MISMATCH)
    return LookupDetail(entry, STATUS_HIT)


def entry_meta(media_path: str) -> EntryMeta | None:
    """Sidecar for tests/diagnostics (None when no validated entry)."""
    return _meta.get(str(media_path))


def clear() -> None:
    _cache.clear()
    _meta.clear()


def pop(media_path: str) -> None:
    _cache.pop(str(media_path), None)
    _meta.pop(str(media_path), None)
