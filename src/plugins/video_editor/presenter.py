import logging
import os
from typing import Dict, List

from PIL import Image
from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap

from plugins.video_editor.model import VideoProjectModel
from plugins.video_editor.preview_gl import apply_preview_to_canvas, build_preview_store
from plugins.video_editor.services.editor import VideoEditorService
from plugins.video_editor.services.export_config import ExportConfigBuilder
from plugins.video_editor.services.playback import PlaybackEngine
from plugins.video_editor.services.thumbnails import ThumbnailService
from shared.image_processing.progressive_loader import load_full_image
from shared_toolkit.workers.generic_worker import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

VIDEO_EDITOR_AUTO_CROP = False

class VideoEditorPresenter(QObject):

    previewUpdated = pyqtSignal(QPixmap)
    previewReady = pyqtSignal()
    timelinePositionChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(bool)
    buttonsStateChanged = pyqtSignal(bool, bool)
    thumbnailsUpdated = pyqtSignal(dict)
    thumbnailReady = pyqtSignal(int, QPixmap)
    exportStarted = pyqtSignal()
    errorOccurred = pyqtSignal(str)

    def __init__(self, view, snapshots, main_controller):
        super().__init__()
        self.view = view
        self.main_controller = main_controller

        initial_fps = 60

        first_snapshot = self._first_snapshot_from_source(snapshots)
        if first_snapshot and hasattr(first_snapshot, "settings_state"):
            snapshot_fps = getattr(
                first_snapshot.settings_state, "video_recording_fps", None
            )
            if snapshot_fps:
                initial_fps = snapshot_fps

        elif (
            main_controller
            and hasattr(main_controller, "store")
            and main_controller.store
        ):
            initial_fps = getattr(
                main_controller.store.settings, "video_recording_fps", 60
            )

        elif hasattr(view, "export_controller") and view.export_controller:
            if (
                hasattr(view.export_controller, "store")
                and view.export_controller.store
            ):
                initial_fps = getattr(
                    view.export_controller.store.settings, "video_recording_fps", 60
                )

        self.model = VideoProjectModel(fps=initial_fps)

        self.editor_service = VideoEditorService(snapshots, fps=initial_fps)
        self.playback_engine = PlaybackEngine()
        self.playback_engine.set_playback_speed(1.0)
        self.thumbnail_service = ThumbnailService()
        if (
            self.main_controller is not None
            and hasattr(self.main_controller, "get_video_export_image")
        ):
            self.thumbnail_service.set_image_loader(
                self.main_controller.get_video_export_image
            )

        self._last_render_params = (None, None, None)
        self._view_destroyed = False

        self._is_rendering_preview = False
        self._render_task_id = 0
        self._preview_ready_emitted = False
        self._preview_updater = QTimer(self)
        self._preview_updater.setSingleShot(True)
        self._preview_updater.setInterval(1)
        self._preview_updater.timeout.connect(self._do_update_preview_heavy)

        self.fit_content_mode = False
        self._cached_global_bounds = None
        self._bounds_calculation_pending = False

        self._stored_crop_resolution = None

        self._connect_service_signals()

        self._connect_view_signals()

        QTimer.singleShot(0, self._initialize_from_snapshots)

    def _first_snapshot_from_source(self, source):
        if source is None:
            return None
        if isinstance(source, (list, tuple)):
            return source[0] if source else None
        if hasattr(source, "evaluate_at"):
            try:
                return source.evaluate_at(0.0)
            except Exception:
                return None
        return None

    def _connect_service_signals(self):
        self.playback_engine.frameChanged.connect(self._on_frame_changed)
        self.playback_engine.playbackStateChanged.connect(
            self._on_playback_state_changed
        )

        self.thumbnail_service.thumbnailReady.connect(self._on_single_thumbnail_ready)
        self.thumbnail_service.thumbnailsGenerated.connect(
            self._on_thumbnails_generated
        )
        self.thumbnail_service.generationFinished.connect(
            self._on_thumbnails_generation_finished
        )

        if self.main_controller and hasattr(
            self.main_controller, "video_export_progress"
        ):
            self.main_controller.video_export_progress.connect(self._on_export_progress)
            self.main_controller.video_export_finished.connect(self._on_export_finished)

    def _connect_view_signals(self):
        self.view.destroyed.connect(self._on_view_destroyed)
        self.view.playClicked.connect(self.toggle_playback)
        self.view.timelineScrubbed.connect(self.seek_to_frame)

        self.view.undoClicked.connect(self.undo)
        self.view.redoClicked.connect(self.redo)
        self.view.trimClicked.connect(self.trim_selection)

        self.view.exportClicked.connect(self.export_video)
        self.view.stopExportClicked.connect(self.stop_export)

        self.view.widthChanged.connect(self._on_width_changed)
        self.view.heightChanged.connect(self._on_height_changed)

        self.view.fpsChanged.connect(self._on_fps_changed)
        self.view.aspectRatioLockChanged.connect(self._on_aspect_ratio_lock_changed)
        self.view.fitContentChanged.connect(self._on_fit_content_changed)
        self.view.fitContentFillColorChanged.connect(
            self._on_fit_content_fill_color_changed
        )
        self.view.containerChanged.connect(self._on_container_changed)
        if hasattr(self.view, "edit_output_dir"):
            self.view.edit_output_dir.textChanged.connect(
                lambda *_: self._refresh_unique_output_filename()
            )
        if hasattr(self.view, "edit_filename"):
            self.view.edit_filename.editingFinished.connect(
                self._refresh_unique_output_filename
            )
        if hasattr(self.view, "timeline"):
            self.view.timeline.viewportChanged.connect(
                self._on_timeline_viewport_changed
            )
            self.view.timeline.resized.connect(self._on_timeline_resized)

        self.view.windowResized.connect(self._on_window_resized)

    def _on_view_destroyed(self, *_args):
        self._view_destroyed = True
        self._preview_updater.stop()
        self.view = None

    def _has_live_view(self) -> bool:
        return self.view is not None and not sip.isdeleted(self.view)

    def _get_preview_size_safe(self) -> tuple[int, int]:
        if not self._has_live_view():
            return (0, 0)
        try:
            return self.view.get_preview_size()
        except RuntimeError:
            return (0, 0)

    def _initialize_from_snapshots(self):
        recording = self.editor_service.get_current_recording()
        if not recording:
            return

        self.view.set_snapshots(
            [],
            fps=self.editor_service.get_fps(),
            timeline_model=recording.timeline,
            duration=self.editor_service.get_duration(),
        )

        total_frames = self.editor_service.get_frame_count()
        self.playback_engine.set_total_frames(total_frames)
        self.playback_engine.set_range(0, total_frames - 1)

        try:
            first_snap = self.editor_service.get_snapshot_at_time(0.0)
            if first_snap is None:
                raise RuntimeError("Missing initial snapshot")
            should_crop = VIDEO_EDITOR_AUTO_CROP
            img1 = load_full_image(first_snap.image1_path, auto_crop=should_crop)
            img2 = load_full_image(first_snap.image2_path, auto_crop=should_crop)
            w1, h1 = img1.size if img1 else (0, 0)
            w2, h2 = img2.size if img2 else (0, 0)
            max_w = max(w1, w2)
            max_h = max(h1, h2)

            if max_w > 0 and max_h > 0:
                self.model.set_resolution(max_w, max_h)
                self.view.set_resolution(max_w, max_h)

        except Exception as e:
            logger.error(f"Error calculating initial resolution: {e}")

        self._last_render_params = (None, None, None)

        self._update_buttons_state()
        self._generate_thumbnails()
        self._preview_updater.start()

    def _initialize_output_fields(self):
        if not hasattr(self.view, "edit_output_dir") or not hasattr(
            self.view, "edit_filename"
        ):
            return

        output_dir = ""
        if (
            self.main_controller
            and hasattr(self.main_controller, "store")
            and self.main_controller.store
        ):
            favorite_dir = getattr(
                self.main_controller.store.settings, "export_video_favorite_dir", None
            )
            if favorite_dir and os.path.isdir(favorite_dir):
                output_dir = favorite_dir

        if not output_dir:
            if (
                self.main_controller
                and hasattr(self.main_controller, "store")
                and self.main_controller.store
            ):
                output_dir = (
                    self.main_controller.store.settings.export_default_dir or ""
                )

        if not output_dir:
            from pathlib import Path

            output_dir = str(Path.home() / "Downloads")

        self.view.edit_output_dir.setText(output_dir)
        self.view.edit_output_dir.setCursorPosition(0)

        suggested_name = self._generate_suggested_name()
        self.view.edit_filename.setText(suggested_name)
        self.view.edit_filename.setCursorPosition(0)
        self._refresh_unique_output_filename()

    def _current_output_extension(self) -> str:
        if not self._has_live_view():
            return "mp4"
        container = ""
        if hasattr(self.view, "combo_container") and self.view.combo_container is not None:
            container = self.view.combo_container.currentData() or ""
        container = str(container or "mp4").strip().lower()
        return container or "mp4"

    def _unique_output_filepath(
        self, directory: str, base_name: str, extension: str
    ) -> str:
        full_path = os.path.join(directory, f"{base_name}.{extension}")
        if not os.path.exists(full_path):
            return full_path

        counter = 1
        while True:
            candidate_name = f"{base_name} ({counter})"
            candidate_path = os.path.join(directory, f"{candidate_name}.{extension}")
            if not os.path.exists(candidate_path):
                return candidate_path
            counter += 1

    def _refresh_unique_output_filename(self) -> None:
        if not self._has_live_view():
            return
        if not hasattr(self.view, "edit_output_dir") or not hasattr(
            self.view, "edit_filename"
        ):
            return

        output_dir = self.view.edit_output_dir.text().strip()
        raw_name = self.view.edit_filename.text().strip() or self._generate_suggested_name()
        extension = self._current_output_extension()

        suffix = f".{extension}"
        if raw_name.lower().endswith(suffix):
            raw_name = raw_name[: -len(suffix)].rstrip()
        if not raw_name:
            raw_name = self._generate_suggested_name()

        unique_path = self._unique_output_filepath(output_dir or "", raw_name, extension)
        unique_name = os.path.splitext(os.path.basename(unique_path))[0]
        if unique_name == self.view.edit_filename.text().strip():
            return

        cursor_pos = self.view.edit_filename.cursorPosition()
        self.view.edit_filename.blockSignals(True)
        self.view.edit_filename.setText(unique_name)
        self.view.edit_filename.setCursorPosition(min(cursor_pos, len(unique_name)))
        self.view.edit_filename.blockSignals(False)

    def _generate_suggested_name(self) -> str:
        snaps = self.editor_service.get_current_snapshots()
        if not snaps:
            return "video_export"

        s = snaps[0]

        n1 = s.name1 if s.name1 else "img1"
        n2 = s.name2 if s.name2 else "img2"

        import re

        def sanitize(text):
            return re.sub(r'[\\/*?:"<>|]', "_", str(text))[:40].strip()

        return f"{sanitize(n1)}_{sanitize(n2)}"

    def set_favorite_path(self, path):
        if (
            self.main_controller
            and hasattr(self.main_controller, "store")
            and self.main_controller.store
        ):
            self.main_controller.store.settings.export_video_favorite_dir = path

            if hasattr(self.main_controller, "settings_manager"):
                self.main_controller.settings_manager._save_setting(
                    "export_video_favorite_dir", path
                )

    def get_favorite_path(self):
        if (
            self.main_controller
            and hasattr(self.main_controller, "store")
            and self.main_controller.store
        ):
            return getattr(
                self.main_controller.store.settings, "export_video_favorite_dir", None
            )
        return None

    def toggle_playback(self):
        if self.playback_engine.is_playing():
            self.pause_playback()
        else:
            self.start_playback()

    def start_playback(self):
        start_frame, end_frame = self.view.get_selection_range()

        self.playback_engine.set_range(start_frame, end_frame)

        current_frame = self.playback_engine.get_current_frame()

        if current_frame >= end_frame:
            self.playback_engine.set_current_frame(start_frame)
            self.timelinePositionChanged.emit(start_frame)
        elif current_frame < start_frame:
            self.playback_engine.set_current_frame(start_frame)
            self.timelinePositionChanged.emit(start_frame)

        self.playback_engine.set_fps(self.model.fps)
        self.editor_service.set_fps(self.model.fps)

        self.playback_engine.play()

    def pause_playback(self):
        self.playback_engine.pause()

    def seek_to_frame(self, frame_index: int):
        self.playback_engine.seek(frame_index)

        if not self.playback_engine.is_playing():
            self._preview_updater.start()

    def undo(self):
        if self.editor_service.undo():
            self._on_data_changed()

    def redo(self):
        if self.editor_service.redo():
            self._on_data_changed()

    def trim_selection(self):
        start_frame, end_frame = self.view.get_selection_range()

        if self.editor_service.delete_selection(start_frame, end_frame):
            self._on_data_changed()

    def export_video(self):
        export_options = self.view.get_export_options()

        export_options["fit_content"] = self.fit_content_mode

        config_params = {
            k: v
            for k, v in export_options.items()
            if k
            not in ["output_dir", "file_name", "fit_content", "fit_content_fill_color"]
        }

        config = ExportConfigBuilder.build_export_config(**config_params)
        export_options.update(config)
        recording = self.editor_service.get_current_recording()

        if self.main_controller:
            resolution = self.model.get_resolution()

            self.main_controller.export_video_from_editor(
                recording, self.model.fps, resolution, export_options
            )
            self.exportStarted.emit()

    def stop_export(self):
        if self.main_controller is not None and hasattr(
            self.main_controller, "cancel_video_export"
        ):
            self.main_controller.cancel_video_export()

    def _on_frame_changed(self, frame_index: int):
        self.timelinePositionChanged.emit(frame_index)

        if self.playback_engine.is_playing():
            self._do_update_preview_heavy()
        else:

            self._preview_updater.start()

    def _on_playback_state_changed(self, is_playing: bool):
        self.playbackStateChanged.emit(is_playing)

        if not is_playing:
            start_frame, end_frame = self.view.get_selection_range()
            current_frame = self.playback_engine.get_current_frame()

            if current_frame >= end_frame:
                self.playback_engine.set_current_frame(start_frame)
                self.timelinePositionChanged.emit(start_frame)
                self._preview_updater.start()

    def _on_data_changed(self):
        snapshots = self.editor_service.get_current_snapshots()
        self.view.set_snapshots(
            snapshots,
            fps=self.editor_service.get_fps(),
            timeline_model=self.editor_service.get_timeline_model(),
        )

        total_frames = self.editor_service.get_frame_count()
        self.playback_engine.set_total_frames(total_frames)

        self.playback_engine.set_current_frame(0)
        self.timelinePositionChanged.emit(0)

        self._update_buttons_state()
        self._generate_thumbnails()

        self._cached_global_bounds = None
        if self.main_controller and hasattr(
            self.main_controller, "invalidate_video_export_bounds_cache"
        ):
            self.main_controller.invalidate_video_export_bounds_cache()

        if self.fit_content_mode:
            self._recalculate_global_bounds()

        self._preview_updater.start()

    def _update_buttons_state(self):
        can_undo = self.editor_service.can_undo()
        can_redo = self.editor_service.can_redo()
        self.buttonsStateChanged.emit(can_undo, can_redo)

    def _calculate_optimal_thumbnail_count(self) -> int:
        if not hasattr(self.view, "timeline"):
            return 50

        timeline = self.view.timeline

        content_height = timeline.height() - timeline.RULER_HEIGHT

        if content_height <= 0:
            return 50

        aspect_ratio = 16.0 / 9.0
        tile_width = content_height * aspect_ratio

        if not timeline.has_snapshots():
            return 50

        total_dur = timeline.get_total_duration()
        px_per_sec = timeline.get_pixels_per_second()
        logical_width = total_dur * px_per_sec

        if logical_width <= 0 or tile_width <= 0:
            return 50

        visible_count = int(logical_width / tile_width) + 2

        return max(20, min(visible_count, 200))

    def _generate_thumbnails(self):

        if hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "clear_thumbnails"
        ):
            self.view.timeline.clear_thumbnails()

        recording = self.editor_service.get_current_recording()
        if recording:
            should_crop = VIDEO_EDITOR_AUTO_CROP

            target_count = self._calculate_optimal_thumbnail_count()

            priority_indices = self._get_visible_frame_indices()

            self.thumbnail_service.generate_thumbnails(
                recording,
                target_count=target_count,
                auto_crop=should_crop,
                priority_indices=priority_indices,
                fps=self.editor_service.get_fps(),
            )

    def _on_single_thumbnail_ready(self, index: int, pixmap: QPixmap):
        if hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "add_thumbnail"
        ):
            self.view.timeline.add_thumbnail(index, pixmap)

    def _on_thumbnails_generated(self, thumbnails: Dict[int, QPixmap]):
        self.thumbnailsUpdated.emit(thumbnails)

    def _on_thumbnails_generation_finished(self):
        pass

    def _on_timeline_viewport_changed(self):
        priority_indices = self._get_visible_frame_indices()

        if not priority_indices:
            return

        self.thumbnail_service.request_priority_thumbnails(priority_indices)

    def _on_timeline_resized(self):
        total_frames = self.editor_service.get_frame_count()
        if total_frames <= 0:
            return

        target_count = self._calculate_optimal_thumbnail_count()

        step = max(1, total_frames // target_count)

        indices_to_generate = []
        for i in range(0, total_frames, step):
            indices_to_generate.append(i)

        self.thumbnail_service.generate_additional_thumbnails(
            indices_to_generate, fps=self.editor_service.get_fps()
        )

    def _get_visible_frame_indices(self, margin: int = 5) -> List[int]:
        if not hasattr(self.view, "timeline"):
            return []

        timeline = self.view.timeline
        total_frames = self.editor_service.get_frame_count()

        if total_frames == 0:
            return []

        try:

            current_frame = self.playback_engine.get_current_frame()

            visible_range = 5
            start_idx = max(0, current_frame - visible_range - margin)
            end_idx = min(total_frames, current_frame + visible_range + margin)

            return list(range(start_idx, end_idx))
        except Exception as e:
            logger.debug(f"Error calculating visible frames: {e}")

            return list(range(min(10, total_frames)))

    def _do_update_preview_heavy(self):
        if self._is_rendering_preview:
            return

        if not self._has_live_view():
            return

        available_size = self._get_preview_size_safe()

        if not available_size or available_size[0] < 10 or available_size[1] < 10:
            return

        if self.fit_content_mode and self._cached_global_bounds is None:
            if not self._bounds_calculation_pending:
                self._recalculate_global_bounds()
            return

        current_frame = self.playback_engine.get_current_frame()
        render_w, render_h = available_size

        last_frame, last_w, last_h = self._last_render_params
        if last_frame == current_frame and last_w and last_h:
            if abs(render_w - last_w) < 2 and abs(render_h - last_h) < 2:
                return

        self._is_rendering_preview = True
        self._render_task_id += 1

        self._last_render_params = (current_frame, render_w, render_h)

        snap = self.editor_service.get_snapshot_at(current_frame)
        if not snap:
            self._is_rendering_preview = False
            return

        try:
            if self._can_render_preview_on_gpu(snap):
                self._render_preview_gpu(snap)
        except Exception as e:
            logger.error(f"GPU preview render failed: {e}", exc_info=True)
        finally:
            self._is_rendering_preview = False

    def _can_render_preview_on_gpu(self, snap) -> bool:
        return (
            self._has_live_view()
            and hasattr(self.view, "preview_label")
            and hasattr(self.view.preview_label, "set_pil_layers")
            and snap is not None
            and self.main_controller is not None
            and hasattr(self.main_controller, "get_video_export_image")
        )

    def _get_preview_images(self, snap):
        img1 = self.main_controller.get_video_export_image(
            snap.image1_path, VIDEO_EDITOR_AUTO_CROP
        )
        img2 = self.main_controller.get_video_export_image(
            snap.image2_path, VIDEO_EDITOR_AUTO_CROP
        )

        if not img1:
            img1 = Image.new("RGBA", (max(1, self.model.width), max(1, self.model.height)), (50, 50, 50, 255))
        if not img2:
            img2 = Image.new("RGBA", (img1.width, img1.height), (80, 80, 80, 255))

        return img1, img2

    def _render_preview_gpu(self, snap) -> bool:
        img1, img2 = self._get_preview_images(snap)
        global_bounds = self._cached_global_bounds if self.fit_content_mode else None
        fill_color = getattr(self.view, "fit_content_fill_color", None)
        (
            preview_store,
            display_img1,
            display_img2,
            source_img1,
            source_img2,
            source_key,
        ) = build_preview_store(
            snap,
            img1,
            img2,
            fit_content=self.fit_content_mode,
            global_bounds=global_bounds,
            fill_color=(
                fill_color.red(),
                fill_color.green(),
                fill_color.blue(),
                fill_color.alpha(),
            )
            if fill_color is not None
            else None,
        )
        apply_preview_to_canvas(
            self.view.preview_label,
            preview_store,
            display_img1,
            display_img2,
            fit_content=self.fit_content_mode,
            source_image1=source_img1,
            source_image2=source_img2,
            source_key=source_key,
        )
        if not self._preview_ready_emitted:
            self._preview_ready_emitted = True
            self.previewReady.emit()
        return True

    def _on_fit_content_fill_color_changed(self, _color):
        self._last_render_params = (None, None, None)
        self._preview_updater.start()

    def _on_width_changed(self, width: int):
        self._last_render_params = (None, None, None)
        if self.model.aspect_ratio_locked:
            new_height = self.model.adjust_height_to_aspect_ratio(width)
            self.model.set_resolution(width, new_height)
            self.view.set_resolution(width, new_height)
        else:
            self.model.width = width
        self._preview_updater.start()

    def _on_height_changed(self, height: int):
        self._last_render_params = (None, None, None)
        if self.model.aspect_ratio_locked:
            new_width = self.model.adjust_width_to_aspect_ratio(height)
            self.model.set_resolution(new_width, height)
            self.view.set_resolution(new_width, height)
        else:
            self.model.height = height
        self._preview_updater.start()

    def _on_fps_changed(self, fps: int):
        self.model.fps = max(1, fps)
        self.editor_service.set_fps(self.model.fps)
        self.playback_engine.set_total_frames(self.editor_service.get_frame_count())
        self.playback_engine.set_fps(self.model.fps)
        self._generate_thumbnails()
        self._preview_updater.start()

    def _on_aspect_ratio_lock_changed(self, locked: bool):
        self.model.aspect_ratio_locked = locked
        if locked:
            if self.model.height > 0:
                self.model.original_ratio = self.model.width / self.model.height
        self._update_buttons_state()

    def _on_fit_content_changed(self, enabled: bool):
        self._last_render_params = (None, None, None)
        self.fit_content_mode = enabled

        if enabled:

            self._stored_crop_resolution = (self.model.width, self.model.height)
            self._recalculate_global_bounds()
        else:

            if self._stored_crop_resolution:
                w, h = self._stored_crop_resolution

                self.view.blockSignals(True)

                was_locked = self.model.aspect_ratio_locked
                self.model.aspect_ratio_locked = False

                self.model.set_resolution(w, h)

                self.model.aspect_ratio_locked = was_locked

                self.view.set_resolution(w, h)
                self.view.blockSignals(False)

            self._cached_global_bounds = None
            if self.main_controller and hasattr(
                self.main_controller, "invalidate_video_export_bounds_cache"
            ):
                self.main_controller.invalidate_video_export_bounds_cache()

        self._preview_updater.start()

    def _recalculate_global_bounds(self):
        if self._bounds_calculation_pending:
            return

        if not self.main_controller or not hasattr(
            self.main_controller, "calculate_video_export_global_bounds"
        ):
            return

        snapshots = self.editor_service.get_current_snapshots()
        if not snapshots:
            return

        should_crop = VIDEO_EDITOR_AUTO_CROP

        self._bounds_calculation_pending = True

        def calculate():
            return self.main_controller.calculate_video_export_global_bounds(
                snapshots, should_crop
            )

        worker = GenericWorker(calculate)
        worker.signals.result.connect(self._on_global_bounds_calculated)
        worker.signals.error.connect(self._on_bounds_calculation_error)
        self.main_controller.thread_pool.start(worker)

    def _on_global_bounds_calculated(self, bounds):
        self._bounds_calculation_pending = False
        self._cached_global_bounds = bounds

        if bounds:
            g_pad_left, g_pad_right, g_pad_top, g_pad_bottom, g_base_w, g_base_h = (
                bounds
            )

            canvas_w = g_base_w + g_pad_left + g_pad_right
            canvas_h = g_base_h + g_pad_top + g_pad_bottom

            logger.info(f"Global bounds calculated: canvas {canvas_w}x{canvas_h}")

            if self.fit_content_mode:
                self.view.blockSignals(True)

                was_locked = self.model.aspect_ratio_locked

                self.model.aspect_ratio_locked = False
                self.model.set_resolution(canvas_w, canvas_h)

                self.model.aspect_ratio_locked = was_locked

                self.view.set_resolution(canvas_w, canvas_h)
                self.view.blockSignals(False)

        self._preview_updater.start()

    def _on_bounds_calculation_error(self, err):
        self._bounds_calculation_pending = False
        logger.error(f"Error calculating global bounds: {err}")

    def _on_container_changed(self, container: str):
        self.model.container = container
        codecs = ExportConfigBuilder.get_codecs_for_container(container)
        default_codec = ExportConfigBuilder.get_default_codec_for_container(container)
        self.view.update_available_codecs(codecs, default_codec)
        self._refresh_unique_output_filename()

    def _on_window_resized(self):
        self._last_render_params = (None, None, None)
        if not self._has_live_view():
            return
        if not self.playback_engine.is_playing():
            self._preview_updater.start()

    def _on_timeline_viewport_changed(self):
        visible_indices = self._get_visible_frame_indices()
        if visible_indices:
            self.thumbnail_service.generate_additional_thumbnails(visible_indices)

    def cleanup(self):
        self._view_destroyed = True
        self._preview_updater.stop()
        self.playback_engine.stop()
        self.thumbnail_service.cancel()
        if self._has_live_view() and hasattr(self.view, "timeline") and hasattr(self.view.timeline, "_lerp_timer"):
            self.view.timeline._lerp_timer.stop()
        if self._has_live_view() and hasattr(self.view, "preview_label"):
            self.view.preview_label._preview_source_key = None
        self.view = None

    def _on_export_progress(self, value):
        self.view.set_export_progress(value)

    def _on_export_finished(self, success):
        self.view.on_export_finished(success)
