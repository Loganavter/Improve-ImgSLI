import logging
import time

from core.tracing import Tracer
from PIL import Image
import shiboken6 as sip
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QPixmap
from tabs.image_compare.video_editor.services.keyframing.engine.values import (
    frozen_value,
    viewport_fingerprint,
)
from sli_ui_toolkit.workers import GenericWorker
from ui.canvas_presentation import apply_canvas_render_plan

logger = logging.getLogger("ImproveImgSLI")
_vplog = logging.getLogger("ImproveImgSLI.video_preview")

class PreviewCoordinator:
    def __init__(
        self,
        view,
        export_controller,
        playback_engine,
        model,
        editor_service,
        timer_parent,
        emit_preview_ready,
    ):
        self.view = view
        self.export_controller = export_controller
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
        self.preview_render_scale = 1.0
        self._cached_global_bounds = None
        self._bounds_calculation_pending = False
        self._stored_crop_resolution = None

        self._preview_frame_cache = None

        self._preview_updater = QTimer(timer_parent)
        self._preview_updater.setSingleShot(True)
        # Debounce heavy GPU preview renders: resizeEvent fires on every pixel
        # of a window drag, and each render is a synchronous ~1s main-thread
        # call. Without a real debounce here, resizing floods the main thread
        # with back-to-back renders, which also starves the thumbnail
        # QThreadPool workers of the main-thread time they need to deliver
        # their queued GPU render requests.
        self._preview_updater.setInterval(120)
        self._preview_updater.timeout.connect(self.do_update_preview_heavy)

    def detach_view(self):
        self.view = None

    def on_view_destroyed(self, *_args):
        self._view_destroyed = True
        self._preview_updater.stop()
        self.view = None

    def has_live_view(self) -> bool:
        return self.view is not None and sip.isValid(self.view)

    def get_preview_size_safe(self) -> tuple[int, int]:
        if not self.has_live_view():
            return (0, 0)
        try:
            return self.view.get_preview_size()
        except RuntimeError:
            return (0, 0)

    def schedule_update(self):
        if self.has_live_view():
            _vplog.debug(
                "schedule_update called active=%s interval=%s",
                self._preview_updater.isActive(),
                self._preview_updater.interval(),
            )
            self._preview_updater.start()

    def reset_render_state(self):
        self._last_render_params = (None, None, None)
        self._preview_frame_cache = None

    def do_update_preview_heavy(self):
        if self._is_rendering_preview or not self.has_live_view():
            _vplog.debug(
                "preview_skip busy=%s live=%s",
                self._is_rendering_preview,
                self.has_live_view(),
            )
            return

        available_size = self.get_preview_size_safe()
        if not available_size or available_size[0] < 10 or available_size[1] < 10:
            _vplog.debug("preview_skip size=%s", available_size)
            return

        if self.fit_content_mode and self._cached_global_bounds is None:
            if not self._bounds_calculation_pending:
                self.recalculate_global_bounds()
            _vplog.debug(
                "preview_wait_global_bounds pending=%s",
                self._bounds_calculation_pending,
            )
            return

        current_frame = self.playback_engine.get_current_frame()
        render_w, render_h = available_size
        last_frame, last_w, last_h = self._last_render_params
        if last_frame == current_frame and last_w and last_h:
            if abs(render_w - last_w) < 2 and abs(render_h - last_h) < 2:
                _vplog.debug(
                    "preview_skip_unchanged frame=%s size=%sx%s",
                    current_frame,
                    render_w,
                    render_h,
                )
                return

        self._is_rendering_preview = True
        self._render_task_id += 1
        self._last_render_params = (current_frame, render_w, render_h)
        _vplog.debug(
            "preview_begin task=%s frame=%s preview=%sx%s fit_content=%s",
            self._render_task_id,
            current_frame,
            render_w,
            render_h,
            self.fit_content_mode,
        )

        snap = self.editor_service.get_snapshot_at(current_frame)
        if not snap:
            self._is_rendering_preview = False
            return

        render_started = time.perf_counter()
        try:
            if self.can_render_preview_on_gpu(snap):
                self.render_preview_gpu(snap)
        except Exception as exc:
            logger.error(f"GPU preview render failed: {exc}", exc_info=True)
        finally:
            _vplog.debug(
                "preview_end task=%s elapsed_ms=%.1f",
                self._render_task_id,
                (time.perf_counter() - render_started) * 1000.0,
            )
            self._is_rendering_preview = False

    def can_render_preview_on_gpu(self, snap) -> bool:
        exporter = getattr(self.export_controller, "video_exporter", None)
        return (
            self.has_live_view()
            and snap is not None
            and exporter is not None
        )

    def _resolve_fill_color_tuple(self):
        fill_color = getattr(self.view, "fit_content_fill_color", None)
        if fill_color is None:
            return None
        return (fill_color.red(), fill_color.green(), fill_color.blue(), fill_color.alpha())

    @staticmethod
    def _trace(kind: str, summary: str, payload: dict) -> None:
        if Tracer.enabled():
            Tracer.instance().record(kind, summary, payload)

    def _resolve_preview_render_size(self, preview_w: int, preview_h: int) -> tuple[int, int]:
        target_w = max(1, int(self.model.width or preview_w or 1))
        target_h = max(1, int(self.model.height or preview_h or 1))
        canvas = getattr(self.view, "preview_label", None)
        dpr = 1.0
        if canvas is not None and hasattr(canvas, "devicePixelRatioF"):
            try:
                dpr = max(1.0, float(canvas.devicePixelRatioF()))
            except Exception:
                dpr = 1.0
        preview_phys_w = max(1, int(round(float(preview_w or 1) * dpr)))
        preview_phys_h = max(1, int(round(float(preview_h or 1) * dpr)))
        scale_factor = max(0.25, min(float(self.preview_render_scale or 1.0), 1.0))

        if self.fit_content_mode:
            base_cap_w = max(1, int(preview_phys_w or target_w))
            base_cap_h = max(1, int(preview_phys_h or target_h))
        else:
            base_cap_w = max(1, max(int(preview_phys_w), min(int(preview_phys_w * 2), 1920)))
            base_cap_h = max(1, max(int(preview_phys_h), min(int(preview_phys_h * 2), 1080)))
        cap_w = max(1, int(round(base_cap_w * scale_factor)))
        cap_h = max(1, int(round(base_cap_h * scale_factor)))
        scale = min(
            1.0,
            float(cap_w) / float(max(1, target_w)),
            float(cap_h) / float(max(1, target_h)),
        )
        if scale >= 0.999:
            return target_w, target_h
        return (
            max(1, int(round(target_w * scale))),
            max(1, int(round(target_h * scale))),
        )

    def _apply_preview_frame(self, frame_pil: Image.Image, request_key) -> None:
        canvas = getattr(self.view, "preview_label", None)
        if canvas is None:
            return

        if hasattr(canvas, "set_pil_layers"):
            from shared.rendering.tab_canvas_services import (
                reset_canvas_overlays,
            )
            canvas._preview_source_key = request_key
            reset_canvas_overlays(canvas)
            state = getattr(canvas, "runtime_state", None)
            if state is not None:
                state._store = None
            canvas.set_pil_layers(
                pil_image1=frame_pil,
                pil_image2=frame_pil,
                source_image1=frame_pil,
                source_image2=frame_pil,
                source_key=(request_key, "preview_source"),
                display_cache_key=(request_key, "preview_display"),
                shader_letterbox=False,
            )
            return

        rgba = frame_pil.convert("RGBA")
        qimage = QImage(
            rgba.tobytes("raw", "RGBA"),
            rgba.width,
            rgba.height,
            QImage.Format.Format_RGBA8888,
        ).copy()
        pixmap = QPixmap.fromImage(qimage)
        if hasattr(canvas, "set_pixmap"):
            canvas._preview_source_key = request_key
            canvas.set_pixmap(pixmap)

    def _apply_preview_scene(
        self,
        snap,
        request_key,
        global_bounds,
        fill_color_tuple,
        render_w: int,
        render_h: int,
    ) -> bool:
        exporter = getattr(self.export_controller, "video_exporter", None)
        canvas = getattr(self.view, "preview_label", None)
        if exporter is None or canvas is None:
            return False
        if hasattr(canvas, "set_read_only"):
            canvas.set_read_only(True)

        prepared = exporter.prepare_snapshot_canvas_frame(
            snap,
            render_w,
            render_h,
            auto_crop=False,
            fit_content=self.fit_content_mode,
            global_bounds=global_bounds,
            fill_color=fill_color_tuple or (0, 0, 0, 0),
            thumbnail=False,
        )

        apply_canvas_render_plan(
            canvas,
            prepared.plan,
            store=prepared.store,
            clip_overlays_to_image_bounds=True,
        )
        self._trace(
            "video.preview.apply_scene",
            f"apply preview scene render={render_w}x{render_h}",
            {
                "render_size": (int(render_w), int(render_h)),
                "plan_canvas": (
                    int(getattr(prepared.plan, "canvas_w", 0) or 0),
                    int(getattr(prepared.plan, "canvas_h", 0) or 0),
                ),
                "plan_image1_size": getattr(
                    getattr(prepared.plan, "image1", None),
                    "size",
                    None,
                ),
                "output_size": (
                    int(getattr(prepared, "output_width", 0) or 0),
                    int(getattr(prepared, "output_height", 0) or 0),
                ),
                "image_dest": (
                    int(getattr(prepared, "image_dest_x", 0) or 0),
                    int(getattr(prepared, "image_dest_y", 0) or 0),
                ),
                "debug": dict(getattr(prepared, "debug", {}) or {}),
            },
        )

        canvas._preview_source_key = request_key
        return True

    def render_preview_gpu(self, snap) -> bool:
        exporter = getattr(self.export_controller, "video_exporter", None)
        if exporter is None:
            return False
        preview_w, preview_h = self.get_preview_size_safe()
        render_w, render_h = self._resolve_preview_render_size(preview_w, preview_h)
        fill_color_tuple = self._resolve_fill_color_tuple()
        global_bounds = self._cached_global_bounds if self.fit_content_mode else None
        self._trace(
            "video.preview.request",
            f"preview request render={render_w}x{render_h} display={preview_w}x{preview_h}",
            {
                "preview_size": (int(preview_w), int(preview_h)),
                "render_size": (int(render_w), int(render_h)),
                "model_size": (
                    int(getattr(self.model, "width", 0) or 0),
                    int(getattr(self.model, "height", 0) or 0),
                ),
                "fit_content": bool(self.fit_content_mode),
                "preview_render_scale": float(self.preview_render_scale or 1.0),
                "global_bounds": repr(global_bounds),
                "fill_color": fill_color_tuple,
            },
        )
        snapshot_signature = (
            getattr(snap, "image1_path", None),
            getattr(snap, "image2_path", None),
            getattr(snap, "timestamp", None),
            viewport_fingerprint(snap.viewport_state),
            frozen_value(snap.settings_state),
        )
        request_key = (
            snapshot_signature,
            render_w,
            render_h,
            preview_w,
            preview_h,
            self.fit_content_mode,
            fill_color_tuple,
            global_bounds,
        )
        request_id = self._render_task_id
        frame_cache_key = (
            request_key,
        )
        cache = self._preview_frame_cache or {}
        if cache.get("key") == frame_cache_key:
            _vplog.debug(
                "preview_cache_hit task=%s render=%sx%s display=%sx%s",
                request_id,
                render_w,
                render_h,
                preview_w,
                preview_h,
            )
        else:
            _vplog.debug(
                "preview_render task=%s render=%sx%s display=%sx%s",
                request_id,
                render_w,
                render_h,
                preview_w,
                preview_h,
            )
            scene_started = time.perf_counter()
            applied = self._apply_preview_scene(
                snap,
                request_key,
                global_bounds,
                fill_color_tuple,
                render_w,
                render_h,
            )
            _vplog.debug(
                "preview_apply_scene task=%s applied=%s elapsed_ms=%.1f",
                request_id,
                applied,
                (time.perf_counter() - scene_started) * 1000.0,
            )
            if not applied:
                fallback_started = time.perf_counter()
                frame_pil = exporter.render_snapshot_to_pil(
                    snap,
                    render_w,
                    render_h,
                    auto_crop=False,
                    fit_content=self.fit_content_mode,
                    global_bounds=global_bounds,
                    fill_color=fill_color_tuple or (0, 0, 0, 0),
                )
                _vplog.debug(
                    "preview_fallback_render task=%s elapsed_ms=%.1f got_frame=%s",
                    request_id,
                    (time.perf_counter() - fallback_started) * 1000.0,
                    frame_pil is not None,
                )
                if frame_pil is None:
                    return False
                self._apply_preview_frame(frame_pil, request_key)
            self._preview_frame_cache = {"key": frame_cache_key}

        if request_id != self._render_task_id or not self.has_live_view():
            _vplog.debug(
                "preview_drop_stale task=%s current=%s live=%s",
                request_id,
                self._render_task_id,
                self.has_live_view(),
            )
            return False

        if not self._preview_ready_emitted:
            self._preview_ready_emitted = True
            self.emit_preview_ready()
        return True

    def on_fit_content_fill_color_changed(self, _color):
        self.reset_render_state()
        self.schedule_update()

    def on_preview_scale_changed(self, scale: float):
        self.preview_render_scale = max(0.25, min(float(scale), 1.0))
        if self.model is not None and hasattr(self.model, "preview_render_scale"):
            self.model.preview_render_scale = self.preview_render_scale
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
            exporter = getattr(self.export_controller, "video_exporter", None)
            if exporter is not None:
                exporter.invalidate_bounds_cache()

        self.schedule_update()

    def recalculate_global_bounds(self):
        if self._bounds_calculation_pending:
            return
        exporter = getattr(self.export_controller, "video_exporter", None)
        if exporter is None:
            return

        snapshots = self.editor_service.get_current_snapshots()
        if not snapshots:
            return

        from .common import VIDEO_EDITOR_AUTO_CROP

        self._bounds_calculation_pending = True

        def calculate():
            return exporter.calculate_global_canvas_bounds(snapshots, VIDEO_EDITOR_AUTO_CROP)

        worker = GenericWorker(calculate)
        worker.signals.result.connect(self.on_global_bounds_calculated)
        worker.signals.error.connect(self.on_bounds_calculation_error)
        self.export_controller.thread_pool.start(worker)

    def on_global_bounds_calculated(self, bounds):
        self._bounds_calculation_pending = False
        self._cached_global_bounds = bounds

        if bounds and self.fit_content_mode and self.has_live_view():
            g_pad_left = int(bounds.pad_left)
            g_pad_right = int(bounds.pad_right)
            g_pad_top = int(bounds.pad_top)
            g_pad_bottom = int(bounds.pad_bottom)
            g_base_w = int(bounds.base_width)
            g_base_h = int(bounds.base_height)
            canvas_w = g_base_w + g_pad_left + g_pad_right
            canvas_h = g_base_h + g_pad_top + g_pad_bottom

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
        self._preview_frame_cache = None
        if self.has_live_view() and hasattr(self.view, "preview_label"):
            self.view.preview_label._preview_source_key = None
        self.view = None
