import logging

from core.events import (
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
    ExportOpenVideoEditorEvent,
    ExportTogglePauseRecordingEvent,
    ExportToggleRecordingEvent,
    SettingsSetDividerLineThicknessEvent,
    SettingsSetMagnifierDividerThicknessEvent,
    SettingsToggleDividerLineVisibilityEvent,
    SettingsToggleIncludeFilenamesInSavedEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
    ViewportOnSliderPressedEvent,
    ViewportOnSliderReleasedEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportToggleMagnifierEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleOrientationEvent,
    ViewportUpdateCaptureSizeRelativeEvent,
    ViewportUpdateMagnifierSizeRelativeEvent,
    ViewportUpdateMovementSpeedEvent,
)
from ui.presenters.toolbar.orientation import (
    on_interpolation_combo_clicked,
    on_magnifier_orientation_middle_clicked,
    on_magnifier_orientation_right_clicked,
    on_orientation_middle_clicked,
    on_orientation_right_clicked,
    on_ui_divider_thickness_changed,
    on_ui_magnifier_thickness_changed,
    show_divider_color_picker,
    show_magnifier_divider_color_picker,
    toggle_magnifier_divider_visibility,
)
from ui.presenters.toolbar.state import check_name_lengths

logger = logging.getLogger("ImproveImgSLI")

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
    viewport_ctrl = getattr(controller, "viewport_plugin", None) if controller else None
    interpolation_handler = _resolve_interpolation_handler(controller)

    if controller:
        if event_bus:
            ui.btn_orientation.toggled.connect(
                lambda checked: event_bus.emit(ViewportToggleOrientationEvent(checked))
            )
            ui.btn_orientation.valueChanged.connect(
                lambda thickness: on_ui_divider_thickness_changed(presenter, thickness)
            )
            ui.btn_magnifier_orientation.toggled.connect(
                lambda checked: event_bus.emit(
                    ViewportToggleMagnifierOrientationEvent(checked)
                )
            )
            ui.btn_magnifier_orientation.valueChanged.connect(
                lambda thickness: on_ui_magnifier_thickness_changed(presenter, thickness)
            )
            ui.btn_magnifier.toggled.connect(
                lambda checked: event_bus.emit(ViewportToggleMagnifierEvent(checked))
            )
            ui.btn_file_names.toggled.connect(
                lambda checked: event_bus.emit(
                    SettingsToggleIncludeFilenamesInSavedEvent(checked)
                )
            )
            ui.btn_freeze.toggled.connect(
                lambda checked: event_bus.emit(
                    ViewportToggleFreezeMagnifierEvent(checked)
                )
            )
            ui.slider_size.valueChanged.connect(
                lambda value: event_bus.emit(
                    ViewportUpdateMagnifierSizeRelativeEvent(value / 100.0)
                )
            )
            ui.slider_capture.valueChanged.connect(
                lambda value: event_bus.emit(
                    ViewportUpdateCaptureSizeRelativeEvent(value / 100.0)
                )
            )
            ui.slider_size.sliderPressed.connect(
                lambda: event_bus.emit(ViewportOnSliderPressedEvent("magnifier_size"))
            )
            ui.slider_size.sliderReleased.connect(
                lambda: event_bus.emit(
                    ViewportOnSliderReleasedEvent(
                        "magnifier_size_relative",
                        lambda: presenter.store.viewport.view_state.magnifier_size_relative,
                    )
                )
            )
            ui.slider_capture.sliderPressed.connect(
                lambda: event_bus.emit(ViewportOnSliderPressedEvent("capture_size"))
            )
            ui.slider_capture.sliderReleased.connect(
                lambda: event_bus.emit(
                    ViewportOnSliderReleasedEvent(
                        "capture_size_relative",
                        lambda: presenter.store.viewport.view_state.capture_size_relative,
                    )
                )
            )
            ui.slider_speed.valueChanged.connect(
                lambda value: event_bus.emit(
                    ViewportUpdateMovementSpeedEvent(value / 10.0)
                )
            )
        else:
            ui.btn_orientation.toggled.connect(controller.viewport.toggle_orientation)
            ui.btn_orientation.valueChanged.connect(
                controller.viewport.set_divider_line_thickness
            )
            ui.btn_magnifier_orientation.toggled.connect(
                controller.viewport.toggle_magnifier_orientation
            )
            ui.btn_magnifier_orientation.valueChanged.connect(
                controller.viewport.set_magnifier_divider_thickness
            )
            ui.btn_magnifier.toggled.connect(controller.viewport.toggle_magnifier)
            ui.btn_file_names.toggled.connect(
                controller.viewport.toggle_include_filenames_in_saved
            )
            ui.btn_freeze.toggled.connect(controller.viewport.toggle_freeze_magnifier)
            if viewport_ctrl is not None:
                ui.slider_size.valueChanged.connect(
                    lambda value: viewport_ctrl.update_magnifier_size_relative(
                        value / 100.0
                    )
                )
                ui.slider_capture.valueChanged.connect(
                    lambda value: viewport_ctrl.update_capture_size_relative(
                        value / 100.0
                    )
                )
                ui.slider_speed.valueChanged.connect(
                    lambda value: viewport_ctrl.update_movement_speed(value / 10.0)
                )

        if interpolation_handler is not None:
            ui.combo_interpolation.currentIndexChanged.connect(interpolation_handler)

