import logging

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QPainter, QPixmap

from domain.qt_adapters import color_to_qcolor, qpoint_to_point

logger = logging.getLogger("ImproveImgSLI")

def on_worker_finished(presenter, result_payload, params, finished_task_id):
    if finished_task_id < presenter._last_displayed_task_id:
        return
    presenter._last_displayed_task_id = finished_task_id
    if presenter.store.viewport.showing_single_image_mode != 0:
        return

    task_type = params.get("type", "unknown")
    if task_type == "background":
        handle_background_result(presenter, result_payload, params)
    elif task_type == "magnifier":
        handle_magnifier_result(presenter, result_payload, params)
    else:
        final_canvas_pil = result_payload.get("final_canvas")
        if final_canvas_pil:
            handle_legacy_result(presenter, result_payload, params)

def handle_background_result(presenter, result, params):
    presenter._is_generating_background = False

    from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

    final_canvas_pil = result.get("final_canvas")
    if not final_canvas_pil:
        return

    padding_left = result.get("padding_left", 0)
    padding_top = result.get("padding_top", 0)
    canvas_pixmap = pil_to_qpixmap_optimized(final_canvas_pil, copy=False)
    if canvas_pixmap.isNull():
        return

    label_width, label_height = params.get("label_dims", presenter.get_current_label_dimensions())
    if label_width <= 0 or label_height <= 0:
        return

    base_pixmap = QPixmap(label_width, label_height)
    base_pixmap.fill(Qt.GlobalColor.transparent)
    base_painter = QPainter(base_pixmap)
    target_rect = presenter.store.viewport.image_display_rect_on_label
    base_painter.drawPixmap(target_rect.x - padding_left, target_rect.y - padding_top, canvas_pixmap)
    base_painter.end()

    presenter._cached_base_pixmap = base_pixmap
    if hasattr(presenter.ui.image_label, "set_pil_layers"):
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
        source1 = presenter.store.document.full_res_image1 or presenter.store.document.original_image1
        source2 = presenter.store.document.full_res_image2 or presenter.store.document.original_image2
        kwargs = {}
        if source1 is not None and source2 is not None:
            kwargs = {
                "source_image1": source1,
                "source_image2": source2,
                "source_key": (
                    presenter.store.document.image1_path,
                    presenter.store.document.image2_path,
                    source1.size,
                    source2.size,
                ),
            }
        presenter.ui.image_label.set_pil_layers(img1, img2, **kwargs)
    else:
        presenter.ui.image_label.set_layers(presenter._cached_base_pixmap, None, None, None)
    presenter.schedule_update()

def handle_magnifier_result(presenter, result, params, debug_state):
    current_time = debug_state["time_fn"]()
    mag_pix = result.get("magnifier_pixmap")
    mag_pos = result.get("magnifier_pos")
    coords_snapshot = result.get("drawing_coords_snapshot")

    if not mag_pix or mag_pix.isNull() or not mag_pos:
        presenter._sync_widget_overlay_coords()
        if hasattr(presenter.ui.image_label, "set_magnifier_content"):
            presenter.ui.image_label.set_magnifier_content(None, None)
        elif presenter._cached_base_pixmap:
            presenter._set_image_layers(presenter._cached_base_pixmap)
        return

    if current_time - debug_state["last"] >= debug_state["interval"]:
        debug_state["setter"](current_time)

    presenter._sync_widget_overlay_coords()
    label_w, label_h = params.get("label_dims", presenter.get_current_label_dimensions())
    pix_w, pix_h = presenter.store.viewport.pixmap_width, presenter.store.viewport.pixmap_height
    offset_x = (label_w - pix_w) // 2
    offset_y = (label_h - pix_h) // 2
    mag_pos_on_label = QPoint(offset_x + mag_pos.x(), offset_y + mag_pos.y())

    if hasattr(presenter.ui.image_label, "set_magnifier_content"):
        presenter.ui.image_label.set_magnifier_content(mag_pix, mag_pos_on_label)
    else:
        presenter._set_image_layers(
            presenter._cached_base_pixmap if presenter._cached_base_pixmap else None,
            mag_pix,
            mag_pos_on_label,
            coords_snapshot,
        )

