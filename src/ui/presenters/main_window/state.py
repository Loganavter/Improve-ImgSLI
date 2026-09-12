from PySide6.QtCore import QSignalBlocker, QTimer

from resources.translations import tr
from ui.canvas_infra.scene.registry import get_canvas_registry


def _document(presenter):
    return presenter.store.get_session_state_slot("document")


def _session_type(store) -> str | None:
    session = store.get_active_workspace_session()
    return session.session_type if session is not None else None


def _set_slider_value_quietly(slider, value: int) -> None:
    if slider.value() == value:
        return
    blocker = QSignalBlocker(slider)
    try:
        slider.setValue(value)
    finally:
        del blocker


def _sync_canvas_feature_bindings(presenter) -> None:
    session_type = _session_type(presenter.store)
    for binding in get_canvas_registry(session_type).get_feature_toolbar_bindings():
        if binding.sync_state is not None:
            binding.sync_state(presenter)


def _refresh_active_session_canvas(presenter) -> None:
    """Re-upload the active image-compare session's images to the canvas.

    Without this, switching back to a session that already had images loaded
    leaves the canvas blank — its texture caches are keyed on the previous
    session's image refs and never re-fetch from the now-active document.
    """
    session_manager = getattr(presenter, "session_manager", None)
    if session_manager is None:
        return
    active = session_manager.get_active_session()
    if active is None or not _session_provides_resource_namespace(
        session_manager,
        active,
        "comparison",
    ):
        presenter._last_active_session_id = getattr(active, "id", None)
        return
    last_id = getattr(presenter, "_last_active_session_id", None)
    presenter._last_active_session_id = active.id
    if last_id == active.id:
        return

    for attr in (
        "_last_img_sig",
        "_last_mag_signature",
        "_last_bg_signature",
        "_last_label_dims",
    ):
        if hasattr(presenter, attr):
            setattr(presenter, attr, None)
    sessions = getattr(getattr(presenter, "main_controller", None), "sessions", None)
    if sessions is None:
        return
    try:
        sessions.set_current_image(1, emit_signal=False)
        sessions.set_current_image(2, emit_signal=False)
    except Exception:
        import logging

        logging.getLogger("ImproveImgSLI").exception(
            "_refresh_active_session_canvas: set_current_image failed"
        )


def _session_provides_resource_namespace(
    session_manager,
    session,
    namespace: str,
) -> bool:
    try:
        blueprint = session_manager.get_session_blueprint(session.session_type)
    except Exception:
        blueprint = None
    if blueprint is None:
        return False
    for resource in getattr(blueprint, "resource_namespaces", ()):
        if getattr(resource, "namespace", None) == namespace:
            return True
    return False


def apply_initial_settings_to_ui(presenter):
    widget = presenter.widget
    viewport = presenter.store.viewport

    _set_slider_value_quietly(
        widget.slider_speed, int(viewport.view_state.movement_speed_per_sec * 100)
    )
    widget.btn_file_names.setChecked(
        viewport.render_config.include_file_names_in_saved, emit_signal=False
    )

    _sync_canvas_feature_bindings(presenter)
    _apply_orientation_underline_mode(presenter)
    widget.toggle_edit_layout_visibility(viewport.render_config.include_file_names_in_saved)

    from domain.qt_adapters import color_to_qcolor

    if presenter.font_settings_flyout:
        presenter.font_settings_flyout.set_values(
            viewport.render_config.font_size_percent,
            viewport.render_config.font_weight,
            color_to_qcolor(viewport.render_config.file_name_color),
            color_to_qcolor(viewport.render_config.file_name_bg_color),
            viewport.render_config.draw_text_background,
            viewport.render_config.text_placement_mode,
            viewport.render_config.text_alpha_percent,
            presenter.store.settings.current_language,
        )

    settings_presenter = presenter.get_feature("settings")
    settings_presenter.update_interpolation_combo_box_ui()
    settings_presenter.setup_view_buttons()
    do_update_file_names_display(presenter)
    on_language_changed(presenter)


def on_store_state_changed(presenter, domain: str):
    is_viewport_domain = domain == "viewport" or domain.startswith("viewport.")

    if domain == "workspace":
        from ui.presenters.main_window.workspace import (
            cover_active_session_transition,
            sync_session_mode,
            sync_workspace_tabs,
        )

        # Cover before swapping the stack page so the flash hides first paint.
        cover_active_session_transition(presenter)
        sync_workspace_tabs(presenter)
        sync_session_mode(presenter)
        _refresh_active_session_canvas(presenter)
        presenter.ui_batcher.schedule_batch_update(
            [
                "file_names",
                "resolution",
                "combobox",
                "slider_tooltips",
                "ratings",
                "window_schedule",
            ]
        )
        return

    if not is_viewport_domain and domain not in ("document", "settings"):
        return

    viewport_subdomain = (
        domain.split(".", 1)[1] if is_viewport_domain and "." in domain else None
    )
    if viewport_subdomain in {"interaction", "geometry"}:
        return

    if domain == "settings":
        _apply_orientation_underline_mode(presenter)

    widget = presenter.widget
    viewport = presenter.store.viewport

    _sync_canvas_feature_bindings(presenter)
    _apply_orientation_underline_mode(presenter)

    widget.toggle_edit_layout_visibility(viewport.render_config.include_file_names_in_saved)
    presenter.ui_batcher.schedule_batch_update(
        [
            "file_names",
            "resolution",
            "combobox",
            "slider_tooltips",
            "ratings",
            "window_schedule",
        ]
    )


