from core.events import CoreUpdateRequestedEvent
from core.state_management.actions import SetCurrentIndexAction


def activate_single_image_mode(controller, image_number: int):
    doc = controller.store.get_session_state_slot("document")
    img = (
        (doc.full_res_image1 or doc.preview_image1 or doc.original_image1)
        if image_number == 1
        else (doc.full_res_image2 or doc.preview_image2 or doc.original_image2)
    )
    mode = image_number if img else 0
    dispatcher = controller.store.get_dispatcher()
    if dispatcher is not None:
        from core.state_management.viewport_actions import SetShowingSingleImageModeAction

        dispatcher.dispatch(SetShowingSingleImageModeAction(mode), scope="viewport")
    if controller.event_bus:
        controller.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        controller.update_requested.emit()


def deactivate_single_image_mode(controller):
    store = controller.store
    dispatcher = store.get_dispatcher()
    if dispatcher is not None:
        from core.state_management.viewport_actions import SetShowingSingleImageModeAction
        from core.state_management.interaction_actions import SetDraggingSplitLineAction
        import importlib

        _magnifier_actions = importlib.import_module(
            "tabs.image_compare.canvas.features.magnifier.input.actions"
        )
        SetDraggingCapturePointAction = _magnifier_actions.SetDraggingCapturePointAction
        SetDraggingSplitInMagnifierAction = _magnifier_actions.SetDraggingSplitInMagnifierAction

        with store.batch_changes():
            dispatcher.dispatch(SetShowingSingleImageModeAction(0), scope="viewport")
            dispatcher.dispatch(SetDraggingSplitLineAction(False), scope="viewport")
            dispatcher.dispatch(SetDraggingCapturePointAction(False), scope="viewport")
            dispatcher.dispatch(SetDraggingSplitInMagnifierAction(False), scope="viewport")
    if controller.event_bus:
        controller.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        controller.update_requested.emit()


def on_combobox_changed(
    controller, image_number: int, index: int, scroll_delta: int = 0
):
    doc = controller.store.get_session_state_slot("document")
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
        if new_index != current_idx:
            # Index changes go through the Dispatcher so browsing is
            # undoable (SET_CURRENT_INDEX; the reducer replaces the document
            # so the reference snapshot stays sound). The pixel load for the
            # new entry follows as separate, deliberately non-undoable
            # actions (the replaced TiledPixelStore is closed).
            dispatcher = controller.store.get_dispatcher()
            if dispatcher is not None:
                dispatcher.dispatch(
                    SetCurrentIndexAction(slot=image_number, index=new_index)
                )
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
        if (
            controller.store.viewport.render_config.interpolation_method
            == selected_method_key
        ):
            return
        _nav_dispatched = False
        _nav_dispatcher = getattr(controller.store, "get_dispatcher", lambda: None)()
        if _nav_dispatcher is not None:
            try:
                from core.state_management.appearance_actions import SetInterpolationMethodAction

                _nav_dispatcher.dispatch(
                    SetInterpolationMethodAction(method=selected_method_key), scope="viewport"
                )
                _nav_dispatched = True
            except Exception:
                pass
        if not _nav_dispatched:
            try:
                setattr(
                    controller.store.viewport.render_config,
                    "interpolation_method",
                    selected_method_key,
                )
            except Exception:
                pass
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
        if not _nav_dispatched:
            controller.store.emit_state_change("viewport")
        if controller.event_bus:
            controller.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            controller.update_requested.emit()
        recorder = getattr(controller.store, "recorder", None)
        if (
            recorder is not None
            and getattr(recorder, "is_recording", False)
            and not getattr(recorder, "is_paused", False)
        ):
            recorder.capture_frame()
        if controller.presenter:
            settings_presenter = controller.presenter.get_feature("settings")
            if settings_presenter is not None:
                settings_presenter.update_interpolation_combo_box_ui()
            ui_manager = getattr(controller.presenter, "ui_manager", None)
            dialogs = getattr(ui_manager, "dialogs", None)
            settings_dialog = getattr(dialogs, "settings_dialog", None)
            if settings_dialog:
                settings_dialog.update_main_interpolation(selected_method_key)
    except Exception:
        pass
