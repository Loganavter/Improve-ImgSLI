from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from plugins.video_editor.widgets.timeline import VideoTimelineWidget
from plugins.video_editor.services.export_config import ExportConfigBuilder
from toolkit.widgets.atomic.custom_button import CustomButton
from toolkit.widgets.atomic.fluent_combobox import FluentComboBox
from toolkit.widgets.atomic.text_labels import BodyLabel, CaptionLabel
from toolkit.widgets.atomic.custom_line_edit import CustomLineEdit
from toolkit.widgets.atomic.fluent_spinbox import FluentSpinBox
from toolkit.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from toolkit.widgets.atomic.simple_icon_button import SimpleIconButton
from toolkit.widgets.atomic.toggle_icon_button import ToggleIconButton
from ui.icon_manager import AppIcon, get_app_icon

def build_settings_panel(dialog):
    settings_panel = QFrame()
    settings_panel.setObjectName("VideoEditorSettingsPanel")

    sp_layout = QVBoxLayout(settings_panel)
    sp_layout.setContentsMargins(0, 0, 0, 0)
    sp_layout.setSpacing(0)

    content_container = QWidget()
    content_layout = QVBoxLayout(content_container)
    content_layout.setContentsMargins(12, 12, 12, 12)
    content_layout.setSpacing(14)

    content_layout.addLayout(create_resolution_settings(dialog))
    content_layout.addLayout(create_fps_settings(dialog))

    dialog.tabs = create_export_tabs(dialog)
    content_layout.addWidget(dialog.tabs)

    content_layout.addStretch()
    sp_layout.addWidget(content_container)

    dialog.export_progress = QProgressBar()
    dialog.export_progress.setVisible(False)
    dialog.export_progress.setFixedHeight(4)
    dialog.export_progress.setTextVisible(False)
    dialog.export_progress.setStyleSheet("""
        QProgressBar {
            border: none;
            background-color: #2d2d2d;
            border-radius: 2px;
        }
        QProgressBar::chunk {
            background-color: #0078D4;
            border-radius: 2px;
        }
    """)
    sp_layout.addWidget(dialog.export_progress)

    dialog.btn_export = CustomButton(get_app_icon(AppIcon.EXPORT_VIDEO), dialog._tr("action.export_video"))
    dialog.btn_export.setProperty("class", "primary")
    dialog.btn_export.setFixedHeight(48)
    dialog.btn_export.set_footer_mode(True)
    dialog.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
    dialog.btn_export.clicked.connect(dialog._on_export_clicked)
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
    res_layout.addWidget(dialog.edit_height)

    dialog.btn_fit_content = ToggleIconButton(AppIcon.CROP_IN, AppIcon.CROP_OUT)
    dialog.btn_fit_content.setObjectName("btnFitContent")
    dialog.btn_fit_content.setFixedSize(32, 32)
    dialog.btn_fit_content.setChecked(False)
    dialog.btn_fit_content.setToolTip(dialog._tr("magnifier.off_crop_to_image_on_fit_magnifier_expand_canvas"))
    dialog.btn_fit_content.toggled.connect(dialog._on_fit_content_toggled)
    res_layout.addWidget(dialog.btn_fit_content)

    res_layout.addStretch()

    dialog.edit_width.editingFinished.connect(dialog._on_width_edited)
    dialog.edit_height.editingFinished.connect(dialog._on_height_edited)

    return res_layout

def create_fps_settings(dialog):
    fps_layout = QHBoxLayout()
    fps_layout.addWidget(BodyLabel(dialog._tr("label.fps") + ":"))

    max_fps = 240
    initial_fps = 60

    if hasattr(dialog, 'snapshots') and dialog.snapshots:
        first_snapshot = dialog.snapshots[0] if dialog.snapshots else None
        if first_snapshot and hasattr(first_snapshot, 'settings_state'):
            recording_fps = getattr(first_snapshot.settings_state, 'video_recording_fps', None)
            if recording_fps:
                max_fps = recording_fps
                initial_fps = min(recording_fps, initial_fps)

    if max_fps == 240 and hasattr(dialog, 'export_controller') and dialog.export_controller:
        if hasattr(dialog.export_controller, 'store') and dialog.export_controller.store:
            initial_fps = getattr(dialog.export_controller.store.settings, 'video_recording_fps', 60)
            max_fps = initial_fps

    dialog.edit_fps = FluentSpinBox(default_value=initial_fps)
    dialog.edit_fps.setRange(1, max_fps)
    dialog.edit_fps.setValue(initial_fps)
    dialog.edit_fps.setFixedWidth(100)
    dialog.edit_fps.setAlignment(Qt.AlignmentFlag.AlignCenter)
    fps_layout.addWidget(dialog.edit_fps)

    fps_layout.addStretch()

    dialog.edit_fps.valueChanged.connect(dialog._on_fps_changed)

    return fps_layout

