import logging

from PySide6.QtWidgets import QMessageBox

from tabs.image_compare.events import (
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
)
from plugins.export.events import (
    ExportOpenVideoEditorEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_toolbar_binding
from tabs.image_compare.presenters.toolbar.orientation import (
    on_interpolation_combo_clicked,
    on_orientation_right_clicked,
)
from tabs.image_compare.presenters.toolbar.state import check_name_lengths

logger = logging.getLogger("ImproveImgSLI")
_WARNED_UNAVAILABLE_TOOLBAR_CONTROLS: set[str] = set()

def _show_unavailable_toolbar_capability(presenter, control_id: str) -> None:
    if control_id in _WARNED_UNAVAILABLE_TOOLBAR_CONTROLS:
        return
    _WARNED_UNAVAILABLE_TOOLBAR_CONTROLS.add(control_id)
    logger.warning("Toolbar capability '%s' is unavailable", control_id)
    ui_manager = getattr(presenter, "ui_manager", None)
    if ui_manager is None or getattr(ui_manager, "messages", None) is None:
        return
    ui_manager.messages.show_non_modal_message(
        QMessageBox.Icon.Warning,
        "Feature unavailable",
        f"The '{control_id}' capability is not available in this build.",
    )

def _invoke_toolbar_binding(control_id: str, hook_name: str, presenter, *args):
    binding = get_canvas_feature_toolbar_binding(control_id)
    if binding is None:
        _show_unavailable_toolbar_capability(presenter, control_id)
        return
    hook = getattr(binding, hook_name, None)
    if hook is None:
        _show_unavailable_toolbar_capability(presenter, control_id)
        return
    hook(presenter, *args)

def _resolve_session_handler(controller):
    if controller is None:
        return None
    sessions = getattr(controller, "sessions", None)
    if sessions is not None:
        return sessions
    return controller if hasattr(controller, "on_combobox_changed") else None

def _resolve_interpolation_handler(controller):
    if controller is None:
        return None
    if hasattr(controller, "on_interpolation_changed"):
        return controller.on_interpolation_changed
    sessions = getattr(controller, "sessions", None)
    if sessions is not None and hasattr(sessions, "on_interpolation_changed"):
        return sessions.on_interpolation_changed
    return None

def _invoke_toolbar_binding_if_scrolling(control, control_id: str, hook_name: str, presenter, *args):
    if not bool(getattr(control, "_is_scrolling", False)):
        return
    _invoke_toolbar_binding(control_id, hook_name, presenter, *args)

def connect_signals(presenter):
    _connect_session_actions(presenter)
    _connect_name_editing(presenter)
    _connect_viewport_controls(presenter)
    _connect_orientation_controls(presenter)
    _connect_mode_specific_controls(presenter)
    _connect_ui_manager_controls(presenter)
    _connect_session_comboboxes(presenter)

def _connect_session_actions(presenter):
    controller = presenter.main_controller
    if controller is None or controller.sessions is None:
        return

    ui = presenter.ui
    ui.btn_swap.shortClicked.connect(controller.sessions.swap_current_images)
    ui.btn_swap.longPressed.connect(controller.sessions.swap_entire_lists)
    ui.btn_clear_list1.shortClicked.connect(
        lambda: controller.sessions.remove_current_image_from_list(1)
    )
    ui.btn_clear_list1.longPressed.connect(
        lambda: controller.sessions.clear_image_list(1)
    )
    ui.btn_clear_list2.shortClicked.connect(
        lambda: controller.sessions.remove_current_image_from_list(2)
    )
    ui.btn_clear_list2.longPressed.connect(
        lambda: controller.sessions.clear_image_list(2)
    )

def _connect_name_editing(presenter):
    controller = presenter.main_controller
    ui = presenter.ui
    if controller is not None and controller.sessions is not None:
        ui.edit_name1.editingFinished.connect(
            lambda: controller.sessions.on_edit_name_changed(1, ui.edit_name1.text())
        )
        ui.edit_name2.editingFinished.connect(
            lambda: controller.sessions.on_edit_name_changed(2, ui.edit_name2.text())
        )
        ui.edit_name1.textEdited.connect(
            lambda text: controller.sessions.on_edit_name_changed(1, text)
        )
        ui.edit_name2.textEdited.connect(
            lambda text: controller.sessions.on_edit_name_changed(2, text)
        )

    ui.edit_name1.textChanged.connect(lambda: check_name_lengths(presenter))
    ui.edit_name2.textChanged.connect(lambda: check_name_lengths(presenter))

def _connect_viewport_controls(presenter):
    controller = presenter.main_controller
    ui = presenter.ui
    event_bus = presenter.event_bus
    interpolation_handler = _resolve_interpolation_handler(controller)

    if controller:
        ui.btn_orientation.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "divider.orientation",
                "on_toggled",
                presenter,
                checked,
            )
        )
        # TODO: btn_orientation.valueChanged removed with Button 0.2.16 scroll feature
        ui.btn_magnifier_orientation.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "magnifier.orientation",
                "on_toggled",
                presenter,
                checked,
            )
        )
        # TODO: btn_magnifier_orientation.valueChanged removed with Button 0.2.16 scroll feature
        ui.btn_magnifier.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "magnifier.enabled",
                "on_toggled",
                presenter,
                checked,
            )
        )
        if hasattr(ui, "btn_magnifier_instances"):
            ui.btn_magnifier_instances.addClicked.connect(
                lambda: _invoke_toolbar_binding(
                    "magnifier.instances.add",
                    "on_toggled",
                    presenter,
                    True,
                )
            )
            ui.btn_magnifier_instances.removeClicked.connect(
                lambda: _invoke_toolbar_binding(
                    "magnifier.instances.remove",
                    "on_toggled",
                    presenter,
                    True,
                )
            )
        ui.btn_file_names.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "filename_overlay.visible",
                "on_toggled",
                presenter,
                checked,
            )
        )
        ui.btn_freeze.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "magnifier.freeze",
                "on_toggled",
                presenter,
                checked,
            )
        )
        ui.slider_size.valueChanged.connect(
            lambda value: _invoke_toolbar_binding(
                "magnifier.size",
                "on_value_changed",
                presenter,
                value,
            )
        )
        ui.slider_capture.valueChanged.connect(
            lambda value: _invoke_toolbar_binding(
                "capture.size",
                "on_value_changed",
                presenter,
                value,
            )
        )
        ui.slider_size.sliderPressed.connect(
            lambda: _invoke_toolbar_binding(
                "magnifier.size",
                "on_pressed",
                presenter,
            )
        )
        ui.slider_size.sliderReleased.connect(
            lambda: _invoke_toolbar_binding(
                "magnifier.size",
                "on_released",
                presenter,
            )
        )
        ui.slider_capture.sliderPressed.connect(
            lambda: _invoke_toolbar_binding(
                "capture.size",
                "on_pressed",
                presenter,
            )
        )
        ui.slider_capture.sliderReleased.connect(
            lambda: _invoke_toolbar_binding(
                "capture.size",
                "on_released",
                presenter,
            )
        )
        store = presenter.store
        if store is not None:

            def on_speed_changed(value: int):
                from core.state_management.actions import SetMovementSpeedAction
                speed = value / 100.0
                dispatcher = store.get_dispatcher() if hasattr(store, "get_dispatcher") else None
                if dispatcher is not None:
                    dispatcher.dispatch(SetMovementSpeedAction(speed), scope="viewport")
                else:
                    store.viewport.view_state.movement_speed_per_sec = speed
                settings_manager = getattr(controller, "settings_manager", None) if controller is not None else None
                if settings_manager is not None:
                    settings_manager._save_setting("movement_speed_per_sec", speed)
            ui.slider_speed.valueChanged.connect(on_speed_changed)

        if interpolation_handler is not None:
            ui.combo_interpolation.currentIndexChanged.connect(interpolation_handler)

