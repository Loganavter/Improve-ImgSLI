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
    from shared.image_processing.embedded_pixel_cache import _UNSET
    from engine.store.tiled_pixel_store import TiledPixelStore

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

        # Validated host lookup: stat-checked (replaced-file evicts loudly)
        # and, when a crop_service is in play, crop-checked (the buffer's
        # recorded crop must equal the currently-computed box, else the hit
        # would serve wrongly-cropped pixels). No crop requested → legacy
        # serve-as-saved behavior.
        _requested_box = _UNSET
        if crop_service is not None:
            try:
                _live_box = crop_service.get(key)
                _requested_box = (
                    _live_box.to_tuple() if _live_box is not None else None
                )
            except Exception:
                _requested_box = _UNSET
                autocrop_debug(
                    "embedded verdict=SKIP reason=%s path=%s "
                    "(crop probe failed; serving as-saved)",
                    "crop-probe-failed", key,
                )
        detail = _emb.lookup_detail(key, crop_box=_requested_box)
        cached = detail.entry
        if detail.status and detail.status.startswith("miss"):
            autocrop_debug(
                "embedded verdict=MISS status=%s path=%s crop_service=%s",
                detail.status, key, bool(crop_service),
            )
            if detail.status == _emb.STATUS_MISS_REPLACED_FILE and crop_service is not None:
                # The file changed under a cached crop verdict: drop the
                # crop service's stale entry (sticky-None fix at the shared
                # entry point) so the from_path decode below recomputes
                # instead of serving the old file's verdict.
                try:
                    crop_service.invalidate(key)
                except Exception:
                    pass
        if cached is None:
            try:
                import os as _os2

                norm2 = _os2.path.normpath(key)
                if norm2 != key:
                    detail2 = _emb.lookup_detail(norm2, crop_box=_requested_box)
                    cached = detail2.entry
                    if detail2.status and detail2.status.startswith("miss"):
                        autocrop_debug(
                            "embedded verdict=MISS status=%s path=%s crop_service=%s",
                            detail2.status, norm2, bool(crop_service),
                        )
            except Exception:
                pass
    if cached is not None:
        cache_path, width, height = cached
        if crop_service is not None:
            autocrop_debug(
                "embedded verdict=HIT path=%s -> from_embedded_cache %dx%d "
                "(recorded crop == current box)",
                key, width, height,
            )
        else:
            autocrop_debug(
                "cache-hit path=%s -> from_embedded_cache %dx%d (crop_service=%s NOT applied)",
                key, width, height, bool(crop_service),
            )
        return TiledPixelStore.from_embedded_cache(cache_path, width, height)
    autocrop_debug("from_path path=%s crop_service=%s", key, bool(crop_service))
    # Shared spill registry (plan_shared_pixel_registry, wave 2, decision
    # A-box): one decoded spill per identical file across tabs. The
    # fingerprint is the resolved crop box (or None) — never the service
    # identity — so identical boxes share even across service instances. A
    # failed probe is *unknown*, not "no crop": bypass the registry entirely
    # (fail-open, today's behavior) instead of risking a wrong share.
    _crop_fp = None
    _registry_ok = True
    if crop_service is not None:
        try:
            _box = crop_service.get(key)
            _crop_fp = _box.to_tuple() if _box is not None else None
        except Exception:
            _registry_ok = False
    _expected_stat = None
    if _registry_ok:
        try:
            from engine.store import shared_pixel_registry as _spr

            handle = _spr.acquire(key, crop_fingerprint=_crop_fp)
            if handle is not None:
                autocrop_debug(
                    "shared-pixel HIT path=%s crop_fp=%s", key, _crop_fp,
                )
                return handle.store
            try:
                import os as _os3

                _st = _os3.stat(key)
                _expected_stat = (int(_st.st_mtime_ns), int(_st.st_size))
            except OSError:
                _expected_stat = None
        except Exception:
            _registry_ok = False
            _expected_stat = None
    # Пробуем новый путь, fallback на legacy сигнатуру
    try:
        store = TiledPixelStore.from_path(key, crop_service=crop_service)
    except TypeError:
        # Fallback для очень старых моков
        if crop_service is not None:
            store = TiledPixelStore.from_path(key, auto_crop=True)
        else:
            store = TiledPixelStore.from_path(key)
    except Exception as exc:
        autocrop_debug(
            "load verdict=SKIP reason=%s path=%s error=%s",
            "undecodable", key, exc,
        )
        raise
    if _registry_ok:
        try:
            from engine.store import shared_pixel_registry as _spr2

            published = _spr2.publish(
                key, store,
                crop_fingerprint=_crop_fp, expected=_expected_stat,
            )
            if published is not None:
                # Registry owns the decoded base now; serve the shared view.
                autocrop_debug(
                    "shared-pixel PUBLISH path=%s crop_fp=%s", key, _crop_fp,
                )
                store = published.store
        except Exception:
            pass
    if crop_service is not None:
        try:
            _box_now = crop_service.get(key)
        except Exception:
            _box_now = "undecodable"
        if _box_now == "undecodable":
            autocrop_debug(
                "load verdict=SKIP reason=%s path=%s", "undecodable", key,
            )
        elif _box_now is None:
            autocrop_debug(
                "load verdict=SKIP reason=%s path=%s", "borderless", key,
            )
        else:
            autocrop_debug(
                "load verdict=APPLIED box=%s path=%s",
                _box_now.to_tuple(), key,
            )
    return store
