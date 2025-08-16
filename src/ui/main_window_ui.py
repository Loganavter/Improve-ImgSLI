from PIL import Image
from typing import Tuple
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy

import logging

from ui.widgets import (
    BodyLabel,
    CaptionLabel,
    FluentSlider,
)

from resources import translations as translations_mod
from ui.icon_manager import get_icon, AppIcon
from ui.widgets.custom_widgets import (
    LongPressIconButton,
    IconButton,
    ScrollableComboBox,
    ButtonType,
)
from ui.widgets.atomic.clickable_label import ClickableLabel
from core.constants import AppConstants
from core.theme import ThemeManager
from ui.widgets import FluentCheckBox
from ui.widgets.atomic.custom_button import CustomButton
from ui.widgets.atomic.custom_line_edit import CustomLineEdit

tr = getattr(translations_mod, "tr", lambda text, lang="en", *args, **kwargs: text)

class Ui_ImageComparisonApp:
    def setupUi(self, main_window: QWidget):
        self.main_window = main_window

        self.resolution_label1 = CaptionLabel("--x--")
        self.resolution_label2 = CaptionLabel("--x--")
        self.magnifier_settings_panel = QWidget(main_window)
        self.image_label = ClickableLabel(main_window)
        self.length_warning_label = BodyLabel(main_window)

        self.btn_image1 = CustomButton(AppIcon.PHOTO, "")
        self.btn_image1.setProperty("class", "primary")
        self.btn_image2 = CustomButton(AppIcon.PHOTO, "")
        self.btn_image2.setProperty("class", "primary")

        self.btn_swap = LongPressIconButton(AppIcon.SYNC, ButtonType.DEFAULT)
        self.btn_clear_list1 = LongPressIconButton(AppIcon.DELETE, ButtonType.DELETE)
        self.btn_clear_list2 = LongPressIconButton(AppIcon.DELETE, ButtonType.DELETE)
        self.help_button = IconButton(AppIcon.HELP, ButtonType.DEFAULT)
        self.btn_settings = IconButton(AppIcon.SETTINGS, ButtonType.DEFAULT)

        self.btn_color_picker = IconButton(AppIcon.TEXT_MANIPULATOR, ButtonType.DEFAULT)
        self.btn_quick_save = IconButton(AppIcon.SAVE, ButtonType.DEFAULT)
        self.btn_save = CustomButton(AppIcon.SAVE, "")
        self.btn_save.setProperty("class", "primary")
        self.label_rating1 = CaptionLabel("–")
        self.label_rating2 = CaptionLabel("–")
        self.combo_image1 = ScrollableComboBox()
        self.combo_image2 = ScrollableComboBox()
        self.combo_interpolation = ScrollableComboBox()
        self.combo_interpolation.setAutoWidthEnabled(True)
        self.checkbox_horizontal = FluentCheckBox()
        self.checkbox_magnifier = FluentCheckBox()
        self.freeze_button = FluentCheckBox()
        self.checkbox_file_names = FluentCheckBox()
        self.slider_size = FluentSlider(Qt.Orientation.Horizontal)
        self.slider_capture = FluentSlider(Qt.Orientation.Horizontal)
        self.slider_speed = FluentSlider(Qt.Orientation.Horizontal)
        self.edit_name1 = CustomLineEdit()
        self.edit_name2 = CustomLineEdit()
        self.label_magnifier_size = BodyLabel()
        self.label_capture_size = BodyLabel()
        self.label_movement_speed = BodyLabel()
        self.label_interpolation = BodyLabel()
        self.file_name_label1 = CaptionLabel("--")
        self.file_name_label2 = CaptionLabel("--")
        self.label_edit_name1 = BodyLabel()
        self.label_edit_name2 = BodyLabel()
        self.drag_overlay1 = QLabel(self.image_label)
        self.drag_overlay2 = QLabel(self.image_label)

        self._configure_image_label()
        self._init_drag_overlays()
        self._init_warning_label()
        main_layout = QVBoxLayout(main_window)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        selection_layout = QVBoxLayout()
        selection_layout.setSpacing(3)
        selection_layout.addLayout(self._create_button_layout())
        selection_layout.addLayout(self._create_combobox_layout())
        main_layout.addLayout(selection_layout)
        main_layout.addLayout(self._create_checkbox_layout())
        self.image_container_layout = QVBoxLayout()
        self.image_container_layout.setContentsMargins(0, 0, 0, 0)
        self._create_slider_layout()
        image_container_widget = QWidget()
        image_container_widget.setLayout(self.image_container_layout)
        image_container_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.image_container_layout.addWidget(self.magnifier_settings_panel)
        self.image_container_layout.addWidget(self.image_label)
        main_layout.addWidget(image_container_widget, 1)
        resolutions_and_filenames_group_layout = QVBoxLayout()
        resolutions_and_filenames_group_layout.setSpacing(0)
        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(
            self.resolution_label1, alignment=Qt.AlignmentFlag.AlignLeft
        )
        resolution_layout.addStretch()
        resolution_layout.addWidget(
            self.resolution_label2, alignment=Qt.AlignmentFlag.AlignRight
        )
        resolution_layout.setContentsMargins(5, 0, 5, 0)
        resolutions_and_filenames_group_layout.addLayout(resolution_layout)
        filenames_layout = self._create_file_names_layout()
        filenames_layout.setContentsMargins(5, 0, 5, 0)
        resolutions_and_filenames_group_layout.addLayout(filenames_layout)
        main_layout.addLayout(resolutions_and_filenames_group_layout)
        main_layout.addWidget(self.length_warning_label)
        self.edit_layout_widget = QWidget()
        self.edit_layout = self._create_edit_layout()
        self.edit_layout_widget.setLayout(self.edit_layout)
        main_layout.addWidget(self.edit_layout_widget)
        main_layout.addWidget(self._create_save_buttons_widget())
        self.toggle_edit_layout_visibility(False)
        self.magnifier_settings_panel.setVisible(False)
        self.freeze_button.setEnabled(False)

        self._post_init_icons_and_sizes()

    def _post_init_icons_and_sizes(self):
        self.btn_quick_save.setIconSize(QSize(24, 24))
        self.help_button.setIconSize(QSize(24, 24))
        self.btn_clear_list1.setIconSize(QSize(22, 22))
        self.btn_clear_list2.setIconSize(QSize(22, 22))

    def reapply_button_styles(self):

        self._post_init_icons_and_sizes()

    def _create_button_layout(self):
        layout = QHBoxLayout()
        layout.setSpacing(8)

        layout.addWidget(self.btn_image1)
        layout.addWidget(self.btn_clear_list1)
        layout.addWidget(self.btn_swap)
        layout.addWidget(self.btn_image2)
        layout.addWidget(self.btn_clear_list2)

        return layout

    def _create_combobox_layout(self):
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)
        layout1 = QHBoxLayout()
        layout1.setSpacing(4)
        self.label_rating1.setFixedWidth(24)
        self.label_rating1.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_rating1.setText(f"<b>{self.label_rating1.text()}</b>")
        self.combo_image1.setMinimumHeight(28)
        self.combo_image1.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout1.addWidget(self.label_rating1)
        layout1.addWidget(self.combo_image1, 1)
        layout2 = QHBoxLayout()
        layout2.setSpacing(4)
        self.label_rating2.setFixedWidth(24)
        self.label_rating2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_rating2.setText(f"<b>{self.label_rating2.text()}</b>")
        self.combo_image2.setMinimumHeight(28)
        self.combo_image2.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout2.addWidget(self.label_rating2)
        layout2.addWidget(self.combo_image2, 1)
        main_layout.addLayout(layout1, 1)
        main_layout.addLayout(layout2, 1)
        self.combo_image1.image_number = 1
        self.combo_image2.image_number = 2
        return main_layout

    def _create_checkbox_layout(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        self.checkbox_sub_layout = QHBoxLayout()
        self.checkbox_sub_layout.setSpacing(-10)

        for cb in (self.checkbox_horizontal, self.checkbox_magnifier, self.freeze_button, self.checkbox_file_names):
            cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.checkbox_sub_layout.addWidget(self.checkbox_horizontal)
        self.checkbox_sub_layout.addWidget(self.checkbox_magnifier)
        self.checkbox_sub_layout.addWidget(self.freeze_button)
        self.checkbox_sub_layout.addWidget(self.checkbox_file_names)
        self.checkbox_sub_layout.addStretch(1)

        self._update_checkbox_stretches()
        layout.addLayout(self.checkbox_sub_layout, 1)

        buttons_sub_layout = QHBoxLayout()
        buttons_sub_layout.setSpacing(8)

        buttons_sub_layout.addWidget(self.btn_quick_save)
        buttons_sub_layout.addWidget(self.btn_settings)
        buttons_sub_layout.addWidget(self.help_button)
        layout.addLayout(buttons_sub_layout)
        return layout

    def _create_slider_layout(self):
        panel_layout = QVBoxLayout(self.magnifier_settings_panel)
        self.magnifier_settings_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.magnifier_settings_panel.sizePolicy().setRetainSizeWhenHidden(True)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(5)
        sliders_main_layout = QHBoxLayout()
        sliders_main_layout.setSpacing(10)
        self.slider_size.setMinimum(5)
        self.slider_size.setMaximum(100)
        self.slider_size.setMinimumWidth(80)
        self.slider_size.setFixedHeight(28)
        sliders_main_layout.addWidget(self.label_magnifier_size, alignment=Qt.AlignmentFlag.AlignVCenter)
        sliders_main_layout.addWidget(self.slider_size, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        sliders_main_layout.addSpacing(15)
        self.slider_capture.setMinimum(1)
        self.slider_capture.setMaximum(100)
        self.slider_capture.setMinimumWidth(80)
        self.slider_capture.setFixedHeight(28)
        sliders_main_layout.addWidget(self.label_capture_size, alignment=Qt.AlignmentFlag.AlignVCenter)
        sliders_main_layout.addWidget(self.slider_capture, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        sliders_main_layout.addSpacing(15)
        self.slider_speed.setMinimum(1)
        self.slider_speed.setMaximum(50)
        self.slider_speed.setMinimumWidth(80)
        self.slider_speed.setFixedHeight(28)
        sliders_main_layout.addWidget(self.label_movement_speed, alignment=Qt.AlignmentFlag.AlignVCenter)
        sliders_main_layout.addWidget(self.slider_speed, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        panel_layout.addLayout(sliders_main_layout)
        interpolation_layout = QHBoxLayout()
        interpolation_layout.setSpacing(5)

        self.combo_interpolation.setMinimumHeight(28)
        self.combo_interpolation.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        interpolation_layout.addWidget(self.label_interpolation)
        interpolation_layout.addWidget(self.combo_interpolation)
        interpolation_layout.addStretch()
        panel_layout.addLayout(interpolation_layout)
        return self.magnifier_settings_panel

    def _configure_image_label(self):
        self.image_label.setMinimumSize(200, 150)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMouseTracking(True)
        self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.image_label.setAutoFillBackground(True)

    def _create_file_names_layout(self):
        layout = QHBoxLayout()
        self.file_name_label1.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.file_name_label2.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.file_name_label1.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.file_name_label2.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.file_name_label1.setMinimumHeight(22)
        self.file_name_label2.setMinimumHeight(22)
        layout.addWidget(self.file_name_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        layout.addWidget(self.file_name_label2, alignment=Qt.AlignmentFlag.AlignRight)
        layout.setContentsMargins(5, 2, 5, 2)
        return layout

    def _create_edit_layout(self):
        edit_outer_layout = QHBoxLayout()
        edit_outer_layout.setSpacing(8)
        self.edit_name1.setMinimumHeight(30)
        self.edit_name2.setMinimumHeight(30)
        edit_outer_layout.addWidget(self.label_edit_name1)
        edit_outer_layout.addWidget(self.edit_name1, 1)
        edit_outer_layout.addSpacing(5)
        edit_outer_layout.addWidget(self.label_edit_name2)
        edit_outer_layout.addWidget(self.edit_name2, 1)
        edit_outer_layout.addSpacing(10)
        edit_outer_layout.addWidget(self.btn_color_picker)
        return edit_outer_layout

    def _create_save_buttons_widget(self):
        save_layout = QHBoxLayout()
        save_layout.setSpacing(0)
        save_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_save.setMinimumHeight(32)
        save_layout.addWidget(self.btn_save)

        save_widget = QWidget()
        save_widget.setLayout(save_layout)
        return save_widget

    def _init_drag_overlays(self):
        style = "background-color: rgba(0, 100, 200, 0.6); color: white; font-size: 20px; border-radius: 10px; padding: 15px; border: 1px solid rgba(255, 255, 255, 0.7);"
        self.drag_overlay1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay1.setStyleSheet(style)
        self.drag_overlay1.setWordWrap(True)
        self.drag_overlay1.hide()
        self.drag_overlay2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay2.setStyleSheet(style)
        self.drag_overlay2.setWordWrap(True)
        self.drag_overlay2.hide()

    def _init_warning_label(self):
        self.length_warning_label.setStyleSheet("color: #FF4500; font-weight: bold;")
        self.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.length_warning_label.setVisible(False)

    def toggle_edit_layout_visibility(self, checked: bool):
        self.edit_layout_widget.setVisible(bool(checked))

    def update_translations(self, lang_code: str):
        self.main_window.setWindowTitle(tr("Improve ImgSLI", lang_code))

        self.label_edit_name1.setText(tr("Name 1:", lang_code))
        self.label_edit_name2.setText(tr("Name 2:", lang_code))

        try:
            self.edit_name1.setPlaceholderText(tr("Edit Current Image 1 Name", lang_code))
            self.edit_name2.setPlaceholderText(tr("Edit Current Image 2 Name", lang_code))
        except Exception:
            pass
        self.btn_image1.setText(tr("Add Image(s) 1", lang_code))
        self.btn_image2.setText(tr("Add Image(s) 2", lang_code))
        self.btn_swap.setToolTip(
            f"{tr('Click: Swap current images', lang_code)}\n{tr('Hold: Swap entire lists', lang_code)}"
        )
        self.btn_clear_list1.setToolTip(
            f"{tr('Click: Remove current image', lang_code)}\n{tr('Hold: Clear entire list', lang_code)}"
        )
        self.btn_clear_list2.setToolTip(
            f"{tr('Click: Remove current image', lang_code)}\n{tr('Hold: Clear entire list', lang_code)}"
        )
        self.btn_quick_save.setToolTip("")
        self.btn_save.setText(tr("Save Result", lang_code))
        self.checkbox_horizontal.setText(tr("Horizontal Split", lang_code))
        self.checkbox_magnifier.setText(tr("Use Magnifier", lang_code))
        self.freeze_button.setText(tr("Freeze Magnifier", lang_code))
        self.checkbox_file_names.setText(
            tr("Include file names in saved image", lang_code)
        )
        self.label_magnifier_size.setText(tr("Magnifier Size (%):", lang_code))
        self.label_capture_size.setText(tr("Capture Size (%):", lang_code))
        self.label_movement_speed.setText(tr("Move Speed:", lang_code))
        self.label_interpolation.setText(tr("Magnifier Interpolation:", lang_code))

        try:
            self._update_checkbox_stretches()
        except Exception:
            pass

    def _update_checkbox_stretches(self):

        checkboxes = [
            self.checkbox_horizontal,
            self.checkbox_magnifier,
            self.freeze_button,
            self.checkbox_file_names,
        ]

        widths = [max(1, cb.sizeHint().width()) for cb in checkboxes]
        for i, w in enumerate(widths):
            self.checkbox_sub_layout.setStretch(i, int(w))

    def update_drag_overlays(self, horizontal: bool = False, visible: bool = False):
        if not self.image_label.isVisible():
            return
        label_geom = self.image_label.geometry()
        margin = 10
        if not horizontal:
            half_width = label_geom.width() // 2
            overlay_w, overlay_h = (
                max(1, half_width - margin - margin // 2),
                max(1, label_geom.height() - 2 * margin),
            )
            self.drag_overlay1.setGeometry(margin, margin, overlay_w, overlay_h)
            self.drag_overlay2.setGeometry(
                half_width + margin // 2, margin, overlay_w, overlay_h
            )
        else:
            half_height = label_geom.height() // 2
            overlay_w, overlay_h = (
                max(1, label_geom.width() - 2 * margin),
                max(1, half_height - margin - margin // 2),
            )
            self.drag_overlay1.setGeometry(margin, margin, overlay_w, overlay_h)
            self.drag_overlay2.setGeometry(
                margin, half_height + margin // 2, overlay_w, overlay_h
            )

        if visible:
            self.drag_overlay1.setText(
                tr("Drop Image(s) 1 Here", self.main_window.app_state.current_language)
            )
            self.drag_overlay2.setText(
                tr("Drop Image(s) 2 Here", self.main_window.app_state.current_language)
            )
            self.drag_overlay1.show()
            self.drag_overlay2.show()
        else:
            self.drag_overlay1.hide()
            self.drag_overlay2.hide()

    def update_resolution_labels(
        self, res1_text: str, tooltip1: str, res2_text: str, tooltip2: str
    ):
        self.resolution_label1.setText(res1_text)
        self.resolution_label2.setText(res2_text)

    def update_file_names_display(
        self,
        name1_text: str,
        name2_text: str,
        is_horizontal: bool,
        current_language: str,
        show_labels: bool,
    ):
        if not show_labels:
            self.file_name_label1.setVisible(False)
            self.file_name_label2.setVisible(False)
            self.file_name_label1.setText("")
            self.file_name_label2.setText("")
            return
        self.file_name_label1.setVisible(True)
        self.file_name_label2.setVisible(True)
        prefix1 = (
            tr("Left", current_language)
            if not is_horizontal
            else tr("Top", current_language)
        )
        prefix2 = (
            tr("Right", current_language)
            if not is_horizontal
            else tr("Bottom", current_language)
        )
        self.file_name_label1.setText(f"{prefix1}: {name1_text}")
        self.file_name_label2.setText(f"{prefix2}: {name2_text}")

    def update_name_length_warning(
        self, warning_text: str, tooltip_text: str, visible: bool
    ):
        self.length_warning_label.setText(warning_text)
        self.length_warning_label.setVisible(visible)

    def update_color_button_tooltip(self, color_name: str, current_language: str):
        pass

    def update_combobox_display(
        self,
        image_number: int,
        count: int,
        current_index: int,
        text: str,
        full_path: str,
    ):
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        combobox.updateState(
            count,
            current_index,
            text=text,
            items=[
                item[2]
                for item in (
                    self.main_window.app_state.image_list1
                    if image_number == 1
                    else self.main_window.app_state.image_list2
                )
            ],
        )

    def update_slider_tooltips(
        self,
        speed_value: float,
        magnifier_size: float,
        capture_size: float,
        current_language: str,
    ):
        pass

    def toggle_magnifier_panel_visibility(self, visible: bool):
        self.magnifier_settings_panel.setVisible(visible)
        self.freeze_button.setEnabled(visible)

    def update_rating_display(
        self, image_number: int, score: int | None, current_language: str
    ):
        label = self.label_rating1 if image_number == 1 else self.label_rating2
        if score is not None:
            label.setText(str(score))
            label.setVisible(True)
        else:
            label.setText("")
            label.setVisible(False)

    def install_rating_wheel_handlers(self):
        def _make_wheel_handler(image_number: int):
            def _wheel(event):
                delta = event.angleDelta().y()
                if delta == 0:
                    return
                if delta > 0:
                    self.main_window.main_controller.increment_rating(image_number, self.main_window.app_state.current_index1 if image_number == 1 else self.main_window.app_state.current_index2)
                else:
                    self.main_window.main_controller.decrement_rating(image_number, self.main_window.app_state.current_index1 if image_number == 1 else self.main_window.app_state.current_index2)
                if self.main_window.presenter:
                    self.main_window.presenter.update_rating_displays()
                event.accept()
            return _wheel
        self.label_rating1.wheelEvent = _make_wheel_handler(1)
        self.label_rating2.wheelEvent = _make_wheel_handler(2)

    def get_current_label_dimensions(self) -> Tuple[int, int]:
        return (
            self.image_label.contentsRect().width(),
            self.image_label.contentsRect().height(),
        )

