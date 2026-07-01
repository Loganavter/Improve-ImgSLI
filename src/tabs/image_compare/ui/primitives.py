"""Primitive widget factory for the image_compare tab."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSizePolicy, QWidget
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    Button,
    CustomLineEdit,
    InstancesCounterButton,
    Label,
    ScrollableComboBox,
    Slider,
)

from sli_ui_toolkit.i18n import tr
from tabs.image_compare.canvas.widget import CanvasWidget
from tabs.image_compare.ui.magnifier_color_controls import ColorSettingsButton
from ui.icon_manager import AppIcon
from ui.theming import resolve_theme_color

logger = logging.getLogger("ImproveImgSLI")


class ImageComparePrimitivesFactory:
    """Creates image_compare's primitive widgets and attaches them to host UI."""

    def __init__(self, ui: Any) -> None:
        self.ui = ui

    def build(self, parent: QWidget) -> object:
        ui = self.ui
        if ui is None:
            raise RuntimeError("ImageComparePrimitivesFactory requires ui")
        if getattr(ui, "_image_compare_primitives_built", False):
            return ui

        self._create_static_widgets(parent)
        self._create_selection_controls(parent)
        self._create_view_controls(parent)
        self._create_video_controls(parent)
        self._create_slider_controls(parent)
        self._create_text_and_status_widgets(parent)
        self._configure_image_label()
        self._init_warning_label()
        ui._image_compare_primitives_built = True
        return ui

    def _create_static_widgets(self, parent: QWidget) -> None:
        ui = self.ui
        ui.resolution_label1 = Label("--x--", variant="group-title")
        ui.resolution_label2 = Label("--x--", variant="group-title")
        ui.magnifier_settings_panel = QWidget(parent)
        ui.image_label = CanvasWidget(parent)
        ui.length_warning_label = Label(parent=parent)

    def _create_selection_controls(self, parent: QWidget) -> None:
        ui = self.ui
        language = ui._current_language()
        ui.btn_image1 = Button(
            AppIcon.PHOTO,
            text=tr("button.add_images_1", language),
            variant="surface",
            parent=parent,
        )
        ui.btn_image2 = Button(
            AppIcon.PHOTO,
            text=tr("button.add_images_2", language),
            variant="surface",
            parent=parent,
        )
        ui.btn_swap = Button(
            AppIcon.SYNC,
            long_press=True,
            variant="surface",
            background_color=QColor(
                resolve_theme_color(ThemeManager.get_instance(), "accent")
            ),
            parent=parent,
        )
        ui.btn_clear_list1 = Button(
            AppIcon.DELETE,
            long_press=True,
            variant="surface",
            background_color=QColor("#D93025"),
            parent=parent,
        )
        ui.btn_clear_list2 = Button(
            AppIcon.DELETE,
            long_press=True,
            variant="surface",
            background_color=QColor("#D93025"),
            parent=parent,
        )
        accent_color = QColor(
            resolve_theme_color(ThemeManager.get_instance(), "accent")
        )
        ui.help_button = Button(
            AppIcon.HELP,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        ui.btn_settings = Button(
            AppIcon.SETTINGS,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        ui.btn_text_settings = Button(
            AppIcon.TEXT_MANIPULATOR,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        ui.btn_quick_save = Button(
            AppIcon.QUICK_SAVE,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        ui.btn_magnifier_orientation = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
            toggle=True,
            scrollable=(0, 10),
            show_underline=True,
            parent=parent,
        )
        ui.btn_save = Button(
            AppIcon.SAVE,
            text=tr("button.save_result", language),
            variant="surface",
            parent=parent,
        )

        ui.label_rating1 = Label("–", parent, variant="group-title", elide=False)
        ui.label_rating2 = Label("–", parent, variant="group-title", elide=False)
        ui.combo_image1 = ScrollableComboBox(parent)
        ui.combo_image2 = ScrollableComboBox(parent)
        ui.combo_interpolation = ScrollableComboBox(parent)
        ui.combo_interpolation.setAutoWidthEnabled(True)

    def _create_view_controls(self, parent: QWidget) -> None:
        ui = self.ui
        ui.btn_orientation = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
            toggle=True,
            scrollable=(0, 10),
            show_underline=True,
            underline_visible_when=lambda btn: btn.get_value() > 0,
            parent=parent,
        )
        ui.btn_magnifier = Button(AppIcon.MAGNIFIER, toggle=True, parent=parent)
        ui.btn_magnifier_instances = InstancesCounterButton(parent=parent)
        ui.btn_freeze = Button(AppIcon.FREEZE, toggle=True, parent=parent)
        ui.btn_file_names = Button(AppIcon.TEXT_FILENAME, toggle=True, parent=parent)

        ui.btn_diff_mode = Button(
            AppIcon.HIGHLIGHT_DIFFERENCES, menu=[], parent=parent
        )
        ui.btn_channel_mode = Button(AppIcon.PHOTO, menu=[], parent=parent)

        ui.btn_magnifier_color_settings = ColorSettingsButton(
            parent=parent, current_language="en"
        )
        ui.btn_magnifier_guides = Button(
            AppIcon.MAGNIFIER_GUIDES,
            toggle=True,
            scrollable=(0, 10),
            parent=parent,
        )

        ui.btn_orientation_simple = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
            toggle=True,
            parent=parent,
        )
        ui.btn_divider_visible = Button(
            icon=(AppIcon.DIVIDER_VISIBLE, AppIcon.DIVIDER_HIDDEN),
            toggle=True,
            parent=parent,
        )
        ui.btn_divider_color = Button(
            AppIcon.DIVIDER_COLOR, show_underline=True, parent=parent
        )
        ui.btn_divider_width = Button(
            AppIcon.DIVIDER_WIDTH,
            scrollable=(0, 10),
            parent=parent,
        )
        ui.btn_magnifier_orientation_simple = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
            toggle=True,
            parent=parent,
        )
        ui.btn_magnifier_divider_visible = Button(
            icon=(AppIcon.DIVIDER_VISIBLE, AppIcon.DIVIDER_HIDDEN),
            toggle=True,
            parent=parent,
        )

        ui.btn_magnifier_color_settings_beginner = ColorSettingsButton(
            parent=parent, current_language="en"
        )
        ui.btn_magnifier_divider_width = Button(
            AppIcon.DIVIDER_WIDTH,
            scrollable=(1, 10),
            show_underline=True,
            parent=parent,
        )
        ui.btn_magnifier_guides_simple = Button(
            AppIcon.MAGNIFIER_GUIDES, toggle=True, parent=parent
        )
        ui.btn_magnifier_guides_width = Button(
            AppIcon.DIVIDER_WIDTH,
            scrollable=(1, 10),
            parent=parent,
        )

    def _create_video_controls(self, parent: QWidget) -> None:
        ui = self.ui
        ui.btn_record = Button(
            icon=(AppIcon.RECORD, AppIcon.STOP), toggle=True, parent=parent
        )
        ui.btn_pause = Button(
            icon=(AppIcon.PAUSE, AppIcon.PLAY), toggle=True, parent=parent
        )
        ui.btn_pause.setEnabled(False)
        ui.btn_video_editor = Button(AppIcon.EXPORT_VIDEO, parent=parent)

    def _create_slider_controls(self, parent: QWidget) -> None:
        ui = self.ui
        ui.slider_size = Slider(Qt.Orientation.Horizontal, parent)
        ui.slider_capture = Slider(Qt.Orientation.Horizontal, parent)
        ui.slider_speed = Slider(Qt.Orientation.Horizontal, parent)

    def _create_text_and_status_widgets(self, parent: QWidget) -> None:
        ui = self.ui
        ui.edit_name1 = CustomLineEdit(parent)
        ui.edit_name2 = CustomLineEdit(parent)
        ui.label_magnifier_size = Label(parent=parent, variant="group-title")
        ui.label_capture_size = Label(parent=parent, variant="group-title")
        ui.label_movement_speed = Label(parent=parent, variant="group-title")
        ui.label_interpolation = Label(parent=parent, variant="group-title")

        ui.file_name_label1 = Label("--", parent, variant="group-title")
        ui.file_name_label2 = Label("--", parent, variant="group-title")
        ui.label_edit_name1 = Label(parent=parent, variant="group-title")
        ui.label_edit_name2 = Label(parent=parent, variant="group-title")

    def _configure_image_label(self) -> None:
        ui = self.ui
        ui.image_label.setMinimumSize(200, 150)
        ui.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        ui.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ui.image_label.setMouseTracking(True)
        ui.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        ui.image_label.setAutoFillBackground(True)

    def _init_warning_label(self) -> None:
        ui = self.ui
        ui.length_warning_label.setProperty("class", "warning-label")
        ui.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ui.length_warning_label.setVisible(False)