def _connect_orientation_controls(presenter):
    ui = presenter.ui
    ui.btn_orientation.rightClicked.connect(
        lambda: on_orientation_right_clicked(presenter)
    )
    ui.btn_magnifier_orientation.rightClicked.connect(
        lambda: on_magnifier_orientation_right_clicked(presenter)
    )

    if hasattr(ui.btn_orientation, "middleClicked"):
        ui.btn_orientation.middleClicked.connect(
            lambda: on_orientation_middle_clicked(presenter)
        )
    if hasattr(ui.btn_magnifier_orientation, "middleClicked"):
        ui.btn_magnifier_orientation.middleClicked.connect(
            lambda: on_magnifier_orientation_middle_clicked(presenter)
        )
    if hasattr(ui.btn_magnifier, "rightClicked"):
        ui.btn_magnifier.rightClicked.connect(
            lambda: toggle_magnifier_divider_visibility(presenter)
        )

def _connect_mode_specific_controls(presenter):
    controller = presenter.main_controller
    event_bus = presenter.event_bus
    ui = presenter.ui

    if not controller:
        return

    if event_bus:
        if hasattr(ui, "btn_orientation_simple"):
            ui.btn_orientation_simple.toggled.connect(
                lambda checked: event_bus.emit(ViewportToggleOrientationEvent(checked))
            )
        if hasattr(ui, "btn_divider_visible"):
            ui.btn_divider_visible.toggled.connect(
                lambda checked: event_bus.emit(
                    SettingsToggleDividerLineVisibilityEvent(not checked)
                )
            )
        if hasattr(ui, "btn_divider_color"):
            ui.btn_divider_color.clicked.connect(
                lambda: show_divider_color_picker(presenter)
            )
        if hasattr(ui, "btn_divider_width"):
            ui.btn_divider_width.valueChanged.connect(
                lambda thickness: event_bus.emit(
                    SettingsSetDividerLineThicknessEvent(thickness)
                )
            )
        if hasattr(ui, "btn_magnifier_orientation_simple"):
            ui.btn_magnifier_orientation_simple.toggled.connect(
                lambda checked: event_bus.emit(
                    ViewportToggleMagnifierOrientationEvent(checked)
                )
            )
        if hasattr(ui, "btn_magnifier_divider_visible"):
            ui.btn_magnifier_divider_visible.toggled.connect(
                lambda checked: event_bus.emit(
                    SettingsToggleMagnifierDividerVisibilityEvent(not checked)
                )
            )
        if hasattr(ui, "btn_magnifier_divider_width"):
            ui.btn_magnifier_divider_width.valueChanged.connect(
                lambda thickness: event_bus.emit(
                    SettingsSetMagnifierDividerThicknessEvent(thickness)
                )
            )
        if hasattr(ui, "btn_magnifier_guides_simple"):
            ui.btn_magnifier_guides_simple.toggled.connect(
                controller.viewport.toggle_magnifier_guides
            )
        if hasattr(ui, "btn_magnifier_guides_width"):
            ui.btn_magnifier_guides_width.valueChanged.connect(
                controller.viewport.set_magnifier_guides_thickness
            )
        return

    if hasattr(ui, "btn_orientation_simple"):
        ui.btn_orientation_simple.toggled.connect(
            controller.viewport.toggle_orientation
        )
    if hasattr(ui, "btn_divider_visible"):
        ui.btn_divider_visible.toggled.connect(
            lambda checked: controller.viewport.toggle_divider_line_visibility(
                not checked
            )
        )
    if hasattr(ui, "btn_divider_color"):
        ui.btn_divider_color.clicked.connect(
            lambda: show_divider_color_picker(presenter)
        )
    if hasattr(ui, "btn_divider_width"):
        ui.btn_divider_width.valueChanged.connect(
            controller.viewport.set_divider_line_thickness
        )
    if hasattr(ui, "btn_magnifier_orientation_simple"):
        ui.btn_magnifier_orientation_simple.toggled.connect(
            controller.viewport.toggle_magnifier_orientation
        )
    if hasattr(ui, "btn_magnifier_divider_visible") and hasattr(controller, "settings"):
        ui.btn_magnifier_divider_visible.toggled.connect(
            lambda checked: controller.settings.toggle_magnifier_divider_visibility(
                not checked
            )
        )
    if hasattr(ui, "btn_magnifier_divider_width"):
        ui.btn_magnifier_divider_width.valueChanged.connect(
            controller.viewport.set_magnifier_divider_thickness
        )
    if hasattr(ui, "btn_magnifier_guides_simple"):
        ui.btn_magnifier_guides_simple.toggled.connect(
            controller.viewport.toggle_magnifier_guides
        )
    if hasattr(ui, "btn_magnifier_guides_width"):
        ui.btn_magnifier_guides_width.valueChanged.connect(
            controller.viewport.set_magnifier_guides_thickness
        )

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
        lambda action: event_bus.emit(AnalysisSetDiffModeEvent(action.data()))
    )
    ui.btn_channel_mode.triggered.connect(
        lambda action: event_bus.emit(AnalysisSetChannelViewModeEvent(action.data()))
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
