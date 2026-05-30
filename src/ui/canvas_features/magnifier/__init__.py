from __future__ import annotations

_BOUNDS_EXPORTS = {
    "compute_magnifier_layout_requirement",
    "compute_magnifier_union_bbox",
}
_MODE_EXPORTS = {"MagnifierModeService"}
_STORE_EXPORTS = {
    "DEFAULT_MAGNIFIER_ID",
    "MagnifierStoreService",
    "active_magnifier_id",
    "add_magnifier_model",
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
}

__all__ = sorted(_BOUNDS_EXPORTS | _MODE_EXPORTS | _STORE_EXPORTS)

def __getattr__(name: str):
    if name in _BOUNDS_EXPORTS:
        from . import bounds

        return getattr(bounds, name)
    if name in _MODE_EXPORTS:
        from . import mode

        return getattr(mode, name)
    if name in _STORE_EXPORTS:
        from . import store

        return getattr(store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
