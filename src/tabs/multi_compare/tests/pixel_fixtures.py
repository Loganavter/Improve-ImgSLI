"""Shared test helpers for multi-compare pixel storage."""

from __future__ import annotations

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore


def slot_image(width: int, height: int, *, color=(0, 0, 0, 255)) -> TiledPixelStore:
    return TiledPixelStore.from_pil(Image.new("RGBA", (width, height), color))
