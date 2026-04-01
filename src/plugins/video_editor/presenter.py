from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

from plugins.video_editor.model import VideoProjectModel
from plugins.video_editor.presenter_parts import (
    ExportCoordinator,
    OutputPathCoordinator,
    PlaybackCoordinator,
    PreviewCoordinator,
    ThumbnailCoordinator,
    initialize_editor_from_snapshots,
    resolve_initial_fps,
)
from plugins.video_editor.services.editor import VideoEditorService
from plugins.video_editor.services.playback import PlaybackEngine
from plugins.video_editor.services.thumbnails import ThumbnailService

class VideoEditorPresenter(QObject):
    previewUpdated = pyqtSignal(QPixmap)
    previewReady = pyqtSignal()
    timelinePositionChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(bool)
    buttonsStateChanged = pyqtSignal(bool, bool)
    thumbnailsUpdated = pyqtSignal(dict)
    thumbnailReady = pyqtSignal(int, QPixmap)
    exportStarted = pyqtSignal()
    exportLog = pyqtSignal(str)
    errorOccurred = pyqtSignal(str)

    def __init__(self, view, snapshots, main_controller):
        super().__init__()
        self.view = view
        self.main_controller = main_controller
        initial_fps = resolve_initial_fps(view, snapshots, main_controller)
        self.model = VideoProjectModel(fps=initial_fps)
        self.editor_service = VideoEditorService(snapshots, fps=initial_fps)
        self.playback_engine = PlaybackEngine()
        self.playback_engine.set_playback_speed(1.0)
        self.thumbnail_service = ThumbnailService()
        if self.main_controller is not None and getattr(
            self.main_controller, "video_export", None
        ):
            self.thumbnail_service.set_image_loader(
                self.main_controller.video_export.get_video_export_image
            )

        self.preview_coordinator = PreviewCoordinator(
            view=view,
            main_controller=main_controller,
            playback_engine=self.playback_engine,
            model=self.model,
            editor_service=self.editor_service,
            timer_parent=self,
            emit_preview_ready=self.previewReady.emit,
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
        )
        self.playback_coordinator = PlaybackCoordinator(
            view=view,
            editor_service=self.editor_service,
            playback_engine=self.playback_engine,
            model=self.model,
            main_controller=main_controller,
            preview_coordinator=self.preview_coordinator,
            thumbnail_coordinator=self.thumbnail_coordinator,
            emit_timeline_position=self.timelinePositionChanged.emit,
            emit_playback_state=self.playbackStateChanged.emit,
            emit_buttons_state=self.buttonsStateChanged.emit,
        )
        self.export_coordinator = ExportCoordinator(
            view=view,
            main_controller=main_controller,
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
        self.preview_coordinator.on_view_destroyed()
        self.output_coordinator.detach_view()
        self.thumbnail_coordinator.detach_view()
        self.playback_coordinator.detach_view()
        self.export_coordinator.detach_view()
        self.view = None

    def _initialize_from_snapshots(self):
        if not initialize_editor_from_snapshots(
            self.view, self.editor_service, self.playback_engine, self.model
        ):
            return
        self.preview_coordinator.reset_render_state()
        self.playback_coordinator.update_buttons_state()
        self.thumbnail_coordinator.generate_thumbnails()
        self.preview_coordinator.schedule_update()

    def _initialize_output_fields(self):
        self.output_coordinator.initialize_output_fields()

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

    def _on_export_progress(self, value):
        if self.view is not None:
            self.view.set_export_progress(value)

    def _on_export_finished(self, success):
        if self.view is not None:
            self.view.on_export_finished(success)
