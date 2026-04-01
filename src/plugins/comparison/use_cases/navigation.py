from core.events import CoreUpdateRequestedEvent

def activate_single_image_mode(controller, image_number: int):
    doc = controller.store.document
    img = (
        (doc.full_res_image1 or doc.preview_image1 or doc.original_image1)
        if image_number == 1
        else (doc.full_res_image2 or doc.preview_image2 or doc.original_image2)
    )
    controller.store.viewport.view_state.showing_single_image_mode = image_number if img else 0
    controller.store.emit_state_change("viewport")
    if controller.event_bus:
        controller.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        controller.update_requested.emit()

def deactivate_single_image_mode(controller):
    vp = controller.store.viewport
    vp.view_state.showing_single_image_mode = 0
    vp.interaction_state.is_dragging_split_line = False
    vp.interaction_state.is_dragging_capture_point = False
    vp.interaction_state.is_dragging_split_in_magnifier = False
    controller.store.emit_state_change("viewport")
    if controller.event_bus:
        controller.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        controller.update_requested.emit()

def on_combobox_changed(controller, image_number: int, index: int, scroll_delta: int = 0):
    doc = controller.store.document
    target_list = doc.image_list1 if image_number == 1 else doc.image_list2
    if not target_list:
        return

    current_idx = doc.current_index1 if image_number == 1 else doc.current_index2
    if index == -1 and scroll_delta != 0:
        step = -1 if scroll_delta > 0 else 1
        new_index = (current_idx + step) % len(target_list)
    else:
        new_index = index

    if 0 <= new_index < len(target_list):
        if image_number == 1:
            controller.store.document.current_index1 = new_index
        else:
            controller.store.document.current_index2 = new_index
        controller.set_current_image(image_number)
        if controller.event_bus:
            controller.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            controller.update_requested.emit()

def on_interpolation_changed(controller, index: int):
    try:
        from core.constants import AppConstants

        all_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        visible_keys = all_keys
        if not (0 <= index < len(visible_keys)):
            return
        selected_method_key = visible_keys[index]
        if controller.store.viewport.render_config.interpolation_method == selected_method_key:
            return
        controller.store.viewport.render_config.interpolation_method = selected_method_key
        if hasattr(controller.store.viewport, "render_config") and controller.store.viewport.render_config is not None:
            controller.store.viewport.render_config.interpolation_method = selected_method_key
        if hasattr(controller.store, "invalidate_render_cache"):
            controller.store.invalidate_render_cache()
        main_controller = getattr(controller, "main_controller", None)
        if (
            main_controller is not None
            and hasattr(main_controller, "settings_manager")
            and main_controller.settings_manager is not None
        ):
            main_controller.settings_manager._save_setting(
                "interpolation_method", selected_method_key
            )
        controller.store.emit_state_change("viewport")
        if controller.event_bus:
            controller.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            controller.update_requested.emit()
        recorder = getattr(controller.store, "recorder", None)
        if recorder is not None and getattr(recorder, "is_recording", False) and not getattr(recorder, "is_paused", False):
            recorder.capture_frame()
        if controller.presenter:
            settings_presenter = controller.presenter.get_feature("settings")
            if settings_presenter is not None:
                settings_presenter.update_interpolation_combo_box_ui()
            ui_manager = getattr(controller.presenter, "ui_manager", None)
            if getattr(ui_manager.dialogs, "settings_dialog", None):
                ui_manager.dialogs.settings_dialog.update_main_interpolation(selected_method_key)
    except Exception:
        pass
