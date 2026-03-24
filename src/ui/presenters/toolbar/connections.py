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

logger = logging.getLogger("ImproveImgSLI")

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
    if controller is None or controller.session_ctrl is None:
        return

    ui = presenter.ui
    ui.btn_swap.shortClicked.connect(controller.session_ctrl.swap_current_images)
    ui.btn_swap.longPressed.connect(controller.session_ctrl.swap_entire_lists)
    ui.btn_clear_list1.shortClicked.connect(
        lambda: controller.session_ctrl.remove_current_image_from_list(1)
    )
    ui.btn_clear_list1.longPressed.connect(
        lambda: controller.session_ctrl.clear_image_list(1)
    )
    ui.btn_clear_list2.shortClicked.connect(
        lambda: controller.session_ctrl.remove_current_image_from_list(2)
    )
    ui.btn_clear_list2.longPressed.connect(
        lambda: controller.session_ctrl.clear_image_list(2)
    )

def _connect_name_editing(presenter):
    controller = presenter.main_controller
    ui = presenter.ui
    if controller is not None and controller.session_ctrl is not None:
        ui.edit_name1.editingFinished.connect(
            lambda: controller.session_ctrl.on_edit_name_changed(1, ui.edit_name1.text())
        )
        ui.edit_name2.editingFinished.connect(
            lambda: controller.session_ctrl.on_edit_name_changed(2, ui.edit_name2.text())
        )
        ui.edit_name1.textEdited.connect(
            lambda text: controller.session_ctrl.on_edit_name_changed(1, text)
        )
        ui.edit_name2.textEdited.connect(
            lambda text: controller.session_ctrl.on_edit_name_changed(2, text)
        )

    ui.edit_name1.textChanged.connect(presenter.check_name_lengths)
    ui.edit_name2.textChanged.connect(presenter.check_name_lengths)

def _connect_viewport_controls(presenter):
    controller = presenter.main_controller
    ui = presenter.ui
    event_bus = presenter.event_bus
    viewport_ctrl = getattr(controller, "viewport_ctrl", None) if controller else None

    if controller:
        if event_bus:
            ui.btn_orientation.toggled.connect(
                lambda checked: event_bus.emit(ViewportToggleOrientationEvent(checked))
            )
            ui.btn_orientation.valueChanged.connect(
                presenter._on_ui_divider_thickness_changed
            )
            ui.btn_magnifier_orientation.toggled.connect(
                lambda checked: event_bus.emit(
                    ViewportToggleMagnifierOrientationEvent(checked)
                )
            )
            ui.btn_magnifier_orientation.valueChanged.connect(
                presenter._on_ui_magnifier_thickness_changed
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
                        lambda: presenter.store.viewport.magnifier_size_relative,
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
                        lambda: presenter.store.viewport.capture_size_relative,
                    )
                )
            )
            ui.slider_speed.valueChanged.connect(
                lambda value: event_bus.emit(
                    ViewportUpdateMovementSpeedEvent(value / 10.0)
                )
            )
        else:
            ui.btn_orientation.toggled.connect(controller.toggle_orientation)
            ui.btn_orientation.valueChanged.connect(
                controller.set_divider_line_thickness
            )
            ui.btn_magnifier_orientation.toggled.connect(
                controller.toggle_magnifier_orientation
            )
            ui.btn_magnifier_orientation.valueChanged.connect(
                controller.set_magnifier_divider_thickness
            )
            ui.btn_magnifier.toggled.connect(controller.toggle_magnifier)
            ui.btn_file_names.toggled.connect(
                controller.toggle_include_filenames_in_saved
            )
            ui.btn_freeze.toggled.connect(controller.toggle_freeze_magnifier)
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

        if controller.session_ctrl:
            ui.combo_interpolation.currentIndexChanged.connect(
                controller.session_ctrl.on_interpolation_changed
            )

