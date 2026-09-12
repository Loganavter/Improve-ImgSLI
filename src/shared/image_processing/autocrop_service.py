"""Deprecated shim — сохранён для обратной совместимости.

Новый источник истины: shared.image_processing.autocrop.CropService (DI, без
глобала). Этот модуль оставлен как тонкий прокси чтобы старые импорты
``from shared.image_processing.autocrop_service import get_crop_box`` не ломались,
но больше не владеет глобальным кэшем.

Audit-Meta: pattern=collaborator reason="deprecated shim over autocrop.CropService — no state, delegates to DI service"
"""
from __future__ import annotations

import os
import warnings

from shared.image_processing.autocrop.scaling import get_scaled_box_for_thumb as _new_scaled

# Ленивый дефолтный сервис для shim-вызовов без DI (deprecated путь)
_default_service = None


def _get_default_service():
    global _default_service
    if _default_service is None:
        try:
            from shared.image_processing.autocrop import CropService

            _default_service = CropService()
        except Exception:
            return None
    return _default_service


def get_crop_box(path_str: str) -> tuple[int, int, int, int] | None:
    """Deprecated — используйте CropService.get()."""
    warnings.warn("autocrop_service.get_crop_box is deprecated, use CropService.get()", DeprecationWarning, stacklevel=2)
    svc = _get_default_service()
    if svc is None:
        return None
    box = svc.get(path_str)
    return box.to_tuple() if box is not None else None


def get_scaled_box_for_thumb(
    orig_box: tuple[int, int, int, int] | None,
    orig_size: tuple[int, int],
    thumb_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    """Deprecated — используйте autocrop.scaling.get_scaled_box_for_thumb."""
    box = _new_scaled(orig_box, orig_size, thumb_size)
    return box.to_tuple() if box is not None else None


def invalidate(path: str | None = None) -> None:
    """Deprecated — инвалидирует все живые CropService.

    Legacy ``_crop_box_cache`` в ``tiled_pixel_store`` — пустой алиас (единый
    ключ ``PipelineCache._pixel_key``), не очищается отдельно.
    """
    try:
        from shared.image_processing.autocrop import invalidate_all_services

        if path is None:
            invalidate_all_services()
        else:
            from shared.image_processing.autocrop.service import _live_services

            for svc in list(_live_services):
                try:
                    svc.invalidate(path)
                except Exception:
                    pass
    except Exception:
        pass


def invalidate_all() -> None:
    invalidate(None)