def _connect_orientation_controls(presenter):
    ui = presenter.ui
    ui.btn_orientation.rightClicked.connect(
        lambda: on_orientation_right_clicked(presenter)
    )
    ui.btn_magnifier_orientation.rightClicked.connect(
        lambda: _invoke_toolbar_binding(
            "magnifier.orientation",
            "on_right_clicked",
            presenter,
        )
    )

    if hasattr(ui.btn_orientation, "middleClicked"):
        ui.btn_orientation.middleClicked.connect(
            lambda: _invoke_toolbar_binding(
                "divider.orientation",
                "on_middle_clicked",
                presenter,
            )
        )
    if hasattr(ui.btn_magnifier_orientation, "middleClicked"):
        ui.btn_magnifier_orientation.middleClicked.connect(
            lambda: _invoke_toolbar_binding(
                "magnifier.orientation",
                "on_middle_clicked",
                presenter,
            )
        )
    if hasattr(ui.btn_magnifier, "rightClicked"):
        ui.btn_magnifier.rightClicked.connect(
            lambda: _invoke_toolbar_binding(
                "magnifier.enabled",
                "on_right_clicked",
                presenter,
            )
        )

def _connect_mode_specific_controls(presenter):
    controller = presenter.main_controller
    ui = presenter.ui

    if not controller:
        return

    if hasattr(ui, "btn_orientation_simple"):
        ui.btn_orientation_simple.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "divider.orientation_simple",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_divider_visible"):
        ui.btn_divider_visible.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "divider.visible",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_divider_color"):
        ui.btn_divider_color.clicked.connect(
            lambda: _invoke_toolbar_binding(
                "divider.color",
                "on_right_clicked",
                presenter,
            )
        )
    if hasattr(ui, "btn_divider_width"):
        # TODO: btn_divider_width.valueChanged removed with Button 0.2.16 scroll feature
        pass
    if hasattr(ui, "btn_magnifier_orientation_simple"):
        ui.btn_magnifier_orientation_simple.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "magnifier.orientation",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_magnifier_divider_visible"):
        ui.btn_magnifier_divider_visible.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "magnifier.divider.visibility",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_magnifier_divider_width"):
        # TODO: btn_magnifier_divider_width.valueChanged removed with Button 0.2.16 scroll feature
        pass
    if hasattr(ui, "btn_magnifier_guides_simple"):
        ui.btn_magnifier_guides_simple.toggled.connect(
            lambda checked: _invoke_toolbar_binding(
                "guides.enabled_simple",
                "on_toggled",
                presenter,
                checked,
            )
        )
    if hasattr(ui, "btn_magnifier_guides_width"):
        # TODO: btn_magnifier_guides_width.valueChanged removed with Button 0.2.16 scroll feature
        pass


