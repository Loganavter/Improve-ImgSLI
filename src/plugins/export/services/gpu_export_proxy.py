import logging
import time
import shiboken6 as sip
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication
from PIL import Image

from engine.gpu.export_tiling import (
    DEFAULT_EXPORT_TILE_MAX_EXTENT,
    CanvasGoneError as _EngineCanvasGoneError,
    TiledFramebufferExporter,
    iter_export_tile_rects,
    qimage_to_pil_rgba,
)
from engine.gpu.offscreen_canvas import (
    configure_offscreen_widget,
    pump_offscreen_to_quiescence,
    render_widget_frame,
    resize_and_show_offscreen_widget,
    show_offscreen_widget,
    shutdown_offscreen_widget,
)
from engine.cache.image_identity import image_uid
from engine.cache.tab_canvas_services import create_canvas_widget

logger = logging.getLogger("ImproveImgSLI")


def _freeze_key_component(value, _depth: int = 0):
    """Recursive hashable freeze for throttle-key components.

    Scalars pass through; containers freeze element-wise; pixel sources
    contribute their stable ``image_uid`` (never reused, unlike ``id()``)
    plus type/size; anything else falls back to a capped ``repr``. The
    fallback may miss a throttle hit but can never alias two distinct
    contents to one key.
    """
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    if isinstance(value, (tuple, list)):
        if _depth > 4:
            return ("len", len(value))
        return tuple(_freeze_key_component(v, _depth + 1) for v in value)
    if isinstance(value, dict):
        if _depth > 4:
            return ("len", len(value))
        return tuple(
            sorted(
                (
                    (_freeze_key_component(k, _depth + 1), _freeze_key_component(v, _depth + 1))
                    for k, v in value.items()
                ),
                key=repr,
            )
        )
    size = getattr(value, "size", None)
    if size is not None or hasattr(value, "tobytes") or hasattr(value, "constBits"):
        try:
            uid = image_uid(value)
        except Exception:
            uid = None
        try:
            frozen_size = _freeze_key_component(
                tuple(size) if not isinstance(size, tuple) else size, _depth + 1
            ) if size is not None else None
        except Exception:
            frozen_size = None
        return ("pixels", type(value).__name__, uid, frozen_size)
    try:
        return ("repr", type(value).__name__, repr(value)[:256])
    except Exception:
        return ("repr", type(value).__name__)


_RENDER_SCENE_KEY_FIELDS = (
    "blank_white",
    "single_image_preview",
    "clip_overlays_to_image_bounds",
    "is_horizontal",
    "split_position_visual",
    "overlay_clip_rect",
    "channel_mode_int",
    "diff_mode_active",
    "diff_mode_int",
    "zoom_interpolation_method",
    "feature_overrides",
)


def _render_scene_signature(scene) -> tuple:
    if scene is None:
        return (None,)
    return tuple(
        (name, _freeze_key_component(getattr(scene, name, None)))
        for name in _RENDER_SCENE_KEY_FIELDS
    )


def export_grab_content_key(plan, diff_image) -> tuple:
    """Content-identity throttle key for one export grab.

    Never uses ``id()``: CPython reuses addresses after GC, so an
    ``id(plan)`` key aliases a new same-size plan to the previous frame's
    pixels across the 50 ms throttle window (silent wrong-image export in
    batch runs). Every component here is content-derived (keys, sizes,
    stable image uids, render-scene scalars).
    """
    try:
        size = (int(plan.canvas_w), int(plan.canvas_h))
    except Exception:
        size = (0, 0)
    return (
        size,
        _freeze_key_component(getattr(plan, "source_key", None)),
        _freeze_key_component(getattr(plan, "display_cache_key", None)),
        image_uid(getattr(plan, "image1", None)),
        image_uid(getattr(plan, "image2", None)),
        image_uid(getattr(plan, "source_image1", None)),
        image_uid(getattr(plan, "source_image2", None)),
        image_uid(diff_image),
        _render_scene_signature(getattr(plan, "render_scene", None)),
        _freeze_key_component(
            (
                getattr(plan, "output_scale", 1.0),
                getattr(plan, "fill_rgba", None),
                getattr(plan, "capture_visible", None),
                getattr(plan, "guides_enabled", None),
                getattr(plan, "guides_thickness", None),
                getattr(plan, "preserve_zoom", None),
            )
        ),
    )


