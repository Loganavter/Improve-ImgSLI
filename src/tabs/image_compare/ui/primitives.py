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
from ui.widgets.scroll_value_button import ScrollValueButton

from sli_ui_toolkit.i18n import tr
from tabs.image_compare.canvas.widget import CanvasWidget
from tabs.image_compare.ui.magnifier_color_controls import ColorSettingsButton
from tabs.image_compare.icons import Icon
from shared_toolkit.ui.mode_picker import ModePicker
from ui.theming import resolve_theme_color

logger = logging.getLogger("ImproveImgSLI")


class ImageComparePrimitivesFactory:
    """Creates image_compare's primitive widgets and attaches them to the tab widget.

    ``target`` is the tab-owned ``ImageCompareWidget`` — the widgets this
    factory builds are its attributes, not the host's. ``host`` is only used
    for the handful of host-side helpers (e.g. current language) these
    widgets need at construction time.
    """

    def __init__(self, target: Any, host: Any) -> None:
        self.target = target
        self.host = host

    def build(self, parent: QWidget) -> object:
        target = self.target
        if target is None:
            raise RuntimeError("ImageComparePrimitivesFactory requires a target widget")
        if getattr(target, "_image_compare_primitives_built", False):
            return target

        self._create_static_widgets(parent)
        self._create_selection_controls(parent)
        self._create_view_controls(parent)
        self._create_video_controls(parent)
        self._create_slider_controls(parent)
        self._create_text_and_status_widgets(parent)
        self._configure_image_label()
        self._init_warning_label()
        target._image_compare_primitives_built = True
        return target

    def _create_static_widgets(self, parent: QWidget) -> None:
        target = self.target
        target.resolution_label1 = Label("--x--", variant="group-title")
        target.resolution_label2 = Label("--x--", variant="group-title")
        target.magnifier_settings_panel = QWidget(parent)
        target.image_label = CanvasWidget(parent)
        target.length_warning_label = Label(parent=parent)

    def _create_selection_controls(self, parent: QWidget) -> None:
        target = self.target
        language = self.host._current_language()
        target.btn_image1 = Button(
            Icon.PHOTO,
            text=tr("button.add_images_1", language),
            variant="surface",
            parent=parent,
        )
        target.btn_image2 = Button(
            Icon.PHOTO,
            text=tr("button.add_images_2", language),
            variant="surface",
            parent=parent,
        )
        target.btn_swap = Button(
            Icon.SYNC,
            long_press=True,
            variant="surface",
            background_color=QColor(
                resolve_theme_color(ThemeManager.get_instance(), "accent")
            ),
            parent=parent,
        )
        target.btn_clear_list1 = Button(
            Icon.DELETE,
            long_press=True,
            variant="surface",
            background_color=QColor("#D93025"),
            parent=parent,
        )
        target.btn_clear_list2 = Button(
            Icon.DELETE,
            long_press=True,
            variant="surface",
            background_color=QColor("#D93025"),
            parent=parent,
        )
        accent_color = QColor(
            resolve_theme_color(ThemeManager.get_instance(), "accent")
        )
        target.help_button = Button(
            Icon.HELP,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        target.btn_settings = Button(
            Icon.SETTINGS,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        target.btn_settings.hide()
        target.help_button.hide()
        target.btn_text_settings = Button(
            Icon.TEXT_MANIPULATOR,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        target.btn_quick_save = Button(
            Icon.QUICK_SAVE,
            variant="surface",
            background_color=accent_color,
            parent=parent,
        )
        target.btn_magnifier_orientation = ScrollValueButton(
            icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
            toggle=True,
            show_underline=True,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )
        target.btn_save = Button(
            Icon.SAVE,
            text=tr("button.save_result", language),
            variant="surface",
            parent=parent,
        )

        target.label_rating1 = Label("–", parent, variant="group-title", elide=False)
        target.label_rating2 = Label("–", parent, variant="group-title", elide=False)
        target.combo_image1 = ScrollableComboBox(parent)
        target.combo_image2 = ScrollableComboBox(parent)
        target.combo_interpolation = ScrollableComboBox(parent)
        target.combo_interpolation.setAutoWidthEnabled(True)

    def _create_view_controls(self, parent: QWidget) -> None:
        target = self.target
        target.btn_orientation = ScrollValueButton(
            icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
            toggle=True,
            show_underline=True,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )
        target.btn_magnifier = Button(Icon.MAGNIFIER, toggle=True, parent=parent)
        target.btn_magnifier_instances = InstancesCounterButton(parent=parent)
        target.btn_freeze = Button(Icon.FREEZE, toggle=True, parent=parent)
        target.btn_file_names = Button(Icon.TEXT_FILENAME, toggle=True, parent=parent)

        target.btn_diff_mode = Button(
            Icon.HIGHLIGHT_DIFFERENCES, parent=parent
        )
        target.btn_channel_mode = Button(Icon.PHOTO, parent=parent)
        target.btn_diff_mode_picker = ModePicker.attach(
            target.btn_diff_mode, id_prefix="diff_mode"
        )
        target.btn_channel_mode_picker = ModePicker.attach(
            target.btn_channel_mode, id_prefix="channel_mode"
        )

        target.btn_magnifier_color_settings = ColorSettingsButton(
            parent=parent, current_language="en"
        )
        target.btn_magnifier_guides = ScrollValueButton(
            icon=Icon.MAGNIFIER_GUIDES,
            toggle=True,
            show_underline=True,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )

        target.btn_orientation_simple = Button(
            icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
            toggle=True,
            parent=parent,
        )
        target.btn_divider_visible = Button(
            icon=(Icon.DIVIDER_VISIBLE, Icon.DIVIDER_HIDDEN),
            toggle=True,
            parent=parent,
        )
        target.btn_divider_color = Button(
            Icon.DIVIDER_COLOR, show_underline=True, parent=parent
        )
        target.btn_divider_width = ScrollValueButton(
            icon=Icon.DIVIDER_WIDTH,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=parent,
        )
        target.btn_magnifier_orientation_simple = Button(
            icon=(Icon.VERTICAL_SPLIT, Icon.HORIZONTAL_SPLIT),
            toggle=True,
            parent=parent,
        )
        target.btn_magnifier_divider_visible = Button(
            icon=(Icon.DIVIDER_VISIBLE, Icon.DIVIDER_HIDDEN),
            toggle=True,
            parent=parent,
        )

        target.btn_magnifier_color_settings_beginner = ColorSettingsButton(
            parent=parent, current_language="en"
        )
        target.btn_magnifier_divider_width = ScrollValueButton(
            icon=Icon.DIVIDER_WIDTH,
            show_underline=True,
            min_value=1,
            max_value=10,
            parent=parent,
        )
        target.btn_magnifier_guides_simple = Button(
            Icon.MAGNIFIER_GUIDES, toggle=True, parent=parent
        )
        target.btn_magnifier_guides_width = ScrollValueButton(
            icon=Icon.DIVIDER_WIDTH,
            show_underline=True,
            min_value=1,
            max_value=10,
            parent=parent,
        )

    def _create_video_controls(self, parent: QWidget) -> None:
        target = self.target
        target.btn_record = Button(
            icon=(Icon.RECORD, Icon.STOP), toggle=True, parent=parent
        )
        target.btn_pause = Button(
            icon=(Icon.PAUSE, Icon.PLAY), toggle=True, parent=parent
        )
        target.btn_pause.setEnabled(False)
        target.btn_video_editor = Button(Icon.EXPORT_VIDEO, parent=parent)

    def _create_slider_controls(self, parent: QWidget) -> None:
        target = self.target
        target.slider_size = Slider(Qt.Orientation.Horizontal, parent)
        target.slider_capture = Slider(Qt.Orientation.Horizontal, parent)
        target.slider_speed = Slider(Qt.Orientation.Horizontal, parent)

    def _create_text_and_status_widgets(self, parent: QWidget) -> None:
        target = self.target
        target.edit_name1 = CustomLineEdit(parent)
        target.edit_name2 = CustomLineEdit(parent)
        target.label_magnifier_size = Label(parent=parent, variant="group-title")
        target.label_capture_size = Label(parent=parent, variant="group-title")
        target.label_movement_speed = Label(parent=parent, variant="group-title")
        target.label_interpolation = Label(parent=parent, variant="group-title")

        target.file_name_label1 = Label("--", parent, variant="group-title")
        target.file_name_label2 = Label("--", parent, variant="group-title")
        target.label_edit_name1 = Label(parent=parent, variant="group-title")
        target.label_edit_name2 = Label(parent=parent, variant="group-title")

    def _configure_image_label(self) -> None:
        target = self.target
        target.image_label.setMinimumSize(200, 150)
        target.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        target.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target.image_label.setMouseTracking(True)
        target.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        target.image_label.setAutoFillBackground(True)

    def _init_warning_label(self) -> None:
        target = self.target
        from PySide6.QtGui import QColor

        if hasattr(target.length_warning_label, "setBold"):
            target.length_warning_label.setBold(True)
        if hasattr(target.length_warning_label, "setTextColor"):
            target.length_warning_label.setTextColor(QColor("#FF4500"))
        target.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target.length_warning_label.setVisible(False)
