import logging
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap

from tabs.image_compare.plugins.video_editor.model import VideoProjectModel
from tabs.image_compare.plugins.video_editor.presenter_parts import (
    ExportCoordinator,
    OutputPathCoordinator,
    PlaybackCoordinator,
    PreviewCoordinator,
    ThumbnailCoordinator,
    initialize_editor_from_snapshots,
    resolve_initial_fps,
)
from tabs.image_compare.plugins.video_editor.services.editor import VideoEditorService
from tabs.image_compare.plugins.video_editor.services.playback import PlaybackEngine
from tabs.image_compare.plugins.video_editor.services.thumbnails import ThumbnailService


logger = logging.getLogger("ImproveImgSLI")

class VideoEditorPresenter(QObject):
    previewUpdated = Signal(QPixmap)
    previewReady = Signal()
    timelinePositionChanged = Signal(int)
    playbackStateChanged = Signal(bool)
    buttonsStateChanged = Signal(bool, bool)
    fitContentAvailableChanged = Signal(bool)
    thumbnailsUpdated = Signal(dict)
    thumbnailReady = Signal(int, QPixmap)
    exportStarted = Signal()
    exportLog = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, view, snapshots, export_controller, main_controller):
        super().__init__()
        self.view = view
        self.export_controller = export_controller
        self.main_controller = main_controller
        initial_fps = resolve_initial_fps(view, snapshots, main_controller)
        self.model = VideoProjectModel(fps=initial_fps)
        self.editor_service = VideoEditorService(snapshots, fps=initial_fps)
        self.playback_engine = PlaybackEngine()
        self.playback_engine.set_playback_speed(1.0)
        self.thumbnail_service = ThumbnailService()
        video_exporter = (
            getattr(self.export_controller, "video_exporter", None)
            if self.export_controller is not None
            else None
        )
        if video_exporter is not None:
            self.thumbnail_service.set_snapshot_renderer(
                video_exporter.render_snapshot_thumbnail_to_pil
            )
            async_renderer = getattr(
                video_exporter, "render_snapshot_thumbnail_to_pil_async", None
            )
            if callable(async_renderer):
                # Preferred path: keeps the thumbnail worker thread from
                # blocking on the GPU round-trip (see ThumbnailService docs).
                self.thumbnail_service.set_async_snapshot_renderer(async_renderer)

        self.preview_coordinator = PreviewCoordinator(
            view=view,
            export_controller=export_controller,
            playback_engine=self.playback_engine,
            model=self.model,
            editor_service=self.editor_service,
            timer_parent=self,
            emit_preview_ready=self.previewReady.emit,
            emit_fit_content_available=self.fitContentAvailableChanged.emit,
        )
        self.output_coordinator = OutputPathCoordinator(
            view=view,
            main_controller=main_controller,
            editor_service=self.editor_service,
            model=self.model,
        )
        self.thumbnail_coordinator = ThumbnailCoordinator(
            view=view,
            editor_service=self.editor_service,
            playback_engine=self.playback_engine,
            thumbnail_service=self.thumbnail_service,
            emit_thumbnails_updated=self.thumbnailsUpdated.emit,
            timer_parent=self,
        )
        self.playback_coordinator = PlaybackCoordinator(
            view=view,
            editor_service=self.editor_service,
            playback_engine=self.playback_engine,
            model=self.model,
            export_controller=export_controller,
            preview_coordinator=self.preview_coordinator,
            thumbnail_coordinator=self.thumbnail_coordinator,
            emit_timeline_position=self.timelinePositionChanged.emit,
            emit_playback_state=self.playbackStateChanged.emit,
            emit_buttons_state=self.buttonsStateChanged.emit,
        )
        self.export_coordinator = ExportCoordinator(
            view=view,
            export_controller=export_controller,
            model=self.model,
            editor_service=self.editor_service,
            preview_coordinator=self.preview_coordinator,
        )

        self._connect_service_signals()
        self._connect_view_signals()
        QTimer.singleShot(0, self._initialize_from_snapshots)

    def _connect_service_signals(self):
        self.playback_engine.frameChanged.connect(self.playback_coordinator.on_frame_changed)
        self.playback_engine.playbackStateChanged.connect(
            self.playback_coordinator.on_playback_state_changed
        )
        self.thumbnail_service.thumbnailReady.connect(
            self.thumbnail_coordinator.on_single_thumbnail_ready
        )
        self.thumbnail_service.thumbnailsGenerated.connect(
            self.thumbnail_coordinator.on_thumbnails_generated
        )
        self.thumbnail_service.generationFinished.connect(
            self.thumbnail_coordinator.on_thumbnails_generation_finished
        )
        if self.main_controller and hasattr(self.main_controller, "video_export_progress"):
            self.main_controller.video_export_progress.connect(self._on_export_progress)
            self.main_controller.video_export_finished.connect(self._on_export_finished)
        if self.main_controller and hasattr(self.main_controller, "error_occurred"):
            self.main_controller.error_occurred.connect(self.errorOccurred)
        if self.main_controller and hasattr(self.main_controller, "video_export_log"):
            self.main_controller.video_export_log.connect(self.exportLog)

    def _disconnect_service_signals(self):
        def _safe_disconnect(signal, slot):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        try:
            _safe_disconnect(self.playback_engine.frameChanged, self.playback_coordinator.on_frame_changed)
            _safe_disconnect(self.playback_engine.playbackStateChanged, self.playback_coordinator.on_playback_state_changed)
            _safe_disconnect(self.thumbnail_service.thumbnailReady, self.thumbnail_coordinator.on_single_thumbnail_ready)
            _safe_disconnect(self.thumbnail_service.thumbnailsGenerated, self.thumbnail_coordinator.on_thumbnails_generated)
            _safe_disconnect(self.thumbnail_service.generationFinished, self.thumbnail_coordinator.on_thumbnails_generation_finished)
        except Exception:
            pass
        if self.main_controller:
            try:
                if hasattr(self.main_controller, "video_export_progress"):
                    _safe_disconnect(self.main_controller.video_export_progress, self._on_export_progress)
                    _safe_disconnect(self.main_controller.video_export_finished, self._on_export_finished)
                if hasattr(self.main_controller, "error_occurred"):
                    _safe_disconnect(self.main_controller.error_occurred, self.errorOccurred)
                if hasattr(self.main_controller, "video_export_log"):
                    _safe_disconnect(self.main_controller.video_export_log, self.exportLog)
            except Exception:
                pass

    def _connect_view_signals(self):
        self.view.destroyed.connect(self._on_view_destroyed)
        self.view.playClicked.connect(self.playback_coordinator.toggle_playback)
        self.view.timelineScrubbed.connect(self.playback_coordinator.seek_to_frame)
        self.view.undoClicked.connect(self.playback_coordinator.undo)
        self.view.redoClicked.connect(self.playback_coordinator.redo)
        self.view.trimClicked.connect(self.playback_coordinator.trim_selection)
        self.view.exportClicked.connect(self.export_video)
        self.view.stopExportClicked.connect(self.export_coordinator.stop_export)
        self.view.widthChanged.connect(self.preview_coordinator.on_width_changed)
        self.view.heightChanged.connect(self.preview_coordinator.on_height_changed)
        self.view.fpsChanged.connect(self.playback_coordinator.on_fps_changed)
        self.view.previewScaleChanged.connect(
            self.preview_coordinator.on_preview_scale_changed
        )
        self.view.aspectRatioLockChanged.connect(
            self.playback_coordinator.on_aspect_ratio_lock_changed
        )
        self.view.fitContentChanged.connect(self.preview_coordinator.on_fit_content_changed)
        self.view.fitContentFillColorChanged.connect(
            self.preview_coordinator.on_fit_content_fill_color_changed
        )
        self.view.containerChanged.connect(self.output_coordinator.on_container_changed)
        if hasattr(self.view, "edit_output_dir"):
            self.view.edit_output_dir.textChanged.connect(
                lambda *_: self.output_coordinator.refresh_unique_output_filename()
            )
        if hasattr(self.view, "edit_filename"):
            self.view.edit_filename.editingFinished.connect(
                self.output_coordinator.refresh_unique_output_filename
            )
        if hasattr(self.view, "timeline"):
            self.view.timeline.viewportChanged.connect(
                self.thumbnail_coordinator.on_timeline_viewport_changed
            )
            self.view.timeline.resized.connect(self.thumbnail_coordinator.on_timeline_resized)
        self.view.windowResized.connect(self.preview_coordinator.on_window_resized)

    def _on_view_destroyed(self, *_args):
        self._disconnect_service_signals()
        self.preview_coordinator.on_view_destroyed()
        self.output_coordinator.detach_view()
        self.thumbnail_coordinator.detach_view()
        self.playback_coordinator.detach_view()
        self.export_coordinator.detach_view()
        self.view = None
        if self.parent() is None:
            try:
                self.deleteLater()
            except Exception:
                pass

    def _initialize_from_snapshots(self):
        _dbg_t0 = time.perf_counter()
        if not initialize_editor_from_snapshots(
            self.view, self.editor_service, self.playback_engine, self.model
        ):
            return
        _dbg_t1 = time.perf_counter()
        self.preview_coordinator.reset_render_state()
        self.playback_coordinator.update_buttons_state()
        self.thumbnail_coordinator.generate_thumbnails()
        self.preview_coordinator.schedule_update()
