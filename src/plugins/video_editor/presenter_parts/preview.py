import logging

from PIL import Image
from PyQt6 import sip
from PyQt6.QtCore import QTimer

from plugins.video_editor.preview_gl import apply_preview_to_canvas, build_preview_store
from shared_toolkit.workers.generic_worker import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class PreviewCoordinator:
    def __init__(
        self,
        view,
        main_controller,
        playback_engine,
        model,
        editor_service,
        timer_parent,
        emit_preview_ready,
    ):
        self.view = view
        self.main_controller = main_controller
        self.playback_engine = playback_engine
        self.model = model
        self.editor_service = editor_service
        self.emit_preview_ready = emit_preview_ready

        self._view_destroyed = False
        self._is_rendering_preview = False
        self._render_task_id = 0
        self._preview_ready_emitted = False
        self._last_render_params = (None, None, None)
        self.fit_content_mode = False
        self._cached_global_bounds = None
        self._bounds_calculation_pending = False
        self._stored_crop_resolution = None

        self._preview_updater = QTimer(timer_parent)
        self._preview_updater.setSingleShot(True)
        self._preview_updater.setInterval(1)
        self._preview_updater.timeout.connect(self.do_update_preview_heavy)

    def detach_view(self):
        self.view = None

    def on_view_destroyed(self, *_args):
        self._view_destroyed = True
        self._preview_updater.stop()
        self.view = None

    def has_live_view(self) -> bool:
        return self.view is not None and not sip.isdeleted(self.view)

    def get_preview_size_safe(self) -> tuple[int, int]:
        if not self.has_live_view():
            return (0, 0)
        try:
            return self.view.get_preview_size()
        except RuntimeError:
            return (0, 0)

    def schedule_update(self):
        if self.has_live_view():
            self._preview_updater.start()

    def reset_render_state(self):
        self._last_render_params = (None, None, None)

    def do_update_preview_heavy(self):
        if self._is_rendering_preview or not self.has_live_view():
            return

        available_size = self.get_preview_size_safe()
        if not available_size or available_size[0] < 10 or available_size[1] < 10:
            return

        if self.fit_content_mode and self._cached_global_bounds is None:
            if not self._bounds_calculation_pending:
                self.recalculate_global_bounds()
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
            if self.can_render_preview_on_gpu(snap):
                self.render_preview_gpu(snap)
        except Exception as exc:
            logger.error(f"GPU preview render failed: {exc}", exc_info=True)
        finally:
            self._is_rendering_preview = False

    def can_render_preview_on_gpu(self, snap) -> bool:
        return (
            self.has_live_view()
            and hasattr(self.view, "preview_label")
            and hasattr(self.view.preview_label, "set_pil_layers")
            and snap is not None
            and self.main_controller is not None
            and getattr(self.main_controller, "video_export", None) is not None
        )

    def get_preview_images(self, snap, auto_crop: bool):
        img1 = self.main_controller.video_export.get_video_export_image(
            snap.image1_path, auto_crop
        )
        img2 = self.main_controller.video_export.get_video_export_image(
            snap.image2_path, auto_crop
        )

        if not img1:
            img1 = Image.new(
                "RGBA",
                (max(1, self.model.width), max(1, self.model.height)),
                (50, 50, 50, 255),
            )
        if not img2:
            img2 = Image.new("RGBA", (img1.width, img1.height), (80, 80, 80, 255))

        return img1, img2

    def render_preview_gpu(self, snap) -> bool:
        from .common import VIDEO_EDITOR_AUTO_CROP

        img1, img2 = self.get_preview_images(snap, VIDEO_EDITOR_AUTO_CROP)
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
            global_bounds=self._cached_global_bounds if self.fit_content_mode else None,
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
            self.emit_preview_ready()
        return True

    def on_fit_content_fill_color_changed(self, _color):
        self.reset_render_state()
        self.schedule_update()

    def on_width_changed(self, width: int):
        self.reset_render_state()
        if self.model.aspect_ratio_locked:
            new_height = self.model.adjust_height_to_aspect_ratio(width)
            self.model.set_resolution(width, new_height)
            if self.has_live_view():
                self.view.set_resolution(width, new_height)
        else:
            self.model.width = width
        self.schedule_update()

    def on_height_changed(self, height: int):
        self.reset_render_state()
        if self.model.aspect_ratio_locked:
            new_width = self.model.adjust_width_to_aspect_ratio(height)
            self.model.set_resolution(new_width, height)
            if self.has_live_view():
                self.view.set_resolution(new_width, height)
        else:
            self.model.height = height
        self.schedule_update()

    def on_fit_content_changed(self, enabled: bool):
        self.reset_render_state()
        self.fit_content_mode = enabled

        if enabled:
            self._stored_crop_resolution = (self.model.width, self.model.height)
            self.recalculate_global_bounds()
        else:
            if self._stored_crop_resolution and self.has_live_view():
                width, height = self._stored_crop_resolution
                self.view.blockSignals(True)
                was_locked = self.model.aspect_ratio_locked
                self.model.aspect_ratio_locked = False
                self.model.set_resolution(width, height)
                self.model.aspect_ratio_locked = was_locked
                self.view.set_resolution(width, height)
                self.view.blockSignals(False)

            self._cached_global_bounds = None
            if self.main_controller and getattr(
                self.main_controller, "video_export", None
            ):
                self.main_controller.video_export.invalidate_video_export_bounds_cache()

        self.schedule_update()

    def recalculate_global_bounds(self):
        if self._bounds_calculation_pending:
            return
        if not self.main_controller or not getattr(
            self.main_controller, "video_export", None
        ):
            return

        snapshots = self.editor_service.get_current_snapshots()
        if not snapshots:
            return

        from .common import VIDEO_EDITOR_AUTO_CROP

        self._bounds_calculation_pending = True

        def calculate():
            return self.main_controller.video_export.calculate_video_export_global_bounds(
                snapshots, VIDEO_EDITOR_AUTO_CROP
            )

        worker = GenericWorker(calculate)
        worker.signals.result.connect(self.on_global_bounds_calculated)
        worker.signals.error.connect(self.on_bounds_calculation_error)
        self.main_controller.thread_pool.start(worker)

    def on_global_bounds_calculated(self, bounds):
        self._bounds_calculation_pending = False
        self._cached_global_bounds = bounds

        if bounds and self.fit_content_mode and self.has_live_view():
            g_pad_left, g_pad_right, g_pad_top, g_pad_bottom, g_base_w, g_base_h = bounds
            canvas_w = g_base_w + g_pad_left + g_pad_right
            canvas_h = g_base_h + g_pad_top + g_pad_bottom
            logger.info(f"Global bounds calculated: canvas {canvas_w}x{canvas_h}")

            self.view.blockSignals(True)
            was_locked = self.model.aspect_ratio_locked
            self.model.aspect_ratio_locked = False
            self.model.set_resolution(canvas_w, canvas_h)
            self.model.aspect_ratio_locked = was_locked
            self.view.set_resolution(canvas_w, canvas_h)
            self.view.blockSignals(False)

        self.schedule_update()

    def on_bounds_calculation_error(self, err):
        self._bounds_calculation_pending = False
        logger.error(f"Error calculating global bounds: {err}")

    def on_window_resized(self):
        self.reset_render_state()
        if self.has_live_view() and not self.playback_engine.is_playing():
            self.schedule_update()

    def cleanup(self):
        self._view_destroyed = True
        self._preview_updater.stop()
        if self.has_live_view() and hasattr(self.view, "preview_label"):
            self.view.preview_label._preview_source_key = None
        self.view = None