class _CanvasGoneError(RuntimeError):
    """Canvas widget deleted mid-export — quiet abort, not a bug."""


def _widget_alive(widget) -> bool:
    """Fail-open liveness probe (same shiboken idiom as export/dialog.py)."""
    try:
        return widget is not None and bool(sip.isValid(widget))
    except Exception:
        return False


class GpuExportProxy(QObject):

    @property
    def has_widget(self) -> bool:
        """True once an offscreen canvas widget exists and is still alive.

        Warm-up callers use this to stop retrying: the first successful
        creation is what populates the GPU pipeline state; repeating it
        recreates the widget (and pays the ~4 s D3D compile again).
        """
        return _widget_alive(getattr(self, "_widget", None))

    render_requested = Signal(object)

    def __init__(self, parent=None, resource_manager=None):
        super().__init__(parent)
        self._widget = None
        self._resource_manager = resource_manager
        self._last_widget_size = None
        self._shutting_down = False
        self._last_grab_ts = 0.0
        self._last_grab_key = None
        self._last_grab_image = None
        self.render_requested.connect(self._render_on_main_thread)

    def _ensure_widget(self):
        if self._shutting_down:
            raise RuntimeError("GpuExportProxy is shut down")
        if self._widget is not None:
            if _widget_alive(self._widget):
                return self._widget
            # Stale cache: the tab closed (or the canvas was torn down)
            # since the last frame. Drop it so this call recreates or
            # skips quietly instead of grabbing from a deleted C++ object
            # on every subsequent frame of the plan.
            logger.debug("GpuExportProxy dropping deleted cached canvas widget")
            self._widget = None
            self._last_widget_size = None

        widget = create_canvas_widget()
        if widget is None:
            logger.debug("GpuExportProxy _ensure_widget skipped: no canvas widget for active tab")
            return None
        widget.setObjectName("gpu_export_canvas")
        configure_offscreen_widget(widget)
        widget._use_plan_fill_clear = True
        show_offscreen_widget(widget)
        if self._resource_manager is not None:
            self._resource_manager.register_widget(widget, name="gpu_export_canvas")
        self._widget = widget
        return widget

    @Slot()
    def shutdown(self):
        self._shutting_down = True
        # Disconnect queued requests so a late delivery does not recreate the
        # offscreen widget post-shutdown (W1.6).
        try:
            self.render_requested.disconnect(self._render_on_main_thread)
        except Exception:
            pass
        widget = self._widget
        self._widget = None
        self._last_widget_size = None
        shutdown_offscreen_widget(widget)

    def _render_widget_frame(self, widget):
        render_widget_frame(widget)

    def _build_exporter(self, widget, plan, diff_image):
        from ui.canvas_presentation.plan_applicator import apply_render_plan_to_canvas
        from ui.canvas_infra.rhi.rhi_backend import query_max_texture_size

        def set_export_viewport(viewport):
            widget.runtime_state._export_canvas_viewport = viewport

        def prepare_frame():
            apply_render_plan_to_canvas(widget, plan)
            widget.upload_diff_source_pil_image(diff_image)

        return TiledFramebufferExporter(
            widget,
            set_export_viewport=set_export_viewport,
            prepare_frame=prepare_frame,
            query_max_texture_size=lambda: query_max_texture_size(widget.rhi()),
        )

    def _render_plan_frame(self, widget, plan, diff_image, debug_timings, store=None):
        from ui.canvas_infra.rhi.rhi_backend import query_max_texture_size

        if not _widget_alive(widget):
            raise _CanvasGoneError("canvas widget deleted before export frame")
        canvas_w, canvas_h = int(plan.canvas_w), int(plan.canvas_h)
        tile_extent = min(
            DEFAULT_EXPORT_TILE_MAX_EXTENT, query_max_texture_size(widget.rhi())
        )
        if canvas_w <= tile_extent and canvas_h <= tile_extent:
            widget.runtime_state._export_canvas_viewport = None
            return self._render_plan_frame_single(
                widget, plan, diff_image, debug_timings, store=store
            )
        return self._render_plan_frame_tiled(
            widget, plan, diff_image, debug_timings, tile_extent, store=store
        )

    def _render_plan_frame_tiled(
        self, widget, plan, diff_image, debug_timings, tile_extent, store=None
    ):
        canvas_w, canvas_h = int(plan.canvas_w), int(plan.canvas_h)
        tile_started = time.perf_counter()
        tile_rects = list(iter_export_tile_rects(canvas_w, canvas_h, tile_extent))
        debug_timings["export_tile_count"] = float(len(tile_rects))

        exporter = self._build_exporter(widget, plan, diff_image)
        final_image = exporter.render_rgba(
            canvas_w, canvas_h, max_extent=tile_extent
        )
        self._last_widget_size = exporter._last_size

        widget.runtime_state._export_canvas_viewport = None
        debug_timings["export_tiled_total_ms"] = (
            time.perf_counter() - tile_started
        ) * 1000.0
        debug_timings["readback_width"] = float(canvas_w)
        debug_timings["readback_height"] = float(canvas_h)
        return final_image

    def _render_plan_frame_single(
        self, widget, plan, diff_image, debug_timings, store=None
    ):
        from ui.canvas_presentation.plan_applicator import apply_render_plan_to_canvas

        # Throttle duplicate grabs for identical plan within short window.
        # The key is content-identity (never id()): id() addresses are
        # recycled after GC, so a fresh same-size plan could alias the
        # previous frame's pixels and export the wrong image silently.
        target_widget_size = (int(plan.canvas_w), int(plan.canvas_h))
        grab_key = export_grab_content_key(plan, diff_image)
        now = time.perf_counter()
        if grab_key == self._last_grab_key and (now - self._last_grab_ts) < 0.05 and self._last_grab_image is not None:
            debug_timings["grab_throttled"] = 1.0
            debug_timings["grab_raw_ms"] = 0.0
            debug_timings["grab_framebuffer_ms"] = 0.0
            debug_timings["widget_resize_show_ms"] = 0.0
            debug_timings["configure_widget_ms"] = 0.0
            debug_timings["paint_gl_ms"] = 0.0
            return self._last_grab_image.copy()

        resize_show_started = time.perf_counter()
        widget_size_changed = self._last_widget_size != target_widget_size
        if widget_size_changed:
            resize_and_show_offscreen_widget(widget, target_widget_size)
            self._last_widget_size = target_widget_size
        debug_timings["widget_resize_show_ms"] = (
            time.perf_counter() - resize_show_started
        ) * 1000.0

        configure_started = time.perf_counter()
        apply_render_plan_to_canvas(widget, plan)
        widget.upload_diff_source_pil_image(diff_image)
        debug_timings["configure_widget_ms"] = (
            time.perf_counter() - configure_started
        ) * 1000.0

        paint_started = time.perf_counter()
        self._render_widget_frame(widget)
        # Cold-tier first frame: tile uploads are budget-limited per frame,
        # so the grab below would read a partial tier. Pump residency to
        # quiescence (engine primitive; no-op when already resident).
        try:
            pumped = pump_offscreen_to_quiescence(widget)
        except Exception:
            pumped = 0
        debug_timings["export_pump_frames"] = float(pumped)
        debug_timings["rhi_render_ms"] = (
            time.perf_counter() - paint_started
        ) * 1000.0
        # Legacy alias — keep for old log parsers
        debug_timings["paint_gl_ms"] = debug_timings["rhi_render_ms"]

        framebuffer_started = time.perf_counter()
        grab_started = time.perf_counter()
        try:
            qimg = widget.grabFramebuffer()
        except RuntimeError as exc:
            # TOCTOU: deleted between the alive-check and the grab (the
            # main-thread event loop runs closes between plan frames).
            raise _CanvasGoneError(f"canvas widget deleted during export grab: {exc}") from exc
        debug_timings["grab_raw_ms"] = (time.perf_counter() - grab_started) * 1000.0

        convert_started = time.perf_counter()
        image = qimage_to_pil_rgba(qimg)
        debug_timings["qimage_convert_ms"] = (time.perf_counter() - convert_started) * 1000.0

        raw_bytes = image.tobytes()
        image._raw_rgba_bytes = raw_bytes

        resize_started = time.perf_counter()
        if image.size != target_widget_size:
            image = image.resize(target_widget_size, Image.Resampling.BILINEAR)
            if hasattr(image, "_raw_rgba_bytes"):
                try:
                    delattr(image, "_raw_rgba_bytes")
                except AttributeError:
                    pass
        debug_timings["pil_resize_ms"] = (time.perf_counter() - resize_started) * 1000.0

        debug_timings["grab_framebuffer_ms"] = (
            time.perf_counter() - framebuffer_started
        ) * 1000.0
        debug_timings["readback_width"] = float(image.width)
        debug_timings["readback_height"] = float(image.height)
        # Update throttle cache
        try:
            self._last_grab_key = grab_key
            self._last_grab_image = image.copy()
            self._last_grab_ts = time.perf_counter()
        except Exception:
            pass
        return image

    @Slot(object)
    def _render_on_main_thread(self, payload):
        # Two calling conventions share this slot: the blocking one (an
        # "event" to signal + "result_box" to fill, used by synchronous
        # callers that park a background thread on Event.wait()) and the
        # async one ("callback", used by callers that must not block their
        # thread — e.g. video-editor thumbnail generation). Both still do
        # the actual GPU render synchronously here, on the main thread.
        if self._shutting_down:
            error = RuntimeError("GpuExportProxy is shut down")
            if payload.get("result_box") is not None:
                payload["result_box"]["error"] = error
            callback = payload.get("callback")
            event = payload.get("event")
            if callback is not None:
                callback(None, {}, error)
            elif event is not None:
                event.set()
            return
        event = payload.get("event")
        result_box = payload.get("result_box")
        callback = payload.get("callback")
        debug_timings = {}
        image = None
        error = None
        widget = None
        try:
            widget = self._ensure_widget()
            if widget is None:
                error = RuntimeError("No canvas widget available for active tab — GPU export skipped")
                logger.debug("GPU export skipped (no canvas provider): %s", error)
                if result_box is not None:
                    result_box["error"] = error
                # error will be delivered via finally callback/event
                return
            mode = payload.get("mode", "render")
            if mode != "render_plan":
                raise RuntimeError(f"Unsupported GPU export mode: {mode}")
            plan = payload["plan"]
            store = payload.get("store")
            diff_image = payload.get("diff_image")
            image = self._render_plan_frame(
                widget,
                plan,
                diff_image,
                debug_timings,
                store=store,
            )
            if result_box is not None:
                result_box["image"] = image
                result_box["debug_timings"] = debug_timings
        except Exception as exc:
            # Degrade for missing canvas is already debug-logged; other failures stay exception.
            # A canvas deleted mid-export is routine (tab closed) — debug, no traceback.
            # Both the proxy-level and the engine tiling-level gone markers route here.
            if isinstance(exc, (_CanvasGoneError, _EngineCanvasGoneError)):
                logger.debug("GPU export aborted (%s)", exc)
            elif widget is None:
                logger.debug("GPU export degraded (no canvas): %s", exc)
            else:
                logger.exception("GPU export rendering failed")
            error = exc
            if result_box is not None:
                result_box["error"] = exc
        finally:
            if callback is not None:
                callback(image, debug_timings, error)
            elif event is not None:
                event.set()