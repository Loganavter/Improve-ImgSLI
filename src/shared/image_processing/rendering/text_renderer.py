import logging
from typing import TYPE_CHECKING

from PIL import Image
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QColor

from core.store import Store

if TYPE_CHECKING:
    from shared.image_processing.pipeline import RenderContext

logger = logging.getLogger("ImproveImgSLI")

def draw_file_names_on_canvas(
    text_drawer,
    ctx: "RenderContext",
    canvas: Image.Image,
    padding_left: int,
    padding_top: int,
    img_w: int,
    img_h: int,
):
    temp_store = Store()
    temp_store.viewport.render_config.include_file_names_in_saved = True
    temp_store.viewport.view_state.is_horizontal = ctx.is_horizontal
    temp_store.viewport.render_config.text_placement_mode = ctx.text_placement_mode
    temp_store.viewport.render_config.draw_text_background = ctx.draw_text_background
    temp_store.viewport.render_config.font_size_percent = ctx.font_size_percent
    temp_store.viewport.render_config.font_weight = ctx.font_weight
    temp_store.viewport.render_config.text_alpha_percent = ctx.text_alpha_percent
    temp_store.viewport.render_config.file_name_color = QColor(*ctx.file_name_color)
    temp_store.viewport.render_config.file_name_bg_color = QColor(*ctx.file_name_bg_color)
    temp_store.viewport.render_config.max_name_length = ctx.max_name_length
    split_pos = (
        padding_left + int(img_w * ctx.split_pos)
        if not ctx.is_horizontal
        else padding_top + int(img_h * ctx.split_pos)
    )
    image_rect = QRect(padding_left, padding_top, img_w, img_h)
    text_drawer.draw_filenames_on_image(
        temp_store,
        canvas,
        image_rect,
        split_pos,
        ctx.divider_line_thickness,
        ctx.file_name1,
        ctx.file_name2,
    )

def render_filenames_patch(
    text_drawer,
    ctx: "RenderContext",
    img_rect: QRect,
    padding_left: int,
    padding_top: int,
) -> tuple[Image.Image | None, QPoint]:
    if not ctx.include_file_names:
        return None, QPoint(0, 0)
    try:
        canvas_w = img_rect.width() + padding_left * 2
        canvas_h = img_rect.height() + padding_top * 2
        patch_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw_file_names_on_canvas(
            text_drawer,
            ctx,
            patch_canvas,
            padding_left,
            padding_top,
            img_rect.width(),
            img_rect.height(),
        )
        return patch_canvas, QPoint(0, 0)
    except Exception as e:
        logger.error(f"Error rendering filenames patch: {e}", exc_info=True)
        return None, QPoint(0, 0)

