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
    if tag is None:
        tag = next(_counter)
        try:
            setattr(image, _UID_INFO_KEY, tag)
        except (AttributeError, TypeError):
            pass
    if tag is not None:
        return tag
    if hasattr(image, "cacheKey"):
        return image.cacheKey()
    return id(image)
