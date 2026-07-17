"""PixelSource protocol — full-res tier contract for tile-addressable images."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PIL import Image


@runtime_checkable
class PixelSource(Protocol):
    """Minimal read-only pixel surface shared by ``TiledPixelStore`` and PIL."""

    mode: str

    @property
    def size(self) -> tuple[int, int]:
        ...

    @property
    def width(self) -> int:
        ...

    @property
    def height(self) -> int:
        ...

    def crop(self, box: tuple[int, int, int, int]) -> Image.Image:
        ...

    def read_tile(self, row: int, col: int) -> Image.Image:
        ...
