from __future__ import annotations

import itertools

_counter = itertools.count(1)
_UID_INFO_KEY = "_imgsli_uid"


def image_uid(image) -> int:
    """Stable per-image identity tag for use in cache/staleness keys.

    ``id()`` is unsafe for this: CPython reuses a freed object's memory
    address for the next allocation of the same size class, so a
    short-lived PIL Image (e.g. one produced by an async unification
    worker) can get the exact ``id()`` of an already-superseded image.
    A cache key built on that ``id()`` then reports a false "unchanged"
    match, and dependents (e.g. the RHI texture upload skip in
    ``plan_applicator._textures_are_current``) silently keep stale data.

    PIL's ``Image._new()`` (used internally by ``convert``/``resize``/
    ``crop``/``copy``/...) copies ``self.info`` into the derived image,
    so a tag stored in ``.info`` here follows an image through those
    derivations -- correctly identifying "same underlying image data"
    across transforms. A genuinely new image (``Image.open``,
    ``Image.new``) starts with an empty ``.info`` dict and gets a fresh
    tag on first use here, so it can never collide with a since-freed
    object's stale tag.
    """
    if image is None:
        return 0
    info = image.info
    tag = info.get(_UID_INFO_KEY)
    if tag is None:
        tag = next(_counter)
        info[_UID_INFO_KEY] = tag
    return tag
