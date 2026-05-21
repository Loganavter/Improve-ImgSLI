import logging

import PIL.Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap

from ui.canvas_infra.viewport.state import (
    get_pan_offset_x,
    get_pan_offset_y,
    get_zoom_level,
    set_pan_offsets,
    set_zoom_level,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
from ui.canvas_presentation import apply_store_to_gl_canvas, build_live_store_presentation
from ui.widgets.gl_canvas.scene import build_gl_render_scene
from ui.widgets.gl_canvas.helpers import get_canvas, get_gl_like_canvas, reset_canvas_overlays

logger = logging.getLogger("ImproveImgSLI")

def _gl_source_kwargs(presenter):
    presentation = build_live_store_presentation(presenter.store)
    if presentation.source_image1 is None or presentation.source_image2 is None:
        return {}
    return {
        "source_image1": presentation.source_image1,
        "source_image2": presentation.source_image2,
        "source_key": presentation.source_key,
    }

def is_gl_canvas(presenter):
    return get_gl_like_canvas(presenter.ui) is not None

def _apply_gl_render_scene(presenter):
    image_label = getattr(presenter.ui, "image_label", None)
    if image_label is None or not is_gl_canvas(presenter):
        return
    image_label = get_gl_like_canvas(presenter.ui)
    image_label.set_render_scene(
        build_gl_render_scene(
            presenter.store,
            apply_channel_mode_in_shader=getattr(
                image_label, "_apply_channel_mode_in_shader", True
            ),
        )
    )
    image_label.set_split_position_sync(
        lambda split: _sync_gl_split_position(presenter, split)
    )

def _sync_gl_split_position(presenter, split_position: float):
    viewport = presenter.store.viewport
    if (
        abs(float(viewport.view_state.split_position) - float(split_position)) <= 1e-6
        and abs(float(viewport.view_state.split_position_visual) - float(split_position))
        <= 1e-6
    ):
        return
    command = get_canvas_feature_command_by_alias("splitter.sync_split_position")
    if command is not None:
        command(presenter, split_position)
    image_label = get_gl_like_canvas(presenter.ui)
    if image_label is not None:
        image_label.set_render_scene(
            build_gl_render_scene(
                presenter.store,
                apply_channel_mode_in_shader=getattr(
                    image_label, "_apply_channel_mode_in_shader", True
                ),
            )
        )

def set_image_layers(
    presenter, background=None, overlay=None, overlay_pos=None, coords_snapshot=None
):
    if is_gl_canvas(presenter):
        presentation = build_live_store_presentation(presenter.store)
        img1 = (
            presentation.display_image1
        )
        img2 = (
            presentation.display_image2
        )
        if overlay is None and overlay_pos is None:
            apply_store_to_gl_canvas(
                presenter.ui.image_label,
                presenter.store,
                img1,
                img2,
                fit_content=False,
                clip_overlays_to_image_bounds=False,
                **_gl_source_kwargs(presenter),
            )
        else:
            _apply_gl_render_scene(presenter)
            presenter.ui.image_label.set_pil_layers(
                img1,
                img2,
                overlay,
                overlay_pos,
                shader_letterbox=True,
                **_gl_source_kwargs(presenter),
            )
    else:
        presenter.ui.image_label.set_layers(
            background, overlay, overlay_pos, coords_snapshot
        )

def display_single_image_on_label(presenter, pil_image: PIL.Image.Image | None):
    image_label = get_canvas(presenter.ui)
    if image_label is None:
        return
    if not pil_image:
        image_label.clear()
        presenter.current_displayed_pixmap = None
        return

    try:
        if is_gl_canvas(presenter):
            image_label = get_gl_like_canvas(presenter.ui)
            zoom_level = get_zoom_level(image_label)
            pan_x = get_pan_offset_x(image_label)
            pan_y = get_pan_offset_y(image_label)
            reset_canvas_overlays(image_label)
            apply_store_to_gl_canvas(
                image_label,
                presenter.store,
                pil_image,
                pil_image,
                fit_content=False,
                source_image1=pil_image,
                source_image2=pil_image,
                source_key=(
                    presenter.store.viewport.view_state.showing_single_image_mode,
                    presenter.store.document.image1_path,
                    presenter.store.document.image2_path,
                    id(pil_image),
                    pil_image.size,
                ),
                clip_overlays_to_image_bounds=False,
            )
            set_zoom_level(image_label, zoom_level)
            set_pan_offsets(image_label, pan_x, pan_y)
            presenter._last_bg_signature = None
            presenter._gl_last_img_sig = None
            presenter._last_mag_signature = None
            presenter.current_displayed_pixmap = None
        else:
            w, h = presenter.get_current_label_dimensions()
            rgba = pil_image.convert("RGBA")
            data = rgba.tobytes("raw", "RGBA")
            qimg = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
            pix = QPixmap.fromImage(qimg).scaled(
                w,
                h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            image_label.setPixmap(pix)
            presenter.current_displayed_pixmap = pix
    except Exception as exc:
        logger.error(
            "ImageCanvasPresenter._display_single_image_on_label: failed to display "
            f"image: {exc}"
        )
