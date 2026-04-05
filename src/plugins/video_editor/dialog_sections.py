from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSize, Qt
from PyQt6.QtGui import QFont, QIntValidator
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from plugins.video_editor.services.export_config import ExportConfigBuilder
from plugins.video_editor.widgets.timeline import VideoTimelineWidget
from shared_toolkit.ui.widgets.atomic.custom_button import CustomButton
from shared_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from shared_toolkit.ui.widgets.atomic.fluent_combobox import FluentComboBox
from shared_toolkit.ui.widgets.atomic.fluent_spinbox import FluentSpinBox
from shared_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from shared_toolkit.ui.widgets.composite import OutputPathSection
from shared_toolkit.ui.widgets.atomic.simple_icon_button import SimpleIconButton
from shared_toolkit.ui.widgets.atomic.text_labels import BodyLabel, CaptionLabel
from shared_toolkit.ui.widgets.atomic.toggle_icon_button import ToggleIconButton
from shared_toolkit.ui.widgets.atomic.simple_icon_button import SimpleIconButton
from ui.icon_manager import AppIcon, get_app_icon

class _NoWheelEventFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            parent = obj.parentWidget() if hasattr(obj, "parentWidget") else None
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    scrollbar = parent.verticalScrollBar()
                    step = scrollbar.singleStep() or 24
                    old_value = scrollbar.value()
                    if delta == 0:
                        event.accept()
                        return True
                    direction = -1 if delta > 0 else 1
                    new_value = old_value + direction * step
                    scrollbar.setValue(new_value)
                    event.accept()
                    return True
                parent = parent.parentWidget()
            return True
        return super().eventFilter(obj, event)

def _install_no_wheel_filter_recursive(root: QWidget, event_filter: QObject) -> None:
    if event_filter is None:
        return
    for child in root.findChildren(QWidget):
        if isinstance(child, (CustomLineEdit, FluentSpinBox, FluentComboBox)):
            child.installEventFilter(event_filter)

def build_settings_panel(dialog):
    settings_panel = QFrame()
    settings_panel.setObjectName("VideoEditorSettingsPanel")

    sp_layout = QVBoxLayout(settings_panel)
    sp_layout.setContentsMargins(0, 0, 0, 0)
    sp_layout.setSpacing(0)

    dialog._settings_no_wheel_filter = _NoWheelEventFilter(settings_panel)

    static_container = QWidget(settings_panel)
    static_layout = QVBoxLayout(static_container)
    static_layout.setContentsMargins(12, 12, 12, 10)
    static_layout.setSpacing(14)
    static_layout.addLayout(create_resolution_settings(dialog))
    static_layout.addLayout(create_fps_settings(dialog))
    sp_layout.addWidget(static_container)

    content_container = QWidget()
    content_layout = QVBoxLayout(content_container)
    content_layout.setContentsMargins(12, 8, 12, 0)
    content_layout.setSpacing(14)

    dialog.tabs = create_export_tabs(dialog)
    sp_layout.addWidget(dialog.tabs, stretch=1)

    footer_gap_top = QWidget(settings_panel)
    footer_gap_top.setFixedHeight(10)
    sp_layout.addWidget(footer_gap_top)

    footer_gap_bottom = QWidget(settings_panel)
    footer_gap_bottom.setFixedHeight(12)
    sp_layout.addWidget(footer_gap_bottom)

    dialog.export_progress = QProgressBar()
    dialog.export_progress.setObjectName("VideoEditorExportProgress")
    dialog.export_progress.setProperty("state", "active")
    dialog.export_progress.setVisible(False)
    dialog.export_progress.setTextVisible(False)
    dialog.export_progress.setFixedHeight(4)
    sp_layout.addWidget(dialog.export_progress)

    dialog.btn_export = CustomButton(
        get_app_icon(AppIcon.EXPORT_VIDEO), dialog._tr("action.export_video")
    )
    dialog.btn_export.setProperty("class", "primary")
    dialog.btn_export.setFixedHeight(48)
    dialog.btn_export.set_footer_mode(True)
    dialog.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
    dialog.btn_export.clicked.connect(dialog._on_export_clicked)

    dialog.btn_stop_export = QPushButton(dialog.btn_export)
    dialog.btn_stop_export.setObjectName("btnStopVideoExport")
    dialog.btn_stop_export.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    dialog.btn_stop_export.setToolTip(dialog._tr("button.stop"))
    dialog.btn_stop_export.setCursor(Qt.CursorShape.PointingHandCursor)
    dialog.btn_stop_export.setIcon(get_app_icon(AppIcon.STOP))
    dialog.btn_stop_export.setIconSize(QSize(12, 12))
    dialog.btn_stop_export.setFixedSize(24, 24)
    dialog.btn_stop_export.clicked.connect(dialog._on_stop_export_clicked)
    dialog.btn_stop_export.hide()
    sp_layout.addWidget(dialog.btn_export)

    return settings_panel

