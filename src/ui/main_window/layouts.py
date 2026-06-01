from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from resources.translations import tr
from sli_ui_toolkit.widgets import BodyLabel, ButtonGroup, CaptionLabel, Slider
from sli_ui_toolkit.ui.widgets.overlays.drag_drop_overlay import DragDropOverlay
from ui.widgets.startup_placeholder import StartupPlaceholder
from ui.widgets.zoom_indicator import ZoomIndicator

SHOW_WORKSPACE_TABS = False


class LayoutComposer:
    """Builds the main window layout tree from widgets already constructed on `ui`.

    The Ui owns widget creation; LayoutComposer assembles them into containers,
    session pages and overlays, and writes the resulting container widgets back
    onto `ui` as attributes (selection_widget, image_container_widget, ...).
    """

    def __init__(self, ui):
        self.ui = ui

    # --- entry point --------------------------------------------------------

    def build(self, main_window: QWidget) -> None:
        main_layout = QVBoxLayout(main_window)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        main_layout.addLayout(self._workspace_layout())
        self._configure_session_pages()

        ui = self.ui
        ui.selection_widget = self._selection_widget(main_window)
        ui.checkbox_widget = self._checkbox_widget(main_window)
        ui.image_container_layout = self._image_container_layout()
        self._slider_panel_layout()
        ui.image_container_widget = self._image_container_widget()
        ui.image_container_layout.addWidget(ui.magnifier_settings_panel)
        ui.image_container_layout.addWidget(ui.image_label)
        self._create_image_startup_placeholder()
        self._create_zoom_indicator()
        ui.drag_overlay = DragDropOverlay(ui.image_container_widget)
        ui.footer_info_widget = self._footer_info_widget(main_window)
        ui.edit_layout_widget = QWidget()
        ui.edit_layout = self._edit_layout()
        ui.edit_layout_widget.setLayout(ui.edit_layout)
        ui.save_buttons_widget = self._save_buttons_widget()
        self._assemble_image_session_page()
        self._assemble_video_session_page()
        main_layout.addWidget(ui.workspace_stack, 1)

        self._finalize()

    # --- finalization -------------------------------------------------------

    def _finalize(self) -> None:
        ui = self.ui
        ui.toggle_edit_layout_visibility(False)
        ui.magnifier_settings_panel.setVisible(False)
        ui.sync_session_mode("image_compare")
        self.apply_icon_sizes()
        self._configure_workspace_tabs()

    def apply_icon_sizes(self) -> None:
        ui = self.ui
        ui.btn_quick_save.setIconSizePx(24)
        ui.help_button.setIconSizePx(24)
        ui.btn_clear_list1.setIconSizePx(22)
        ui.btn_clear_list2.setIconSizePx(22)
        ui.btn_divider_color.setIconSizePx(22)
        ui.btn_divider_width.setIconSizePx(22)
        ui.btn_magnifier_divider_width.setIconSizePx(22)
        ui.btn_magnifier_guides_width.setIconSizePx(22)

    def _configure_workspace_tabs(self) -> None:
        ui = self.ui
        tabs = ui.workspace_tabs
        tabs.setObjectName("WorkspaceTabs")
        tabs.setDocumentMode(True)
        tabs.setDrawBase(False)
        tabs.setMovable(False)
        tabs.setExpanding(False)
        tabs.setUsesScrollButtons(True)
        tabs.setElideMode(Qt.TextElideMode.ElideRight)
        tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tabs.setMinimumHeight(36)
        settings = getattr(getattr(ui.main_window, "store", None), "settings", None)
        show = (
            getattr(settings, "show_workspace_tabs", SHOW_WORKSPACE_TABS)
            if settings
            else SHOW_WORKSPACE_TABS
        )
        tabs.setVisible(show)
        ui.btn_new_session.setVisible(show)

    # --- workspace / session pages ------------------------------------------

    def _workspace_layout(self) -> QHBoxLayout:
        ui = self.ui
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(6)
        layout.addWidget(ui.workspace_tabs, 1)
        layout.addWidget(ui.btn_new_session, 0, Qt.AlignmentFlag.AlignTop)
        return layout

    def _configure_session_pages(self) -> None:
        ui = self.ui
        ui.workspace_stack.addWidget(ui.image_session_page)
        ui.workspace_stack.addWidget(ui.video_session_page)
        self._install_tab_registry()

    def _install_tab_registry(self) -> None:
        from tabs.contract import TabContext
        from tabs.registry import TabRegistry

        ui = self.ui
        ui._tab_registry = TabRegistry()
        ui._tab_registry.discover()
        context = TabContext(
            store=getattr(ui.main_window, "store", None),
            main_window=ui.main_window,
        )
        ui._tab_registry.install_pages(ui.workspace_stack, context)

    def _assemble_image_session_page(self) -> None:
        ui = self.ui
        layout = QVBoxLayout(ui.image_session_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(ui.selection_widget)
        layout.addWidget(ui.checkbox_widget)
        layout.addWidget(ui.image_container_widget, 1)
        layout.addWidget(ui.footer_info_widget)
        layout.addWidget(ui.length_warning_label)
        layout.addWidget(ui.edit_layout_widget)
        layout.addWidget(ui.save_buttons_widget)

    def _assemble_video_session_page(self) -> None:
        ui = self.ui
        layout = QVBoxLayout(ui.video_session_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(ui.video_session_widget)
        layout.addStretch(1)

    # --- selection / checkbox / image container ------------------------------

    def _selection_widget(self, parent: QWidget) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setSpacing(3)
        layout.addLayout(self._button_row())
        layout.addLayout(self._combobox_row())
        return widget

    def _checkbox_widget(self, parent: QWidget) -> QWidget:
        widget = QWidget(parent)
        widget.setLayout(self._checkbox_layout())
        return widget

    def _image_container_layout(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        return layout

    def _image_container_widget(self) -> QWidget:
        widget = QWidget()
        widget.setLayout(self.ui.image_container_layout)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return widget

    def _create_image_startup_placeholder(self) -> None:
        ui = self.ui
        ui.image_startup_placeholder = StartupPlaceholder(
            ui.image_container_widget, target_widget=ui.image_label
        )

    def _create_zoom_indicator(self) -> None:
        ui = self.ui
        ui.zoom_indicator = ZoomIndicator(
            ui.image_container_widget,
            lang_provider=ui._current_language,
            target_widget=ui.image_label,
        )
        ui.btn_zoom_reset = ui.zoom_indicator.btn_zoom_reset

    # --- footer / resolution / file names -----------------------------------

    def _footer_info_widget(self, parent: QWidget) -> QWidget:
        ui = self.ui
        ui.psnr_label = CaptionLabel("PSNR: --")
        ui.ssim_label = CaptionLabel("SSIM: --")
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.addLayout(self._resolution_layout())
        filenames_layout = self._file_names_layout()
        filenames_layout.setContentsMargins(5, 0, 5, 0)
        layout.addLayout(filenames_layout)
        return widget

    def _resolution_layout(self) -> QHBoxLayout:
        ui = self.ui
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
        ui = self.ui
        layout = QHBoxLayout()
        ui.file_name_label1.setMinimumHeight(22)
        ui.file_name_label2.setMinimumHeight(22)
        layout.addWidget(ui.file_name_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        layout.addWidget(ui.file_name_label2, alignment=Qt.AlignmentFlag.AlignRight)
        layout.setContentsMargins(5, 2, 5, 2)
        return layout

    # --- button row / combobox row ------------------------------------------

    def _button_row(self) -> QHBoxLayout:
        ui = self.ui
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.addWidget(ui.btn_image1)
        layout.addWidget(ui.btn_clear_list1)
        layout.addWidget(ui.btn_swap)
        layout.addWidget(ui.btn_image2)
        layout.addWidget(ui.btn_clear_list2)
        return layout

    def _combobox_row(self) -> QHBoxLayout:
        ui = self.ui
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)
        main_layout.addLayout(self._rated_combo_layout(ui.label_rating1, ui.combo_image1), 1)
        main_layout.addLayout(self._rated_combo_layout(ui.label_rating2, ui.combo_image2), 1)
        ui.combo_image1.image_number = 1
        ui.combo_image2.image_number = 2
        return main_layout

    def _rated_combo_layout(self, rating_label, combo) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(4)
        rating_label.setFixedWidth(30)
        rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rating_label.setProperty("class", "rating-label")
        combo.setMinimumHeight(28)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(rating_label)
        layout.addWidget(combo, 1)
        return layout

    # --- checkbox row -------------------------------------------------------

    def _checkbox_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.addLayout(self._checkbox_groups_layout())
        layout.addStretch(1)
        layout.addLayout(self._checkbox_actions_layout())
        return layout

    def _checkbox_groups_layout(self) -> QHBoxLayout:
        ui = self.ui
        groups_layout = QHBoxLayout()
        groups_layout.setSpacing(16)
        groups_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        ui.line_group_container = self._button_group(
            [ui.btn_orientation], "label.line"
        )
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
        ui = self.ui
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(ui.btn_quick_save)
        layout.addWidget(ui.btn_settings)
        layout.addWidget(ui.help_button)
        return layout

    # --- slider panel -------------------------------------------------------

    def _slider_panel_layout(self) -> QWidget:
        ui = self.ui
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
        ui = self.ui
        layout = QHBoxLayout()
        layout.setSpacing(10)
        self._configure_slider(
            ui.slider_size, minimum=50, maximum=1000,
            label=ui.label_magnifier_size, layout=layout, trailing_spacing=15,
        )
        self._configure_slider(
            ui.slider_capture, minimum=1, maximum=1000,
            label=ui.label_capture_size, layout=layout, trailing_spacing=15,
        )
        self._configure_slider(
            ui.slider_speed, minimum=1, maximum=500,
            label=ui.label_movement_speed, layout=layout,
        )
        return layout

    def _configure_slider(
        self,
        slider: Slider,
        *,
        minimum: int,
        maximum: int,
        label: BodyLabel,
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

    # --- edit / save row ----------------------------------------------------

    def _edit_layout(self) -> QHBoxLayout:
        ui = self.ui
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
        ui = self.ui
        layout = QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        ui.btn_save.setMinimumHeight(32)
        layout.addWidget(ui.btn_save)
        widget = QWidget()
        widget.setLayout(layout)
        return widget