def do_update_resolution_labels(presenter):
    document = _document(presenter)
    if document is None:
        return
    has_both_images = bool(document.image1_path and document.image2_path)

    res1_text = ""
    res2_text = ""
    if has_both_images:
        if dim := get_image_dimensions(presenter, 1):
            res1_text = f"{dim[0]}x{dim[1]}"
        if dim := get_image_dimensions(presenter, 2):
            res2_text = f"{dim[0]}x{dim[1]}"
    presenter.widget.update_resolution_labels(res1_text, res1_text, res2_text, res2_text)

    psnr_visible = presenter.store.viewport.session_data.image_state.auto_calculate_psnr
    presenter.widget.psnr_label.setVisible(psnr_visible)
    if psnr_visible:
        psnr = presenter.store.viewport.session_data.image_state.psnr_value
        if psnr is not None:
            presenter.widget.psnr_label.setText(
                f"{tr('ui.psnr', presenter.store.settings.current_language)}: {psnr:.2f} dB"
            )
        else:
            presenter.widget.psnr_label.setText(
                f"{tr('ui.psnr', presenter.store.settings.current_language)}: --"
            )

    ssim_visible = (
        presenter.store.viewport.session_data.image_state.auto_calculate_ssim
        or presenter.store.viewport.view_state.diff_mode == "ssim"
    )
    presenter.widget.ssim_label.setVisible(ssim_visible)
    if ssim_visible:
        ssim = presenter.store.viewport.session_data.image_state.ssim_value
        if ssim is not None:
            presenter.widget.ssim_label.setText(
                f"{tr('ui.ssim', presenter.store.settings.current_language)}: {ssim:.4f}"
            )
        else:
            presenter.widget.ssim_label.setText(
                f"{tr('ui.ssim', presenter.store.settings.current_language)}: --"
            )


def do_update_file_names_display(presenter):
    document = _document(presenter)
    if document is None:
        return
    active_name1 = document.get_active_display_name(1)
    active_name2 = document.get_active_display_name(2)
    name1 = active_name1 or "-----"
    name2 = active_name2 or "-----"
    lang = presenter.store.settings.current_language
    show_labels = bool(name1 != "-----" or name2 != "-----")

    presenter.widget.update_file_names_display(
        name1_text=name1,
        name2_text=name2,
        is_horizontal=presenter.store.viewport.view_state.is_horizontal,
        current_language=lang,
        show_labels=show_labels,
    )

    if not presenter.widget.edit_name1.hasFocus():
        presenter.widget.edit_name1.blockSignals(True)
        presenter.widget.edit_name1.setText(active_name1)
        presenter.widget.edit_name1.setCursorPosition(0)
        presenter.widget.edit_name1.blockSignals(False)

    if not presenter.widget.edit_name2.hasFocus():
        presenter.widget.edit_name2.blockSignals(True)
        presenter.widget.edit_name2.setText(active_name2)
        presenter.widget.edit_name2.setCursorPosition(0)
        presenter.widget.edit_name2.blockSignals(False)

    presenter.check_name_lengths()


def do_update_combobox_displays(presenter):
    document = _document(presenter)
    if document is None:
        return
    settings_presenter = presenter.get_feature("settings")
    if settings_presenter is not None:
        settings_presenter.update_interpolation_combo_box_ui()
        settings_presenter.setup_view_buttons()
    count1 = len(document.image_list1)
    idx1 = document.current_index1
    text1 = (
        get_current_display_name(presenter, 1)
        if 0 <= idx1 < count1
        else tr("misc.select_an_image", presenter.store.settings.current_language)
    )
    presenter.widget.update_combobox_display(1, count1, idx1, text1, "")

    count2 = len(document.image_list2)
    idx2 = document.current_index2
    text2 = (
        get_current_display_name(presenter, 2)
        if 0 <= idx2 < count2
        else tr("misc.select_an_image", presenter.store.settings.current_language)
    )
    presenter.widget.update_combobox_display(2, count2, idx2, text2, "")

    if (
        presenter.ui_manager
        and presenter.ui_manager.transient.unified_flyout.isVisible()
    ):
        presenter.ui_manager.transient.unified_flyout.sync_from_store()


def do_update_slider_tooltips(presenter):
    magnifier_size = 0.2
    capture_size = 0.1
    session_type = _session_type(presenter.store)
    build_payload = get_canvas_registry(session_type).get_feature_command_by_alias(
        "overlay.canvas_payload"
    )
    if build_payload is not None:
        payload = build_payload(presenter.store)
        magnifier_size = float(payload.get("size", 0.2))
        capture_size = float(payload.get("capture_size", 0.1))
    presenter.widget.update_slider_tooltips(
        presenter.store.viewport.view_state.movement_speed_per_sec,
        magnifier_size,
        capture_size,
        presenter.store.settings.current_language,
    )


