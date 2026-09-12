"""Shared pixel-cache loader — single source for B10 snippet ×4.

Four call sites duplicated the same ``lookup → from_embedded_cache/from_path``
branch. This helper centralizes it so the registry check and the store
creation live in one place.
"""

from __future__ import annotations

from pathlib import Path


def load_pixel_store(
    path: str | Path,
    *,
    crop_service=None,
    auto_crop: bool | None = None,
    embedded_cache=None,
):
    """Return a ``TiledPixelStore`` for *path*, using embedded cache if present.

    Mirrors the previously duplicated snippet, теперь с DI CropService вместо bool.
    crop_service — предпочтительно; auto_crop — deprecated для совместимости.
    ``embedded_cache`` — DI для embedded tier (PipelineCache instance или
    объект с ``lookup`` / mapping). Если ``None`` — используется host-owned
    ``shared.image_processing.embedded_pixel_cache`` (без импорта ``tabs``).
    """
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
    # DI: если передан PipelineCache / registry instance — используем его
    cached = None
    if embedded_cache is not None:
        try:
            if hasattr(embedded_cache, "lookup"):
                cached = embedded_cache.lookup(key)  # type: ignore
            elif hasattr(embedded_cache, "lookup_embedded_cache"):
                cached = embedded_cache.lookup_embedded_cache(key)  # type: ignore
            elif hasattr(embedded_cache, "get"):
                cached = embedded_cache.get(key)  # type: ignore
            elif isinstance(embedded_cache, dict):
                cached = embedded_cache.get(key)
            # also handle PipelineCache module-level helper via instance? fallback
            if cached is None and hasattr(embedded_cache, "_embedded_cache"):
                try:
                    cached = embedded_cache._embedded_cache.get(key)  # type: ignore
                except Exception:
                    pass
        except Exception:
            cached = None
        # try normalized variant if injected
        if cached is None:
            try:
                import os as _os

                norm = _os.path.normpath(key)
                if norm != key:
                    if hasattr(embedded_cache, "lookup"):
                        cached = embedded_cache.lookup(norm)  # type: ignore
                    elif hasattr(embedded_cache, "lookup_embedded_cache"):
                        cached = embedded_cache.lookup_embedded_cache(norm)  # type: ignore
            except Exception:
                pass
    if cached is None:
        from shared.image_processing import embedded_pixel_cache as _emb

        cached = _emb.lookup(key)
        if cached is None:
            try:
                import os as _os2

                norm2 = _os2.path.normpath(key)
                if norm2 != key:
                    cached = _emb.lookup(norm2)
            except Exception:
                pass
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