def create_resolution_settings(dialog):
    res_layout = QHBoxLayout()
    res_layout.setSpacing(8)

    res_label = BodyLabel(dialog._tr("label.resolution") + ":")
    res_layout.addWidget(res_label)

    dialog.edit_width = CustomLineEdit()
    dialog.edit_width.setValidator(QIntValidator(16, 8192))
    dialog.edit_width.setText("1920")
    dialog.edit_width.setFixedWidth(60)
    dialog.edit_width.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.edit_width.installEventFilter(dialog._settings_no_wheel_filter)
    res_layout.addWidget(dialog.edit_width)

    dialog.btn_lock_ratio = ToggleIconButton(AppIcon.UNLINK, AppIcon.LINK)
    dialog.btn_lock_ratio.setObjectName("btnLockRatio")
    dialog.btn_lock_ratio.setFixedSize(32, 32)
    dialog.btn_lock_ratio.setChecked(True)
    dialog.btn_lock_ratio.setToolTip(dialog._tr("video.lock_aspect_ratio"))
    dialog.btn_lock_ratio.toggled.connect(dialog._on_ratio_lock_toggled)
    res_layout.addWidget(dialog.btn_lock_ratio)

    dialog.edit_height = CustomLineEdit()
    dialog.edit_height.setValidator(QIntValidator(16, 8192))
    dialog.edit_height.setText("1080")
    dialog.edit_height.setFixedWidth(60)
    dialog.edit_height.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.edit_height.installEventFilter(dialog._settings_no_wheel_filter)
    res_layout.addWidget(dialog.edit_height)

    dialog.btn_fit_content = ToggleIconButton(AppIcon.CROP_IN, AppIcon.CROP_OUT)
    dialog.btn_fit_content.setObjectName("btnFitContent")
    dialog.btn_fit_content.setFixedSize(32, 32)
    dialog.btn_fit_content.setChecked(False)
    dialog.btn_fit_content.setToolTip(
        dialog._tr("magnifier.fit_mode_toggle")
    )
    dialog.btn_fit_content.toggled.connect(dialog._on_fit_content_toggled)
    res_layout.addWidget(dialog.btn_fit_content)

    dialog.btn_fit_fill_color = SimpleIconButton(AppIcon.DIVIDER_COLOR)
    dialog.btn_fit_fill_color.setObjectName("btnFitFillColor")
    dialog.btn_fit_fill_color.setFixedSize(32, 32)
    dialog.btn_fit_fill_color.setToolTip(dialog._tr("export.select_background_color"))
    dialog.btn_fit_fill_color.clicked.connect(dialog._on_fit_fill_color_clicked)
    dialog.btn_fit_fill_color.setVisible(False)
    if hasattr(dialog, "_update_fit_fill_color_button"):
        dialog._update_fit_fill_color_button()
    res_layout.addWidget(dialog.btn_fit_fill_color)

    res_layout.addStretch()

    dialog.edit_width.editingFinished.connect(dialog._on_width_edited)
    dialog.edit_height.editingFinished.connect(dialog._on_height_edited)

    return res_layout

