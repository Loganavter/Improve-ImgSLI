"""Shared image dimension helper — single source for ``_img_dims`` (B6).

Four copies inside ``tabs.image_compare`` (plan_applicator, render_config,
texture_parts/base_images, interaction) used the same duck-typing probe over
PIL/QImage/TiledPixelStore. This module is the canonical implementation.

Import via ``from shared.image_processing.image_dims import get_image_dims``.
"""

from __future__ import annotations


def get_image_dims(img) -> tuple[int, int]:
    """Return ``(width, height)`` for PIL/QImage/TiledPixelStore duck types.

    Resolution order mirrors the original quartet:
    1. ``img.width()`` / ``img.height()`` if callable
    2. ``img.size`` as tuple/list ``(w, h)``
    3. ``img.size()`` as QRect-like with ``.width()/.height()``
    4. ``img.width`` / ``img.height`` attributes (fallback 0)
    """
    if img is None:
        return (0, 0)
    w, h = 0, 0
    # width
    if hasattr(img, "width") and callable(getattr(img, "width")):
        try:
            w = int(img.width())  # type: ignore[operator]
        except Exception:
            w = 0
    elif hasattr(img, "size") and isinstance(getattr(img, "size"), (tuple, list)):
        try:
            w = int(img.size[0])  # type: ignore[index]
        except Exception:
            w = 0
    elif hasattr(img, "size") and callable(getattr(img, "size")):
        try:
            w = int(img.size().width())  # type: ignore[operator]
        except Exception:
            w = 0
    else:
        try:
            w = int(getattr(img, "width", 0))
        except Exception:
            w = 0
    # height
    if hasattr(img, "height") and callable(getattr(img, "height")):
        try:
            h = int(img.height())  # type: ignore[operator]
        except Exception:
            h = 0
    elif hasattr(img, "size") and isinstance(getattr(img, "size"), (tuple, list)):
        try:
            h = int(img.size[1])  # type: ignore[index]
        except Exception:
            h = 0
    elif hasattr(img, "size") and callable(getattr(img, "size")):
        try:
            h = int(img.size().height())  # type: ignore[operator]
        except Exception:
            h = 0
    else:
        try:
            h = int(getattr(img, "height", 0))
        except Exception:
            h = 0
    return w, h
