"""Shared pixel-cache loader — single source for B10 snippet ×4.

Four call sites duplicated the same ``lookup → from_embedded_cache/from_path``
branch. This helper centralizes it so the registry check and the store
creation live in one place.
"""

from __future__ import annotations

from pathlib import Path


def load_pixel_store(
    path: str | Path, *, crop_service=None, auto_crop: bool | None = None
):
    """Return a ``TiledPixelStore`` for *path*, using embedded cache if present.

    Mirrors the previously duplicated snippet, теперь с DI CropService вместо bool.
    crop_service — предпочтительно; auto_crop — deprecated для совместимости.
    """
    from shared.image_processing import pixel_cache_registry
    from shared.image_processing.autocrop.debug import autocrop_debug
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    # Нормализация deprecated auto_crop → crop_service
    if crop_service is None and auto_crop is not None:
        if isinstance(auto_crop, bool) and auto_crop:
            try:
                from shared.image_processing.autocrop import CropService

                crop_service = CropService()
            except Exception:
                crop_service = None
        elif auto_crop is not None and not isinstance(auto_crop, bool):
            crop_service = auto_crop
        elif auto_crop is False:
            crop_service = None
    # Старые вызовы load_pixel_store(path, auto_crop=True) без сервиса — создаём ephemeral
    # сервис только если явно передали auto_crop=True, иначе оставляем как есть
    # (для DI вызывающий должен передать свой сервис)

    key = str(path)
    cached = pixel_cache_registry.lookup(key)
    if cached is not None:
        cache_path, width, height = cached
        autocrop_debug(
            "cache-hit path=%s -> from_embedded_cache %dx%d (crop_service=%s NOT applied)",
            key, width, height, bool(crop_service),
        )
        return TiledPixelStore.from_embedded_cache(cache_path, width, height)
    autocrop_debug("from_path path=%s crop_service=%s", key, bool(crop_service))
    # Пробуем новый путь, fallback на legacy сигнатуру
    try:
        return TiledPixelStore.from_path(key, crop_service=crop_service)
    except TypeError:
        # Fallback для очень старых моков
        if crop_service is not None:
            return TiledPixelStore.from_path(key, auto_crop=True)
        return TiledPixelStore.from_path(key)