def create_fps_settings(dialog):
    fps_layout = QHBoxLayout()
    fps_layout.addWidget(BodyLabel(dialog._tr("label.fps") + ":"))

    max_fps = 240
    initial_fps = 60

    first_snapshot = (
        dialog._get_first_snapshot() if hasattr(dialog, "_get_first_snapshot") else None
    )
    if first_snapshot and hasattr(first_snapshot, "settings_state"):
        recording_fps = getattr(
            first_snapshot.settings_state, "video_recording_fps", None
        )
        if recording_fps:
            max_fps = recording_fps
            initial_fps = recording_fps

    if (
        max_fps == 240
        and hasattr(dialog, "export_controller")
        and dialog.export_controller
    ):
        if (
            hasattr(dialog.export_controller, "store")
            and dialog.export_controller.store
        ):
            initial_fps = getattr(
                dialog.export_controller.store.settings, "video_recording_fps", 60
            )
            max_fps = initial_fps

    dialog.edit_fps = FluentSpinBox(default_value=initial_fps)
    dialog.edit_fps.setRange(1, max_fps)
    dialog.edit_fps.setValue(initial_fps)
    dialog.edit_fps.setFixedWidth(100)
    dialog.edit_fps.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.edit_fps.installEventFilter(dialog._settings_no_wheel_filter)
    fps_layout.addWidget(dialog.edit_fps)

    fps_layout.addStretch()

    dialog.edit_fps.valueChanged.connect(dialog._on_fps_changed)

    return fps_layout

def create_export_tabs(dialog):
    tabs = QTabWidget()
    tabs.setObjectName("VideoEditorTabs")
    tabs.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    tabs.tabBar().setExpanding(False)

    dialog.tab_standard = create_standard_export_tab(dialog)
    tabs.addTab(dialog.tab_standard, dialog._tr("video.standard"))

    dialog.tab_manual = create_manual_export_tab(dialog)
    tabs.addTab(dialog.tab_manual, dialog._tr("video.manual_cli"))

    dialog.tab_output = create_output_tab(dialog)
    tabs.addTab(dialog.tab_output, dialog._tr("label.output"))

    dialog.tab_log = create_log_tab(dialog)
    tabs.addTab(dialog.tab_log, dialog._tr("video.export_log"))

    dialog.combo_container.currentTextChanged.connect(dialog._on_container_changed)
    dialog.combo_codec.currentTextChanged.connect(dialog._on_codec_changed)

    return tabs

def create_log_tab(dialog) -> QWidget:
    tab = QWidget()
    tab.setObjectName("VideoEditorTabContent")
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(0)

    log_edit = QPlainTextEdit()
    log_edit.setObjectName("VideoExportLog")
    log_edit.setReadOnly(True)
    log_edit.setPlaceholderText("Export log will appear here...")
    mono_font = QFont("Monospace")
    mono_font.setStyleHint(QFont.StyleHint.Monospace)
    mono_font.setPointSize(9)
    log_edit.setFont(mono_font)

    dialog.export_log_edit = log_edit
    layout.addWidget(log_edit)
    return tab

def _wrap_tab_scroll(content: QWidget) -> QWidget:
    tab = QWidget()
    tab.setObjectName("VideoEditorTabContent")
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    scroll_area = OverlayScrollArea(tab)
    scroll_area.set_reserve_scrollbar_space(False)
    scroll_area.setWidget(content)
    layout.addWidget(scroll_area)
    return tab