def _connect_ui_manager_controls(presenter):
    ui = presenter.ui
    ui_manager = presenter.ui_manager

    if (
        ui_manager is not None
        and hasattr(ui, "btn_file_names")
        and ui.btn_file_names is not None
        and hasattr(ui.btn_file_names, "rightClicked")
    ):
        ui.btn_file_names.rightClicked.connect(
            lambda: ui_manager.transient.toggle_font_settings_flyout(anchor_widget=ui.btn_file_names)
        )

    ui.combo_interpolation.clicked.connect(
        lambda: on_interpolation_combo_clicked(presenter)
    )

    if ui_manager:
        ui.combo_image1.clicked.connect(lambda: ui_manager.show_flyout(1))
        ui.combo_image2.clicked.connect(lambda: ui_manager.show_flyout(2))
        ui.help_button.clicked.connect(ui_manager.dialogs.show_help_dialog)
        ui.btn_settings.clicked.connect(ui_manager.dialogs.show_settings_dialog)
    else:
        logger.warning("ToolbarPresenter: ui_manager not set, flyout connections skipped")
        logger.warning(
            "ToolbarPresenter: ui_manager not set, help/settings connections skipped"
        )

def _connect_session_comboboxes(presenter):
    controller = presenter.main_controller
    ui = presenter.ui
    session_handler = _resolve_session_handler(controller)
    interpolation_handler = _resolve_interpolation_handler(controller)
    if controller is None or session_handler is None:
        return

    ui.combo_image1.wheelScrolledToIndex.connect(
        lambda index: session_handler.on_combobox_changed(1, index)
    )
    ui.combo_image2.wheelScrolledToIndex.connect(
        lambda index: session_handler.on_combobox_changed(2, index)
    )
    if interpolation_handler is not None:
        ui.combo_interpolation.wheelScrolledToIndex.connect(interpolation_handler)

    event_bus = presenter.event_bus or getattr(controller, "event_bus", None)
    if event_bus is None:
        return

    ui.btn_diff_mode.triggered.connect(
        lambda data: event_bus.emit(AnalysisSetDiffModeEvent(data))
    )
    ui.btn_channel_mode.triggered.connect(
        lambda data: event_bus.emit(AnalysisSetChannelViewModeEvent(data))
    )
    ui.btn_record.toggled.connect(
        lambda checked: event_bus.emit(ExportToggleRecordingEvent())
    )
    ui.btn_pause.toggled.connect(
        lambda checked: event_bus.emit(ExportTogglePauseRecordingEvent())
    )
    ui.btn_video_editor.clicked.connect(
        lambda: event_bus.emit(ExportOpenVideoEditorEvent())
    )
