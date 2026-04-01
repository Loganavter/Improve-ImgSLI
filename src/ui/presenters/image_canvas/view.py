import logging

import PIL.Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap

from plugins.analysis.processing import prepare_gl_background_layers_for_mode
from ui.widgets.gl_canvas.scene import build_gl_render_scene

logger = logging.getLogger("ImproveImgSLI")

def _gl_source_kwargs(presenter):
    source1 = presenter.store.document.full_res_image1 or presenter.store.document.original_image1
    source2 = presenter.store.document.full_res_image2 or presenter.store.document.original_image2
    if source1 is None or source2 is None:
        return {}
    return {
        "source_image1": source1,
        "source_image2": source2,
        "source_key": (
            presenter.store.document.image1_path,
            presenter.store.document.image2_path,
            id(source1),
            id(source2),
            source1.size if source1 is not None else None,
            source2.size if source2 is not None else None,
        ),
    }

def is_gl_canvas(presenter):
    return hasattr(presenter.ui.image_label, "set_pil_layers")

def _apply_gl_render_scene(presenter):
    image_label = getattr(presenter.ui, "image_label", None)
    if image_label is None or not hasattr(image_label, "set_render_scene"):
        return
    image_label.set_render_scene(
        build_gl_render_scene(
            presenter.store,
            apply_channel_mode_in_shader=getattr(
                image_label, "_apply_channel_mode_in_shader", True
            ),
        )
    )
    if hasattr(image_label, "set_split_position_sync"):
        image_label.set_split_position_sync(
            lambda split: _sync_gl_split_position(presenter, split)
        )

def _sync_gl_split_position(presenter, split_position: float):
    viewport = presenter.store.viewport
    if (
        abs(float(getattr(viewport.view_state, "split_position", 0.5)) - split_position) <= 1e-6
        and abs(float(getattr(viewport.view_state, "split_position_visual", 0.5)) - split_position) <= 1e-6
    ):
        return
    viewport.view_state.split_position = split_position
    viewport.view_state.split_position_visual = split_position
    presenter.store.emit_viewport_change("interaction")

def set_image_layers(
    presenter, background=None, magnifier=None, mag_pos=None, coords_snapshot=None
):
    if is_gl_canvas(presenter):
        _apply_gl_render_scene(presenter)
        img1 = (
            presenter.store.viewport.session_data.render_cache.display_cache_image1
            or presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
            or presenter.store.viewport.session_data.image_state.image1
        )
        img2 = (
            presenter.store.viewport.session_data.render_cache.display_cache_image2
            or presenter.store.viewport.session_data.render_cache.scaled_image2_for_display
            or presenter.store.viewport.session_data.image_state.image2
        )
        presenter.ui.image_label.set_pil_layers(
            img1,
            img2,
            magnifier,
            mag_pos,
            shader_letterbox=True,
            **_gl_source_kwargs(presenter),
        )
    else:
        presenter.ui.image_label.set_layers(
            background, magnifier, mag_pos, coords_snapshot
        )

def prepare_gl_background_layers(presenter, image1, image2):
    vp = presenter.store.viewport
    try:
        return prepare_gl_background_layers_for_mode(
            image1,
            image2,
            getattr(vp.view_state, "diff_mode", "off"),
            getattr(vp.view_state, "channel_view_mode", "RGB"),
            optimize_ssim=False,
        )
    except Exception:
        logger.exception("Failed to prepare GL background layers")

    return image1, image2

def display_single_image_on_label(presenter, pil_image: PIL.Image.Image | None):
    if not hasattr(presenter.ui, "image_label") or presenter.ui.image_label is None:
        return
    if not pil_image:
        presenter.ui.image_label.clear()
        presenter.current_displayed_pixmap = None
        return

    try:
        if is_gl_canvas(presenter):
            _apply_gl_render_scene(presenter)
            if hasattr(presenter.ui.image_label, "clear_magnifier_gpu"):
                presenter.ui.image_label.clear_magnifier_gpu()
            if hasattr(presenter.ui.image_label, "set_magnifier_content"):
                presenter.ui.image_label.set_magnifier_content(None, None)
            if hasattr(presenter.ui.image_label, "set_overlay_coords"):
                presenter.ui.image_label.set_overlay_coords(None, 0, [], 0)
            if hasattr(presenter.ui.image_label, "set_capture_area"):
                presenter.ui.image_label.set_capture_area(None, 0)
            presenter.ui.image_label.set_pil_layers(
                pil_image,
                pil_image,
                source_image1=pil_image,
                source_image2=pil_image,
                source_key=(
                    presenter.store.viewport.view_state.showing_single_image_mode,
                    presenter.store.document.image1_path,
                    presenter.store.document.image2_path,
                    id(pil_image),
                    pil_image.size,
                ),
                shader_letterbox=True,
            )
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
            presenter.ui.image_label.setPixmap(pix)
            presenter.current_displayed_pixmap = pix
    except Exception as exc:
        logger.error(
            "ImageCanvasPresenter._display_single_image_on_label: failed to display "
            f"image: {exc}"
        )
