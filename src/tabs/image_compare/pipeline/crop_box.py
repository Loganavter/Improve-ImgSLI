"""Effective crop box for image_compare (non-destructive crop, W1+W2).

Decode tiers (``PipelineCache`` pixel/preview, ``TiledPixelStore``) are
FULL-FRAME: crop is never baked at alloc. The detected box is side
metadata, queried through :func:`effective_crop_box_for_path` — the
session ``CropService`` stays attached for DETECTION ONLY (it is never
passed to ``load_pixel_store`` / ``load_preview_image`` / ``put_pixel`` /
``put_preview``; cache keys are the boxless ``(path, mtime, size, False)``
shape, see ``pipeline/cache._pixel_key``).

Callers must pass the session service (``controller._get_crop_service()`` —
``None`` when ``auto_crop_black_borders`` is OFF) and must not call this on
the GUI thread unless the box is already warmed (``schedule_crop_warmup`` /
worker-side ``svc.get``): the first ``CropService.get`` does IO.
"""

from __future__ import annotations

from typing import Any

from shared.image_processing.autocrop.model import CropBox


def effective_crop_box_for_path(
    path: str,
    *,
    crop_service: Any | None = None,
    override: bool | None = None,
) -> CropBox | None:
    """Detected box for *path* in full-source coords, or ``None``.

    * ``override is False`` (per-image Off) → ``None`` without touching
      detection (skips ``CropService.get`` entirely).
    * Otherwise (``None`` == Auto, ``True`` == On) → detection as today:
      ``crop_service=None`` (crop disabled) → ``None``, else delegates to
      ``crop_service.get(path)`` (detection only, never bakes). On with no
      detected box yields ``None`` naturally. Any failure → ``None``.
    """
    if override is False:
        return None
    if crop_service is None or isinstance(crop_service, bool):
        return None
    get = getattr(crop_service, "get", None)
    if not callable(get):
        return None
    try:
        return get(str(path))
    except Exception:
        return None