def _connect_orientation_controls(presenter):
    ui = presenter.ui
    ui.btn_orientation.rightClicked.connect(presenter._on_orientation_right_clicked)
    ui.btn_magnifier_orientation.rightClicked.connect(
        presenter._on_magnifier_orientation_right_clicked
    )

    if hasattr(ui.btn_orientation, "middleClicked"):
        ui.btn_orientation.middleClicked.connect(presenter._on_orientation_middle_clicked)
    if hasattr(ui.btn_magnifier_orientation, "middleClicked"):
        ui.btn_magnifier_orientation.middleClicked.connect(
            presenter._on_magnifier_orientation_middle_clicked
        )
    if hasattr(ui.btn_magnifier, "rightClicked"):
        ui.btn_magnifier.rightClicked.connect(
            presenter._toggle_magnifier_divider_visibility
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
                    SettingsToggleDividerLineVisibilityEvent(checked)
                )
            )
        if hasattr(ui, "btn_divider_color"):
            ui.btn_divider_color.clicked.connect(presenter._show_divider_color_picker)
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
                    SettingsToggleMagnifierDividerVisibilityEvent(checked)
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
                controller.toggle_magnifier_guides
            )
        if hasattr(ui, "btn_magnifier_guides_width"):
            ui.btn_magnifier_guides_width.valueChanged.connect(
                controller.set_magnifier_guides_thickness
            )
        return

    if hasattr(ui, "btn_orientation_simple"):
        ui.btn_orientation_simple.toggled.connect(controller.toggle_orientation)
    if hasattr(ui, "btn_divider_visible") and hasattr(
        controller, "toggle_divider_line_visibility"
    ):
        ui.btn_divider_visible.toggled.connect(
            controller.toggle_divider_line_visibility
        )
    if hasattr(ui, "btn_divider_color"):
        ui.btn_divider_color.clicked.connect(presenter._show_divider_color_picker)
    if hasattr(ui, "btn_divider_width"):
        ui.btn_divider_width.valueChanged.connect(controller.set_divider_line_thickness)
    if hasattr(ui, "btn_magnifier_orientation_simple"):
        ui.btn_magnifier_orientation_simple.toggled.connect(
            controller.toggle_magnifier_orientation
        )
    if hasattr(ui, "btn_magnifier_divider_visible") and hasattr(
        controller, "toggle_magnifier_divider_visibility"
    ):
        ui.btn_magnifier_divider_visible.toggled.connect(
            controller.toggle_magnifier_divider_visibility
        )
    if hasattr(ui, "btn_magnifier_divider_width"):
        ui.btn_magnifier_divider_width.valueChanged.connect(
            controller.set_magnifier_divider_thickness
        )
    if hasattr(ui, "btn_magnifier_guides_simple") and hasattr(
        controller, "toggle_magnifier_guides"
    ):
        ui.btn_magnifier_guides_simple.toggled.connect(
            controller.toggle_magnifier_guides
        )
    if hasattr(ui, "btn_magnifier_guides_width") and hasattr(
        controller, "set_magnifier_guides_thickness"
    ):
        ui.btn_magnifier_guides_width.valueChanged.connect(
            controller.set_magnifier_guides_thickness
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
            lambda: ui_manager.toggle_font_settings_flyout(anchor_widget=ui.btn_file_names)
        )

    ui.combo_interpolation.clicked.connect(presenter._on_interpolation_combo_clicked)

    if ui_manager:
        ui.combo_image1.clicked.connect(lambda: ui_manager.show_flyout(1))
        ui.combo_image2.clicked.connect(lambda: ui_manager.show_flyout(2))
        ui.help_button.clicked.connect(ui_manager.show_help_dialog)
        ui.btn_settings.clicked.connect(ui_manager.show_settings_dialog)
    else:
        logger.warning("ToolbarPresenter: ui_manager not set, flyout connections skipped")
        logger.warning(
            "ToolbarPresenter: ui_manager not set, help/settings connections skipped"
        )

def _connect_session_comboboxes(presenter):
    controller = presenter.main_controller
    ui = presenter.ui
    if controller is None or controller.session_ctrl is None:
        return

    ui.combo_image1.wheelScrolledToIndex.connect(
        lambda index: controller.session_ctrl.on_combobox_changed(1, index)
    )
    ui.combo_image2.wheelScrolledToIndex.connect(
        lambda index: controller.session_ctrl.on_combobox_changed(2, index)
    )
    ui.combo_interpolation.wheelScrolledToIndex.connect(
        controller.session_ctrl.on_interpolation_changed
    )

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
