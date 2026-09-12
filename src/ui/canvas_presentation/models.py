from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PIL import Image
from shared.rendering import VirtualCanvasLayout

@dataclass(slots=True, frozen=True)
class CanvasTarget:
    width: int
    height: int
    fit_mode: Literal["contain", "stretch"] = "contain"
    fill_rgba: tuple[int, int, int, int] = (0, 0, 0, 0)

@dataclass(slots=True, frozen=True)
class CanvasContentLayout:
    canvas_width: int
    canvas_height: int
    content_x: int
    content_y: int
    content_width: int
    content_height: int

    @property
    def content_rect(self) -> tuple[int, int, int, int]:
        return (
            self.content_x,
            self.content_y,
            self.content_width,
            self.content_height,
        )

@dataclass(slots=True)
class PresentationImageSet:
    display_image1: Image.Image | None
    display_image2: Image.Image | None
    source_image1: Image.Image | None
    source_image2: Image.Image | None
    source_key: tuple
    display_cache_key: tuple | None = None

@dataclass(slots=True)
class SnapshotStorePresentation:
    store: object
    images: PresentationImageSet
    fit_content: bool = False
    fill_rgba: tuple[int, int, int, int] = (0, 0, 0, 0)
    virtual_layout: VirtualCanvasLayout | None = None

    @property
    def display_image1(self) -> Image.Image | None:
        return self.images.display_image1

    @property
    def display_image2(self) -> Image.Image | None:
        return self.images.display_image2

    @property
    def source_image1(self) -> Image.Image | None:
        return self.images.source_image1

    @property
    def source_image2(self) -> Image.Image | None:
        return self.images.source_image2

    @property
    def source_key(self) -> tuple:
        return self.images.source_key

    @property
    def display_cache_key(self) -> tuple | None:
        return self.images.display_cache_key

@dataclass(slots=True)
class RenderFramePresentation:
    store: object
    images: PresentationImageSet
    target: CanvasTarget
    layout: CanvasContentLayout
    render_width: int
    render_height: int
    image_dest_x: int
    image_dest_y: int
    scaled_image1: Image.Image
    scaled_image2: Image.Image
    virtual_layout: VirtualCanvasLayout | None = None

    @property
    def display_image1(self) -> Image.Image:
        return self.images.display_image1

    @property
    def display_image2(self) -> Image.Image:
        return self.images.display_image2

    @property
    def source_image1(self) -> Image.Image:
        return self.images.source_image1

    @property
    def source_image2(self) -> Image.Image:
        return self.images.source_image2

    @property
    def source_key(self) -> tuple:
        return self.images.source_key