<<<<<<< Updated upstream:src/tabs/image_compare/plugins/video_editor/presenter.py
        # Eager, independent of fit_content_mode: lets the UI disable the
        # fit-content toggle up front when the canvas never leaves 0..1.
        self.preview_coordinator.recalculate_global_bounds()
=======
        logger.warning(
            "DBG-BUG4 _initialize_from_snapshots: bootstrap=%.1fms rest=%.1fms total=%.1fms",
            (_dbg_t1 - _dbg_t0) * 1000,
            (time.perf_counter() - _dbg_t1) * 1000,
            (time.perf_counter() - _dbg_t0) * 1000,
        )
>>>>>>> Stashed changes:src/plugins/video_editor/presenter.py

    def _initialize_output_fields(self):
        _dbg_t0 = time.perf_counter()
        self.output_coordinator.initialize_output_fields()
        logger.warning(
            "DBG-BUG4 _initialize_output_fields took %.1fms",
            (time.perf_counter() - _dbg_t0) * 1000,
        )

    def set_favorite_path(self, path):
        self.output_coordinator.set_favorite_path(path)

    def get_favorite_path(self):
        return self.output_coordinator.get_favorite_path()

    def toggle_playback(self):
        self.playback_coordinator.toggle_playback()

    def start_playback(self):
        self.playback_coordinator.start_playback()

    def pause_playback(self):
        self.playback_coordinator.pause_playback()

    def seek_to_frame(self, frame_index: int):
        self.playback_coordinator.seek_to_frame(frame_index)

    def undo(self):
        self.playback_coordinator.undo()

    def redo(self):
        self.playback_coordinator.redo()

    def trim_selection(self):
        self.playback_coordinator.trim_selection()

    def export_video(self):
        self.export_coordinator.export_video(self.exportStarted.emit)

    def stop_export(self):
        self.export_coordinator.stop_export()

    def cleanup(self):
        self._disconnect_service_signals()
        self.playback_engine.stop()
        self.thumbnail_coordinator.cleanup()
        if self.view is not None and hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "_lerp_timer"
        ):
            self.view.timeline._lerp_timer.stop()
        self.preview_coordinator.cleanup()
        self.output_coordinator.detach_view()
        self.thumbnail_coordinator.detach_view()
        self.playback_coordinator.detach_view()
        self.export_coordinator.detach_view()
        self.view = None
        if self.parent() is None:
            try:
                self.deleteLater()
            except Exception:
                pass

    def _on_export_progress(self, value):
        if self.view is not None:
            self.view.set_export_progress(value)

    def _on_export_finished(self, success):
        if self.view is not None:
            self.view.on_export_finished(success)
