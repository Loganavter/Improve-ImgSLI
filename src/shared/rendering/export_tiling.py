"""Shared export framebuffer tiling helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from PIL import Image
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from shared.image_processing.regions import build_uniform_tile_grid
from shared.rendering.offscreen_canvas import (
    configure_offscreen_widget,
    render_widget_frame,
    resize_offscreen_widget,
    show_offscreen_widget,
)

DEFAULT_EXPORT_TILE_MAX_EXTENT = 4096


def iter_export_tile_rects(
    canvas_width: int, canvas_height: int, max_extent: int
) -> Iterator[tuple[int, int, int, int]]:
    """Yield ``(left, top, width, height)`` tile rects covering the export canvas."""
    grid = build_uniform_tile_grid(
        canvas_width, canvas_height, max_tile_width=max_extent
    )
    for row in range(grid.rows):
        top = row * grid.tile_height
        if top >= canvas_height:
            continue
        height = min(grid.tile_height, canvas_height - top)
        for col in range(grid.columns):
            left = col * grid.tile_width
            if left >= canvas_width:
                continue
            width = min(grid.tile_width, canvas_width - left)
            yield left, top, width, height


def qimage_to_pil_rgba(qimg: QImage) -> Image.Image:
    qimg_rgba = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes(
        "RGBA",
        (qimg_rgba.width(), qimg_rgba.height()),
        bytes(qimg_rgba.constBits()),
    )


class TiledFramebufferExporter:
    """Render a large canvas by tiling the offscreen widget framebuffer."""

    def __init__(
        self,
        widget: QWidget,
        *,
        set_export_viewport: Callable[[tuple[int, int, int, int] | None], None],
        prepare_frame: Callable[[], None],
        query_max_texture_size: Callable[[], int],
    ):
        self._widget = widget
        self._set_export_viewport = set_export_viewport
        self._prepare_frame = prepare_frame
        self._query_max_texture_size = query_max_texture_size
        self._last_size: tuple[int, int] | None = None

    def render_rgba(
        self,
        canvas_w: int,
        canvas_h: int,
        *,
        max_extent: int = DEFAULT_EXPORT_TILE_MAX_EXTENT,
    ) -> Image.Image:
        tile_extent = min(max_extent, self._query_max_texture_size())
        if canvas_w <= tile_extent and canvas_h <= tile_extent:
            return self._render_single(canvas_w, canvas_h)

        final_image = Image.new("RGBA", (canvas_w, canvas_h))
        for tile_left, tile_top, tile_w, tile_h in iter_export_tile_rects(
            canvas_w, canvas_h, tile_extent
        ):
            tile_image = self._render_tile(canvas_w, canvas_h, tile_left, tile_top, tile_w, tile_h)
            final_image.paste(tile_image, (tile_left, tile_top))
        self._set_export_viewport(None)
        return final_image

    def _render_single(self, canvas_w: int, canvas_h: int) -> Image.Image:
        self._set_export_viewport(None)
        target = (canvas_w, canvas_h)
        if self._last_size != target:
            resize_offscreen_widget(self._widget, target)
            show_offscreen_widget(self._widget)
            self._last_size = target
        self._prepare_frame()
        render_widget_frame(self._widget)
        render_widget_frame(self._widget)
        qimg = self._widget.grabFramebuffer()
        image = qimage_to_pil_rgba(qimg)
        if image.size != target:
            image = image.resize(target, Image.Resampling.BILINEAR)
        return image

    def _render_tile(
        self,
        canvas_w: int,
        canvas_h: int,
        tile_left: int,
        tile_top: int,
        tile_w: int,
        tile_h: int,
    ) -> Image.Image:
        target = (tile_w, tile_h)
        if self._last_size != target:
            resize_offscreen_widget(self._widget, target)
            show_offscreen_widget(self._widget)
            self._last_size = target
        self._set_export_viewport((canvas_w, canvas_h, tile_left, tile_top))
        self._prepare_frame()
        render_widget_frame(self._widget)
        render_widget_frame(self._widget)
        qimg = self._widget.grabFramebuffer()
        tile_image = qimage_to_pil_rgba(qimg)
        if tile_image.size != target:
            tile_image = tile_image.resize(target, Image.Resampling.BILINEAR)
        return tile_image


def create_offscreen_export_widget(factory: Callable[[], QWidget]) -> QWidget:
    widget = factory()
    configure_offscreen_widget(widget)
    show_offscreen_widget(widget)
    return widget
