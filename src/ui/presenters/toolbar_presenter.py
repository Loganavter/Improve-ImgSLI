import logging
from PyQt6.QtCore import QObject

from core.store import Store
from core.events import (
    SettingsToggleIncludeFilenamesInSavedEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportUpdateMagnifierSizeRelativeEvent,
    ViewportUpdateCaptureSizeRelativeEvent,
    ViewportOnSliderPressedEvent,
    ViewportOnSliderReleasedEvent,
    ViewportUpdateMovementSpeedEvent,
    ViewportToggleOrientationEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleMagnifierEvent,
    SettingsToggleDividerLineVisibilityEvent,
    SettingsSetDividerLineThicknessEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
    SettingsSetMagnifierDividerThicknessEvent,
    AnalysisSetDiffModeEvent,
    AnalysisSetChannelViewModeEvent,
    ExportToggleRecordingEvent,
    ExportTogglePauseRecordingEvent,
    ExportOpenVideoEditorEvent,
)

logger = logging.getLogger("ImproveImgSLI")

class ToolbarPresenter(QObject):

    def __init__(
        self,
        store: Store,
        main_controller,
        ui,
        main_window_app,
        ui_manager=None,
        parent=None
    ):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.main_window_app = main_window_app
        self.ui_manager = ui_manager
        self.event_bus = main_controller.event_bus if main_controller else None

        self._orientation_popup = None
        self._popup_timer = None

    def connect_signals(self):

        if self.main_controller is not None and self.main_controller.session_ctrl is not None:
            self.ui.btn_swap.shortClicked.connect(
                self.main_controller.session_ctrl.swap_current_images
            )
            self.ui.btn_swap.longPressed.connect(
                self.main_controller.session_ctrl.swap_entire_lists
            )
            self.ui.btn_clear_list1.shortClicked.connect(
                lambda: self.main_controller.session_ctrl.remove_current_image_from_list(1)
            )
            self.ui.btn_clear_list1.longPressed.connect(
                lambda: self.main_controller.session_ctrl.clear_image_list(1)
            )
            self.ui.btn_clear_list2.shortClicked.connect(
                lambda: self.main_controller.session_ctrl.remove_current_image_from_list(2)
            )
            self.ui.btn_clear_list2.longPressed.connect(
                lambda: self.main_controller.session_ctrl.clear_image_list(2)
            )

        if self.main_controller is not None and self.main_controller.session_ctrl is not None:
            self.ui.edit_name1.editingFinished.connect(
                lambda: self.main_controller.session_ctrl.on_edit_name_changed(
                    1, self.ui.edit_name1.text()
                )
            )
            self.ui.edit_name2.editingFinished.connect(
                lambda: self.main_controller.session_ctrl.on_edit_name_changed(
                    2, self.ui.edit_name2.text()
                )
            )
            self.ui.edit_name1.textEdited.connect(
                lambda text: self.main_controller.session_ctrl.on_edit_name_changed(1, text)
            )
            self.ui.edit_name2.textEdited.connect(
                lambda text: self.main_controller.session_ctrl.on_edit_name_changed(2, text)
            )
        self.ui.edit_name1.textChanged.connect(self.check_name_lengths)
        self.ui.edit_name2.textChanged.connect(self.check_name_lengths)

        if self.main_controller:
            if self.event_bus:
                self.ui.btn_orientation.toggled.connect(
                    lambda checked: self.event_bus.emit(ViewportToggleOrientationEvent(checked))
                )

                self.ui.btn_orientation.valueChanged.connect(self._on_ui_divider_thickness_changed)

                self.ui.btn_magnifier_orientation.toggled.connect(
                    lambda checked: self.event_bus.emit(ViewportToggleMagnifierOrientationEvent(checked))
                )

                self.ui.btn_magnifier_orientation.valueChanged.connect(self._on_ui_magnifier_thickness_changed)

                self.ui.btn_magnifier.toggled.connect(
                    lambda checked: self.event_bus.emit(ViewportToggleMagnifierEvent(checked))
                )
                self.ui.btn_file_names.toggled.connect(
                    lambda checked: self.event_bus.emit(SettingsToggleIncludeFilenamesInSavedEvent(checked))
                )
                self.ui.btn_freeze.toggled.connect(
                    lambda checked: self.event_bus.emit(ViewportToggleFreezeMagnifierEvent(checked))
                )
                self.ui.slider_size.valueChanged.connect(
                    lambda value: self.event_bus.emit(ViewportUpdateMagnifierSizeRelativeEvent(value / 100.0))
                )
                self.ui.slider_capture.valueChanged.connect(
                    lambda value: self.event_bus.emit(ViewportUpdateCaptureSizeRelativeEvent(value / 100.0))
                )
                self.ui.slider_size.sliderPressed.connect(
                    lambda: self.event_bus.emit(ViewportOnSliderPressedEvent("magnifier_size"))
                )
                self.ui.slider_size.sliderReleased.connect(
                    lambda: self.event_bus.emit(
                        ViewportOnSliderReleasedEvent(
                        "magnifier_size_relative",
                        lambda: self.store.viewport.magnifier_size_relative
                        )
                    )
                )
                self.ui.slider_capture.sliderPressed.connect(
                    lambda: self.event_bus.emit(ViewportOnSliderPressedEvent("capture_size"))
                )
                self.ui.slider_capture.sliderReleased.connect(
                    lambda: self.event_bus.emit(
                        ViewportOnSliderReleasedEvent(
                        "capture_size_relative",
                        lambda: self.store.viewport.capture_size_relative
                        )
                    )
                )
                self.ui.slider_speed.valueChanged.connect(
                    lambda value: self.event_bus.emit(ViewportUpdateMovementSpeedEvent(value / 10.0))
                )
            else:

                self.ui.btn_orientation.toggled.connect(
                    self.main_controller.toggle_orientation
                )
                self.ui.btn_orientation.valueChanged.connect(
                    self.main_controller.set_divider_line_thickness
                )
                self.ui.btn_magnifier_orientation.toggled.connect(
                    self.main_controller.toggle_magnifier_orientation
                )
                self.ui.btn_magnifier_orientation.valueChanged.connect(
                    self.main_controller.set_magnifier_divider_thickness
                )
                self.ui.btn_magnifier.toggled.connect(
                    self.main_controller.toggle_magnifier
                )
                self.ui.btn_file_names.toggled.connect(
                    self.main_controller.toggle_include_filenames_in_saved
                )
                self.ui.btn_freeze.toggled.connect(
                    self.main_controller.toggle_freeze_magnifier
                )
                self.ui.slider_size.valueChanged.connect(
                    lambda value: self.event_bus.emit(ViewportUpdateMagnifierSizeRelativeEvent(value / 100.0))
                )
                self.ui.slider_capture.valueChanged.connect(
                    lambda value: self.event_bus.emit(ViewportUpdateCaptureSizeRelativeEvent(value / 100.0))
                )
                self.ui.slider_size.sliderPressed.connect(
                    lambda: self.event_bus.emit(ViewportOnSliderPressedEvent("magnifier_size"))
                )
                self.ui.slider_size.sliderReleased.connect(
                    lambda: self.event_bus.emit(
                        ViewportOnSliderReleasedEvent(
                        "magnifier_size_relative",
                        lambda: self.store.viewport.magnifier_size_relative
                        )
                    )
                )
                self.ui.slider_capture.sliderPressed.connect(
                    lambda: self.event_bus.emit(ViewportOnSliderPressedEvent("capture_size"))
                )
                self.ui.slider_capture.sliderReleased.connect(
                    lambda: self.event_bus.emit(
                        ViewportOnSliderReleasedEvent(
                        "capture_size_relative",
                        lambda: self.store.viewport.capture_size_relative
                        )
                    )
                )
                self.ui.slider_speed.valueChanged.connect(
                    lambda value: self.event_bus.emit(ViewportUpdateMovementSpeedEvent(value / 10.0))
                )

            if self.main_controller.session_ctrl:
                self.ui.combo_interpolation.currentIndexChanged.connect(
                    self.main_controller.session_ctrl.on_interpolation_changed
                )

        self.ui.btn_orientation.rightClicked.connect(
            self._on_orientation_right_clicked
        )

        self.ui.btn_magnifier_orientation.rightClicked.connect(
            self._on_magnifier_orientation_right_clicked
        )

        if hasattr(self.ui.btn_orientation, 'middleClicked'):
            self.ui.btn_orientation.middleClicked.connect(
                self._on_orientation_middle_clicked
            )
        if hasattr(self.ui.btn_magnifier_orientation, 'middleClicked'):
            self.ui.btn_magnifier_orientation.middleClicked.connect(
                self._on_magnifier_orientation_middle_clicked
            )

        if hasattr(self.ui.btn_magnifier, 'rightClicked'):
            self.ui.btn_magnifier.rightClicked.connect(
                self._toggle_magnifier_divider_visibility
            )

        if self.main_controller:
            if self.event_bus:

                if hasattr(self.ui, 'btn_orientation_simple'):
                    self.ui.btn_orientation_simple.toggled.connect(
                        lambda checked: self.event_bus.emit(ViewportToggleOrientationEvent(checked))
                    )
                if hasattr(self.ui, 'btn_divider_visible'):
                    self.ui.btn_divider_visible.toggled.connect(
                        lambda checked: self.event_bus.emit(SettingsToggleDividerLineVisibilityEvent(checked))
                    )
                if hasattr(self.ui, 'btn_divider_color'):
                    self.ui.btn_divider_color.clicked.connect(
                        self._show_divider_color_picker
                    )
                if hasattr(self.ui, 'btn_divider_width'):
                    self.ui.btn_divider_width.valueChanged.connect(
                        lambda thickness: self.event_bus.emit(SettingsSetDividerLineThicknessEvent(thickness))
                    )

                if hasattr(self.ui, 'btn_magnifier_orientation_simple'):
                    self.ui.btn_magnifier_orientation_simple.toggled.connect(
                        lambda checked: self.event_bus.emit(ViewportToggleMagnifierOrientationEvent(checked))
                    )
                if hasattr(self.ui, 'btn_magnifier_divider_visible'):
                    self.ui.btn_magnifier_divider_visible.toggled.connect(
                        lambda checked: self.event_bus.emit(SettingsToggleMagnifierDividerVisibilityEvent(checked))
                    )
                if hasattr(self.ui, 'btn_magnifier_divider_width'):
                    self.ui.btn_magnifier_divider_width.valueChanged.connect(
                        lambda thickness: self.event_bus.emit(SettingsSetMagnifierDividerThicknessEvent(thickness))
                    )

                if hasattr(self.ui, 'btn_magnifier_guides_simple') and self.main_controller:
                    self.ui.btn_magnifier_guides_simple.toggled.connect(
                        self.main_controller.toggle_magnifier_guides
                    )
                if hasattr(self.ui, 'btn_magnifier_guides_width') and self.main_controller:
                    self.ui.btn_magnifier_guides_width.valueChanged.connect(
                        self.main_controller.set_magnifier_guides_thickness
                    )
            else:

                if hasattr(self.ui, 'btn_orientation_simple'):
                    self.ui.btn_orientation_simple.toggled.connect(
                        self.main_controller.toggle_orientation
                    )
                if hasattr(self.ui, 'btn_divider_visible'):
                    if hasattr(self.main_controller, 'toggle_divider_line_visibility'):
                        self.ui.btn_divider_visible.toggled.connect(
                            self.main_controller.toggle_divider_line_visibility
                        )
                if hasattr(self.ui, 'btn_divider_color'):
                    self.ui.btn_divider_color.clicked.connect(
                        self._show_divider_color_picker
                    )
                if hasattr(self.ui, 'btn_divider_width'):
                    self.ui.btn_divider_width.valueChanged.connect(
                        self.main_controller.set_divider_line_thickness
                    )

                if hasattr(self.ui, 'btn_magnifier_orientation_simple'):
                    self.ui.btn_magnifier_orientation_simple.toggled.connect(
                        self.main_controller.toggle_magnifier_orientation
                    )
                if hasattr(self.ui, 'btn_magnifier_divider_visible'):
                    if hasattr(self.main_controller, 'toggle_magnifier_divider_visibility'):
                        self.ui.btn_magnifier_divider_visible.toggled.connect(
                            self.main_controller.toggle_magnifier_divider_visibility
                        )
                if hasattr(self.ui, 'btn_magnifier_divider_width'):
                    self.ui.btn_magnifier_divider_width.valueChanged.connect(
                        self.main_controller.set_magnifier_divider_thickness
                    )

                if hasattr(self.ui, 'btn_magnifier_guides_simple'):
                    if hasattr(self.main_controller, 'toggle_magnifier_guides'):
                        self.ui.btn_magnifier_guides_simple.toggled.connect(
                            self.main_controller.toggle_magnifier_guides
                        )
                if hasattr(self.ui, 'btn_magnifier_guides_width'):
                    if hasattr(self.main_controller, 'set_magnifier_guides_thickness'):
                        self.ui.btn_magnifier_guides_width.valueChanged.connect(
                            self.main_controller.set_magnifier_guides_thickness
                        )

        if self.ui_manager is not None and hasattr(self.ui, 'btn_file_names') and self.ui.btn_file_names is not None:
            if hasattr(self.ui.btn_file_names, "rightClicked"):
                self.ui.btn_file_names.rightClicked.connect(
                    lambda: self.ui_manager.toggle_font_settings_flyout(anchor_widget=self.ui.btn_file_names)
                )
        self.ui.combo_interpolation.clicked.connect(
            self._on_interpolation_combo_clicked
        )

        if self.ui_manager:
            self.ui.combo_image1.clicked.connect(
                lambda: self.ui_manager.show_flyout(1)
            )
            self.ui.combo_image2.clicked.connect(
                lambda: self.ui_manager.show_flyout(2)
            )
        else:
            logger.warning("ToolbarPresenter: ui_manager not set, flyout connections skipped")

        if self.ui_manager:
            self.ui.help_button.clicked.connect(
                self.ui_manager.show_help_dialog
            )
            self.ui.btn_settings.clicked.connect(
                self.ui_manager.show_settings_dialog
            )
        else:
            logger.warning("ToolbarPresenter: ui_manager not set, help/settings connections skipped")

        if self.main_controller is not None and self.main_controller.session_ctrl is not None:
            self.ui.combo_image1.wheelScrolledToIndex.connect(
                lambda index: self.main_controller.session_ctrl.on_combobox_changed(1, index)
            )
            self.ui.combo_image2.wheelScrolledToIndex.connect(
                lambda index: self.main_controller.session_ctrl.on_combobox_changed(2, index)
            )
            self.ui.combo_interpolation.wheelScrolledToIndex.connect(
                self.main_controller.session_ctrl.on_interpolation_changed
            )

            if self.event_bus is not None:
                self.ui.btn_diff_mode.triggered.connect(
                    lambda action: self.event_bus.emit(AnalysisSetDiffModeEvent(action.data()))
                )
                self.ui.btn_channel_mode.triggered.connect(
                    lambda action: self.event_bus.emit(AnalysisSetChannelViewModeEvent(action.data()))
                )
                self.ui.btn_record.toggled.connect(
                    lambda checked: self.event_bus.emit(ExportToggleRecordingEvent())
                )
                self.ui.btn_pause.toggled.connect(
                    lambda checked: self.event_bus.emit(ExportTogglePauseRecordingEvent())
                )
                self.ui.btn_video_editor.clicked.connect(
                    lambda: self.event_bus.emit(ExportOpenVideoEditorEvent())
                )
            else:
                if hasattr(self.main_controller, 'event_bus') and self.main_controller.event_bus:
                    self.ui.btn_diff_mode.triggered.connect(
                        lambda action: self.main_controller.event_bus.emit(AnalysisSetDiffModeEvent(action.data()))
                    )
                    self.ui.btn_channel_mode.triggered.connect(
                        lambda action: self.main_controller.event_bus.emit(AnalysisSetChannelViewModeEvent(action.data()))
                    )
                    self.ui.btn_record.toggled.connect(
                        lambda checked: self.main_controller.event_bus.emit(ExportToggleRecordingEvent())
                    )
                    self.ui.btn_pause.toggled.connect(
                        lambda checked: self.main_controller.event_bus.emit(ExportTogglePauseRecordingEvent())
                    )
                    self.ui.btn_video_editor.clicked.connect(
                        lambda: self.main_controller.event_bus.emit(ExportOpenVideoEditorEvent())
                    )

    def _on_ui_divider_thickness_changed(self, thickness):

        self.event_bus.emit(SettingsSetDividerLineThicknessEvent(thickness))

        if thickness > 0 and not self.ui.btn_orientation.isChecked():
            self.event_bus.emit(SettingsToggleDividerLineVisibilityEvent(True))

        elif thickness == 0 and self.ui.btn_orientation.isChecked():
            self.event_bus.emit(SettingsToggleDividerLineVisibilityEvent(False))

    def _on_ui_magnifier_thickness_changed(self, thickness):
        self.event_bus.emit(SettingsSetMagnifierDividerThicknessEvent(thickness))

        if thickness > 0 and not self.ui.btn_magnifier_orientation.isChecked():
            self.event_bus.emit(SettingsToggleMagnifierDividerVisibilityEvent(True))

        elif thickness == 0 and self.ui.btn_magnifier_orientation.isChecked():
            self.event_bus.emit(SettingsToggleMagnifierDividerVisibilityEvent(False))

    def _on_interpolation_combo_clicked(self):
        if self.ui_manager:
            self.ui_manager.toggle_interpolation_flyout()
        else:
            logger.warning("ToolbarPresenter: ui_manager not set, interpolation flyout skipped")

    def _show_divider_color_picker(self):

        settings_presenter = None
        if hasattr(self.main_window_app, 'presenter') and hasattr(self.main_window_app.presenter, 'settings_presenter'):
            settings_presenter = self.main_window_app.presenter.settings_presenter

        if settings_presenter:
            settings_presenter.show_divider_color_picker()
        else:
            logger.warning("ToolbarPresenter: settings_presenter not found")

    def _show_magnifier_divider_color_picker(self):

        settings_presenter = None
        if hasattr(self.main_window_app, 'presenter') and hasattr(self.main_window_app.presenter, 'settings_presenter'):
            settings_presenter = self.main_window_app.presenter.settings_presenter

        if settings_presenter:
            settings_presenter.show_magnifier_divider_color_picker()
        else:
            logger.warning("ToolbarPresenter: settings_presenter not found")

    def _on_orientation_right_clicked(self):
        current_mode = getattr(self.store.settings, "ui_mode", "beginner")

        if current_mode == "advanced":

            self._show_magnifier_orientation_popup()

            if self.event_bus:
                current_orientation = self.store.viewport.magnifier_is_horizontal
                self.event_bus.emit(ViewportToggleMagnifierOrientationEvent(not current_orientation))
            elif self.main_controller:
                current_orientation = self.store.viewport.magnifier_is_horizontal
                self.main_controller.toggle_magnifier_orientation(not current_orientation)
        else:

            self._show_divider_color_picker()

    def _show_magnifier_orientation_popup(self):
        from PyQt6.QtWidgets import QLabel
        from PyQt6.QtCore import QPoint, QTimer, Qt
        from PyQt6.QtGui import QPixmap
        from ui.icon_manager import AppIcon, get_app_icon

        current_orientation = self.store.viewport.magnifier_is_horizontal

        icon_enum = AppIcon.HORIZONTAL_SPLIT if not current_orientation else AppIcon.VERTICAL_SPLIT

        if hasattr(self.ui.btn_orientation, '_value_popup'):
            popup = self.ui.btn_orientation._value_popup
            if popup is None:
                popup = QLabel(parent=self.ui.btn_orientation.window())
                popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
                popup.setObjectName("ValuePopupLabel")
                popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.ui.btn_orientation._value_popup = popup

            pixmap = get_app_icon(icon_enum).pixmap(18, 18)
            popup.setPixmap(pixmap)
            popup.setText("")
            popup.setFixedSize(32, 28)

            pos = self.ui.btn_orientation.mapToGlobal(QPoint(0, 0))
            popup_x = pos.x() + (self.ui.btn_orientation.width() - popup.width()) // 2
            popup_y = pos.y() - popup.height() - 6
            popup.move(popup_x, popup_y)

            if not popup.isVisible():
                popup.show()

            popup.raise_()

            if hasattr(self.ui.btn_orientation, '_scroll_end_timer'):
                timer = self.ui.btn_orientation._scroll_end_timer
                timer.stop()
                timer.start(800)

    def _on_magnifier_orientation_right_clicked(self):
        current_mode = getattr(self.store.settings, "ui_mode", "beginner")

        if current_mode == "advanced":

            if self.event_bus:
                current_orientation = self.store.viewport.magnifier_is_horizontal
                self.event_bus.emit(ViewportToggleMagnifierOrientationEvent(not current_orientation))
            elif self.main_controller:
                current_orientation = self.store.viewport.magnifier_is_horizontal
                self.main_controller.toggle_magnifier_orientation(not current_orientation)
        else:

            self._show_magnifier_divider_color_picker()

    def _on_orientation_middle_clicked(self):
        current_mode = getattr(self.store.settings, "ui_mode", "beginner")

        if current_mode == "expert":
            current_value = self.ui.btn_orientation.get_value()

            if current_value == 0:

                saved_value = self.ui.btn_orientation.restore_saved_value()

                target_value = saved_value if (saved_value is not None and saved_value > 0) else 3

                self.ui.btn_orientation.blockSignals(True)
                self.ui.btn_orientation.set_value(target_value)
                self.ui.btn_orientation.blockSignals(False)

                if self.event_bus:

                    self.event_bus.emit(SettingsToggleDividerLineVisibilityEvent(True))
                    self.event_bus.emit(SettingsSetDividerLineThicknessEvent(target_value))
                elif self.main_controller:
                    self.main_controller.toggle_divider_line_visibility(True)
                    self.main_controller.set_divider_line_thickness(target_value)
            else:

                self.ui.btn_orientation.set_saved_value(current_value)

                self.ui.btn_orientation.blockSignals(True)
                self.ui.btn_orientation.set_value(0)
                self.ui.btn_orientation.blockSignals(False)

                if self.event_bus:

                    self.event_bus.emit(SettingsToggleDividerLineVisibilityEvent(False))
                    self.event_bus.emit(SettingsSetDividerLineThicknessEvent(0))
                elif self.main_controller:
                    self.main_controller.toggle_divider_line_visibility(False)
                    self.main_controller.set_divider_line_thickness(0)

    def _on_magnifier_orientation_middle_clicked(self):
        current_mode = getattr(self.store.settings, "ui_mode", "beginner")

        if current_mode == "expert":
            current_value = self.ui.btn_magnifier_orientation.get_value()

            if current_value == 0:

                saved_value = self.ui.btn_magnifier_orientation.restore_saved_value()
                target_value = saved_value if (saved_value is not None and saved_value > 0) else 3

                self.ui.btn_magnifier_orientation.blockSignals(True)
                self.ui.btn_magnifier_orientation.set_value(target_value)
                self.ui.btn_magnifier_orientation.blockSignals(False)

                if self.event_bus:
                    self.event_bus.emit(SettingsToggleMagnifierDividerVisibilityEvent(True))
                    self.event_bus.emit(SettingsSetMagnifierDividerThicknessEvent(target_value))
                elif self.main_controller:
                    if hasattr(self.main_controller, 'settings_ctrl'):
                        self.main_controller.settings_ctrl.toggle_magnifier_divider_visibility(True)
                    self.main_controller.set_magnifier_divider_thickness(target_value)
            else:

                self.ui.btn_magnifier_orientation.set_saved_value(current_value)

                self.ui.btn_magnifier_orientation.blockSignals(True)
                self.ui.btn_magnifier_orientation.set_value(0)
                self.ui.btn_magnifier_orientation.blockSignals(False)

                if self.event_bus:
                    self.event_bus.emit(SettingsToggleMagnifierDividerVisibilityEvent(False))
                    self.event_bus.emit(SettingsSetMagnifierDividerThicknessEvent(0))
                elif self.main_controller:
                    if hasattr(self.main_controller, 'settings_ctrl'):
                        self.main_controller.settings_ctrl.toggle_magnifier_divider_visibility(False)
                    self.main_controller.set_magnifier_divider_thickness(0)

    def _toggle_magnifier_divider_visibility(self):
        if self.event_bus is not None:
            self.event_bus.emit(SettingsToggleMagnifierDividerVisibilityEvent(not self.store.viewport.magnifier_divider_visible))
        elif self.main_controller is not None and self.main_controller.settings_ctrl is not None:
            if hasattr(self.main_controller.settings_ctrl, 'toggle_magnifier_divider_visibility'):
                self.main_controller.settings_ctrl.toggle_magnifier_divider_visibility(not self.store.viewport.magnifier_divider_visible)

    def update_magnifier_orientation_button_state(self):
        self.ui.btn_magnifier_orientation.setChecked(
            self.store.viewport.magnifier_is_horizontal, emit_signal=False
        )

    def check_name_lengths(self):
        from resources.translations import tr
        len1 = len(self.ui.edit_name1.text().strip())
        len2 = len(self.ui.edit_name2.text().strip())
        limit = self.store.viewport.max_name_length
        if (len1 > limit or len2 > limit) and self.store.viewport.include_file_names_in_saved:
            warning = tr(
                "Name length limit ({limit}) exceeded!",
                self.store.settings.current_language
            ).format(limit=limit)
            self.ui.update_name_length_warning(warning, "", True)
        else:
            self.ui.update_name_length_warning("", "", False)

    def update_toolbar_states(self):
        self.ui.btn_orientation.setChecked(
            self.store.viewport.is_horizontal, emit_signal=False
        )
        self.ui.btn_magnifier_orientation.setChecked(
            self.store.viewport.magnifier_is_horizontal, emit_signal=False
        )
        self.ui.btn_magnifier.setChecked(
            self.store.viewport.use_magnifier, emit_signal=False
        )
        self.ui.btn_freeze.setChecked(
            self.store.viewport.freeze_magnifier, emit_signal=False
        )
        self.ui.btn_file_names.setChecked(
            self.store.viewport.include_file_names_in_saved, emit_signal=False
        )

        divider_thickness = 0 if not self.store.viewport.divider_line_visible else self.store.viewport.divider_line_thickness
        magnifier_thickness = 0 if not self.store.viewport.magnifier_divider_visible else self.store.viewport.magnifier_divider_thickness

        self.ui.btn_orientation.set_value(divider_thickness)
        self.ui.btn_magnifier_orientation.set_value(magnifier_thickness)

        self.ui.slider_size.setValue(int(self.store.viewport.magnifier_size_relative * 100))
        self.ui.slider_capture.setValue(int(self.store.viewport.capture_size_relative * 100))
        self.ui.slider_speed.setValue(int(self.store.viewport.movement_speed_per_sec * 10))

    def _on_color_option_clicked(self, option: str):
        from plugins.settings.presenter import SettingsPresenter

        settings_presenter = None
        if hasattr(self.main_controller, 'settings_ctrl') and hasattr(self.main_controller.settings_ctrl, 'presenter'):
            settings_presenter = self.main_controller.settings_ctrl.presenter

        if not settings_presenter:

            settings_presenter = SettingsPresenter(
                self.store,
                self.main_controller,
                self.ui_manager,
                self.main_window_app
            )

        if option == "divider":
            settings_presenter.show_magnifier_divider_color_picker()
        elif option == "capture":
            settings_presenter.show_capture_ring_color_picker()
        elif option == "border":
            settings_presenter.show_magnifier_border_color_picker()
        elif option == "laser":
            settings_presenter.show_laser_color_picker()