def create_standard_export_tab(dialog):
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(12, 16, 12, 16)
    layout.setSpacing(12)

    layout.addWidget(CaptionLabel(dialog._tr("label.container") + ":"))
    dialog.combo_container = FluentComboBox()
    for container in ExportConfigBuilder.get_available_containers():
        dialog.combo_container.addItem(dialog._tr(container), container)
    dialog.combo_container.setCurrentIndex(max(0, dialog.combo_container.findData("mp4")))
    layout.addWidget(dialog.combo_container)

    layout.addWidget(CaptionLabel(dialog._tr("label.video_codec") + ":"))
    dialog.combo_codec = FluentComboBox()
    for codec in ExportConfigBuilder.get_codecs_for_container("mp4"):
        dialog.combo_codec.addItem(
            dialog._tr(ExportConfigBuilder.get_codec_display_key(codec)), codec
        )
    layout.addWidget(dialog.combo_codec)

    dialog.pix_fmt_container = QWidget()
    pf_layout = QVBoxLayout(dialog.pix_fmt_container)
    pf_layout.setContentsMargins(0, 0, 0, 0)
    pf_layout.setSpacing(12)
    dialog.lbl_pix_fmt = CaptionLabel(dialog._tr("video.pixel_format") + ":")
    pf_layout.addWidget(dialog.lbl_pix_fmt)
    dialog.combo_pix_fmt = FluentComboBox()
    for pix_fmt in ExportConfigBuilder.get_pixel_formats_for_codec("h264 (AVC)"):
        dialog.combo_pix_fmt.addItem(pix_fmt, pix_fmt)
    dialog.combo_pix_fmt.setCurrentText("yuv420p")
    pf_layout.addWidget(dialog.combo_pix_fmt)
    layout.addWidget(dialog.pix_fmt_container)

    dialog.quality_controls_container = QWidget()
    qc_layout = QVBoxLayout(dialog.quality_controls_container)
    qc_layout.setContentsMargins(0, 0, 0, 0)
    qc_layout.setSpacing(12)

    qc_layout.addWidget(CaptionLabel(dialog._tr("video.quality_control") + ":"))
    dialog.combo_quality_mode = FluentComboBox()
    dialog.combo_quality_mode.addItem(dialog._tr("video.crf_constant_quality"), "crf")
    dialog.combo_quality_mode.addItem(dialog._tr("video.bitrate_cbrvbr"), "bitrate")
    qc_layout.addWidget(dialog.combo_quality_mode)

    dialog.stack_quality = create_quality_stack(dialog)
    qc_layout.addWidget(dialog.stack_quality)

    layout.addWidget(dialog.quality_controls_container)

    dialog.preset_container = QWidget()
    p_layout = QVBoxLayout(dialog.preset_container)
    p_layout.setContentsMargins(0, 0, 0, 0)
    p_layout.setSpacing(12)

    dialog.lbl_preset = CaptionLabel(dialog._tr("video.encoding_speed_preset") + ":")
    p_layout.addWidget(dialog.lbl_preset)
    dialog.combo_preset = FluentComboBox()
    for preset in ExportConfigBuilder.get_encoding_presets():
        dialog.combo_preset.addItem(dialog._tr_preset(preset), preset)
    dialog.combo_preset.setCurrentIndex(max(0, dialog.combo_preset.findData("medium")))
    p_layout.addWidget(dialog.combo_preset)

    layout.addWidget(dialog.preset_container)

    dialog.combo_quality_mode.currentIndexChanged.connect(
        dialog.stack_quality.setCurrentIndex
    )

    layout.addStretch()
    _install_no_wheel_filter_recursive(content, dialog._settings_no_wheel_filter)
    return _wrap_tab_scroll(content)

def create_manual_export_tab(dialog):
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(12, 16, 12, 16)

    info_lbl = CaptionLabel(
        dialog._tr("video.ffmpeg_output_args_hint")
    )
    info_lbl.setWordWrap(True)
    layout.addWidget(info_lbl)

    dialog.edit_manual_args = CustomLineEdit()
    dialog.edit_manual_args.setPlaceholderText("-c:v libx264 -crf 23 -pix_fmt yuv420p")
    layout.addWidget(dialog.edit_manual_args)

    layout.addStretch()
    _install_no_wheel_filter_recursive(content, dialog._settings_no_wheel_filter)
    return _wrap_tab_scroll(content)

def create_output_tab(dialog):
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    dialog.output_section = OutputPathSection(
        directory_label_text=dialog._tr("export.select_output_directory") + ":",
        browse_text=dialog._tr("button.browse"),
        set_favorite_text=dialog._tr("misc.set_as_favorite"),
        use_favorite_text=dialog._tr("tooltip.use_favorite"),
        filename_label_text=dialog._tr("label.file_name") + ":",
        on_browse=dialog._browse_output_dir,
        on_set_favorite=dialog._on_set_favorite_clicked,
        on_use_favorite=dialog._on_use_favorite_clicked,
        use_custom_line_edit=True,
        filename_editor_factory=CustomLineEdit,
        button_min_size=(40, 30),
        button_fixed_height=30,
    )
    dialog.dir_picker_row = dialog.output_section.dir_picker_row
    dialog.edit_output_dir = dialog.output_section.edit_dir
    dialog.btn_browse_output = dialog.output_section.btn_browse_dir
    dialog.favorite_actions = dialog.output_section.favorite_actions
    dialog.btn_set_favorite = dialog.output_section.btn_set_favorite
    dialog.btn_use_favorite = dialog.output_section.btn_use_favorite
    dialog.edit_filename = dialog.output_section.filename_edit
    layout.addWidget(dialog.output_section)

    layout.addStretch()
    _install_no_wheel_filter_recursive(content, dialog._settings_no_wheel_filter)
    return _wrap_tab_scroll(content)