def do_update_rating_displays(presenter):
    presenter.widget.update_rating_display(
        1, get_current_score(presenter, 1), presenter.store.settings.current_language
    )
    presenter.widget.update_rating_display(
        2, get_current_score(presenter, 2), presenter.store.settings.current_language
    )

    if (
        presenter.ui_manager
        and presenter.ui_manager.transient.unified_flyout.isVisible()
    ):
        document = _document(presenter)
        current_idx1 = document.current_index1
        current_idx2 = document.current_index2
        if current_idx1 >= 0:
            presenter.ui_manager.transient.unified_flyout.update_rating_for_item(
                1, current_idx1
            )
        if current_idx2 >= 0:
            presenter.ui_manager.transient.unified_flyout.update_rating_for_item(
                2, current_idx2
            )
        QTimer.singleShot(
            0, presenter.ui_manager.transient.unified_flyout.refreshGeometry
        )


def on_language_changed(presenter):
    """Handle non-text consequences of a language switch.

    Static text re-applies itself via the ``language_changed`` signal in
    ``sli_ui_toolkit.i18n``; this function only triggers dynamic content
    that doesn't go through ``translatable_*`` bindings.

    Workspace-page chrome (Image Compare lists, flyouts, etc.) is skipped
    while that page is stacked away — same idea as visible-only theme
    ``apply_appearance``. Call ``flush_stale_workspace_language`` when the
    page becomes current again. Button polish is not needed for text-only
    changes.
    """
    lang_code = presenter.store.settings.current_language
    from ui.presenters.main_window.workspace import configure_workspace_actions

    configure_workspace_actions(presenter)
    presenter.get_feature("settings").on_language_changed()
    if (
        hasattr(presenter.main_window_app, "tray_manager")
        and presenter.main_window_app.tray_manager
    ):
        presenter.main_window_app.tray_manager.update_language(lang_code)

    widget = getattr(presenter, "widget", None)
    page_visible = widget is not None and widget.isVisible()
    if page_visible:
        presenter._workspace_language_stale = False
        _refresh_visible_workspace_language(presenter, lang_code)
    else:
        presenter._workspace_language_stale = True

    from shared_toolkit.ui.layout_sizing import defer_dialog_geometry
    from ui.layout_geometry import apply_main_window_minimum

    defer_dialog_geometry(
        presenter.main_window_app,
        lambda: apply_main_window_minimum(presenter.main_window_app),
    )


def _refresh_visible_workspace_language(presenter, lang_code: str) -> None:
    from domain.qt_adapters import color_to_qcolor

    do_update_combobox_displays(presenter)
    do_update_slider_tooltips(presenter)
    do_update_rating_displays(presenter)
    do_update_file_names_display(presenter)
    if presenter.font_settings_flyout is not None:
        presenter.font_settings_flyout.set_values(
            presenter.store.viewport.render_config.font_size_percent,
            presenter.store.viewport.render_config.font_weight,
            color_to_qcolor(presenter.store.viewport.render_config.file_name_color),
            color_to_qcolor(presenter.store.viewport.render_config.file_name_bg_color),
            presenter.store.viewport.render_config.draw_text_background,
            presenter.store.viewport.render_config.text_placement_mode,
            getattr(
                presenter.store.viewport.render_config, "text_alpha_percent", 100
            ),
            lang_code,
        )
    presenter.repopulate_flyouts()


def flush_stale_workspace_language(presenter) -> None:
    """Apply deferred language chrome when a workspace page becomes visible."""
    if not getattr(presenter, "_workspace_language_stale", False):
        return
    widget = getattr(presenter, "widget", None)
    if widget is None or not widget.isVisible():
        return
    presenter._workspace_language_stale = False
    lang_code = presenter.store.settings.current_language
    # Active tab is now the visible workspace page — refresh view/diff labels.
    presenter.get_feature("settings").on_language_changed()
    _refresh_visible_workspace_language(presenter, lang_code)


def get_current_display_name(presenter, image_number: int) -> str:
    document = _document(presenter)
    if document is None:
        return ""
    return document.get_current_display_name(image_number)


def get_current_score(presenter, image_number: int) -> int | None:
    document = _document(presenter)
    if document is None:
        return None
    target_list, index = (
        (document.image_list1, document.current_index1)
        if image_number == 1
        else (document.image_list2, document.current_index2)
    )
    if 0 <= index < len(target_list):
        return target_list[index].rating
    return None


def get_image_dimensions(presenter, image_number: int) -> tuple[int, int] | None:
    document = _document(presenter)
    if document is None:
        return None
    if image_number == 1:
        if not document.image1_path:
            return None
        img = document.full_res_image1 or document.preview_image1
    else:
        if not document.image2_path:
            return None
        img = document.full_res_image2 or document.preview_image2
    if img and hasattr(img, "size"):
        return img.size
    return None


def _apply_orientation_underline_mode(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if hasattr(presenter.widget.btn_orientation, "set_show_underline"):
        presenter.widget.btn_orientation.set_show_underline(current_mode == "expert")