def handle_legacy_result(presenter, result, params, debug_state):
    presenter._is_generating_background = False
    current_time = debug_state["time_fn"]()

    final_canvas_pil = result.get("final_canvas")
    if not final_canvas_pil:
        return
    if current_time - debug_state["last"] >= debug_state["interval"]:
        debug_state["setter"](current_time)

    padding_left = result.get("padding_left", 0)
    padding_top = result.get("padding_top", 0)
    magnifier_bbox = result.get("magnifier_bbox")
    combined_center = result.get("combined_center")

    if magnifier_bbox and isinstance(magnifier_bbox, QRect):
        target_rect = presenter.store.viewport.image_display_rect_on_label
        if combined_center and isinstance(combined_center, QPoint):
            qt_center = combined_center + QPoint(target_rect.x, target_rect.y)
            presenter.store.viewport.magnifier_screen_center = qpoint_to_point(qt_center)
            presenter.store.viewport.magnifier_screen_size = magnifier_bbox.width()
        else:
            draw_x = target_rect.x - padding_left
            draw_y = target_rect.y - padding_top
            qt_center = magnifier_bbox.translated(draw_x, draw_y).center()
            presenter.store.viewport.magnifier_screen_center = qpoint_to_point(qt_center)
            presenter.store.viewport.magnifier_screen_size = max(
                magnifier_bbox.width(), magnifier_bbox.height()
            )

    try:
        from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

        canvas_pixmap = pil_to_qpixmap_optimized(final_canvas_pil, copy=False)
        if canvas_pixmap.isNull():
            return

        label_width, label_height = params.get("label_dims", presenter.get_current_label_dimensions())
        if label_width <= 0 or label_height <= 0:
            return

        final_pixmap = QPixmap(label_width, label_height)
        final_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(final_pixmap)
        target_rect = presenter.store.viewport.image_display_rect_on_label
        painter.drawPixmap(target_rect.x - padding_left, target_rect.y - padding_top, canvas_pixmap)
        painter.end()

        render_params_dict = params.get("render_params_dict", {})
        presenter._cached_split_pos = render_params_dict.get("split_pos", 0.5)
        is_interactive = result.get("is_interactive", False)
        magnifier_coords = params.get("magnifier_coords")

        if is_interactive and render_params_dict.get("diff_mode", "off") == "off":
            base_pixmap = QPixmap(label_width, label_height)
            base_pixmap.fill(Qt.GlobalColor.transparent)
            base_painter = QPainter(base_pixmap)
            base_painter.drawPixmap(target_rect.x() - padding_left, target_rect.y() - padding_top, canvas_pixmap)
            base_painter.end()
            presenter._cached_base_pixmap = base_pixmap
            presenter._cached_render_params = (
                render_params_dict.get("diff_mode", "off"),
                render_params_dict.get("channel_view_mode", "RGB"),
                render_params_dict.get("is_horizontal", False),
                render_params_dict.get("include_file_names_in_saved", False),
                (label_width, label_height),
            )

        magnifier_pil = result.get("magnifier_pil")
        if magnifier_pil and magnifier_coords and len(magnifier_coords) > 5:
            magnifier_pixmap = pil_to_qpixmap_optimized(magnifier_pil, copy=False)
            if not magnifier_pixmap.isNull():
                mag_bbox_on_image = magnifier_coords[5]
                if mag_bbox_on_image and isinstance(mag_bbox_on_image, QRect):
                    mag_pos_on_image = mag_bbox_on_image.topLeft()
                    mag_pos_on_label = QPoint(
                        target_rect.x() + mag_pos_on_image.x(),
                        target_rect.y() + mag_pos_on_image.y(),
                    )
                    if len(magnifier_coords) > 2:
                        presenter._last_magnifier_pos = magnifier_coords[2]
                    if presenter.store.viewport.show_capture_area_on_main_image and len(magnifier_coords) > 6:
                        capture_center_on_img = magnifier_coords[6]
                        if capture_center_on_img:
                            cap_x = target_rect.x() + int(capture_center_on_img.x())
                            cap_y = target_rect.y() + int(capture_center_on_img.y())
                            unified_w, unified_h = presenter.store.viewport.pixmap_width, presenter.store.viewport.pixmap_height
                            ref_dim = min(unified_w, unified_h)
                            cap_size = max(5, int(round(presenter.store.viewport.capture_size_relative * ref_dim)))
                            col = color_to_qcolor(presenter.store.viewport.capture_ring_color)
                            presenter.ui.image_label.set_capture_area(QPoint(cap_x, cap_y), cap_size, col)

                    bg_to_use = (
                        presenter._cached_base_pixmap
                        if is_interactive and presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull()
                        else final_pixmap
                    )
                    presenter._set_image_layers(bg_to_use, magnifier_pixmap, mag_pos_on_label)
                else:
                    if hasattr(presenter.ui.image_label, "set_capture_area"):
                        presenter.ui.image_label.set_capture_area(None, 0)
                    bg_to_use = (
                        presenter._cached_base_pixmap
                        if is_interactive and presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull()
                        else final_pixmap
                    )
                    presenter._set_image_layers(bg_to_use)
            else:
                if hasattr(presenter.ui.image_label, "set_capture_area"):
                    presenter.ui.image_label.set_capture_area(None, 0)
                bg_to_use = (
                    presenter._cached_base_pixmap
                    if is_interactive and presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull()
                    else final_pixmap
                )
                presenter._set_image_layers(bg_to_use)
        else:
            if hasattr(presenter.ui.image_label, "set_capture_area"):
                presenter.ui.image_label.set_capture_area(None, 0)
            bg_to_use = (
                presenter._cached_base_pixmap
                if is_interactive and presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull()
                else final_pixmap
            )
            presenter._set_image_layers(bg_to_use)

        presenter.current_displayed_pixmap = final_pixmap
    except Exception as exc:
        logger.error(f"Error displaying task: {exc}")

def on_worker_error(presenter, msg):
    presenter._is_generating_background = False
    logger.error(f"Render worker error: {msg}")

def on_generic_worker_error(error_tuple):
    exctype, value, traceback_str = error_tuple
    error_msg = f"{exctype.__name__}: {value}"
    if traceback_str:
        logger.error(f"Generic worker error: {error_msg}\n{traceback_str}")
    else:
        logger.error(f"Generic worker error: {error_msg}")
