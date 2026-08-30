"""Autocrop package — явные типы, DI-сервис, без глобала.

Публичный API:
  from shared.image_processing.autocrop import CropBox, CropResult, CropConfig, CropService
  from shared.image_processing.autocrop.scaling import get_scaled_box_for_thumb
  from shared.image_processing.autocrop.debug import autocrop_debug
"""
from .debug import autocrop_debug
from .model import CropBox, CropConfig, CropResult
from .scaling import get_scaled_box_for_thumb
from .service import CropService, invalidate_all_services

__all__ = [
    "CropBox",
    "CropConfig",
    "CropResult",
    "CropService",
    "get_scaled_box_for_thumb",
    "autocrop_debug",
    "invalidate_all_services",
]
