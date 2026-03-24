import logging

import PIL.Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap

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
            source1.size if source1 is not None else None,
            source2.size if source2 is not None else None,
        ),
    }

def is_gl_canvas(presenter):
    return hasattr(presenter.ui.image_label, "set_pil_layers")

def set_image_layers(
    presenter, background=None, magnifier=None, mag_pos=None, coords_snapshot=None
):
    if is_gl_canvas(presenter):
        img1 = (
            presenter.store.viewport.display_cache_image1
            or presenter.store.viewport.scaled_image1_for_display
            or presenter.store.viewport.image1
        )
        img2 = (
            presenter.store.viewport.display_cache_image2
            or presenter.store.viewport.scaled_image2_for_display
            or presenter.store.viewport.image2
        )
        presenter.ui.image_label.set_pil_layers(
            img1,
            img2,
            magnifier,
            mag_pos,
            **_gl_source_kwargs(presenter),
        )
    else:
        presenter.ui.image_label.set_layers(
            background, magnifier, mag_pos, coords_snapshot
        )

def prepare_gl_background_layers(presenter, image1, image2):
    vp = presenter.store.viewport
    processed1 = image1
    processed2 = image2

    try:
        channel_mode = getattr(vp, "channel_view_mode", "RGB")
        if channel_mode != "RGB":
            from plugins.analysis.processing.channel_analyzer import extract_channel

            processed1 = extract_channel(processed1, channel_mode) or processed1
            processed2 = extract_channel(processed2, channel_mode) or processed2

        diff_mode = getattr(vp, "diff_mode", "off")
        if diff_mode == "off":
            return processed1, processed2

        from plugins.analysis.processing import (
            create_edge_map,
            create_grayscale_diff,
            create_highlight_diff,
            create_ssim_map,
        )

        if diff_mode == "edges":
            return (
                create_edge_map(processed1) or processed1,
                create_edge_map(processed2) or processed2,
            )

        diff_builders = {
            "highlight": lambda: create_highlight_diff(
                processed1, processed2, threshold=10
            ),
            "grayscale": lambda: create_grayscale_diff(processed1, processed2),
            "ssim": lambda: create_ssim_map(processed1, processed2),
        }
        diff_image = diff_builders.get(diff_mode, lambda: None)()
        if diff_image is not None:
            return diff_image, diff_image
    except Exception:
        logger.exception("Failed to prepare GL background layers")

    return processed1, processed2

def display_single_image_on_label(presenter, pil_image: PIL.Image.Image | None):
    if not hasattr(presenter.ui, "image_label") or presenter.ui.image_label is None:
        return
    if not pil_image:
        presenter.ui.image_label.clear()
        presenter.current_displayed_pixmap = None
        return

    try:
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

        if is_gl_canvas(presenter):
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
                    presenter.store.viewport.showing_single_image_mode,
                    presenter.store.document.image1_path,
                    presenter.store.document.image2_path,
                    pil_image.size,
                ),
            )
            presenter._last_bg_signature = None
            presenter._gl_last_img_sig = None
            presenter._last_mag_signature = None
        else:
            presenter.ui.image_label.setPixmap(pix)
        presenter.current_displayed_pixmap = pix
    except Exception as exc:
        logger.error(
            "ImageCanvasPresenter._display_single_image_on_label: failed to display "
            f"image: {exc}"
        )
