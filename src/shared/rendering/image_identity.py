from __future__ import annotations

import itertools

_counter = itertools.count(1)
_UID_INFO_KEY = "_imgsli_uid"


def image_uid(image) -> int:
    if image is None:
        return 0
    if hasattr(image, "info"):
        info = image.info
        tag = info.get(_UID_INFO_KEY)
        if tag is None:
            tag = next(_counter)
            info[_UID_INFO_KEY] = tag
        return tag

    tag = getattr(image, _UID_INFO_KEY, None)
    if tag is not None:
        return tag
    # Try to attach a stable counter-based tag.
    try:
        tag = next(_counter)
        setattr(image, _UID_INFO_KEY, tag)
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
    return id(image)
