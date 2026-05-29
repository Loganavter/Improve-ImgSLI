import logging
from typing import Tuple

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from resources.translations import tr
from sli_ui_toolkit.widgets import (
    BodyLabel,
    Button,
    ButtonGroup,
    CaptionLabel,
    CustomLineEdit,
    InstancesCounterButton,
    ScrollableComboBox,
    Slider,
)
from ui.widgets.magnifier_color_controls import ColorSettingsButton
from sli_ui_toolkit.ui.widgets.overlays.drag_drop_overlay import DragDropOverlay
from ui.icon_manager import AppIcon
from ui.widgets import VideoSessionWidget
from ui.widgets.gl_canvas import GLCanvas

logger = logging.getLogger("ImproveImgSLI")

SHOW_WORKSPACE_TABS = False

class _RoundedOverlayWidget(QWidget):
    """Child widget that paints its own AA rounded background.
    Works correctly when hosted over a QOpenGLWidget where QSS border-radius
    on a child widget leaves a leaking rectangle outside the rounded shape."""

    def __init__(self, parent=None, *, bg_color=QColor(0, 0, 0, 140), radius=6):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._bg_color = bg_color
        self._radius = float(radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(self.rect(), self._radius, self._radius)
        painter.end()

class Ui_ImageComparisonApp:
    def setupUi(self, main_window: QWidget):
        self.main_window = main_window
        self._create_static_widgets(main_window)
        self._create_selection_controls(main_window)
        self._create_view_controls(main_window)
        self._create_video_controls(main_window)
        self._create_slider_controls(main_window)
        self._create_text_and_status_widgets(main_window)
        self._configure_core_widgets()
        self._build_main_window_layout(main_window)
        self._finalize_ui_state()

    def _create_static_widgets(self, main_window: QWidget):
        self.resolution_label1 = CaptionLabel("--x--")
        self.resolution_label2 = CaptionLabel("--x--")
        self.magnifier_settings_panel = QWidget(main_window)
        self.image_label = GLCanvas(main_window)
        self.length_warning_label = BodyLabel(main_window)
        self.workspace_tabs = QTabBar(main_window)
        self.btn_new_session = Button(AppIcon.ADD, menu=[], parent=main_window)
        self.workspace_stack = QStackedWidget(main_window)
        self.image_session_page = QWidget(main_window)
        self.video_session_page = QWidget(main_window)
        self.video_session_widget = VideoSessionWidget(main_window)
        self._tab_registry = None

    def _create_selection_controls(self, parent: QWidget):
        self.btn_image1 = Button(AppIcon.PHOTO, text="", variant="primary", parent=parent)
        self.btn_image2 = Button(AppIcon.PHOTO, text="", variant="primary", parent=parent)

        self.btn_swap = Button(AppIcon.SYNC, long_press=True, variant="accent", parent=parent)
        self.btn_clear_list1 = Button(AppIcon.DELETE, long_press=True, variant="delete", parent=parent)
        self.btn_clear_list2 = Button(AppIcon.DELETE, long_press=True, variant="delete", parent=parent)
        self.help_button = Button(AppIcon.HELP, variant="accent", parent=parent)
        self.btn_settings = Button(AppIcon.SETTINGS, variant="accent", parent=parent)

        self.btn_text_settings = Button(AppIcon.TEXT_MANIPULATOR, variant="accent", parent=parent)
        self.btn_quick_save = Button(AppIcon.QUICK_SAVE, variant="accent", parent=parent)
        self.btn_magnifier_orientation = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
            toggle=True, scrollable=(0, 10), show_underline=True, parent=parent,
        )
        self.btn_save = Button(AppIcon.SAVE, text="", variant="primary", parent=parent)

        self.label_rating1 = CaptionLabel("–", parent)
        self.label_rating2 = CaptionLabel("–", parent)
        self.combo_image1 = ScrollableComboBox(parent)
        self.combo_image2 = ScrollableComboBox(parent)
        self.combo_interpolation = ScrollableComboBox(parent)
        self.combo_interpolation.setAutoWidthEnabled(True)

    def _create_view_controls(self, parent: QWidget):
        self.btn_orientation = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT),
            toggle=True, scrollable=(0, 20), show_underline=True, parent=parent,
        )
        self.btn_magnifier = Button(AppIcon.MAGNIFIER, toggle=True, parent=parent)
        self.btn_magnifier_instances = InstancesCounterButton(parent=parent)
        self.btn_freeze = Button(AppIcon.FREEZE, toggle=True, parent=parent)
        self.btn_file_names = Button(AppIcon.TEXT_FILENAME, toggle=True, parent=parent)

        self.btn_diff_mode = Button(AppIcon.HIGHLIGHT_DIFFERENCES, menu=[], parent=parent)
        self.btn_channel_mode = Button(AppIcon.PHOTO, menu=[], parent=parent)

        self.btn_magnifier_color_settings = ColorSettingsButton(parent=parent, current_language="en")

        self.btn_magnifier_guides = Button(
            AppIcon.MAGNIFIER_GUIDES, toggle=True, scrollable=(0, 10),
            show_underline=True, parent=parent,
        )

        self.btn_orientation_simple = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT), toggle=True, parent=parent,
        )
        self.btn_divider_visible = Button(
            icon=(AppIcon.DIVIDER_VISIBLE, AppIcon.DIVIDER_HIDDEN), toggle=True, parent=parent,
        )
        self.btn_divider_color = Button(AppIcon.DIVIDER_COLOR, show_underline=True, parent=parent)
        self.btn_divider_width = Button(
            AppIcon.DIVIDER_WIDTH, scrollable=(1, 20), show_underline=True, parent=parent,
        )
        self.btn_magnifier_orientation_simple = Button(
            icon=(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT), toggle=True, parent=parent,
        )
        self.btn_magnifier_divider_visible = Button(
            icon=(AppIcon.DIVIDER_VISIBLE, AppIcon.DIVIDER_HIDDEN), toggle=True, parent=parent,
        )

        self.btn_magnifier_color_settings_beginner = ColorSettingsButton(
            parent=parent, current_language="en"
        )
        self.btn_magnifier_divider_width = Button(
            AppIcon.DIVIDER_WIDTH, scrollable=(1, 10), show_underline=True, parent=parent,
        )

        self.btn_magnifier_guides_simple = Button(AppIcon.MAGNIFIER_GUIDES, toggle=True, parent=parent)
        self.btn_magnifier_guides_width = Button(
            AppIcon.DIVIDER_WIDTH, scrollable=(1, 10), show_underline=True, parent=parent,
        )

    def _create_video_controls(self, parent: QWidget):
        self.btn_record = Button(icon=(AppIcon.RECORD, AppIcon.STOP), toggle=True, parent=parent)
        self.btn_pause = Button(icon=(AppIcon.PAUSE, AppIcon.PLAY), toggle=True, parent=parent)
        self.btn_pause.setEnabled(False)

        self.btn_video_editor = Button(AppIcon.EXPORT_VIDEO, show_underline=True, parent=parent)

    def _create_slider_controls(self, parent: QWidget):
        self.slider_size = Slider(Qt.Orientation.Horizontal, parent)
        self.slider_capture = Slider(Qt.Orientation.Horizontal, parent)
        self.slider_speed = Slider(Qt.Orientation.Horizontal, parent)

    def _create_text_and_status_widgets(self, parent: QWidget):
        self.edit_name1 = CustomLineEdit(parent)
        self.edit_name2 = CustomLineEdit(parent)
        self.label_magnifier_size = BodyLabel(parent)
        self.label_capture_size = BodyLabel(parent)
        self.label_movement_speed = BodyLabel(parent)
        self.label_interpolation = BodyLabel(parent)

        self.file_name_label1 = CaptionLabel("--", parent)
        self.file_name_label2 = CaptionLabel("--", parent)
        self.label_edit_name1 = BodyLabel(parent)
        self.label_edit_name2 = BodyLabel(parent)

    def _configure_core_widgets(self):
        self._configure_image_label()
        self._init_drag_overlays()
        self._init_warning_label()

    def _build_main_window_layout(self, main_window: QWidget):
        main_layout = QVBoxLayout(main_window)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        main_layout.addLayout(self._create_workspace_layout())
        self._configure_session_pages()
        self.selection_widget = self._create_selection_widget(main_window)
        self.checkbox_widget = self._create_checkbox_widget(main_window)
        self.image_container_layout = self._create_image_container_layout()
        self._create_slider_layout()
        self.image_container_widget = self._create_image_container_widget()
        self.image_container_layout.addWidget(self.magnifier_settings_panel)
        self.image_container_layout.addWidget(self.image_label)
        self._create_image_startup_placeholder()
        self._create_zoom_indicator()
        self.drag_overlay = DragDropOverlay(self.image_container_widget)
        self.footer_info_widget = self._create_footer_info_widget(main_window)
        self.edit_layout_widget = QWidget()
        self.edit_layout = self._create_edit_layout()
        self.edit_layout_widget.setLayout(self.edit_layout)
        self.save_buttons_widget = self._create_save_buttons_widget()
        self._assemble_image_session_page()
        self._assemble_video_session_page()
        main_layout.addWidget(self.workspace_stack, 1)

    def _finalize_ui_state(self):
        self.toggle_edit_layout_visibility(False)
        self.magnifier_settings_panel.setVisible(False)
        self.sync_session_mode("image_compare")
        self._post_init_icons_and_sizes()
        self._configure_workspace_tabs()

    def _create_selection_widget(self, parent: QWidget) -> QWidget:
        selection_widget = QWidget(parent)
        selection_layout = QVBoxLayout(selection_widget)
        selection_layout.setSpacing(3)
        selection_layout.addLayout(self._create_button_layout())
        selection_layout.addLayout(self._create_combobox_layout())
        return selection_widget

    def _create_checkbox_widget(self, parent: QWidget) -> QWidget:
        checkbox_widget = QWidget(parent)
        checkbox_widget.setLayout(self._create_checkbox_layout())
        return checkbox_widget

    def _create_image_container_layout(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        return layout

    def _create_image_container_widget(self) -> QWidget:
        widget = QWidget()
        widget.setLayout(self.image_container_layout)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return widget

    def _create_footer_info_widget(self, parent: QWidget) -> QWidget:
        self.psnr_label = CaptionLabel("PSNR: --")
        self.ssim_label = CaptionLabel("SSIM: --")
        footer_info_widget = QWidget(parent)
        resolutions_and_filenames_group_layout = QVBoxLayout(footer_info_widget)
        resolutions_and_filenames_group_layout.setSpacing(0)
        resolutions_and_filenames_group_layout.addLayout(
            self._create_resolution_layout()
        )
        filenames_layout = self._create_file_names_layout()
        filenames_layout.setContentsMargins(5, 0, 5, 0)
        resolutions_and_filenames_group_layout.addLayout(filenames_layout)
        return footer_info_widget

    def _create_resolution_layout(self) -> QHBoxLayout:
        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(
            self.resolution_label1, alignment=Qt.AlignmentFlag.AlignLeft
        )
        resolution_layout.addStretch()
        resolution_layout.addWidget(self.psnr_label)
        resolution_layout.addSpacing(15)
        resolution_layout.addWidget(self.ssim_label)
        resolution_layout.addStretch()
        resolution_layout.addWidget(
            self.resolution_label2, alignment=Qt.AlignmentFlag.AlignRight
        )
        resolution_layout.setContentsMargins(5, 0, 5, 0)
        return resolution_layout

    def _post_init_icons_and_sizes(self):
        self.btn_quick_save.setIconSizePx(24)
        self.help_button.setIconSizePx(24)
        self.btn_clear_list1.setIconSizePx(22)
        self.btn_clear_list2.setIconSizePx(22)
        self.btn_divider_color.setIconSizePx(22)
        self.btn_divider_width.setIconSizePx(22)
        self.btn_magnifier_divider_width.setIconSizePx(22)
        self.btn_magnifier_guides_width.setIconSizePx(22)

    def _configure_workspace_tabs(self):
        self.workspace_tabs.setObjectName("WorkspaceTabs")
        self.workspace_tabs.setDocumentMode(True)
        self.workspace_tabs.setDrawBase(False)
        self.workspace_tabs.setMovable(False)
        self.workspace_tabs.setExpanding(False)
        self.workspace_tabs.setUsesScrollButtons(True)
        self.workspace_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.workspace_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.workspace_tabs.setMinimumHeight(36)
        show = getattr(getattr(self.main_window, "store", None), "settings", None)
        show = getattr(show, "show_workspace_tabs", SHOW_WORKSPACE_TABS) if show else SHOW_WORKSPACE_TABS
        self.workspace_tabs.setVisible(show)
        self.btn_new_session.setVisible(show)

    def _configure_session_pages(self):
        self.workspace_stack.addWidget(self.image_session_page)
        self.workspace_stack.addWidget(self.video_session_page)
        self._install_tab_registry()

    def _assemble_image_session_page(self):
        layout = QVBoxLayout(self.image_session_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.selection_widget)
        layout.addWidget(self.checkbox_widget)
        layout.addWidget(self.image_container_widget, 1)
        layout.addWidget(self.footer_info_widget)
        layout.addWidget(self.length_warning_label)
        layout.addWidget(self.edit_layout_widget)
        layout.addWidget(self.save_buttons_widget)

    def _assemble_video_session_page(self):
        layout = QVBoxLayout(self.video_session_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.video_session_widget)
        layout.addStretch(1)

    def _install_tab_registry(self):
        from tabs.contract import TabContext
        from tabs.registry import TabRegistry

        self._tab_registry = TabRegistry()
        self._tab_registry.discover()

        context = TabContext(
            store=getattr(self.main_window, "store", None),
            main_window=self.main_window,
        )
        self._tab_registry.install_pages(self.workspace_stack, context)

    def _create_workspace_layout(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(6)
        layout.addWidget(self.workspace_tabs, 1)
        layout.addWidget(self.btn_new_session, 0, Qt.AlignmentFlag.AlignTop)
        return layout

    def sync_workspace_tabs(self, sessions, active_session_id):
        self.workspace_tabs.blockSignals(True)
        while self.workspace_tabs.count() > 0:
            self.workspace_tabs.removeTab(0)

        active_index = -1
        for index, session in enumerate(sessions):
            self.workspace_tabs.addTab(session.title)
            self.workspace_tabs.setTabData(index, session.id)
            self.workspace_tabs.setTabToolTip(
                index, f"{session.title} [{session.session_type}]"
            )
            if session.id == active_session_id:
                active_index = index

        if active_index >= 0:
            self.workspace_tabs.setCurrentIndex(active_index)

        self.workspace_tabs.blockSignals(False)

    def sync_session_mode(self, session_type: str, session_title: str | None = None):
        is_image_session = session_type == "image_compare"

        tab_page = (
            self._tab_registry.get_page(session_type)
            if self._tab_registry
            else None
        )
        if tab_page is not None:
            self.workspace_stack.setCurrentWidget(tab_page)
            if self._tab_registry:
                self._tab_registry.activate(session_type)
        elif is_image_session:
            self.workspace_stack.setCurrentWidget(self.image_session_page)
        else:
            self.workspace_stack.setCurrentWidget(self.video_session_page)

        self.edit_layout_widget.setVisible(
            is_image_session and self.btn_file_names.isChecked()
        )

        if session_type == "video":
            title = session_title or session_type.replace("_", " ").title()
            self.video_session_widget.title_label.setText(title)

    def _update_button_group_container(self, container, buttons):
        layout = container.layout()
        if layout:

            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)

            for btn in buttons:
                layout.addWidget(btn)

    def reapply_button_styles(self):

        self._post_init_icons_and_sizes()

        for btn in [self.btn_settings, self.btn_quick_save, self.help_button]:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

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
        self.label_rating1.setFixedWidth(30)
        self.label_rating1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_rating1.setProperty("class", "rating-label")
        self.combo_image1.setMinimumHeight(28)
        self.combo_image1.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout1.addWidget(self.label_rating1)
        layout1.addWidget(self.combo_image1, 1)
        layout2 = QHBoxLayout()
        layout2.setSpacing(4)
        self.label_rating2.setFixedWidth(30)
        self.label_rating2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_rating2.setProperty("class", "rating-label")
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
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)
        main_layout.addLayout(self._create_checkbox_groups_layout())
        main_layout.addStretch(1)
        main_layout.addLayout(self._create_checkbox_actions_layout())
        return main_layout

    def _create_slider_layout(self):
        panel_layout = QVBoxLayout(self.magnifier_settings_panel)
        self.magnifier_settings_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(5)
        panel_layout.addLayout(self._create_magnifier_sliders_row())
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

    def _create_checkbox_groups_layout(self) -> QHBoxLayout:
        groups_layout = QHBoxLayout()
        groups_layout.setSpacing(16)
        groups_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.line_group_container = self._create_button_group_container(
            [self.btn_orientation], "label.line"
        )
        self.view_group_container = self._create_button_group_container(
            [self.btn_diff_mode, self.btn_channel_mode, self.btn_file_names],
            "label.view",
        )
        self.magnifier_group_container = self._create_button_group_container(
            [
                self.btn_magnifier,
                self.btn_magnifier_instances,
                self.btn_freeze,
                self.btn_magnifier_orientation,
                self.btn_magnifier_color_settings,
                self.btn_magnifier_guides,
            ],
            "label.magnifier",
        )
        self.record_group_container = self._create_button_group_container(
            [self.btn_record, self.btn_pause, self.btn_video_editor],
            "button.record",
        )
        for container in (
            self.line_group_container,
            self.view_group_container,
            self.magnifier_group_container,
            self.record_group_container,
        ):
            groups_layout.addWidget(container)
        return groups_layout

    def _create_button_group_container(self, buttons, label_key: str):
        return ButtonGroup(buttons, label=tr(label_key, "en"))

    def _create_checkbox_actions_layout(self) -> QHBoxLayout:
        buttons_sub_layout = QHBoxLayout()
        buttons_sub_layout.setSpacing(8)
        buttons_sub_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        buttons_sub_layout.addWidget(self.btn_quick_save)
        buttons_sub_layout.addWidget(self.btn_settings)
        buttons_sub_layout.addWidget(self.help_button)
        return buttons_sub_layout

    def _create_magnifier_sliders_row(self) -> QHBoxLayout:
        sliders_main_layout = QHBoxLayout()
        sliders_main_layout.setSpacing(10)
        self._configure_slider(
            self.slider_size,
            minimum=50,
            maximum=1000,
            label=self.label_magnifier_size,
            layout=sliders_main_layout,
            trailing_spacing=15,
        )
        self._configure_slider(
            self.slider_capture,
            minimum=1,
            maximum=1000,
            label=self.label_capture_size,
            layout=sliders_main_layout,
            trailing_spacing=15,
        )
        self._configure_slider(
            self.slider_speed,
            minimum=1,
            maximum=500,
            label=self.label_movement_speed,
            layout=sliders_main_layout,
        )
        return sliders_main_layout

    def _configure_slider(
        self,
        slider: Slider,
        *,
        minimum: int,
        maximum: int,
        label: BodyLabel,
        layout: QHBoxLayout,
        trailing_spacing: int = 0,
    ):
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setMinimumWidth(80)
        slider.setFixedHeight(28)
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(slider, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        if trailing_spacing:
            layout.addSpacing(trailing_spacing)

    def _configure_image_label(self):
        self.image_label.setMinimumSize(200, 150)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMouseTracking(True)
        self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.image_label.setAutoFillBackground(True)

    def _create_image_startup_placeholder(self):
        self.image_startup_placeholder = QWidget(self.image_container_widget)
        self.image_startup_placeholder.setObjectName("ImageStartupPlaceholder")
        self.image_startup_placeholder.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        layout = QVBoxLayout(self.image_startup_placeholder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        self.image_startup_placeholder_label = QLabel("", self.image_startup_placeholder)
        self.image_startup_placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_startup_placeholder_label.hide()
        layout.addWidget(
            self.image_startup_placeholder_label,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        layout.addStretch(1)

        self.sync_image_startup_placeholder()
        self.image_startup_placeholder.show()
        self.image_startup_placeholder.raise_()

    def sync_image_startup_placeholder(self):
        if not hasattr(self, "image_startup_placeholder"):
            return
        self.image_startup_placeholder.setGeometry(self.image_label.geometry())
        self.image_startup_placeholder.raise_()

    def hide_image_startup_placeholder(self):
        if hasattr(self, "image_startup_placeholder"):
            self.image_startup_placeholder.hide()

    def _create_zoom_indicator(self):
        self.zoom_indicator = _RoundedOverlayWidget(
            self.image_container_widget,
            bg_color=QColor(0, 0, 0, 140),
            radius=6,
        )
        self.zoom_indicator.setObjectName("ZoomIndicator")
        self.zoom_indicator.setStyleSheet(
            "#ZoomIndicator QLabel { color: white; padding: 0 6px; background: transparent; }"
        )
        layout = QHBoxLayout(self.zoom_indicator)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)
        self.zoom_indicator_label = QLabel("100%", self.zoom_indicator)
        layout.addWidget(self.zoom_indicator_label)
        self.btn_zoom_reset = Button(AppIcon.SYNC, parent=self.zoom_indicator)
        self.btn_zoom_reset.setFixedSize(QSize(22, 22))
        self.btn_zoom_reset.setToolTip("Reset zoom")
        layout.addWidget(self.btn_zoom_reset)
        self.zoom_indicator.adjustSize()
        self.zoom_indicator.hide()
        self.update_zoom_indicator(1.0)

    def _zoom_label_prefix(self) -> str:
        try:
            lang = self.main_window.store.settings.current_language
        except AttributeError:
            lang = "en"
        return tr("label.zoom", lang)

    def update_zoom_indicator(self, zoom: float):
        if not hasattr(self, "zoom_indicator"):
            return
        percent = int(round(float(zoom) * 100))
        self.zoom_indicator_label.setText(f"{self._zoom_label_prefix()}: {percent}%")
        self.zoom_indicator.adjustSize()
        pan_x = float(getattr(self.image_label, "pan_offset_x", 0.0) or 0.0)
        pan_y = float(getattr(self.image_label, "pan_offset_y", 0.0) or 0.0)
        visible = (
            abs(float(zoom) - 1.0) > 1e-3
            or abs(pan_x) > 1e-4
            or abs(pan_y) > 1e-4
        )
        self.zoom_indicator.setVisible(visible)
        if visible:
            self.sync_zoom_indicator()
            self.zoom_indicator.raise_()

    def sync_zoom_indicator(self):
        if not hasattr(self, "zoom_indicator") or not self.zoom_indicator.isVisible():
            return
        label_geo = self.image_label.geometry()
        margin = 8
        w = self.zoom_indicator.width()
        h = self.zoom_indicator.height()
        x = label_geo.right() - w - margin
        y = label_geo.top() + margin
        self.zoom_indicator.move(x, y)
        self.zoom_indicator.raise_()

    def set_image_startup_placeholder_color(self, color):
        if not hasattr(self, "image_startup_placeholder"):
            return
        self.image_startup_placeholder.setStyleSheet(
            f"background-color: {color.name(color.NameFormat.HexArgb)};"
        )

    def _create_file_names_layout(self):
        layout = QHBoxLayout()

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
        edit_outer_layout.addWidget(self.btn_text_settings)
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
        self.image_label.set_drag_overlay_state(False)
        if hasattr(self, "drag_overlay"):
            self.drag_overlay.hide()

    def is_drag_overlay_visible(self) -> bool:
        return self.image_label.is_drag_overlay_visible()

    def _init_warning_label(self):
        self.length_warning_label.setProperty("class", "warning-label")
        self.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.length_warning_label.setVisible(False)

    def toggle_edit_layout_visibility(self, checked: bool):
        self.edit_layout_widget.setVisible(bool(checked))

    def update_translations(self, lang_code: str):
        self.main_window.setWindowTitle(tr("app.name", lang_code))
        self._update_translation_labels(lang_code)
        self._update_translation_placeholders(lang_code)
        self._update_translation_buttons(lang_code)
        self._update_translation_tooltips(lang_code)
        self._update_translation_group_titles(lang_code)
        self._update_translation_slider_labels(lang_code)

    def _update_translation_labels(self, lang_code: str):
        self.label_edit_name1.setText(tr("label.name_1", lang_code) + ":")
        self.label_edit_name2.setText(tr("label.name_2", lang_code) + ":")

    def _update_translation_placeholders(self, lang_code: str):
        try:
            self.edit_name1.setPlaceholderText(
                tr("ui.edit_current_image_1_name", lang_code)
            )
            self.edit_name2.setPlaceholderText(
                tr("ui.edit_current_image_2_name", lang_code)
            )
        except Exception:
            pass

    def _update_translation_buttons(self, lang_code: str):
        self.btn_image1.setText(tr("button.add_images_1", lang_code))
        self.btn_image2.setText(tr("button.add_images_2", lang_code))
        self.btn_save.setText(tr("button.save_result", lang_code))

    def _update_translation_tooltips(self, lang_code: str):
        self.btn_image1.setToolTip(tr("tooltip.add_images_1", lang_code))
        self.btn_image2.setToolTip(tr("tooltip.add_images_2", lang_code))
        self.btn_swap.setToolTip(
            f"{tr('tooltip.click_swap_current_images', lang_code)}\n{tr('tooltip.hold_swap_entire_lists', lang_code)}"
        )
        clear_tooltip = (
            f"{tr('tooltip.click_remove_current_image', lang_code)}\n"
            f"{tr('button.hold_clear_entire_list', lang_code)}"
        )
        self.btn_clear_list1.setToolTip(clear_tooltip)
        self.btn_clear_list2.setToolTip(clear_tooltip)
        self.btn_text_settings.setToolTip(
            tr("tooltip.open_file_name_text_settings", lang_code)
        )
        self.btn_quick_save.setToolTip(tr("tooltip.quick_save_image", lang_code))
        self.btn_save.setToolTip(tr("tooltip.save_result", lang_code))
        self.btn_orientation.setToolTip(
            tr("ui.toggle_split_orientation", lang_code)
        )
        self.btn_orientation_simple.setToolTip(
            tr("ui.toggle_split_orientation", lang_code)
        )
        self.btn_magnifier.setToolTip(tr("magnifier.toggle_magnifier", lang_code))
        self.btn_magnifier_instances.setToolTip(
            tr("tooltip.add_or_remove_magnifier", lang_code)
        )
        self.btn_freeze.setToolTip(tr("magnifier.freeze_magnifier_position", lang_code))
        self.btn_magnifier_orientation.setToolTip(
            tr("ui.toggle_split_orientation", lang_code)
        )
        self.btn_magnifier_orientation_simple.setToolTip(
            tr("ui.toggle_split_orientation", lang_code)
        )
        self.btn_file_names.setToolTip(
            tr("ui.include_file_names_in_saved_image", lang_code)
        )
        self.btn_diff_mode.setToolTip(tr("tooltip.change_diff_mode", lang_code))
        self.btn_channel_mode.setToolTip(tr("tooltip.change_channel_mode", lang_code))
        self.btn_magnifier_color_settings.setToolTip(
            tr("magnifier.change_magnifier_colors", lang_code)
        )
        self.btn_magnifier_color_settings_beginner.setToolTip(
            tr("magnifier.change_magnifier_colors", lang_code)
        )
        if hasattr(self.btn_magnifier_color_settings, "update_language"):
            self.btn_magnifier_color_settings.update_language(lang_code)
        if hasattr(self.btn_magnifier_color_settings_beginner, "update_language"):
            self.btn_magnifier_color_settings_beginner.update_language(lang_code)
        self.btn_magnifier_guides.setToolTip(
            tr("magnifier.toggle_magnifier_guide_lines", lang_code)
        )
        self.btn_magnifier_guides_simple.setToolTip(
            tr("magnifier.toggle_magnifier_guide_lines", lang_code)
        )
        self.btn_divider_visible.setToolTip(
            tr("tooltip.toggle_divider_visibility", lang_code)
        )
        self.btn_divider_color.setToolTip(
            tr("ui.choose_divider_line_color", lang_code)
        )
        self.btn_divider_width.setToolTip(
            tr("tooltip.adjust_divider_width", lang_code)
        )
        self.btn_magnifier_divider_visible.setToolTip(
            tr("tooltip.toggle_magnifier_divider_visibility", lang_code)
        )
        self.btn_magnifier_divider_width.setToolTip(
            tr("tooltip.adjust_magnifier_divider_width", lang_code)
        )
        self.btn_magnifier_guides_width.setToolTip(
            tr("tooltip.adjust_magnifier_guides_width", lang_code)
        )
        self.btn_record.setToolTip(tr("button.startstop_recording", lang_code))
        self.btn_pause.setToolTip(tr("button.pauseresume_recording", lang_code))
        self.btn_video_editor.setToolTip(
            tr("action.open_video_editor_exporter", lang_code)
        )
        self.btn_new_session.setToolTip(
            tr("tooltip.create_workspace_session", lang_code)
        )
        self.btn_settings.setToolTip(tr("action.open_application_settings", lang_code))
        self.help_button.setToolTip(tr("action.show_help", lang_code))

    def _update_translation_group_titles(self, lang_code: str):
        container_titles = (
            ("line_group_container", "label.line"),
            ("magnifier_group_container", "label.magnifier"),
            ("view_group_container", "label.view"),
            ("record_group_container", "button.record"),
        )
        for attr_name, key in container_titles:
            container = getattr(self, attr_name, None)
            if container:
                container.set_label_text(tr(key, lang_code))

    def _update_translation_slider_labels(self, lang_code: str):
        self.label_magnifier_size.setText(tr("label.magnifier_size", lang_code) + ":")
        self.label_capture_size.setText(tr("label.capture_size", lang_code) + ":")
        self.label_movement_speed.setText(tr("magnifier.move_speed", lang_code) + ":")
        self.label_interpolation.setText(
            tr("magnifier.magnifier_interpolation", lang_code) + ":"
        )

    def update_drag_overlays(self, horizontal: bool = False, visible: bool = False):
        if not self.image_label.isVisible():
            if hasattr(self, "drag_overlay"):
                self.drag_overlay.hide()
            return
        self.image_label.set_drag_overlay_state(
            visible=False,
            horizontal=horizontal,
            text1=tr(
                "ui.drop_images_1_here",
                self.main_window.store.settings.current_language,
            ),
            text2=tr(
                "ui.drop_images_2_here",
                self.main_window.store.settings.current_language,
            ),
        )
        if hasattr(self, "drag_overlay"):
            self.drag_overlay.set_overlay_state(
                visible=visible,
                target_rect=self.image_label.geometry(),
                horizontal=horizontal,
                text1=tr(
                    "ui.drop_images_1_here",
                    self.main_window.store.settings.current_language,
                ),
                text2=tr(
                    "ui.drop_images_2_here",
                    self.main_window.store.settings.current_language,
                ),
            )

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
            self._hide_file_name_labels()
            return
        self._show_file_name_labels()
        prefix1, prefix2 = self._get_file_name_prefixes(is_horizontal, current_language)
        max_text_width = self._get_max_file_name_width()
        font_metrics = QFontMetrics(self.file_name_label1.font())
        self.file_name_label1.setText(
            self._elide_file_name_text(
                f"{prefix1}: {name1_text}", font_metrics, max_text_width
            )
        )
        self.file_name_label2.setText(
            self._elide_file_name_text(
                f"{prefix2}: {name2_text}", font_metrics, max_text_width
            )
        )

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
                item.display_name
                for item in (
                    self.main_window.store.document.image_list1
                    if image_number == 1
                    else self.main_window.store.document.image_list2
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
        try:
            self.magnifier_settings_panel.updateGeometry()
            parent = self.magnifier_settings_panel.parentWidget()
            if parent and parent.layout():
                parent.layout().activate()
        except Exception:
            pass

        try:
            if hasattr(self.main_window, "schedule_update"):
                QTimer.singleShot(0, self.main_window.schedule_update)
        except Exception:
            pass

    def update_rating_display(
        self, image_number: int, score: int | None, current_language: str
    ):
        label = self.label_rating1 if image_number == 1 else self.label_rating2
        if score is not None:

            label.setText(f"<b>{score}</b>")
            label.setVisible(True)
        else:
            label.setText("–")
            label.setVisible(False)

    def install_rating_wheel_handlers(self):
        self.label_rating1.wheelEvent = self._make_rating_wheel_handler(1)
        self.label_rating2.wheelEvent = self._make_rating_wheel_handler(2)

    def get_current_label_dimensions(self) -> Tuple[int, int]:
        return (
            self.image_label.contentsRect().width(),
            self.image_label.contentsRect().height(),
        )

    def _hide_file_name_labels(self):
        self.file_name_label1.setVisible(False)
        self.file_name_label2.setVisible(False)
        self.file_name_label1.setText("")
        self.file_name_label2.setText("")

    def _show_file_name_labels(self):
        self.file_name_label1.setVisible(True)
        self.file_name_label2.setVisible(True)

    def _get_file_name_prefixes(
        self, is_horizontal: bool, current_language: str
    ) -> Tuple[str, str]:
        if not is_horizontal:
            return (
                tr("common.position.left", current_language),
                tr("common.position.right", current_language),
            )
        return (
            tr("common.position.top", current_language),
            tr("common.position.bottom", current_language),
        )

    def _get_max_file_name_width(self) -> int:
        window_width = (
            self.main_window.width()
            if hasattr(self, "main_window") and self.main_window
            else 800
        )
        return window_width // 2 - 20

    def _elide_file_name_text(
        self, text: str, font_metrics: QFontMetrics, max_text_width: int
    ) -> str:
        if font_metrics.horizontalAdvance(text) > max_text_width:
            return font_metrics.elidedText(
                text, Qt.TextElideMode.ElideRight, max_text_width
            )
        return text

    def _make_rating_wheel_handler(self, image_number: int):
        def _wheel(event):
            delta = event.angleDelta().y()
            if delta == 0:
                return
            session_ctrl = self._get_session_controller()
            if session_ctrl is None:
                return
            current_idx = self._get_current_rating_index(image_number)
            if current_idx < 0:
                return
            if delta > 0:
                session_ctrl.increment_rating(image_number, current_idx)
            else:
                session_ctrl.decrement_rating(image_number, current_idx)
            self._refresh_rating_displays()
            event.accept()

        return _wheel

    def _get_session_controller(self):
        controller = getattr(self.main_window, "main_controller", None)
        if not controller or not hasattr(controller, "sessions"):
            return None
        return controller.sessions

    def _get_current_rating_index(self, image_number: int) -> int:
        state = self.main_window.store
        return (
            state.document.current_index1
            if image_number == 1
            else state.document.current_index2
        )

    def _refresh_rating_displays(self):
        if hasattr(self.main_window, "presenter"):
            self.main_window.presenter.update_rating_displays()
