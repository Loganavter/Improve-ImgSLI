from .bounds import compute_magnifier_padding, compute_magnifier_union_bbox
from .mode import MagnifierModeService
from .store import (
    DEFAULT_MAGNIFIER_ID,
    MagnifierStoreService,
    active_magnifier_id,
    add_magnifier_model,
    default_capture_size,
    default_magnifier_size,
    iter_magnifier_models,
    magnifier_enabled,
    remove_magnifier_model,
    set_active_magnifier_id,
    set_default_capture_size,
    set_default_magnifier_size,
    set_magnifier_enabled_flag,
    update_magnifier_model,
)

__all__ = [
    "DEFAULT_MAGNIFIER_ID",
    "MagnifierModeService",
    "MagnifierStoreService",
    "active_magnifier_id",
    "add_magnifier_model",
    "compute_magnifier_padding",
    "compute_magnifier_union_bbox",
    "default_capture_size",
    "default_magnifier_size",
    "iter_magnifier_models",
    "magnifier_enabled",
    "remove_magnifier_model",
    "set_active_magnifier_id",
    "set_default_capture_size",
    "set_default_magnifier_size",
    "set_magnifier_enabled_flag",
    "update_magnifier_model",
]