def create_quality_stack(dialog):
    stack = QStackedWidget()

    p_crf = QWidget()
    l_crf = QVBoxLayout(p_crf)
    l_crf.setContentsMargins(0, 0, 0, 0)
    l_crf.setSpacing(6)
    dialog.lbl_quality_value = CaptionLabel(
        dialog._tr("video.crf_value_hint") + ":"
    )
    l_crf.addWidget(dialog.lbl_quality_value)

    dialog.edit_crf = CustomLineEdit()
    dialog.edit_crf.setValidator(QIntValidator(0, 63))
    dialog.edit_crf.setText("23")
    dialog.edit_crf.setPlaceholderText("23")
    dialog.edit_crf.setFixedWidth(80)
    dialog.edit_crf.setAlignment(Qt.AlignmentFlag.AlignCenter)
    l_crf.addWidget(dialog.edit_crf)

    stack.addWidget(p_crf)

    p_bit = QWidget()
    l_bit = QVBoxLayout(p_bit)
    l_bit.setContentsMargins(0, 0, 0, 0)
    l_bit.setSpacing(6)
    l_bit.addWidget(CaptionLabel(dialog._tr("video.bitrate_hint") + ":"))

    dialog.edit_bitrate = CustomLineEdit()
    dialog.edit_bitrate.setText("8000k")
    l_bit.addWidget(dialog.edit_bitrate)

    stack.addWidget(p_bit)

    return stack

def create_toolbar(dialog):
    toolbar_frame = QFrame()
    toolbar_frame.setObjectName("VideoEditorToolbar")
    toolbar_frame.setFixedHeight(50)

    toolbar_layout = QHBoxLayout(toolbar_frame)
    toolbar_layout.setContentsMargins(10, 5, 10, 5)
    toolbar_layout.setSpacing(8)

    dialog.btn_play = ToggleIconButton(AppIcon.PLAY, AppIcon.PAUSE)
    dialog.btn_play.setToolTip(
        dialog._tr("button.play") + " / " + dialog._tr("button.pause")
    )
    dialog.btn_play.toggled.connect(dialog._on_play_toggled)

    dialog.btn_undo = SimpleIconButton(AppIcon.UNDO)
    dialog.btn_undo.setToolTip(dialog._tr("button.undo_ctrlz"))
    dialog.btn_undo.clicked.connect(dialog._on_undo_clicked)

    dialog.btn_redo = SimpleIconButton(AppIcon.REDO)
    dialog.btn_redo.setToolTip(dialog._tr("button.redo"))
    dialog.btn_redo.clicked.connect(dialog._on_redo_clicked)

    dialog.btn_trim = SimpleIconButton(AppIcon.SCISSORS)
    dialog.btn_trim.setToolTip(dialog._tr("button.trim_to_selection"))
    dialog.btn_trim.clicked.connect(dialog._on_trim_clicked)

    toolbar_layout.addWidget(dialog.btn_play)
    toolbar_layout.addWidget(dialog.btn_undo)
    toolbar_layout.addWidget(dialog.btn_redo)
    toolbar_layout.addWidget(dialog.btn_trim)

    toolbar_layout.addStretch()
    return toolbar_frame

def create_timeline_scroll_area(dialog):
    scroll_area = QScrollArea()
    scroll_area.setObjectName("VideoEditorTimelineScrollArea")
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setMinimumHeight(210)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    store = None
    if hasattr(dialog, "export_controller") and dialog.export_controller:
        if (
            hasattr(dialog.export_controller, "store")
            and dialog.export_controller.store
        ):
            store = dialog.export_controller.store
    dialog.timeline = VideoTimelineWidget([], store=store)
    dialog.timeline.setSizePolicy(
        QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred
    )
    scroll_area.setWidget(dialog.timeline)

    dialog.timeline.headMoved.connect(dialog._on_head_moved)
    dialog.timeline.deletePressed.connect(dialog._on_trim_clicked)

    return scroll_area