def create_export_tabs(dialog):
    tabs = QTabWidget()
    tabs.setObjectName("VideoEditorTabs")
    tabs.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    tabs.tabBar().setExpanding(False)
    tabs.setStyleSheet("""
        QTabWidget::tab-bar {
            alignment: center;
        }
        QTabBar::tab {
            min-width: 80px;
            margin: 0px 4px;
        }
    """)

    dialog.tab_standard = create_standard_export_tab(dialog)
    tabs.addTab(dialog.tab_standard, dialog._tr("video.standard"))

    dialog.tab_manual = create_manual_export_tab(dialog)
    tabs.addTab(dialog.tab_manual, dialog._tr("video.manual_cli"))

    dialog.tab_output = create_output_tab(dialog)
    tabs.addTab(dialog.tab_output, dialog._tr("label.output"))

    dialog.combo_container.currentTextChanged.connect(dialog._on_container_changed)
    dialog.combo_codec.currentTextChanged.connect(dialog._on_codec_changed)

    return tabs

def create_standard_export_tab(dialog):
    tab = QWidget()
    tab.setObjectName("VideoEditorTabContent")
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(12, 16, 12, 16)
    layout.setSpacing(12)

    layout.addWidget(CaptionLabel(dialog._tr("label.container") + ":"))
    dialog.combo_container = FluentComboBox()
    for container in ExportConfigBuilder.get_available_containers():
        dialog.combo_container.addItem(dialog._tr(container))
    dialog.combo_container.setCurrentText(dialog._tr("mp4"))
    layout.addWidget(dialog.combo_container)

    layout.addWidget(CaptionLabel(dialog._tr("label.video_codec") + ":"))
    dialog.combo_codec = FluentComboBox()
    dialog.combo_codec.addItems([dialog._tr(codec) for codec in ExportConfigBuilder.get_codecs_for_container("mp4")])
    layout.addWidget(dialog.combo_codec)

    dialog.quality_controls_container = QWidget()
    qc_layout = QVBoxLayout(dialog.quality_controls_container)
    qc_layout.setContentsMargins(0, 0, 0, 0)
    qc_layout.setSpacing(12)

    qc_layout.addWidget(CaptionLabel(dialog._tr("video.quality_control") + ":"))
    dialog.combo_quality_mode = FluentComboBox()
    dialog.combo_quality_mode.addItems([dialog._tr("video.crf_constant_quality"), dialog._tr("video.bitrate_cbrvbr")])
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
        dialog.combo_preset.addItem(dialog._tr_preset(preset))
    dialog.combo_preset.setCurrentText(dialog._tr_preset("medium"))
    p_layout.addWidget(dialog.combo_preset)

    layout.addWidget(dialog.preset_container)

    dialog.combo_quality_mode.currentIndexChanged.connect(dialog.stack_quality.setCurrentIndex)

    layout.addStretch()
    return tab

def create_manual_export_tab(dialog):
    tab = QWidget()
    tab.setObjectName("VideoEditorTabContent")
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(12, 16, 12, 16)

    info_lbl = CaptionLabel(dialog._tr("video.enter_ffmpeg_output_arguments_input_is_rawvideo_pipe"))
    info_lbl.setWordWrap(True)
    layout.addWidget(info_lbl)

    dialog.edit_manual_args = CustomLineEdit()
    dialog.edit_manual_args.setPlaceholderText("-c:v libx264 -crf 23 -pix_fmt yuv420p")
    layout.addWidget(dialog.edit_manual_args)

    layout.addStretch()
    return tab

