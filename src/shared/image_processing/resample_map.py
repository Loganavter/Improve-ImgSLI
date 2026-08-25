"""Shared PIL resample map — single source for ``_RESAMPLE`` (B12).

All consumers previously duplicated the same 5-entry mapping. Import via
``from shared.image_processing.resample_map import RESAMPLE_MAP, get_resample``.
"""

from __future__ import annotations

from PIL import Image

RESAMPLE_MAP: dict[str, Image.Resampling] = {
    "NEAREST": Image.Resampling.NEAREST,
    "BILINEAR": Image.Resampling.BILINEAR,
    "BICUBIC": Image.Resampling.BICUBIC,
    "LANCZOS": Image.Resampling.LANCZOS,
    "EWA_LANCZOS": Image.Resampling.LANCZOS,
}


def get_resample(method_name: str | None) -> Image.Resampling:
    """Resolve *method_name* (case-insensitive) to a PIL resample."""
    key = str(method_name or "LANCZOS").upper()
    return RESAMPLE_MAP.get(key, Image.Resampling.LANCZOS)
