import logging
import os

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPixmap, QResizeEvent, QShortcut
from PyQt6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from domain.qt_adapters import color_to_hex, hex_to_color, qcolor_to_color
from plugins.video_editor.dialog_sections import (
    build_settings_panel,
    create_timeline_scroll_area,
    create_toolbar,
)
from plugins.video_editor.presenter import VideoEditorPresenter
from plugins.video_editor.services.export_config import ExportConfigBuilder
from resources.translations import tr
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from ui.widgets.gl_canvas import GLCanvas

logger = logging.getLogger("ImproveImgSLI")

class VideoEditorDialog(QDialog):
    readyToShow = pyqtSignal()

    playClicked = pyqtSignal(bool)
    timelineScrubbed = pyqtSignal(int)
    undoClicked = pyqtSignal()
    redoClicked = pyqtSignal()
    trimClicked = pyqtSignal()
    exportClicked = pyqtSignal()
    stopExportClicked = pyqtSignal()

    widthChanged = pyqtSignal(int)
    heightChanged = pyqtSignal(int)

    fpsChanged = pyqtSignal(int)
    aspectRatioLockChanged = pyqtSignal(bool)
    fitContentChanged = pyqtSignal(bool)
    fitContentFillColorChanged = pyqtSignal(object)
    containerChanged = pyqtSignal(str)
    windowResized = pyqtSignal()
    timelineHeightChanged = pyqtSignal(int)

    def __init__(self, snapshots, export_controller, main_window_app, parent=None):
        super().__init__(parent)

        self.current_language = "en"
        if hasattr(export_controller, "store") and export_controller.store:
            self.current_language = export_controller.store.settings.current_language

        self.setWindowTitle(tr("video.video_editor_exporter", self.current_language))
        self.resize(1200, 850)
        self.setMinimumSize(1100, 820)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.export_controller = export_controller
        self.main_window_app = main_window_app
        self.theme_manager = ThemeManager.get_instance()
        self.snapshots = snapshots
        self.fit_content_fill_color = QColor(0, 0, 0, 255)
        self._ready_to_show_emitted = False

        self._init_ui()
        self._apply_style()

        main_controller = (
            export_controller.presenter.main_controller
            if hasattr(export_controller, "presenter")
            else None
        )
        self.presenter = VideoEditorPresenter(self, snapshots, main_controller)
        self._connect_presenter_signals()

        if hasattr(self, "edit_fps") and hasattr(self.presenter, "model"):

            max_fps = 240
            first_snapshot = self._get_first_snapshot()
            if first_snapshot and hasattr(first_snapshot, "settings_state"):
                recording_fps = getattr(
                    first_snapshot.settings_state, "video_recording_fps", None
                )
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
        self.theme_manager.theme_changed.connect(self._update_preview_palette)
        self._update_preview_palette()

        self._load_export_settings()
        self._connect_export_settings_persistence()

        QTimer.singleShot(0, self.presenter._initialize_output_fields)
        QTimer.singleShot(10, self._update_settings_panel_width)
        QTimer.singleShot(1200, self._emit_ready_to_show)

    def _get_first_snapshot(self):
        snapshots = getattr(self, "snapshots", None)
        if snapshots is None:
            return None
        if isinstance(snapshots, (list, tuple)):
            return snapshots[0] if snapshots else None
        if hasattr(snapshots, "evaluate_at"):
            try:
                return snapshots.evaluate_at(0.0)
            except Exception:
                return None
        return None

    def _connect_presenter_signals(self):
        self.presenter.previewUpdated.connect(self._on_preview_updated)
        self.presenter.previewReady.connect(self._emit_ready_to_show)
        self.presenter.timelinePositionChanged.connect(
            self._on_timeline_position_changed
        )
        self.presenter.playbackStateChanged.connect(self._on_playback_state_changed)
        self.presenter.buttonsStateChanged.connect(self._on_buttons_state_changed)
        self.presenter.thumbnailsUpdated.connect(self._on_thumbnails_updated)
        self.presenter.exportStarted.connect(self._on_export_started)
        self.presenter.errorOccurred.connect(self._on_error_occurred)

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.setHandleWidth(8)
        self.main_layout.addWidget(self.vertical_splitter, stretch=1)

        self.top_container = QWidget()
        top_layout = QHBoxLayout(self.top_container)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(10)

        self.preview_label = GLCanvas()
        self.preview_label.setObjectName("VideoEditorPreviewLabel")
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self.preview_label.setMinimumSize(480, 270)
        top_layout.addWidget(self.preview_label, stretch=1)

        self.settings_panel = build_settings_panel(self)
        top_layout.addWidget(self.settings_panel)
        self.vertical_splitter.addWidget(self.top_container)

        self.bottom_container = QWidget()
        bottom_layout = QVBoxLayout(self.bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        self.toolbar_frame = create_toolbar(self)
        bottom_layout.addWidget(self.toolbar_frame)

        self.scroll_area = create_timeline_scroll_area(self)
        bottom_layout.addWidget(self.scroll_area, stretch=1)
        self.bottom_container.setMinimumHeight(250)
        self.vertical_splitter.addWidget(self.bottom_container)
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 0)
        self.vertical_splitter.setSizes([560, 260])
        self.vertical_splitter.splitterMoved.connect(self._on_splitter_moved)

        self._set_focus_policies()
        self._setup_shortcuts()

    def _on_splitter_moved(self, _pos: int, _index: int):
        self.timelineHeightChanged.emit(self.scroll_area.viewport().height())

    def _update_settings_panel_width(self):
        try:
            self.settings_panel.ensurePolished()

            max_tab_content_width = 0
            for i in range(self.tabs.count()):
                widget = self.tabs.widget(i)
                if widget:
                    widget.ensurePolished()
                    widget.adjustSize()

                    max_tab_content_width = max(
                        max_tab_content_width, widget.sizeHint().width()
                    )

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

            optimal_width = max(
                min_panel_width, required_by_tabs, required_by_tabbar, required_by_btn
            )
            optimal_width = min(optimal_width, max_panel_width)

            self.settings_panel.setFixedWidth(int(optimal_width))

        except Exception as e:
            logger.warning(f"Error calculating panel width: {e}")
            self.settings_panel.setFixedWidth(380)

    def _set_focus_policies(self):
        for btn in [
            self.btn_undo,
            self.btn_redo,
            self.btn_trim,
            self.btn_play,
            self.btn_export,
            self.btn_lock_ratio,
            self.btn_fit_content,
            self.btn_fit_fill_color,
        ]:
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        if hasattr(self, "btn_stop_export"):
            self.btn_stop_export.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.timeline.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _position_stop_export_button(self):
        if not hasattr(self, "btn_export") or not hasattr(self, "btn_stop_export"):
            return
        btn = self.btn_stop_export
        host = self.btn_export
        x = 12
        y = max(0, (host.height() - btn.height()) // 2)
        btn.move(x, y)
        btn.raise_()

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
            if hasattr(self.preview_label, "set_pixmap"):
                self.preview_label.set_pixmap(pixmap)
                return

            label_w = self.preview_label.width()
            label_h = self.preview_label.height()
            pix_w = pixmap.width()
            pix_h = pixmap.height()

            if (
                label_w > 0
                and label_h > 0
                and (abs(pix_w - label_w) > 10 or abs(pix_h - label_h) > 10)
            ):

                scaled_pixmap = pixmap.scaled(
                    label_w,
                    label_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_label.setPixmap(scaled_pixmap)
            else:

                self.preview_label.setPixmap(pixmap)
        else:
            logger.warning("[set_preview_image] Received None pixmap!")

    def set_timeline_position(self, frame_idx: int):
        self.timeline.blockSignals(True)
        self.timeline.set_current_frame(frame_idx)
        self.timeline.blockSignals(False)

    def set_snapshots(
        self,
        snapshots,
        fps: int | None = None,
        timeline_model=None,
        duration: float | None = None,
    ):
        self.timeline.set_data(
            snapshots, fps=fps, timeline_model=timeline_model, duration=duration
        )

    def set_resolution(self, width: int, height: int):
        self.edit_width.blockSignals(True)
        self.edit_height.blockSignals(True)
        self.edit_width.setText(str(width))
        self.edit_height.setText(str(height))
        self.edit_width.blockSignals(False)
        self.edit_height.blockSignals(False)

    def update_available_codecs(self, codecs: list, default_codec: str):
        current_codec = self.combo_codec.currentData()
        self.combo_codec.blockSignals(True)
        self.combo_codec.clear()
        for codec in codecs:
            self.combo_codec.addItem(self._tr(codec), codec)

        target_codec = current_codec if current_codec in codecs else default_codec
        idx = self.combo_codec.findData(target_codec)
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
            "file_name": self.edit_filename.text(),
        }

        if is_manual:
            return {
                "manual_mode": True,
                "manual_args": self.edit_manual_args.text(),
                "fit_content_fill_color": self.fit_content_fill_color.name(
                    QColor.NameFormat.HexArgb
                ),
                **output_opts,
            }
        else:

            return {
                "manual_mode": False,
                "container": self.combo_container.currentData() or "mp4",
                "codec": ExportConfigBuilder.get_codec_internal_name(
                    self.combo_codec.currentData() or "h264 (AVC)"
                ),
                "quality_mode": self.combo_quality_mode.currentData() or "crf",
                "crf": (
                    int(self.edit_crf.text()) if self.edit_crf.text().isdigit() else 23
                ),
                "bitrate": self.edit_bitrate.text(),
                "preset": self.combo_preset.currentData() or "",
                "pix_fmt": self.combo_pix_fmt.currentData() or "",
                "fit_content_fill_color": self.fit_content_fill_color.name(
                    QColor.NameFormat.HexArgb
                ),
                **output_opts,
            }

    def get_preview_size(self) -> tuple:
        try:
            width = self.preview_label.width()
            height = self.preview_label.height()
            if width >= 10 and height >= 10:
                return width, height
            hint = self.preview_label.sizeHint()
            return max(width, hint.width()), max(height, hint.height())
        except RuntimeError:
            return (0, 0)

    def _emit_ready_to_show(self) -> None:
        if self._ready_to_show_emitted:
            return
        self._ready_to_show_emitted = True
        self.readyToShow.emit()

    def _on_play_toggled(self, checked: bool):
        self.playClicked.emit(checked)

    def _on_undo_clicked(self):
        self.undoClicked.emit()

    def _on_redo_clicked(self):
        self.redoClicked.emit()

    def _on_trim_clicked(self):
        self.trimClicked.emit()

    def _on_export_clicked(self):
        if hasattr(self, "export_progress") and self.export_progress.isVisible():
            return
        self.exportClicked.emit()

    def _on_stop_export_clicked(self):
        self.stopExportClicked.emit()

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
        if hasattr(self, "btn_fit_fill_color"):
            self.btn_fit_fill_color.setVisible(bool(checked))
        self.fitContentChanged.emit(checked)

    def _on_fit_fill_color_clicked(self):
        color = QColorDialog.getColor(
            self.fit_content_fill_color,
            self,
            self._tr("export.select_background_color"),
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        self.fit_content_fill_color = color
        self._update_fit_fill_color_button()
        self._persist_export_settings()
        self.fitContentFillColorChanged.emit(color)

    def _update_fit_fill_color_button(self):
        if not hasattr(self, "btn_fit_fill_color"):
            return

        color = QColor(self.fit_content_fill_color)
        if not color.isValid():
            color = QColor(0, 0, 0, 255)
        if hasattr(self.btn_fit_fill_color, "set_color"):
            self.btn_fit_fill_color.set_color(color)

    def _on_container_changed(self, text: str):
        container = self.combo_container.currentData()
        if container:
            self.containerChanged.emit(container)

    def _on_codec_changed(self, codec_text: str):
        codec_name = self.combo_codec.currentData() or codec_text
        caps = ExportConfigBuilder.get_codec_capabilities(codec_name)
        current_quality_mode = self.combo_quality_mode.currentData()
        current_preset = self.combo_preset.currentData()
        current_pix_fmt = self.combo_pix_fmt.currentData()

        has_quality = caps["has_crf"] or caps["has_bitrate"]
        self.quality_controls_container.setVisible(has_quality)

        if has_quality:

            self.combo_quality_mode.blockSignals(True)
            self.combo_quality_mode.clear()

            if caps["has_crf"]:
                self.combo_quality_mode.addItem(
                    self._tr("video.crf_constant_quality"), "crf"
                )
            if caps["has_bitrate"]:
                self.combo_quality_mode.addItem(
                    self._tr("video.bitrate_cbrvbr"), "bitrate"
                )

            preferred_quality_mode = (
                current_quality_mode
                if current_quality_mode in {
                    self.combo_quality_mode.itemData(i)
                    for i in range(self.combo_quality_mode.count())
                }
                else ("crf" if caps["has_crf"] else "bitrate")
            )
            quality_idx = self.combo_quality_mode.findData(preferred_quality_mode)
            self.combo_quality_mode.setCurrentIndex(max(0, quality_idx))
            self.combo_quality_mode.blockSignals(False)

            self.stack_quality.setCurrentIndex(self.combo_quality_mode.currentIndex())

        self.preset_container.setVisible(caps["has_preset"])

        if caps["has_preset"]:
            self.lbl_preset.setText(
                self._tr(caps.get("preset_label", "video.encoding_speed_preset")) + ":"
            )

            self.combo_preset.blockSignals(True)
            self.combo_preset.clear()
            presets = ExportConfigBuilder.get_presets_for_codec(codec_name)

            for p in presets:
                self.combo_preset.addItem(self._tr_preset(p), p)

            preferred_preset = current_preset
            if preferred_preset not in presets:
                if "medium" in presets:
                    preferred_preset = "medium"
                elif "standard" in presets:
                    preferred_preset = "standard"
                elif presets:
                    preferred_preset = presets[0]

            idx = self.combo_preset.findData(preferred_preset)
            if idx >= 0:
                self.combo_preset.setCurrentIndex(idx)
            elif presets:
                self.combo_preset.setCurrentIndex(0)

            self.combo_preset.blockSignals(False)
        else:
            self.combo_preset.clear()

        pix_fmts = ExportConfigBuilder.get_pixel_formats_for_codec(codec_name)
        self.pix_fmt_container.setVisible(bool(pix_fmts))
        self.combo_pix_fmt.blockSignals(True)
        self.combo_pix_fmt.clear()
        for pix_fmt in pix_fmts:
            self.combo_pix_fmt.addItem(pix_fmt, pix_fmt)

        preferred_pix_fmt = current_pix_fmt
        if preferred_pix_fmt not in pix_fmts:
            preferred_pix_fmt = ExportConfigBuilder.get_default_pixel_format_for_codec(
                codec_name
            )

        pix_fmt_idx = self.combo_pix_fmt.findData(preferred_pix_fmt)
        if pix_fmt_idx >= 0:
            self.combo_pix_fmt.setCurrentIndex(pix_fmt_idx)
        elif pix_fmts:
            self.combo_pix_fmt.setCurrentIndex(0)
        self.combo_pix_fmt.blockSignals(False)

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
        self.timeline.set_thumbnails(thumbnails)

    def _on_export_started(self):
        self._set_export_progress_state("active")
        self.set_export_progress(0)

    def set_export_progress(self, value: int):
        if not self.export_progress.isVisible():
            self.export_progress.setVisible(True)
            self.btn_export.set_override_bg_color(
                QColor(self.theme_manager.get_color("button.primary.background"))
            )
            self.btn_export.setCursor(Qt.CursorShape.ArrowCursor)
            self.btn_export.setText(self._tr("video.rendering"))
            self.btn_stop_export.show()
            self._position_stop_export_button()

        self.export_progress.setValue(value)

    def on_export_finished(self, success: bool):
        if success:

            self.export_progress.setValue(100)
            self._set_export_progress_state("success")
            self.btn_export.setText(self._tr("video.done"))

            QTimer.singleShot(2000, self._reset_export_ui_state)
        else:

            self._reset_export_ui_state()

    def _reset_export_ui_state(self):
        self.export_progress.setVisible(False)
        self.export_progress.setValue(0)
        self.btn_export.set_override_bg_color(None)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setText(self._tr("action.export_video"))
        if hasattr(self, "btn_stop_export"):
            self.btn_stop_export.hide()
        self._set_export_progress_state("active")

    def _on_error_occurred(self, error_message: str):
        logger.error(f"Video editor error: {error_message}")

    def _set_export_progress_state(self, state: str) -> None:
        if not hasattr(self, "export_progress"):
            return
        self.export_progress.setProperty("state", state)
        self.export_progress.style().unpolish(self.export_progress)
        self.export_progress.style().polish(self.export_progress)
        self.export_progress.update()

    def _browse_output_dir(self, checked: bool = False):

        current_dir = (
            self.edit_output_dir.text() if hasattr(self, "edit_output_dir") else ""
        )

        if not current_dir or not os.path.isdir(current_dir):
            if (
                self.export_controller
                and hasattr(self.export_controller, "store")
                and self.export_controller.store
            ):
                current_dir = (
                    self.export_controller.store.settings.export_default_dir or ""
                )
            if not current_dir:
                from pathlib import Path

                current_dir = str(Path.home() / "Downloads")

        selected_dir = QFileDialog.getExistingDirectory(
            self,
            self._tr("export.select_output_directory"),
            current_dir,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog,
        )

        if selected_dir:
            self.edit_output_dir.setText(selected_dir)
            self.edit_output_dir.setCursorPosition(0)

    def _on_set_favorite_clicked(self, checked: bool = False):

        if not hasattr(self, "edit_output_dir"):
            return

        current_path = self.edit_output_dir.text().strip()
        if not current_path:
            return

        if self.presenter:
            self.presenter.set_favorite_path(current_path)

    def _on_use_favorite_clicked(self, checked: bool = False):

        if not hasattr(self, "edit_output_dir") or not self.presenter:
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
            "Compact (Dithered)": "video.compact_dithered",
        }
        if preset in gif_mapping:
            return self._tr(gif_mapping[preset])

        return self._tr(f"video.{preset}")

    def _preset_from_translated(self, translated_text):

        gif_reverse_mapping = {
            self._tr("video.high_quality"): "High Quality",
            self._tr("video.balanced"): "Balanced",
            self._tr("video.compact_dithered"): "Compact (Dithered)",
        }
        if translated_text in gif_reverse_mapping:
            return gif_reverse_mapping[translated_text]

        standard_presets = [
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ]
        prores_presets = ["proxy", "lt", "standard", "hq", "4444"]
        all_presets = standard_presets + prores_presets
        for preset in all_presets:
            if self._tr_preset(preset) == translated_text:
                return preset
        return "medium"

    def _get_settings_refs(self):
        store = None
        settings_manager = None
        if self.export_controller and hasattr(self.export_controller, "store"):
            store = self.export_controller.store
        if self.export_controller and hasattr(self.export_controller, "presenter"):
            main_controller = getattr(
                self.export_controller.presenter, "main_controller", None
            )
            if main_controller is not None:
                settings_manager = getattr(main_controller, "settings_manager", None)
                if store is None:
                    store = getattr(main_controller, "store", None)
        return store, settings_manager

    def _load_export_settings(self):
        store, settings_manager = self._get_settings_refs()
        settings = getattr(store, "settings", None)
        if settings is None:
            self._on_container_changed(self.combo_container.currentText())
            return

        self.edit_manual_args.setText(
            getattr(settings, "export_video_manual_args", self.edit_manual_args.text())
        )
        self.edit_crf.setText(str(getattr(settings, "export_video_crf", 23)))
        self.edit_bitrate.setText(
            getattr(settings, "export_video_bitrate", self.edit_bitrate.text())
        )

        container = getattr(settings, "export_video_container", "mp4")
        container_idx = self.combo_container.findData(container)
        if container_idx >= 0:
            self.combo_container.setCurrentIndex(container_idx)

        self._on_container_changed(self.combo_container.currentText())

        codec = getattr(settings, "export_video_codec", "h264 (AVC)")
        codec_idx = self.combo_codec.findData(codec)
        if codec_idx >= 0:
            self.combo_codec.setCurrentIndex(codec_idx)
        self._on_codec_changed(self.combo_codec.currentText())

        quality_mode = getattr(settings, "export_video_quality_mode", "crf")
        quality_idx = self.combo_quality_mode.findData(quality_mode)
        if quality_idx >= 0:
            self.combo_quality_mode.setCurrentIndex(quality_idx)
            self.stack_quality.setCurrentIndex(quality_idx)

        preset = getattr(settings, "export_video_preset", "medium")
        preset_idx = self.combo_preset.findData(preset)
        if preset_idx >= 0:
            self.combo_preset.setCurrentIndex(preset_idx)

        pix_fmt = getattr(settings, "export_video_pix_fmt", "yuv420p")
        pix_fmt_idx = self.combo_pix_fmt.findData(pix_fmt)
        if pix_fmt_idx >= 0:
            self.combo_pix_fmt.setCurrentIndex(pix_fmt_idx)

        fill_color_hex = getattr(settings, "export_video_fit_fill_color", None)
        if not fill_color_hex and settings_manager is not None:
            fill_color_hex = settings_manager._get_setting(
                "export_video_fit_fill_color", "#FF000000", str
            )
        if not fill_color_hex:
            fill_color_hex = "#FF000000"
        try:
            self.fit_content_fill_color = QColor(
                color_to_hex(hex_to_color(fill_color_hex))
            )
        except Exception:
            self.fit_content_fill_color = QColor(0, 0, 0, 255)
        self._update_fit_fill_color_button()
        if hasattr(self, "btn_fit_fill_color"):
            self.btn_fit_fill_color.setVisible(self.btn_fit_content.isChecked())

    def _connect_export_settings_persistence(self):
        self.combo_container.currentIndexChanged.connect(
            lambda *_: self._persist_export_settings()
        )
        self.combo_codec.currentIndexChanged.connect(
            lambda *_: self._persist_export_settings()
        )
        self.combo_quality_mode.currentIndexChanged.connect(
            lambda *_: self._persist_export_settings()
        )
        self.combo_preset.currentIndexChanged.connect(
            lambda *_: self._persist_export_settings()
        )
        self.combo_pix_fmt.currentIndexChanged.connect(
            lambda *_: self._persist_export_settings()
        )
        self.edit_crf.textChanged.connect(lambda *_: self._persist_export_settings())
        self.edit_bitrate.textChanged.connect(
            lambda *_: self._persist_export_settings()
        )
        self.edit_manual_args.textChanged.connect(
            lambda *_: self._persist_export_settings()
        )

    def _persist_export_settings(self):
        store, settings_manager = self._get_settings_refs()
        settings = getattr(store, "settings", None)
        if settings is None:
            return

        settings.export_video_container = self.combo_container.currentData() or "mp4"
        settings.export_video_codec = self.combo_codec.currentData() or "h264 (AVC)"
        settings.export_video_quality_mode = (
            self.combo_quality_mode.currentData() or "crf"
        )
        settings.export_video_crf = (
            int(self.edit_crf.text()) if self.edit_crf.text().isdigit() else 23
        )
        settings.export_video_bitrate = self.edit_bitrate.text().strip() or "8000k"
        settings.export_video_preset = self.combo_preset.currentData() or ""
        settings.export_video_pix_fmt = self.combo_pix_fmt.currentData() or ""
        settings.export_video_manual_args = self.edit_manual_args.text()
        settings.export_video_fit_fill_color = color_to_hex(
            qcolor_to_color(self.fit_content_fill_color)
        )

        if settings_manager is None:
            return

        settings_manager._save_setting(
            "export_video_container", settings.export_video_container
        )
        settings_manager._save_setting("export_video_codec", settings.export_video_codec)
        settings_manager._save_setting(
            "export_video_quality_mode", settings.export_video_quality_mode
        )
        settings_manager._save_setting("export_video_crf", settings.export_video_crf)
        settings_manager._save_setting(
            "export_video_bitrate", settings.export_video_bitrate
        )
        settings_manager._save_setting("export_video_preset", settings.export_video_preset)
        settings_manager._save_setting("export_video_pix_fmt", settings.export_video_pix_fmt)
        settings_manager._save_setting(
            "export_video_manual_args", settings.export_video_manual_args
        )
        settings_manager._save_setting(
            "export_video_fit_fill_color", settings.export_video_fit_fill_color
        )

    def _update_preview_palette(self):
        from PyQt6.QtGui import QPalette
        bg = QColor("#0a0a0a") if self.theme_manager.is_dark() else QColor("#f5f5f5")
        pal = self.preview_label.palette()
        pal.setColor(QPalette.ColorRole.Window, bg)
        self.preview_label.setPalette(pal)
        self.preview_label.update()

    def _apply_style(self):
        self.theme_manager.apply_theme_to_dialog(self)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.windowResized.emit()

        if hasattr(self, "timeline"):
            self.timeline.update_layout_width()
        self._position_stop_export_button()

    def showEvent(self, event):
        super().showEvent(event)

        if hasattr(self, "timeline"):
            QTimer.singleShot(100, self.timeline.fit_view)
        self._position_stop_export_button()

        self.setFocus()

        QTimer.singleShot(150, self.windowResized.emit)

    def closeEvent(self, event):
        self._persist_export_settings()
        if hasattr(self, "presenter"):
            self.presenter.cleanup()
        super().closeEvent(event)

    def keyPressEvent(self, event):

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        focused_widget = self.focusWidget()
        if isinstance(focused_widget, (QLineEdit, CustomLineEdit)):
            focused_widget.clearFocus()
        super().mousePressEvent(event)
