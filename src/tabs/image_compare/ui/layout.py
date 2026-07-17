"""Layout helpers for the image_compare tab.

Stage 2 of the migration: the helpers that used to live in
``ui.main_window.layouts.LayoutComposer`` are moved here so they
no longer pollute the host. They still operate on the primitive
widgets owned by ``MainWindowUI`` (passed in as ``ui``) — Stage 3
will route those primitives behind tab-owned proxies.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.widgets import ButtonGroup, Label, Slider

from sli_ui_toolkit.i18n import tr
from ui.widgets.startup_placeholder import StartupPlaceholder
from ui.widgets.themed_container import ThemedBackgroundContainer
from ui.widgets.zoom_indicator import ZoomIndicator


class ImageCompareLayoutBuilder:
    """Builds the container widgets that make up the image_compare page.

    Holds a reference to the host UI object (``MainWindowUI``) and reuses
    the primitive widgets already created there (buttons, sliders, the
    canvas, etc.). Mutates ``ui`` by setting attributes for built containers
    (``ui.selection_widget``, ``ui.image_container_widget``, ...) so that
    legacy callers keep working.
    """

    def __init__(self, target, host) -> None:
        self.target = target
        self.host = host

    def build_into(self, page: QWidget) -> QVBoxLayout:
        """Build all containers and assemble them into ``page``.

        Returns the top-level layout installed on ``page``.
        """
        ui = self.target
        ui.selection_widget = self._selection_widget(page)
        ui.checkbox_widget = self._checkbox_widget(page)
        ui.image_container_layout = self._image_container_layout()
        self._slider_panel_layout()
        ui.image_container_widget = self._image_container_widget()
        ui.image_container_layout.addWidget(ui.magnifier_settings_panel)
        ui.image_container_layout.addWidget(ui.image_label)
        self._create_image_startup_placeholder()
        self._create_zoom_indicator()

        from sli_ui_toolkit.ui.widgets.overlays.drag_drop_overlay import DragDropOverlay

        ui.drag_overlay = DragDropOverlay(ui.image_container_widget)
        ui.footer_info_widget = self._footer_info_widget(page)
        ui.edit_layout_widget = ThemedBackgroundContainer()
        ui.edit_layout = self._edit_layout()
        ui.edit_layout_widget.setLayout(ui.edit_layout)
        ui.save_buttons_widget = self._save_buttons_widget()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(ui.selection_widget)
        layout.addWidget(ui.checkbox_widget)
        layout.addWidget(ui.image_container_widget, 1)
        layout.addWidget(ui.footer_info_widget)
        layout.addWidget(ui.length_warning_label)
        layout.addWidget(ui.edit_layout_widget)
        layout.addWidget(ui.save_buttons_widget)
        return layout

    def _selection_widget(self, parent: QWidget) -> QWidget:
        widget = ThemedBackgroundContainer(parent)
        layout = QVBoxLayout(widget)
        layout.setSpacing(3)
        layout.addLayout(self._button_row())
        layout.addLayout(self._combobox_row())
        return widget

    def _checkbox_widget(self, parent: QWidget) -> QWidget:
        widget = ThemedBackgroundContainer(parent)
        widget.setLayout(self._checkbox_layout())
        return widget

    def _image_container_layout(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        return layout

    def _image_container_widget(self) -> QWidget:
        widget = QWidget()
        widget.setLayout(self.target.image_container_layout)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return widget

    def _create_image_startup_placeholder(self) -> None:
        ui = self.target
        ui.image_startup_placeholder = StartupPlaceholder(
            ui.image_container_widget, target_widget=ui.image_label
        )

    def _create_zoom_indicator(self) -> None:
        ui = self.target
        ui.zoom_indicator = ZoomIndicator(
            ui.image_container_widget,
            lang_provider=self.host._current_language,
            target_widget=ui.image_label,
        )
        ui.btn_zoom_reset = ui.zoom_indicator.btn_zoom_reset

    def _footer_info_widget(self, parent: QWidget) -> QWidget:
        ui = self.target
        ui.psnr_label = Label("PSNR: --", variant="group-title")
        ui.ssim_label = Label("SSIM: --", variant="group-title")
        widget = ThemedBackgroundContainer(parent)
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.addLayout(self._resolution_layout())
        filenames_layout = self._file_names_layout()
        filenames_layout.setContentsMargins(5, 0, 5, 0)
        layout.addLayout(filenames_layout)
        return widget

    def _resolution_layout(self) -> QHBoxLayout:
        ui = self.target
        layout = QHBoxLayout()
        layout.addWidget(ui.resolution_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        layout.addWidget(ui.psnr_label)
        layout.addSpacing(15)
        layout.addWidget(ui.ssim_label)
        layout.addStretch()
        layout.addWidget(ui.resolution_label2, alignment=Qt.AlignmentFlag.AlignRight)
        layout.setContentsMargins(5, 0, 5, 0)
        return layout

    def _file_names_layout(self) -> QHBoxLayout:
        ui = self.target
        layout = QHBoxLayout()
        ui.file_name_label1.setMinimumHeight(22)
        ui.file_name_label2.setMinimumHeight(22)
        layout.addWidget(ui.file_name_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        layout.addWidget(ui.file_name_label2, alignment=Qt.AlignmentFlag.AlignRight)
        layout.setContentsMargins(5, 2, 5, 2)
        return layout

    def _button_row(self) -> QHBoxLayout:
        ui = self.target
        layout = QHBoxLayout()
        layout.setSpacing(8)
        ui.btn_image1.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        ui.btn_image2.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(ui.btn_image1, 1)
        layout.addWidget(ui.btn_clear_list1)
        layout.addWidget(ui.btn_swap)
        layout.addWidget(ui.btn_image2, 1)
        layout.addWidget(ui.btn_clear_list2)
        return layout

    def _combobox_row(self) -> QHBoxLayout:
        ui = self.target
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)
        main_layout.addLayout(
            self._rated_combo_layout(ui.label_rating1, ui.combo_image1), 1
        )
        main_layout.addLayout(
            self._rated_combo_layout(ui.label_rating2, ui.combo_image2), 1
        )
        ui.combo_image1.image_number = 1
        ui.combo_image2.image_number = 2
        return main_layout

    def _rated_combo_layout(self, rating_label, combo) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(4)
        rating_label.setFixedWidth(30)
        rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if hasattr(rating_label, "setBold"):
            rating_label.setBold(True)
        if hasattr(rating_label, "setPixelSize"):
            rating_label.setPixelSize(14)
        combo.setMinimumHeight(28)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(rating_label)
        layout.addWidget(combo, 1)
        return layout

    def _checkbox_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.addLayout(self._checkbox_groups_layout())
        layout.addStretch(1)
        layout.addLayout(self._checkbox_actions_layout())
        return layout

    def _checkbox_groups_layout(self) -> QHBoxLayout:
        ui = self.target
        groups_layout = QHBoxLayout()
        groups_layout.setSpacing(16)
        groups_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        ui.line_group_container = self._button_group([ui.btn_orientation], "label.line")
        ui.view_group_container = self._button_group(
            [ui.btn_diff_mode, ui.btn_channel_mode, ui.btn_file_names], "label.view"
        )
        ui.magnifier_group_container = self._button_group(
            [
                ui.btn_magnifier,
                ui.btn_magnifier_instances,
                ui.btn_freeze,
                ui.btn_magnifier_orientation,
                ui.btn_magnifier_color_settings,
                ui.btn_magnifier_guides,
            ],
            "label.magnifier",
        )
        ui.record_group_container = self._button_group(
            [ui.btn_record, ui.btn_pause, ui.btn_video_editor], "button.record"
        )
        for container in (
            ui.line_group_container,
            ui.view_group_container,
            ui.magnifier_group_container,
            ui.record_group_container,
        ):
            groups_layout.addWidget(container)
        return groups_layout

    def _button_group(self, buttons, label_key: str) -> ButtonGroup:
        return ButtonGroup(buttons, label=tr(label_key, "en"))

    def _checkbox_actions_layout(self) -> QHBoxLayout:
        ui = self.target
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(ui.btn_quick_save)
        return layout

    def _slider_panel_layout(self) -> QWidget:
        ui = self.target
        panel = ui.magnifier_settings_panel
        panel_layout = QVBoxLayout(panel)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(5)
        panel_layout.addLayout(self._magnifier_sliders_row())

        interpolation_layout = QHBoxLayout()
        interpolation_layout.setSpacing(5)
        ui.combo_interpolation.setMinimumHeight(28)
        ui.combo_interpolation.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        interpolation_layout.addWidget(ui.label_interpolation)
        interpolation_layout.addWidget(ui.combo_interpolation)
        interpolation_layout.addStretch()
        panel_layout.addLayout(interpolation_layout)
        return panel

    def _magnifier_sliders_row(self) -> QHBoxLayout:
        ui = self.target
        layout = QHBoxLayout()
        layout.setSpacing(10)
        self._configure_slider(
            ui.slider_size,
            minimum=50,
            maximum=1000,
            label=ui.label_magnifier_size,
            layout=layout,
            trailing_spacing=15,
        )
        self._configure_slider(
            ui.slider_capture,
            minimum=1,
            maximum=1000,
            label=ui.label_capture_size,
            layout=layout,
            trailing_spacing=15,
        )
        self._configure_slider(
            ui.slider_speed,
            minimum=1,
            maximum=500,
            label=ui.label_movement_speed,
            layout=layout,
        )
        return layout

    def _configure_slider(
        self,
        slider: Slider,
        *,
        minimum: int,
        maximum: int,
        label: Label,
        layout: QHBoxLayout,
        trailing_spacing: int = 0,
    ) -> None:
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setMinimumWidth(80)
        slider.setFixedHeight(28)
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(slider, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        if trailing_spacing:
            layout.addSpacing(trailing_spacing)

    def _edit_layout(self) -> QHBoxLayout:
        ui = self.target
        layout = QHBoxLayout()
        layout.setSpacing(8)
        ui.edit_name1.setMinimumHeight(30)
        ui.edit_name2.setMinimumHeight(30)
        layout.addWidget(ui.label_edit_name1)
        layout.addWidget(ui.edit_name1, 1)
        layout.addSpacing(5)
        layout.addWidget(ui.label_edit_name2)
        layout.addWidget(ui.edit_name2, 1)
        layout.addSpacing(10)
        layout.addWidget(ui.btn_text_settings)
        return layout

    def _save_buttons_widget(self) -> QWidget:
        ui = self.target
        layout = QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(5, 2, 5, 2)
        ui.btn_save.setMinimumHeight(32)
        ui.btn_save.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(ui.btn_save, 1)
        widget = ThemedBackgroundContainer()
        widget.setLayout(layout)
        return widget
