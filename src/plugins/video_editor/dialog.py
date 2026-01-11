import logging
import os
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QResizeEvent, QShortcut, QKeySequence
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QWidget, QFrame, QSizePolicy, QLineEdit, QPushButton, QFileDialog)

from plugins.video_editor.widgets.timeline import VideoTimelineWidget
from toolkit.widgets.atomic.custom_line_edit import CustomLineEdit
from toolkit.widgets.atomic.text_labels import BodyLabel, CaptionLabel, GroupTitleLabel
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from plugins.video_editor.presenter import VideoEditorPresenter
from plugins.video_editor.services.export_config import ExportConfigBuilder
from resources.translations import tr
from plugins.video_editor.dialog_sections import build_settings_panel, create_toolbar, create_timeline_scroll_area

logger = logging.getLogger("ImproveImgSLI")

class VideoEditorDialog(QDialog):

    playClicked = pyqtSignal(bool)
    timelineScrubbed = pyqtSignal(int)
    undoClicked = pyqtSignal()
    redoClicked = pyqtSignal()
    trimClicked = pyqtSignal()
    exportClicked = pyqtSignal()

    widthChanged = pyqtSignal(int)
    heightChanged = pyqtSignal(int)

    fpsChanged = pyqtSignal(int)
    aspectRatioLockChanged = pyqtSignal(bool)
    fitContentChanged = pyqtSignal(bool)
    containerChanged = pyqtSignal(str)
    windowResized = pyqtSignal()

    def __init__(self, snapshots, export_controller, main_window_app, parent=None):
        super().__init__(main_window_app if main_window_app else parent)

        self.current_language = "en"
        if hasattr(export_controller, 'store') and export_controller.store:
            self.current_language = export_controller.store.settings.current_language

        self.setWindowTitle(tr("video.video_editor_exporter", self.current_language))
        self.resize(1200, 850)

        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.WindowTitleHint |
                            Qt.WindowType.WindowCloseButtonHint |
                            Qt.WindowType.WindowMaximizeButtonHint |
                            Qt.WindowType.WindowMinimizeButtonHint)

        self.export_controller = export_controller
        self.main_window_app = main_window_app
        self.theme_manager = ThemeManager.get_instance()
        self.snapshots = snapshots

        self._init_ui()
        self._apply_style()

        main_controller = export_controller.presenter.main_controller if hasattr(export_controller, 'presenter') else None
        self.presenter = VideoEditorPresenter(self, snapshots, main_controller)
        self._connect_presenter_signals()

        if hasattr(self, 'edit_fps') and hasattr(self.presenter, 'model'):

            max_fps = 240
            if hasattr(self, 'snapshots') and self.snapshots:
                first_snapshot = self.snapshots[0] if self.snapshots else None
                if first_snapshot and hasattr(first_snapshot, 'settings_state'):
                    recording_fps = getattr(first_snapshot.settings_state, 'video_recording_fps', None)
                    if recording_fps:
                        max_fps = recording_fps

            self.edit_fps.blockSignals(True)
            self.edit_fps.setRange(1, max_fps)
            initial_fps = min(self.presenter.model.fps, max_fps)
            self.edit_fps.setValue(initial_fps)
            if initial_fps != self.presenter.model.fps:
                self.presenter.model.fps = initial_fps
            self.edit_fps.blockSignals(False)

        self.theme_manager.theme_changed.connect(self._apply_style)
        self.theme_manager.theme_changed.connect(self._update_settings_panel_width)

        self._on_container_changed(self.combo_container.currentText())

        QTimer.singleShot(0, self.presenter._initialize_output_fields)
        QTimer.singleShot(10, self._update_settings_panel_width)

    def _connect_presenter_signals(self):
        self.presenter.previewUpdated.connect(self._on_preview_updated)
        self.presenter.timelinePositionChanged.connect(self._on_timeline_position_changed)
        self.presenter.playbackStateChanged.connect(self._on_playback_state_changed)
        self.presenter.buttonsStateChanged.connect(self._on_buttons_state_changed)
        self.presenter.thumbnailsUpdated.connect(self._on_thumbnails_updated)
        self.presenter.exportStarted.connect(self._on_export_started)
        self.presenter.errorOccurred.connect(self._on_error_occurred)

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.top_container = QWidget()
        top_layout = QHBoxLayout(self.top_container)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(10)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("VideoEditorPreviewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview_label.setMinimumSize(480, 270)
        top_layout.addWidget(self.preview_label, stretch=1)

        self.settings_panel = build_settings_panel(self)
        top_layout.addWidget(self.settings_panel)

        self.main_layout.addWidget(self.top_container, stretch=1)

        self.toolbar_frame = create_toolbar(self)
        self.main_layout.addWidget(self.toolbar_frame)

        self.scroll_area = create_timeline_scroll_area(self)
        self.main_layout.addWidget(self.scroll_area)

        self._set_focus_policies()
        self._setup_shortcuts()

    def _update_settings_panel_width(self):
        try:
            self.settings_panel.ensurePolished()

            max_tab_content_width = 0
            for i in range(self.tabs.count()):
                widget = self.tabs.widget(i)
                if widget:
                    widget.ensurePolished()
                    widget.adjustSize()

                    max_tab_content_width = max(max_tab_content_width, widget.sizeHint().width())

            tab_bar_width = self.tabs.tabBar().sizeHint().width()

            self.btn_export.ensurePolished()
            self.btn_export.adjustSize()
            btn_width = self.btn_export.sizeHint().width()

            padding = 24

            safe_margin = 20

            min_panel_width = 350

            max_panel_width = 650

            required_by_tabs = max_tab_content_width + padding + safe_margin

            required_by_tabbar = tab_bar_width + padding + safe_margin

            required_by_btn = btn_width + padding

            optimal_width = max(min_panel_width, required_by_tabs, required_by_tabbar, required_by_btn)
            optimal_width = min(optimal_width, max_panel_width)

            self.settings_panel.setFixedWidth(int(optimal_width))

        except Exception as e:
            logger.warning(f"Error calculating panel width: {e}")
            self.settings_panel.setFixedWidth(380)

    def _set_focus_policies(self):
        for btn in [self.btn_undo, self.btn_redo, self.btn_trim, self.btn_play, self.btn_export, self.btn_lock_ratio, self.btn_fit_content]:
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.timeline.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_shortcuts(self):

        def handle_space():
            focused = self.focusWidget()
            if not isinstance(focused, (QLineEdit, CustomLineEdit)):
                self._on_play_toggled(not self.btn_play.isChecked())

        self.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.shortcut_space.activated.connect(handle_space)

        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self._on_undo_clicked)

        self.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.shortcut_redo.activated.connect(self._on_redo_clicked)

        self.shortcut_redo_alt = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.shortcut_redo_alt.activated.connect(self._on_redo_clicked)

        def handle_delete():
            focused = self.focusWidget()
            if not isinstance(focused, (QLineEdit, CustomLineEdit)):
                self._on_trim_clicked()

        self.shortcut_delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self.shortcut_delete.activated.connect(handle_delete)

        self.shortcut_backspace = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self.shortcut_backspace.activated.connect(handle_delete)

    def _load_initial_data(self):

        pass

    def set_preview_image(self, pixmap: QPixmap):
        if pixmap:
            label_w = self.preview_label.width()
            label_h = self.preview_label.height()
            pix_w = pixmap.width()
            pix_h = pixmap.height()

            logger.debug(f"[set_preview_image] Label size: {label_w}x{label_h}, Pixmap size: {pix_w}x{pix_h}")

            if label_w > 0 and label_h > 0 and (abs(pix_w - label_w) > 10 or abs(pix_h - label_h) > 10):

                scaled_pixmap = pixmap.scaled(
                    label_w, label_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                logger.debug(f"[set_preview_image] Scaled to: {scaled_pixmap.width()}x{scaled_pixmap.height()}")
                self.preview_label.setPixmap(scaled_pixmap)
            else:

                self.preview_label.setPixmap(pixmap)
        else:
            logger.warning(f"[set_preview_image] Received None pixmap!")

    def set_timeline_position(self, frame_idx: int):
        self.timeline.blockSignals(True)
        self.timeline.set_current_frame(frame_idx)
        self.timeline.blockSignals(False)

    def set_snapshots(self, snapshots):
        self.timeline.set_data(snapshots)

    def set_resolution(self, width: int, height: int):
        self.edit_width.blockSignals(True)
        self.edit_height.blockSignals(True)
        self.edit_width.setText(str(width))
        self.edit_height.setText(str(height))
        self.edit_width.blockSignals(False)
        self.edit_height.blockSignals(False)

    def update_available_codecs(self, codecs: list, default_codec: str):
        self.combo_codec.blockSignals(True)
        self.combo_codec.clear()
        self.combo_codec.addItems([self._tr(codec) for codec in codecs])

        idx = self.combo_codec.findText(self._tr(default_codec))
        if idx >= 0:
            self.combo_codec.setCurrentIndex(idx)
        elif self.combo_codec.count() > 0:
            self.combo_codec.setCurrentIndex(0)

        self.combo_codec.blockSignals(False)

        self._on_codec_changed(self.combo_codec.currentText())

    def get_selection_range(self) -> tuple:
        return self.timeline.get_selection_range()

    def get_export_options(self) -> dict:
        is_manual = self.tabs.currentIndex() == 1

        output_opts = {
            "output_dir": self.edit_output_dir.text(),
            "file_name": self.edit_filename.text()
        }

        if is_manual:
            return {
                "manual_mode": True,
                "manual_args": self.edit_manual_args.text(),
                **output_opts
            }
        else:

            container_text = self.combo_container.currentText()
            codec_text = self.combo_codec.currentText()
            preset_text = self.combo_preset.currentText()

            container_map = {self._tr(c): c for c in ExportConfigBuilder.get_available_containers()}
            codec_map = {self._tr(c): c for c in ExportConfigBuilder.get_codecs_for_container(container_map.get(container_text, "mp4"))}

            preset_value = self._preset_from_translated(preset_text)

            return {
                "manual_mode": False,
                "container": container_map.get(container_text, "mp4"),
                "codec": codec_map.get(codec_text, "h264 (AVC)"),
                "quality_mode": "crf" if self.combo_quality_mode.currentIndex() == 0 else "bitrate",
                "crf": int(self.edit_crf.text()) if self.edit_crf.text().isdigit() else 23,
                "bitrate": self.edit_bitrate.text(),
                "preset": preset_value,
                **output_opts
            }

    def get_preview_size(self) -> tuple:
        return self.preview_label.width(), self.preview_label.height()

    def _on_play_toggled(self, checked: bool):
        self.playClicked.emit(checked)

    def _on_undo_clicked(self):
        self.undoClicked.emit()

    def _on_redo_clicked(self):
        self.redoClicked.emit()

    def _on_trim_clicked(self):
        self.trimClicked.emit()

    def _on_export_clicked(self):
        self.exportClicked.emit()

    def _on_head_moved(self, index: int):
        self.timelineScrubbed.emit(index)

    def _on_width_edited(self):
        try:
            val = int(self.edit_width.text())
            self.widthChanged.emit(val)
        except ValueError:
            pass

    def _on_height_edited(self):
        try:
            val = int(self.edit_height.text())
            self.heightChanged.emit(val)
        except ValueError:
            pass

    def _on_fps_changed(self, fps: int):
        self.fpsChanged.emit(fps)

    def _on_ratio_lock_toggled(self, checked: bool):
        self.aspectRatioLockChanged.emit(checked)

    def _on_fit_content_toggled(self, checked: bool):
        self.fitContentChanged.emit(checked)

    def _on_container_changed(self, text: str):
        self.containerChanged.emit(text)

    def _on_codec_changed(self, codec_text: str):
        caps = ExportConfigBuilder.get_codec_capabilities(codec_text)

        has_quality = caps["has_crf"] or caps["has_bitrate"]
        self.quality_controls_container.setVisible(has_quality)

        if has_quality:

            self.combo_quality_mode.blockSignals(True)
            self.combo_quality_mode.clear()

            if caps["has_crf"]:
                self.combo_quality_mode.addItem(self._tr("video.crf_constant_quality"))
            if caps["has_bitrate"]:
                self.combo_quality_mode.addItem(self._tr("video.bitrate_cbrvbr"))

            self.combo_quality_mode.setCurrentIndex(0)
            self.combo_quality_mode.blockSignals(False)

            self.stack_quality.setCurrentIndex(0)

        self.preset_container.setVisible(caps["has_preset"])

        if caps["has_preset"]:
            self.lbl_preset.setText(self._tr(caps.get("preset_label", "video.encoding_speed_preset")) + ":")

            self.combo_preset.blockSignals(True)
            self.combo_preset.clear()
            presets = ExportConfigBuilder.get_presets_for_codec(codec_text)

            for p in presets:
                self.combo_preset.addItem(self._tr_preset(p))

            if "medium" in presets:
                self.combo_preset.setCurrentText(self._tr_preset("medium"))
            elif "standard" in presets:
                self.combo_preset.setCurrentText(self._tr_preset("standard"))
            elif len(presets) > 0:
                self.combo_preset.setCurrentIndex(0)

            self.combo_preset.blockSignals(False)

    def _on_preview_updated(self, pixmap: QPixmap):
        self.set_preview_image(pixmap)

    def _on_timeline_position_changed(self, frame_idx: int):
        self.set_timeline_position(frame_idx)

    def _on_playback_state_changed(self, is_playing: bool):
        if self.btn_play.isChecked() != is_playing:
            self.btn_play.setChecked(is_playing, emit_signal=False)

    def _on_buttons_state_changed(self, can_undo: bool, can_redo: bool):
        self.btn_undo.setEnabled(can_undo)
        self.btn_redo.setEnabled(can_redo)

        undo_opacity = "1.0" if can_undo else "0.4"
        redo_opacity = "1.0" if can_redo else "0.4"

        self.btn_undo.setProperty("opacity", undo_opacity)
        self.btn_redo.setProperty("opacity", redo_opacity)

    def _on_thumbnails_updated(self, thumbnails: dict):
        self.timeline._thumbnails.update(thumbnails)
        self.timeline._thumb_indices = sorted(thumbnails.keys())
        self.timeline.update()

    def _on_export_started(self):

        self.export_progress.setStyleSheet("""
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
        self.set_export_progress(0)

    def set_export_progress(self, value: int):
        if not self.export_progress.isVisible():
            self.export_progress.setVisible(True)
            self.btn_export.setEnabled(False)
            self.btn_export.setText(self._tr("video.rendering"))

        self.export_progress.setValue(value)

    def on_export_finished(self, success: bool):
        if success:

            self.export_progress.setValue(100)

            self.export_progress.setStyleSheet("""
                QProgressBar {
                    border: none;
                    background-color: #2d2d2d;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background-color: #28a745;
                    border-radius: 2px;
                }
            """)
            self.btn_export.setText(self._tr("video.done"))

            QTimer.singleShot(2000, self._reset_export_ui_state)
        else:

            self._reset_export_ui_state()

    def _reset_export_ui_state(self):
        self.export_progress.setVisible(False)
        self.export_progress.setValue(0)
        self.btn_export.setEnabled(True)
        self.btn_export.setText(self._tr("action.export_video"))

        self.export_progress.setStyleSheet("""
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

    def _on_error_occurred(self, error_message: str):
        logger.error(f"Video editor error: {error_message}")

    def _browse_output_dir(self, checked: bool = False):

        current_dir = self.edit_output_dir.text() if hasattr(self, 'edit_output_dir') else ""

        if not current_dir or not os.path.isdir(current_dir):
            if self.export_controller and hasattr(self.export_controller, 'store') and self.export_controller.store:
                current_dir = self.export_controller.store.settings.export_default_dir or ""
            if not current_dir:
                from pathlib import Path
                current_dir = str(Path.home() / "Downloads")

        selected_dir = QFileDialog.getExistingDirectory(
            self,
            self._tr("export.select_output_directory"),
            current_dir,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog
        )

        if selected_dir:
            self.edit_output_dir.setText(selected_dir)
            self.edit_output_dir.setCursorPosition(0)

    def _on_set_favorite_clicked(self, checked: bool = False):

        if not hasattr(self, 'edit_output_dir'):
            return

        current_path = self.edit_output_dir.text().strip()
        if not current_path:
            return

        if self.presenter:
            self.presenter.set_favorite_path(current_path)

    def _on_use_favorite_clicked(self, checked: bool = False):

        if not hasattr(self, 'edit_output_dir') or not self.presenter:
            return

        favorite_path = self.presenter.get_favorite_path()
        if favorite_path and os.path.isdir(favorite_path):
            self.edit_output_dir.setText(favorite_path)
            self.edit_output_dir.setCursorPosition(0)

    def _tr(self, text):
        return tr(text, self.current_language)

    def _tr_preset(self, preset):

        gif_mapping = {
            "High Quality": "video.high_quality",
            "Balanced": "video.balanced",
            "Compact (Dithered)": "video.compact_dithered"
        }
        if preset in gif_mapping:
            return self._tr(gif_mapping[preset])

        return self._tr(f"video.{preset}")

    def _preset_from_translated(self, translated_text):

        gif_reverse_mapping = {
            self._tr("video.high_quality"): "High Quality",
            self._tr("video.balanced"): "Balanced",
            self._tr("video.compact_dithered"): "Compact (Dithered)"
        }
        if translated_text in gif_reverse_mapping:
            return gif_reverse_mapping[translated_text]

        standard_presets = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
        prores_presets = ["proxy", "lt", "standard", "hq", "4444"]
        all_presets = standard_presets + prores_presets
        for preset in all_presets:
            if self._tr_preset(preset) == translated_text:
                return preset
        return "medium"

    def _apply_style(self):
        self.theme_manager.apply_theme_to_dialog(self)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.windowResized.emit()

        if hasattr(self, 'timeline'):
            self.timeline.update_layout_width()

    def showEvent(self, event):
        super().showEvent(event)

        if hasattr(self, 'timeline'):
            QTimer.singleShot(100, self.timeline.fit_view)

        self.setFocus()

        QTimer.singleShot(150, self.windowResized.emit)

    def keyPressEvent(self, event):

            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        focused_widget = self.focusWidget()
        if isinstance(focused_widget, (QLineEdit, CustomLineEdit)):
            focused_widget.clearFocus()
        super().mousePressEvent(event)

