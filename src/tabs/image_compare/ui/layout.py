"""Layout helpers for the image_compare tab.

Stage 2 of the migration: the helpers that used to live in
``ui.main_window.layouts.LayoutComposer`` are moved here so they
no longer pollute the host. They still operate on the primitive
widgets owned by ``MainWindowUI`` (passed in as ``ui``) — Stage 3
will route those primitives behind tab-owned proxies.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.widgets import ButtonGroup, Label, Slider

from sli_ui_toolkit.i18n import tr
from tabs.image_compare.icons import Icon, get_icon
from tabs.layout_constants import CONTROL_EDGE_PADDING_PX
from ui.widgets.info_hud import InfoHUD
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
        ui.image_container_layout.addWidget(ui.image_label)
        self._create_image_startup_placeholder()
        self._create_zoom_indicator()
        self._create_info_huds()

        from sli_ui_toolkit.ui.widgets.overlays.drag_drop_overlay import DragDropOverlay

        ui.drag_overlay = DragDropOverlay(ui.image_container_widget)
        ui.footer_info_widget = self._footer_info_widget(page)
        ui.edit_layout_widget = ThemedBackgroundContainer()
        ui.edit_layout = self._edit_layout()
        ui.edit_layout_widget.setLayout(ui.edit_layout)
        ui.save_buttons_widget = self._save_buttons_widget()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, CONTROL_EDGE_PADDING_PX, 0, 0)
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
        layout.setContentsMargins(CONTROL_EDGE_PADDING_PX, 0, CONTROL_EDGE_PADDING_PX, 0)
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

    def _create_info_huds(self) -> None:
        ui = self.target
        ui.image_info_hud1 = InfoHUD(ui.image_container_widget, corner="left")
        ui.image_info_hud1.add_label(ui.resolution_label1)
        ui.image_info_hud1.add_label(ui.file_name_label1)
        ui.image_info_hud1.show_on(ui.image_label)

        ui.image_info_hud2 = InfoHUD(ui.image_container_widget, corner="right")
        ui.image_info_hud2.add_label(ui.resolution_label2)
        ui.image_info_hud2.add_label(ui.file_name_label2)
        ui.image_info_hud2.show_on(ui.image_label)

    def _footer_info_widget(self, parent: QWidget) -> QWidget:
        ui = self.target
        ui.psnr_label = Label("PSNR: --", variant="group-title")
        ui.ssim_label = Label("SSIM: --", variant="group-title")
        widget = ThemedBackgroundContainer(parent)
        layout = QHBoxLayout(widget)
        layout.addStretch()
        layout.addWidget(ui.psnr_label)
        layout.addSpacing(15)
        layout.addWidget(ui.ssim_label)
        layout.addStretch()
        layout.setContentsMargins(CONTROL_EDGE_PADDING_PX, 4, CONTROL_EDGE_PADDING_PX, 4)
        return widget

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
        layout.setContentsMargins(CONTROL_EDGE_PADDING_PX, 0, CONTROL_EDGE_PADDING_PX, 0)
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
        panel_layout.setContentsMargins(
            CONTROL_EDGE_PADDING_PX, 0, CONTROL_EDGE_PADDING_PX, 0
        )
        panel_layout.setSpacing(5)
        panel_layout.addLayout(self._magnifier_sliders_column())

        interpolation_layout = QHBoxLayout()
        interpolation_layout.setSpacing(5)
        ui.combo_interpolation.setMinimumHeight(28)
        ui.combo_interpolation.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        ui.label_interpolation.hide()
        interpolation_layout.addStretch(1)
        interpolation_layout.addWidget(ui.combo_interpolation)
        interpolation_layout.addStretch(1)
        panel_layout.addLayout(interpolation_layout)
        return panel

    def _magnifier_sliders_column(self) -> QVBoxLayout:
        ui = self.target
        column = QVBoxLayout()
        column.setSpacing(6)
        column.addLayout(
            self._configure_slider(
                ui.slider_size,
                minimum=50,
                maximum=1000,
                icon=Icon.MAGNIFIER_SIZE,
                icon_attr="icon_magnifier_size",
                label=ui.label_magnifier_size,
            )
        )
        column.addLayout(
            self._configure_slider(
                ui.slider_capture,
                minimum=1,
                maximum=1000,
                icon=Icon.CAPTURE_SIZE,
                icon_attr="icon_capture_size",
                label=ui.label_capture_size,
            )
        )
        column.addLayout(
            self._configure_slider(
                ui.slider_speed,
                minimum=1,
                maximum=500,
                icon=Icon.MOVEMENT_SPEED,
                icon_attr="icon_movement_speed",
                label=ui.label_movement_speed,
            )
        )
        return column

    def _configure_slider(
        self,
        slider: Slider,
        *,
        minimum: int,
        maximum: int,
        icon: Icon,
        icon_attr: str,
        label: Label,
    ) -> QHBoxLayout:
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setMinimumWidth(80)
        slider.setFixedHeight(28)
        # Text label is kept alive (translations.py still updates it) but not
        # shown -- the icon is the row's only leading element now, and carries
        # the same text as a tooltip (see translations.py _bind_slider_labels).
        label.hide()
        icon_label = self._slider_icon(icon)
        setattr(self.target, icon_attr, icon_label)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(slider, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row

    def _slider_icon(self, icon: Icon) -> QLabel:
        pixmap_label = QLabel()
        pixmap_label.setPixmap(get_icon(icon).pixmap(QSize(18, 18)))
        pixmap_label.setFixedSize(18, 18)
        return pixmap_label

    def _edit_layout(self) -> QHBoxLayout:
        ui = self.target
        layout = QHBoxLayout()
        layout.setContentsMargins(CONTROL_EDGE_PADDING_PX, 0, CONTROL_EDGE_PADDING_PX, 0)
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
        layout.setContentsMargins(
            CONTROL_EDGE_PADDING_PX, 0, CONTROL_EDGE_PADDING_PX, 6
        )
        ui.btn_save.setMinimumHeight(32)
        ui.btn_save.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(ui.btn_save, 1)
        widget = ThemedBackgroundContainer()
        widget.setFixedHeight(42)
        widget.setLayout(layout)
        return widget