def create_output_tab(dialog):
    tab = QWidget()
    tab.setObjectName("VideoEditorTabContent")
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    layout.addWidget(CaptionLabel(dialog._tr("export.select_output_directory") + ":"))
    dir_row = QHBoxLayout()
    dialog.edit_output_dir = CustomLineEdit()
    dialog.btn_browse_output = CustomButton(None, "...")
    dialog.btn_browse_output.setFixedSize(40, 30)
    dialog.btn_browse_output.clicked.connect(dialog._browse_output_dir)
    dir_row.addWidget(dialog.edit_output_dir)
    dir_row.addWidget(dialog.btn_browse_output)
    layout.addLayout(dir_row)

    fav_row = QHBoxLayout()
    dialog.btn_set_favorite = CustomButton(None, dialog._tr("misc.set_as_favorite"))
    dialog.btn_use_favorite = CustomButton(None, dialog._tr("tooltip.use_favorite"))
    dialog.btn_set_favorite.setFixedHeight(30)
    dialog.btn_use_favorite.setFixedHeight(30)
    dialog.btn_set_favorite.clicked.connect(dialog._on_set_favorite_clicked)
    dialog.btn_use_favorite.clicked.connect(dialog._on_use_favorite_clicked)
    fav_row.addWidget(dialog.btn_set_favorite)
    fav_row.addWidget(dialog.btn_use_favorite)
    layout.addLayout(fav_row)

    layout.addSpacing(10)
    layout.addWidget(CaptionLabel(dialog._tr("label.file_name") + ":"))
    dialog.edit_filename = CustomLineEdit()
    layout.addWidget(dialog.edit_filename)

    layout.addStretch()
    return tab

def create_quality_stack(dialog):
    stack = QStackedWidget()

    p_crf = QWidget()
    l_crf = QVBoxLayout(p_crf)
    l_crf.setContentsMargins(0, 0, 0, 0)
    l_crf.setSpacing(6)
    l_crf.addWidget(CaptionLabel(dialog._tr("video.crf_value_051_lower_is_better") + ":"))

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
    l_bit.addWidget(CaptionLabel(dialog._tr("video.bitrate_eg_5000k_5m") + ":"))

    dialog.edit_bitrate = CustomLineEdit()
    dialog.edit_bitrate.setText("8000k")
    l_bit.addWidget(dialog.edit_bitrate)

    stack.addWidget(p_bit)

    return stack

def create_toolbar(dialog):
    toolbar_frame = QFrame()
    toolbar_frame.setObjectName("VideoEditorToolbar")
    toolbar_frame.setFixedHeight(50)
    toolbar_frame.setStyleSheet("""
        QFrame#VideoEditorToolbar {
            background: transparent;
            border: none;
            border-top: 1px solid rgba(128, 128, 128, 0.2);
        }
    """)

    toolbar_layout = QHBoxLayout(toolbar_frame)
    toolbar_layout.setContentsMargins(10, 5, 10, 5)
    toolbar_layout.setSpacing(8)

    dialog.btn_play = ToggleIconButton(AppIcon.PLAY, AppIcon.PAUSE)
    dialog.btn_play.setToolTip(dialog._tr("button.play") + " / " + dialog._tr("button.pause"))
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
    scroll_area.setFixedHeight(135)
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setStyleSheet("background: transparent;")
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    dialog.custom_scrollbar = MinimalistScrollBar(Qt.Orientation.Horizontal, scroll_area)
    scroll_area.setHorizontalScrollBar(dialog.custom_scrollbar)

    store = None
    if hasattr(dialog, 'export_controller') and dialog.export_controller:
        if hasattr(dialog.export_controller, 'store') and dialog.export_controller.store:
            store = dialog.export_controller.store
    dialog.timeline = VideoTimelineWidget(dialog.snapshots, store=store)
    dialog.timeline.setFixedHeight(120)
    scroll_area.setWidget(dialog.timeline)

    dialog.timeline.headMoved.connect(dialog._on_head_moved)
    dialog.timeline.deletePressed.connect(dialog._on_trim_clicked)

    return scroll_area

