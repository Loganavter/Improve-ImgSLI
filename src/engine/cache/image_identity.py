from __future__ import annotations

"""Stable per-object content identity for image payloads.

``image_uid`` tags each payload object with a process-unique counter so
caches can key on content without hashing pixels on every frame. Two
correctness rules:

- Tags are invalidated when the payload's shape fingerprint (size, mode,
  dtype) changes: an in-place resize/replace must never keep serving the
  old content (stale-counter false hit).
- Objects that reject tag attachment (numpy arrays, some Qt types) get a
  **fresh counter on every call** -- a guaranteed cache miss, never a hit.
  The old ``id()`` fallback was an address that CPython reuses after GC,
  so a freed array's id could collide with a live unrelated object and
  serve wrong cached content. A miss only costs a re-decode; a false hit
  corrupts the frame.

QImage payloads bypass the counter via ``cacheKey()``, which Qt already
bumps on detach/mutation (content-sensitive by construction).
"""

import itertools

_counter = itertools.count(1)
_UID_INFO_KEY = "_imgsli_uid"


def _fingerprint(image):
    """Shape signals that change when the payload is replaced in place.

    Returns a hashable tuple, or ``None`` when the object exposes no
    shape at all (then the tag is used as-is).
    """
    try:
        shape = getattr(image, "shape", None)
        if shape is not None:
            dtype = str(getattr(image, "dtype", ""))
            return ("shape", tuple(int(v) for v in shape), dtype)
        size = getattr(image, "size", None)
        if size is not None:
            if callable(size):
                size = size()
            mode = getattr(image, "mode", None)
            if callable(mode):
                mode = mode()
            fmt = getattr(image, "format", None)
            if callable(fmt) or not isinstance(fmt, int):
                fmt = None
            return ("size", tuple(int(v) for v in tuple(size)), str(mode), fmt)
    except Exception:
        pass
    return None


def _fresh_tag() -> int:
    return next(_counter)


def _checked_tag(stored, fingerprint):
    """Returns the stored tag if its fingerprint still matches, else None.

    Legacy plain-int tags (written before fingerprints existed) carry no
    fingerprint: they match only a ``None`` fingerprint, otherwise they
    are retagged once and from then on carry one.

    A ``None`` fingerprint against a fingerprinted tag means the shape is
    currently unreadable (e.g. a closed TiledPixelStore whose ``size``
    raises) — that is no evidence of a content change, so the tag is kept.
    Retagging there would break identity-keyed sweeps that run exactly
    after close (pyramid_registry).
    """
    if isinstance(stored, list | tuple) and len(stored) == 2:
        tag, saved = stored
        if fingerprint is None or saved == fingerprint:
            return int(tag)
        return None
    if fingerprint is None and isinstance(stored, int):
        return stored
    return None


def _wrap_tag(tag: int, fingerprint):
    if fingerprint is None:
        return tag
    return [tag, fingerprint]


def image_uid(image) -> int:
    if image is None:
        return 0
    fingerprint = _fingerprint(image)
    if hasattr(image, "info"):
        try:
            info = image.info
        except Exception:
            info = None
        if isinstance(info, dict):
            stored = info.get(_UID_INFO_KEY)
            tag = _checked_tag(stored, fingerprint)
            if tag is None:
                tag = _fresh_tag()
                try:
                    info[_UID_INFO_KEY] = _wrap_tag(tag, fingerprint)
                except Exception:
                    pass
            return tag
        # `.info` exists but is not a plain dict (exotic image type):
        # fall through to the generic paths below.

    tag = getattr(image, _UID_INFO_KEY, None)
    if isinstance(tag, list | tuple):
        checked = _checked_tag(tag, fingerprint)
        if checked is not None:
            return checked
    elif isinstance(tag, int):
        if fingerprint is None:
            return tag
    # Try to attach a stable counter-based tag.
    try:
        tag = _fresh_tag()
        setattr(image, _UID_INFO_KEY, _wrap_tag(tag, fingerprint))
        return tag
    except (AttributeError, TypeError):
        pass
    # Object rejects setattr (numpy ndarray, some Qt types). Fall back to
    # a stable per-identity value instead of churning a fresh counter on
    # every call (pure cache miss otherwise).
    if hasattr(image, "cacheKey"):
        try:
            return int(image.cacheKey())
        except Exception:
            pass
    # GC-safe miss: a fresh counter can never collide with a live tag,
    # while id() can be reused by an unrelated object after this one dies.
    return _fresh_tag()
