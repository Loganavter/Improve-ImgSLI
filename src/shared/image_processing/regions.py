from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image

@dataclass(frozen=True)
class ImageRegion:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

@dataclass(frozen=True)
class UniformTileGrid:
    total_width: int
    total_height: int
    tile_width: int
    tile_height: int
    columns: int
    rows: int

    @property
    def padded_width(self) -> int:
        return self.tile_width * self.columns

    @property
    def padded_height(self) -> int:
        return self.tile_height * self.rows

    def iter_regions(self):
        for row in range(self.rows):
            for col in range(self.columns):
                left = col * self.tile_width
                top = row * self.tile_height
                yield row, col, ImageRegion(
                    left=left,
                    top=top,
                    width=min(self.tile_width, self.padded_width - left),
                    height=min(self.tile_height, self.padded_height - top),
                )

def build_uniform_tile_grid(
    total_width: int,
    total_height: int,
    *,
    max_tile_width: int,
    max_tile_height: int | None = None,
    min_tiles_per_axis: int = 1,
) -> UniformTileGrid:
    safe_total_width = max(1, int(total_width))
    safe_total_height = max(1, int(total_height))
    safe_max_tile_width = max(1, int(max_tile_width))
    safe_max_tile_height = max(
        1,
        int(max_tile_height if max_tile_height is not None else max_tile_width),
    )
    safe_min_tiles = max(1, int(min_tiles_per_axis))

    columns = max(
        safe_min_tiles,
        int(math.ceil(safe_total_width / float(safe_max_tile_width))),
    )
    rows = max(
        safe_min_tiles,
        int(math.ceil(safe_total_height / float(safe_max_tile_height))),
    )

    tile_width = int(math.ceil(safe_total_width / float(columns)))
    tile_height = int(math.ceil(safe_total_height / float(rows)))

    return UniformTileGrid(
        total_width=safe_total_width,
        total_height=safe_total_height,
        tile_width=tile_width,
        tile_height=tile_height,
        columns=columns,
        rows=rows,
    )

def build_square_tile_grid(
    total_width: int,
    total_height: int,
    *,
    max_tile_extent: int,
    min_tiles_per_axis: int = 1,
) -> UniformTileGrid:
    safe_total_width = max(1, int(total_width))
    safe_total_height = max(1, int(total_height))
    safe_max_extent = max(1, int(max_tile_extent))
    safe_min_tiles = max(1, int(min_tiles_per_axis))

    divisions = max(
        safe_min_tiles,
        int(
            math.ceil(
                max(safe_total_width, safe_total_height) / float(safe_max_extent)
            )
        ),
    )
    tile_width = int(math.ceil(safe_total_width / float(divisions)))
    tile_height = int(math.ceil(safe_total_height / float(divisions)))

    return UniformTileGrid(
        total_width=safe_total_width,
        total_height=safe_total_height,
        tile_width=tile_width,
        tile_height=tile_height,
        columns=divisions,
        rows=divisions,
    )

def pad_image_to_size(
    image: Image.Image,
    width: int,
    height: int,
    *,
    fill: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Image.Image:
    target_width = max(1, int(width))
    target_height = max(1, int(height))
    if image.width == target_width and image.height == target_height:
        return image

    result = Image.new("RGBA", (target_width, target_height), fill)
    result.paste(image, (0, 0))
    return result

def compute_centered_box(
    *,
    width: int,
    height: int,
    center_x: float,
    center_y: float,
    box_width: float,
    box_height: float | None = None,
) -> tuple[float, float, float, float]:
    safe_width = max(1.0, float(width))
    safe_height = max(1.0, float(height))
    target_box_width = max(1.0, min(float(box_width), safe_width))
    target_box_height = max(
        1.0,
        min(
            float(box_height if box_height is not None else box_width),
            safe_height,
        ),
    )

    half_w = target_box_width / 2.0
    half_h = target_box_height / 2.0

    left = min(max(0.0, float(center_x) - half_w), max(0.0, safe_width - target_box_width))
    top = min(max(0.0, float(center_y) - half_h), max(0.0, safe_height - target_box_height))
    right = left + target_box_width
    bottom = top + target_box_height

    return (left, top, right, bottom)
