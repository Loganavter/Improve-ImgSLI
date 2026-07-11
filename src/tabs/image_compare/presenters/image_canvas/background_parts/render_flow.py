import logging

from PySide6.QtGui import QPixmap

from domain.types import Rect
from tabs.image_compare.canvas.registry import registry

_mlog = logging.getLogger("ImproveImgSLI.magnifier.render_flow")
from tabs.image_compare.canvas.presentation.surface import apply_store_to_canvas
from tabs.image_compare.canvas.helpers import get_canvas_widget, reset_canvas_overlays
from tabs.image_compare.canvas.scene import build_render_scene

from .diff import sync_diff_texture


def _query_overlay(store, capability_id: str, default=None):
    command = registry().get_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result


def schedule_update(presenter):
    if (
        hasattr(presenter.main_window_app, "_closing")
        and presenter.main_window_app._closing
    ):
        return

    is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode

    if is_interactive:
        presenter._pending_interactive_mode = True

    if is_interactive:
        presenter._update_scheduler_timer.stop()
        result = presenter.update_comparison_if_needed()
        if result:
            presenter._pending_interactive_mode = None
    else:
        if not presenter._update_scheduler_timer.isActive():
            presenter._update_scheduler_timer.start()


def update_comparison_if_needed(presenter):
    if (
        not getattr(presenter.main_window_app, "_is_ui_stable", False)
        or presenter.store.viewport.interaction_state.resize_in_progress
    ):
        return False

    if (
        not presenter.main_window_app.isVisible()
        or presenter.main_window_app.isMinimized()
    ):
        return False

    label_width, label_height = presenter.get_current_label_dimensions()
    if label_width <= 2 or label_height <= 2:
        return False

    if getattr(
        presenter.store.viewport.session_data.render_cache,
        "unification_in_progress",
        False,
    ):
        if presenter.store.viewport.session_data.image_state.image1 is None:
            return False

    _document = presenter.store.get_session_state_slot("document")
    if _document is None:
        return False
    source1 = (
        _document.full_res_image1
        or _document.preview_image1
        or _document.original_image1
    )
    source2 = (
        _document.full_res_image2
        or _document.preview_image2
        or _document.original_image2
    )

    if presenter.store.viewport.view_state.showing_single_image_mode != 0:
        image_to_show = (
            (
                presenter.store.viewport.session_data.render_cache.display_cache_image1
                or presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
                or presenter.store.viewport.session_data.image_state.image1
                or source1
            )
            if presenter.store.viewport.view_state.showing_single_image_mode == 1
            else (
                presenter.store.viewport.session_data.render_cache.display_cache_image2
                or presenter.store.viewport.session_data.render_cache.scaled_image2_for_display
                or presenter.store.viewport.session_data.image_state.image2
                or source2
            )
        )
        presenter.view.display_single_image_on_label(image_to_show)
        return False

    if (
        presenter.store.viewport.session_data.image_state.image1 is None
        or presenter.store.viewport.session_data.image_state.image2 is None
        or not source1
        or not source2
    ):
        presenter.ui.image_label.clear()
        presenter.current_displayed_pixmap = None
        return False

    if presenter.background.ensure_images_unified(source1, source2):
        if not presenter.background.create_preview_cache_async(
            presenter.store.viewport.session_data.image_state.image1,
            presenter.store.viewport.session_data.image_state.image2,
        ):
            return False

    src_resize1 = (
        presenter.store.viewport.session_data.render_cache.display_cache_image1
        or presenter.store.viewport.session_data.image_state.image1
    )
    src_resize2 = (
        presenter.store.viewport.session_data.render_cache.display_cache_image2
        or presenter.store.viewport.session_data.image_state.image2
    )
    if src_resize1 and src_resize2:
        img1_w, img1_h = src_resize1.size
        img2_w, img2_h = src_resize2.size
        scale1 = min(label_width / img1_w, label_height / img1_h)
        scale2 = min(label_width / img2_w, label_height / img2_h)
        scale = min(scale1, scale2)
        scaled_w = max(1, int(img1_w * scale))
        scaled_h = max(1, int(img1_h * scale))
    else:
        scaled_w, scaled_h = label_width, label_height

    if (
        not presenter.view.is_canvas_widget()
        and not presenter.background.ensure_images_scaled(scaled_w, scaled_h)
    ):
        return False

    presenter.store.viewport.geometry_state.pixmap_width = scaled_w
    presenter.store.viewport.geometry_state.pixmap_height = scaled_h
    img_x, img_y = (label_width - scaled_w) // 2, (label_height - scaled_h) // 2
    presenter.store.viewport.geometry_state.image_display_rect_on_label = Rect(
        img_x, img_y, scaled_w, scaled_h
    )

    current_bg_sig = presenter.background.get_background_signature(source1, source2)
    last_bg_sig = getattr(presenter, "_last_bg_signature", None)
    current_label_dims = (label_width, label_height)
    label_dims_changed = presenter._last_label_dims != current_label_dims

    bg_is_dirty = (
        (current_bg_sig != last_bg_sig)
        or label_dims_changed
        or (presenter._cached_base_pixmap is None)
    )

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    if (
        presenter.view.is_canvas_widget()
        and diff_mode == "ssim"
        and getattr(
            presenter.store.viewport.session_data.render_cache,
            "cached_diff_image",
            None,
        )
        is None
    ):
        request_cached_diff = registry().get_feature_command_by_alias(
            "overlay.request_cached_diff",
        )
        if request_cached_diff is not None:
            request_cached_diff(
                presenter,
                source1,
                source2,
                diff_mode,
            )

    if presenter.view.is_canvas_widget():
        sync_diff_texture(presenter, diff_mode)

    if bg_is_dirty:
        if presenter.view.is_canvas_widget():
            image_label = get_canvas_widget(presenter.ui)
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
            render_img1, render_img2 = img1, img2

            gui_source1 = presenter.store.viewport.session_data.image_state.image1
            gui_source2 = presenter.store.viewport.session_data.image_state.image2
            document = presenter.store.get_session_state_slot("document")
            source_key = (
                document.image1_path,
                document.image2_path,
                id(gui_source1) if gui_source1 is not None else 0,
                id(gui_source2) if gui_source2 is not None else 0,
                gui_source1.size if gui_source1 is not None else None,
                gui_source2.size if gui_source2 is not None else None,
            )
            img_sig = (
                id(render_img1),
                id(render_img2),
                current_label_dims,
                presenter.store.viewport.view_state.diff_mode,
                presenter.store.viewport.view_state.channel_view_mode,
                source_key,
            )
            if img_sig != getattr(presenter, "_last_img_sig", None):
                presenter._last_img_sig = img_sig
                if render_img1 and render_img2:
                    apply_store_to_canvas(
                        image_label,
                        presenter.store,
                        render_img1,
                        render_img2,
                        fit_content=False,
                        source_image1=gui_source1,
                        source_image2=gui_source2,
                        source_key=source_key,
                        clip_overlays_to_image_bounds=False,
                    )
            else:
                runtime_state = getattr(image_label, "runtime_state", None)
                if runtime_state is not None:
                    runtime_state._store = presenter.store
                    image_label.set_render_scene(
                        build_render_scene(
                            presenter.store,
                            apply_channel_mode_in_shader=bool(
                                getattr(
                                    runtime_state, "_apply_channel_mode_in_shader", True
                                )
                            ),
                            clip_overlays_to_image_bounds=False,
                        )
                    )
            presenter._last_mag_signature = None
            presenter._last_bg_signature = current_bg_sig
            presenter._last_label_dims = current_label_dims
            if presenter._cached_base_pixmap is None:
                presenter._cached_base_pixmap = QPixmap(1, 1)
        else:
            return False
    visible_models = [
        model
        for model in (_query_overlay(presenter.store, "overlay.all_states", ()) or ())
        if bool(model.get("visible", False))
    ]
    _should_render = bool(_query_overlay(presenter.store, "overlay.enabled", False))
    if _should_render and visible_models:
        current_mag_sig = presenter.overlay.get_signature()
        last_mag_sig = getattr(presenter, "_last_mag_signature", None)
        image_label = presenter.ui.image_label
        current_mag_state = (
            current_mag_sig,
            getattr(image_label, "_source_images_ready", False),
            tuple(getattr(image_label, "_source_image_ids", []) or []),
        )
        mag_is_dirty = current_mag_state != last_mag_sig

        if mag_is_dirty:
            presenter.overlay.rebuild_overlay()
            presenter._last_mag_signature = current_mag_state
            return True
    else:
        reset_canvas_overlays(presenter.ui.image_label)
        presenter._last_mag_signature = None
    return False


def should_use_dirty_rects_optimization(presenter, render_params_dict, label_dims=None):
    if not presenter.store.viewport.interaction_state.is_interactive_mode:
        return False
    if render_params_dict.get("use_magnifier", False):
        return False
    if not presenter._cached_base_pixmap or presenter._cached_base_pixmap.isNull():
        return False
    if label_dims is None:
        label_dims = presenter.get_current_label_dimensions()

    current_params = (
        render_params_dict.get("diff_mode", "off"),
        render_params_dict.get("channel_view_mode", "RGB"),
        render_params_dict.get("is_horizontal", False),
        render_params_dict.get("include_file_names_in_saved", False),
        label_dims,
    )
    if (
        presenter._cached_render_params
        and presenter._cached_render_params[:4] != current_params[:4]
    ):
        return False
    return True


def finish_resize_delay(presenter):
    if presenter.store.viewport.interaction_state.resize_in_progress:
        presenter.store.viewport.interaction_state.resize_in_progress = False
        presenter.schedule_update()
