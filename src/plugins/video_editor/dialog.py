import logging

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QResizeEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from plugins.video_editor.dialog_sections import (
    build_settings_panel,
    create_timeline_scroll_area,
    create_toolbar,
)
from plugins.video_editor.dialog_export import VideoEditorDialogExport
from plugins.video_editor.dialog_persistence import VideoEditorDialogPersistence
from plugins.video_editor.dialog_runtime import VideoEditorDialogRuntime
from plugins.video_editor.presenter import VideoEditorPresenter
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
        self.runtime = VideoEditorDialogRuntime(self)
        self.persistence = VideoEditorDialogPersistence(self)
        self.export_ui = VideoEditorDialogExport(self)

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

        self.persistence.load_export_settings()
        self.persistence.connect_export_settings_persistence()

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
        self.runtime.connect_presenter_signals()

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
        self.runtime.update_settings_panel_width()

    def _set_focus_policies(self):
        self.runtime.set_focus_policies()

    def _position_stop_export_button(self):
        self.runtime.position_stop_export_button()

    def _setup_shortcuts(self):
        self.runtime.setup_shortcuts()

    def _load_initial_data(self):

        pass

    def set_preview_image(self, pixmap: QPixmap):
        self.runtime.set_preview_image(pixmap)

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
        from plugins.video_editor.services.export_config import ExportConfigBuilder

        current_codec = self.combo_codec.currentData()
        self.combo_codec.blockSignals(True)
        self.combo_codec.clear()
        for codec in codecs:
            self.combo_codec.addItem(
                self._tr(ExportConfigBuilder.get_codec_display_key(codec)), codec
            )

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
        return self.export_ui.get_export_options()

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
        self.runtime.emit_ready_to_show()

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
        self.export_ui.on_fit_fill_color_clicked()

    def _update_fit_fill_color_button(self):
        self.export_ui.update_fit_fill_color_button()

    def _on_container_changed(self, text: str):
        container = self.combo_container.currentData()
        if container:
            self.containerChanged.emit(container)

    def _on_codec_changed(self, codec_text: str):
        self.export_ui.on_codec_changed(codec_text)

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
        if hasattr(self, "export_log_edit"):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            self.export_log_edit.appendPlainText(f"\n── Export started {ts} ──")

    def set_export_progress(self, value: int):
        self.runtime.set_export_progress(value)

    def on_export_finished(self, success: bool):
        self.runtime.on_export_finished(success)

    def _reset_export_ui_state(self):
        self.runtime.reset_export_ui_state()

    def _on_export_log(self, line: str):
        if hasattr(self, "export_log_edit"):
            self.export_log_edit.appendPlainText(line)

    def _on_error_occurred(self, error_message: str):
        logger.error(f"Video editor error: {error_message}")
        if hasattr(self, "export_log_edit"):
            self.export_log_edit.appendPlainText(error_message)
        if hasattr(self, "tabs") and hasattr(self, "tab_log"):
            self.tabs.setCurrentWidget(self.tab_log)

    def _set_export_progress_state(self, state: str) -> None:
        if not hasattr(self, "export_progress"):
            return
        self.export_progress.setProperty("state", state)
        self.export_progress.style().unpolish(self.export_progress)
        self.export_progress.style().polish(self.export_progress)
        self.export_progress.update()

    def _browse_output_dir(self, checked: bool = False):
        self.persistence.browse_output_dir()

    def _on_set_favorite_clicked(self, checked: bool = False):
        self.persistence.on_set_favorite_clicked()

    def _on_use_favorite_clicked(self, checked: bool = False):
        self.persistence.on_use_favorite_clicked()

    def _tr(self, text):
        return tr(text, self.current_language)

    def _tr_preset(self, preset):
        from plugins.video_editor.services.export_config import ExportConfigBuilder

        key = ExportConfigBuilder.get_preset_translation_key(preset) or f"video.{preset}"
        translated = self._tr(key)
        return preset if translated == key else translated

    def _preset_from_translated(self, translated_text):

        gif_reverse_mapping = {
            self._tr("video.high_quality"): "High Quality",
            self._tr("video.balanced"): "Balanced",
            self._tr("video.compact_dithered"): "Compact (Dithered)",
        }
        if translated_text in gif_reverse_mapping:
            return gif_reverse_mapping[translated_text]

        from plugins.video_editor.services.export_config import CODEC_PROFILES

        all_presets = []
        for profile in CODEC_PROFILES.values():
            all_presets.extend(profile.presets)
        for preset in all_presets:
            if self._tr_preset(preset) == translated_text:
                return preset
        return "medium"

    def _get_settings_refs(self):
        return self.persistence.get_settings_refs()

    def _load_export_settings(self):
        self.persistence.load_export_settings()

    def _connect_export_settings_persistence(self):
        self.persistence.connect_export_settings_persistence()

    def _persist_export_settings(self):
        self.persistence.persist_export_settings()

    def _update_preview_palette(self):
        self.runtime.update_preview_palette()

    def _apply_style(self):
        self.runtime.apply_style()

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
        self.persistence.persist_export_settings()
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
