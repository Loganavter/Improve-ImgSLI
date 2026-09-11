# Audit-Meta: pattern=thin-owner reason="Canvas widget thin owner — delegates to interaction/render_context/features"
from PIL import Image as PilImage
from PySide6.QtCore import QCoreApplication, QPoint, QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QRhiWidget

from tabs.image_compare.first_frame_debug import (
    ic_first_frame_debug,
    ic_first_frame_debug_enabled,
    ic_first_frame_readiness_repr,
)
from ui.context_menu.manager import open_context_menu
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget

from .feature_overlay_gpu import (
    clear_feature_overlay_gpu,
    set_feature_overlay_content,
    set_feature_overlay_gpu_params,
    upload_feature_overlay_crop,
)
from .interaction import (
    handle_key_press_event,
    handle_key_release_event,
    handle_leave_event,
    handle_mouse_move_event,
    handle_mouse_press_event,
    handle_mouse_release_event,
    handle_wheel_event,
)
from .interaction import reset_view as reset_view_impl
from .interaction import set_capture_area as set_capture_area_impl
from .interaction import set_capture_color as set_capture_color_impl
from .interaction import set_drag_overlay_state as set_drag_overlay_state_impl
from .interaction import set_guides_params as set_guides_params_impl
from .interaction import set_overlay_coords as set_overlay_coords_impl
from .interaction import set_pan as set_pan_impl
from .interaction import set_zoom as set_zoom_impl
from .interaction import (
    update_split_for_zoom,
)
from .render_context import (
    begin_update_batch,
    emit_viewport_state_change,
    end_update_batch,
    preload_source_textures,
    request_update,
    resize_canvas,
    schedule_source_preload,
)
from ui.canvas_infra.rhi.rhi_backend import configure_rhi_widget
from ui.canvas_infra.rhi.rhi_render import render_clear_frame
from shared.rendering.coalesced_flush import CoalescedFlush
from shared.rendering.glass_panel import GlassPanelRegistry
from .rhi_renderer import RhiCanvasRenderer
from .scene import build_render_scene
from .state import CanvasRuntimeState, init_widget_state
from .texture_parts.base_images import (
    configure_offscreen_render,
    get_letterbox_params,
    letterbox_pil,
    upload_diff_source_pil_image,
    upload_image,
    upload_pil_images,
)
from .texture_parts.common import set_texture_filter
from .texture_parts.layers import clear as clear_textures_and_layers
from .texture_parts.layers import (
    set_background,
    set_layers,
    set_pil_layers,
    set_pixmap,
)

# How many completed presents get a compositor settle kick. Shared with
# multi_compare so both canvas tabs wait for the first frame that actually
# reaches the display (see shared/rendering/first_frame_gate.py).
from shared.rendering.first_frame_gate import (
    FIRST_PRESENT_SETTLE_COUNT as _FIRST_PRESENT_SETTLE_COUNT,
    first_visual_present_count as _first_visual_present_count,
)

# DnD show-edge settle: one delayed compositor kick (drag-scoped).
# The immediate flush restacks while only the pre-tile buffer exists;
# the delayed kick lands amid presented tile-frames. Single-shot, no
# re-arm: repeated-kick and kick-weight experiments moved nothing
# visually (whole-window stall during grabs lives outside our timing),
# so this stays the minimal proven recipe (MC drag/DnD path parity).
_DND_RESTACK_DELAY_MS = 120


def _schedule_drag_restack(w) -> None:
    """Fire the delayed settle kick; no-op if the zone already hid."""
    from PySide6.QtCore import QTimer as _QTimer

    _QTimer.singleShot(_DND_RESTACK_DELAY_MS, lambda: _drag_restack_tick(w))


def _drag_restack_tick(w) -> None:
    """One settle kick; stands down if the zone already hid."""
    try:
        from tabs.image_compare.debug import ic_dnd_debug as _icdd

        import time as _time

        t0 = getattr(w, "_dnd_show_t0", None)
        still = bool(w.runtime_state._drag_overlay_visible)
        _icdd(
            "canvas.restack fired +%sms still_visible=%s",
            round((_time.monotonic() - t0) * 1000) if t0 is not None else "?",
            still,
        )
        if not still:
            return
        # activate=False: external drag focus belongs to the source app —
        # raise_/activateWindow is a guaranteed-denied xdg-activation
        # request (Mutter «ожидает» banner, internal-docs inv-flyout-wayland).
        from ui.canvas_infra.rhi.rhi_present_sync import flush_qrhi_compositor

        flush_qrhi_compositor(w, reason="ic-dnd-show-settle", activate=False)
    except Exception:
        pass


class CanvasWidget(QRhiWidget):
    mousePressed = Signal(object)
    mouseMoved = Signal(object)
    mouseReleased = Signal(object)
    wheelScrolled = Signal(object)
    zoomChanged = Signal(float)
    keyPressed = Signal(object)
    keyReleased = Signal(object)
    firstFrameRendered = Signal()
    firstVisualFrameReady = Signal()

    _alignment = Qt.AlignmentFlag.AlignCenter

    def __init__(self, parent=None):
        super().__init__(parent)
        configure_rhi_widget(self)
        self._first_frame_rendered_emitted = False
        self._rhi_presents_completed = 0
        # DnD show→visible latency probes (env-gated logs only, see
        # set_drag_overlay_state/render — prod-silent without IMGSLI_IC_DEBUG).
        self._dnd_show_t0: float | None = None
        self._dnd_first_present_t: float | None = None
        self._rhi_renderer = RhiCanvasRenderer()
        # Registered/unregistered by GlassHUD instances anchored to this
        # canvas (see ui/widgets/glass_hud/hud.py) -- consumed by
        # RhiCanvasRenderer.render(), which populates
        # self._glass_panel_sprites for each GlassHUD's own
        # GlassPanelDisplayWidget to read.
        self.glass_panels = GlassPanelRegistry()
        self.runtime_state: CanvasRuntimeState
        self._context_menu_provider = None
        self._render_scene_flush = CoalescedFlush(self._flush_render_scene)
        init_widget_state(self)
        # Tracks the device size (widget size * DPR) resizeEvent last
        # committed to the GPU-rendering machinery -- see paintEvent's
        # stale-device-size self-heal below (docs/dev/investigations/
        # image-compare-first-activation-flicker-and-qrhi.md Bug 3
        # follow-up, ported from Telegram Desktop's lib_ui gl_surface.cpp).
        self._device_size = QSize()
        ic_first_frame_debug(self, "canvas constructed")

    def set_store(self, store):
        state = self.runtime_state
        state._store = store
        state._render_scene = build_render_scene(
            store, apply_channel_mode_in_shader=state._apply_channel_mode_in_shader
        )
        ic_first_frame_debug(self, "set_store plan=%s", state._render_scene is not None)
        if hasattr(store, "on_change"):
            store.on_change(lambda scope: self._refresh_render_scene())

    def set_context_menu_provider(self, provider) -> None:
        self._context_menu_provider = provider
        pending_ctrl = getattr(self, "_pending_session_controller", None)
        if pending_ctrl is not None and hasattr(provider, "attach_session_controller"):
            provider.attach_session_controller(pending_ctrl)
            self._pending_session_controller = None

    def _refresh_render_scene(self):
        self._render_scene_flush.request()
        self.update()

    def _flush_render_scene(self):
        state = self.runtime_state
        if state._store is None:
            return
        state._render_scene = build_render_scene(
            state._store,
            apply_channel_mode_in_shader=state._apply_channel_mode_in_shader,
        )
        plan = getattr(self, "_active_render_plan", None)
        if plan is not None:
            from tabs.image_compare.canvas.registry import registry

            registry().apply_feature_live_runtime_overlays(state._store, self)
        self.update()

    def set_apply_channel_mode_in_shader(self, enabled: bool):
        state = self.runtime_state
        state._apply_channel_mode_in_shader = enabled
        if state._store is not None:
            state._render_scene = build_render_scene(
                state._store,
                apply_channel_mode_in_shader=state._apply_channel_mode_in_shader,
            )
        self.update()

    def set_render_scene(self, scene):
        self.runtime_state._render_scene = scene
        self.update()

    def set_split_position_sync(self, sync_callback):
        self.runtime_state._split_position_sync = sync_callback

    def set_drag_overlay_state(
        self,
        visible: bool,
        horizontal: bool = False,
        text1: str = "",
        text2: str = "",
    ):
        import traceback
        before = bool(self.runtime_state._drag_overlay_visible)
        set_drag_overlay_state_impl(self, visible, horizontal, text1, text2)
        after = bool(self.runtime_state._drag_overlay_visible)
        if before != after:
            try:
                from tabs.image_compare.debug import ic_dnd_debug

                ic_dnd_debug(
                    "canvas.set_drag_overlay_state %s->%s visible=%s stack=%s",
                    before,
                    after,
                    visible,
                    "".join(traceback.format_stack(limit=8)[:-2]),
                )
            except Exception:
                pass
            if after and not before:
                # Mark the present counter: on hide we log how many frames
                # actually presented during the TRUE window. Tells apart
                # "no frames scheduled" from "frames recorded but dropped by
                # the compositor" without needing FIRST_FRAME_DEBUG (whose
                # sampler would itself pump frames and confound the test).
                try:
                    self._dnd_show_present_mark = int(self._rhi_presents_completed)
                except Exception:
                    self._dnd_show_present_mark = None
                # Wall-clock show edge for the show→first-present latency probe.
                # (Per-gesture clock: reset every show, cleared on hide.)
                try:
                    import time as _time

                    self._dnd_show_t0 = _time.monotonic()
                except Exception:
                    self._dnd_show_t0 = None
                try:
                    self._dnd_first_present_t = None
                except Exception:
                    pass
            if before and not after:
                try:
                    from tabs.image_compare.debug import ic_dnd_debug as _icdd

                    import time as _time

                    mark = getattr(self, "_dnd_show_present_mark", None)
                    now = int(self._rhi_presents_completed)
                    t0 = getattr(self, "_dnd_show_t0", None)
                    t_first = getattr(self, "_dnd_first_present_t", None)
                    t_now = _time.monotonic()
                    if t0 is None:
                        first_ms: object = "?"
                        vis_ms: object = "?"
                    else:
                        vis_ms = round((t_now - t0) * 1000)
                        first_ms = (
                            round((t_first - t0) * 1000)
                            if t_first is not None
                            else "never"
                        )
                    _icdd(
                        "canvas.hide presents_during_show=%s visible_ms=%s first_present_ms=%s",
                        (now - mark) if mark is not None else "?",
                        vis_ms,
                        first_ms,
                    )
                except Exception:
                    pass
                try:
                    self._dnd_show_t0 = None
                    self._dnd_first_present_t = None
                except Exception:
                    pass
            if after:
                # Wayland quirk (docs/dev/KNOWN_BUGS / qrhi-gotchas): the
                # compositor can keep showing the previous subsurface buffer
                # even though a frame with the DragDropOverlayPass tiles was
                # presented — "SSOT True, screen stale". During an external
                # drag the app additionally reports ApplicationInactive and
                # Wayland throttles the subsurface. Kick the compositor once
                # on the show edge, mirroring Multi Compare's drag/DnD path
                # and the startup first-present settle.
                try:
                    from ui.canvas_infra.rhi.rhi_present_sync import (
                        flush_qrhi_compositor,
                    )

                    # activate=False on both kicks: external drag focus belongs
                    # to the source app — activation would be denied and
                    # banner (see _schedule_drag_restack below). chrome=False
                    # on the immediate kick: it provably restacks the
                    # pre-tile buffer (useless for tiles) while its full
                    # repaint churn synchronously delays the first tile
                    # frame inside the DragEnter handler — keep it light,
                    # the settle chain (full kicks) does the real work.
                    flush_qrhi_compositor(
                        self, reason="ic-dnd-show", activate=False, chrome=False
                    )
                    # ...and once more after the first tile-frames are
                    # flowing. The immediate flush above restacks while only
                    # the pre-tile buffer exists; a lone restack there leaves
                    # the compositor settled on stale content. The delayed
                    # kick lands amid presented tile-frames. Single-shot,
                    # drag-scoped; no-op if the zone already hid.
                    _schedule_drag_restack(self)
                except Exception:
                    self._request_update()

    def is_drag_overlay_visible(self) -> bool:
        return bool(self.runtime_state._drag_overlay_visible)

    def showEvent(self, event):
        super().showEvent(event)
        ic_first_frame_debug(self, "showEvent (canvas visible)")
        self._start_first_frame_sampler()
        self._ensure_dnd_keepwarm()
        # Hidden stack pages never present; the first show on Windows/D3D often
        # lands on an uninitialized swapchain buffer (see-through CSD shell).
        self._request_update()
        if self._rhi_presents_completed < _FIRST_PRESENT_SETTLE_COUNT:
            QTimer.singleShot(0, self._settle_first_presents)

    def _start_first_frame_sampler(self) -> None:
        """Periodically log what the canvas region actually shows on screen.

        Catches the "transparent first frame" that the present timeline can't:
        the compositor may keep showing the untouched (transparent) subsurface
        even while RHI presents are being recorded. Samples every ~50 ms for
        the first ~1.5 s after show, reporting Qt-side visibility/exposure and
        the opaque fraction of a corner grab.
        """
        if not ic_first_frame_debug_enabled():
            return
        if getattr(self, "_ffd_sampler_started", False):
            return
        self._ffd_sampler_started = True
        self._ffd_sampler_ticks = 0
        from tabs.image_compare.first_frame_debug import (
            ic_first_frame_surface_repr,
        )

        def _tick():
            self._ffd_sampler_ticks += 1
            ic_first_frame_debug(
                self,
                "sampler presents=%s [%s]",
                self._rhi_presents_completed,
                ic_first_frame_surface_repr(self),
            )
            if self._ffd_sampler_ticks < 30:
                QTimer.singleShot(50, _tick)

        QTimer.singleShot(50, _tick)

    def _ensure_dnd_keepwarm(self) -> None:
        """Idle pipeline primer: silent canvas update ticks.

        A long-static canvas shows drop feedback ~350 ms late on NVIDIA
        Wayland (cold swapchain/fences + deprioritized static surface;
        proven by bisection: 50 ms grabs+logs instant at any age, silent
        grabs fail, render logs alone fail, event loop free, wire healthy).
        A periodic no-op RHI frame keeps the pipeline primed so the first
        drag frame displays immediately. Default 250 ms (proven value);
        opt out with ``IMGSLI_DND_KEEPWARM_MS=0``. Ticks stand down while
        the canvas is hidden/minimized or while the drag pump owns frames.
        """
        try:
            import os as _os

            try:
                _interval = int(_os.environ.get("IMGSLI_DND_KEEPWARM_MS", "250"))
            except Exception:
                _interval = 250
            if _interval <= 0:
                return
            if getattr(self, "_dnd_keepwarm_started", False):
                return
            self._dnd_keepwarm_started = True
            from PySide6.QtCore import QTimer as _QTimer

            _timer = _QTimer(self)
            _timer.setInterval(_interval)

            def _on_tick() -> None:
                try:
                    if not self.isVisible():
                        return
                    _win = self.window()
                    if _win is not None:
                        try:
                            if _win.isMinimized():
                                return
                        except Exception:
                            pass
                    try:
                        if bool(self.runtime_state._drag_overlay_visible):
                            return  # drag pump owns frames while shown
                    except Exception:
                        pass
                    self.update()
                except Exception:
                    pass

            _timer.timeout.connect(_on_tick)
            _timer.start()
            try:
                from tabs.image_compare.debug import ic_dnd_debug as _icdd

                _icdd("dnd keep-warm started interval_ms=%s", _interval)
            except Exception:
                pass
        except Exception:
            pass

            _timer.timeout.connect(_on_tick)
            _timer.start()
        except Exception:
            pass

    def resizeEvent(self, event):
        # lib_ui's gl_surface.cpp guard: refuse to forward a resize into
        # GPU-rendering machinery before the top-level's native window
        # exists at all (see docs/dev/investigations/
        # image-compare-first-activation-flicker-and-qrhi.md Bug 3
        # follow-up). Qt's own geometry bookkeeping for this widget is
        # already done by the time the event is dispatched, so skipping
        # here loses nothing -- the next resizeEvent once the window handle
        # exists will pick up the current size.
        top = self.window()
        if top is None or top.windowHandle() is None:
            return
        state = self.runtime_state
        state._drag_overlay_cache_key = None
        state._drag_overlay_cached_image = None
        super().resizeEvent(event)
        size = event.size()
        ic_first_frame_debug(self, "resizeEvent -> %s", size)
        self._device_size = size * self.devicePixelRatio()
        resize_canvas(self, size.width(), size.height())

    def paintEvent(self, event):
        # lib_ui's gl_surface.cpp guard: self-heal the "stuck at old size"
        # symptom directly -- if the widget's current size*DPR has drifted
        # from what resizeEvent last committed to the GPU-rendering
        # machinery (e.g. a resize was skipped above, or landed before the
        # RHI surface was ready), re-post a synthetic resize instead of
        # painting a frame at the stale size. See docs/dev/investigations/
        # image-compare-first-activation-flicker-and-qrhi.md Bug 3
        # follow-up.
        expected = self.size() * self.devicePixelRatio()
        if self._device_size != expected and expected.width() > 0 and expected.height() > 0:
            self._device_size = expected
            QCoreApplication.postEvent(
                self, QResizeEvent(self.size(), self.size())
            )
            self.update()
            return
        super().paintEvent(event)

    def set_session_controller(self, session_controller) -> None:
        if self._context_menu_provider is not None:
            self._context_menu_provider.attach_session_controller(session_controller)
        else:
            self._pending_session_controller = session_controller

    def initialize(self, command_buffer):
        ic_first_frame_debug(self, "initialize() renderer init starts")
        self._rhi_renderer.initialize(self, command_buffer)
        ic_first_frame_debug(self, "initialize() renderer ready")

    def releaseResources(self):
        self._rhi_renderer.release()

    def upload_image(self, qimage: QImage, slot_index: int):
        return upload_image(self, qimage, slot_index)

    def upload_image2(self, qimage: QImage):
        self.upload_image(qimage, 1)

    def _letterbox_pil(
        self, img: PilImage.Image, slot_index: int = -1
    ) -> PilImage.Image:
        return letterbox_pil(self, img, slot_index)

    def upload_pil_images(
        self,
        pil_image1,
        pil_image2,
        source_image1=None,
        source_image2=None,
        source_key=None,
        display_cache_key=None,
        shader_letterbox: bool = False,
    ):
        return upload_pil_images(
            self,
            pil_image1,
            pil_image2,
            source_image1,
            source_image2,
            source_key,
            display_cache_key,
            shader_letterbox,
        )

    def render(self, command_buffer):
        # Match Multi Compare: only treat a completed beginPass/endPass as a
        # real present. Emitting on a no-op (target/rhi still None) made the
        # startup cover drop onto an empty D3D swapchain buffer on Windows.
        #
        # Docs: render-pass-contract (FBO α=1), qrhi-gotchas (display lags
        # store / compositor), patterns (QRhiWidget under translucent CSD).
        # On D3D the *first* presented buffer is often still an alpha hole
        # through the shell; wait for a settle present + compositor flush.
        # Like Multi Compare, firstFrameRendered is emitted only *after* that
        # flush (see _emit_first_frame_if_ready): on Wayland/Vulkan the
        # present is recorded while the compositor still shows the untouched
        # (transparent) subsurface, and only flush_qrhi_compositor()'s
        # requestUpdate/restack makes the frame visible. Emitting here would
        # hide the startup placeholder a frame too early — the user sees the
        # transparent subsurface until the flush lands.
        painted = render_clear_frame(self, command_buffer)
        if not painted:
            ic_first_frame_debug(
                self, "render() returned NOT-painted (engine not ready yet)"
            )
            return

        self._rhi_presents_completed = int(self._rhi_presents_completed) + 1
        # DnD latency probe: first completed present after the show edge.
        # Deliberately independent of FIRST_FRAME_DEBUG (whose sampler grabs
        # and would itself pump frames, confounding the measurement). Logs
        # once per show window; silent when no drag is active.
        try:
            _t0 = getattr(self, "_dnd_show_t0", None)
            if (
                _t0 is not None
                and getattr(self, "_dnd_first_present_t", None) is None
                and bool(
                    getattr(getattr(self, "runtime_state", None),
                            "_drag_overlay_visible", False)
                )
            ):
                import time as _time3

                _t_first = _time3.monotonic()
                self._dnd_first_present_t = _t_first
                from tabs.image_compare.debug import ic_dnd_debug as _icdd3

                _icdd3(
                    "canvas.first-present +%sms after show (present #%s)",
                    round((_t_first - _t0) * 1000),
                    self._rhi_presents_completed,
                )
        except Exception:
            pass
        ic_first_frame_debug(
            self, "render() painted present #%s [%s]",
            self._rhi_presents_completed, ic_first_frame_readiness_repr(self),
        )
        if self._rhi_presents_completed <= _FIRST_PRESENT_SETTLE_COUNT:
            self._settle_first_presents()

    def _settle_first_presents(self) -> None:
        """Settle present + window restack so the compositor shows an opaque
        frame instead of the untouched transparent subsurface (see render())."""

        def _flush() -> None:
            try:
                drag_vis = bool(
                    getattr(
                        getattr(self, "runtime_state", None),
                        "_drag_overlay_visible",
                        False,
                    )
                )
            except Exception:
                drag_vis = False
            if drag_vis:
                # Startup settle must not fire mid-drag: its activated flush
                # (raise_/activateWindow with default activate=True) is an
                # xdg-activation storm while the drag source owns focus —
                # Mutter answers with busy-cursor flashes — plus full repaint
                # churn on the GUI thread inside the show→visible window.
                # The DnD settle chain owns restack while the zone is shown;
                # the pre-emit gate check below still runs.
                try:
                    from tabs.image_compare.debug import ic_dnd_debug as _icdd0

                    _icdd0("first-present settle skipped (drag overlay visible)")
                except Exception:
                    pass
            else:
                try:
                    from ui.canvas_infra.rhi.rhi_present_sync import flush_qrhi_compositor

                    flush_qrhi_compositor(self, reason="ic-first-present")
                    ic_first_frame_debug(self, "compositor settle flush ran")
                except Exception:
                    self._request_update()
            self._emit_first_frame_if_ready()

        QTimer.singleShot(0, _flush)

    def _emit_first_frame_if_ready(self) -> None:
        """Emit firstFrameRendered only once the frame is compositor-visible.

        Mirrors multi_compare's canvas_widget: called from the settle flush
        (after flush_qrhi_compositor restacks an opaque buffer), not from the
        present itself.
        """
        if self._rhi_presents_completed < _first_visual_present_count():
            return
        if not self._first_frame_rendered_emitted:
            self._first_frame_rendered_emitted = True
            ic_first_frame_debug(
                self, "EMIT firstFrameRendered (presents=%s) [%s]",
                self._rhi_presents_completed, ic_first_frame_readiness_repr(self),
            )
            self.firstFrameRendered.emit()
            self.firstVisualFrameReady.emit()

    def _request_update(self):
        request_update(self)

    def _emit_viewport_state_change(self):
        emit_viewport_state_change(self)

    def _schedule_source_preload(self):
        schedule_source_preload(self)

    def _preload_source_textures(self):
        preload_source_textures(self)

    def begin_update_batch(self):
        begin_update_batch(self)

    def end_update_batch(self):
        end_update_batch(self)

    def set_split_pos(self, pos: float):
        self.split_position = pos
        self._request_update()

    def set_background(self, pixmap: QPixmap | None):
        return set_background(self, pixmap)

    def set_pixmap(self, pixmap: QPixmap | None):
        return set_pixmap(self, pixmap)

    def set_feature_overlay_content(
        self, pixmap: QPixmap | None, top_left: QPoint | None
    ):
        return set_feature_overlay_content(self, pixmap, top_left)

    def get_letterbox_params(self, slot: int = 0) -> tuple:
        return get_letterbox_params(self, slot)

    def set_feature_overlay_gpu_params(
        self,
        slots: list[dict | None],
        channel_mode: int = 0,
        diff_mode: int = 0,
        diff_threshold: float = 20.0 / 255.0,
        border_color: QColor | None = None,
        border_width: float = 2.0,
        interp_mode: int = 1,
    ):
        return set_feature_overlay_gpu_params(
            self,
            slots,
            channel_mode,
            diff_mode,
            diff_threshold,
            border_color,
            border_width,
            interp_mode,
        )

    def _set_texture_filter(self, texture_id: int, canvas_filter: int):
        return set_texture_filter(self, texture_id, canvas_filter)

    def clear_feature_overlay_gpu(self):
        return clear_feature_overlay_gpu(self)

    def upload_feature_overlay_crop(
        self,
        pil_image,
        center: QPointF,
        radius: float,
        border_color: QColor | None = None,
        border_width: float = 2.0,
        index: int = 0,
        canvas_filter: int | None = None,
    ):
        return upload_feature_overlay_crop(
            self,
            pil_image,
            center,
            radius,
            border_color,
            border_width,
            index,
            canvas_filter,
        )

    def upload_diff_source_pil_image(self, pil_image):
        return upload_diff_source_pil_image(self, pil_image)

    def configure_offscreen_render(
        self,
        *,
        stored_images,
        source_images,
        content_rect: tuple[int, int, int, int],
        shader_letterbox: bool = False,
    ):
        return configure_offscreen_render(
            self,
            stored_images=stored_images,
            source_images=source_images,
            content_rect=content_rect,
            shader_letterbox=shader_letterbox,
        )

    def set_overlay_coords(
        self,
        capture_center: QPointF | None,
        capture_radius: float,
        overlay_centers: list[QPointF],
        overlay_radius: float,
    ):
        set_overlay_coords_impl(
            self, capture_center, capture_radius, overlay_centers, overlay_radius
        )

    def set_guides_params(self, visible: bool, color: QColor, thickness: int):
        set_guides_params_impl(self, visible, color, thickness)

    def set_capture_color(self, color: QColor):
        set_capture_color_impl(self, color)

    def set_capture_area(
        self, center: QPoint | None, size: int, color: QColor | None = None
    ):
        set_capture_area_impl(self, center, size, color)

    def set_layers(
        self,
        background: QPixmap | None,
        overlay: QPixmap | None,
        overlay_pos: QPoint | None,
        coords_snapshot: tuple | None = None,
    ):
        return set_layers(self, background, overlay, overlay_pos, coords_snapshot)

    def set_pil_layers(
        self,
        pil_image1=None,
        pil_image2=None,
        overlay=None,
        overlay_pos=None,
        source_image1=None,
        source_image2=None,
        source_key=None,
        display_cache_key=None,
        shader_letterbox: bool = False,
    ):
        return set_pil_layers(
            self,
            pil_image1,
            pil_image2,
            overlay,
            overlay_pos,
            source_image1,
            source_image2,
            source_key,
            display_cache_key,
            shader_letterbox,
        )

    def setPixmap(self, pixmap: QPixmap | None):
        return set_pixmap(self, pixmap)

    def clear(self):
        return clear_textures_and_layers(self)

    def setAlignment(self, alignment):
        self._alignment = alignment

    def alignment(self):
        return self._alignment

    def set_read_only(self, enabled: bool):
        self.runtime_state._read_only = bool(enabled)
        if enabled:
            from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level

            set_zoom_level(self, 1.0)
            set_pan_offsets(self, 0.0, 0.0)
            self.update()

    def is_read_only(self) -> bool:
        return bool(getattr(self.runtime_state, "_read_only", False))

    def setAutoFillBackground(self, enabled):

        pass

    def setFocusPolicy(self, policy):
        super().setFocusPolicy(policy)

    def setAttribute(self, attribute, on=True):
        super().setAttribute(attribute, on)

    def contentsRect(self):
        return self.rect()

    def _update_split_for_zoom(self, new_zoom, new_pan_x, new_pan_y):
        update_split_for_zoom(self, new_zoom, new_pan_x, new_pan_y)

    def set_zoom(self, zoom: float):
        set_zoom_impl(self, zoom)

    def set_pan(self, x: float, y: float):
        set_pan_impl(self, x, y)

    def reset_view(self):
        reset_view_impl(self)

    def wheelEvent(self, event):
        handle_wheel_event(self, event)

    def mousePressEvent(self, event):
        handle_mouse_press_event(self, event)

    def contextMenuEvent(self, event: QContextMenuEvent):
        from ui.canvas_infra.scene.context_menu_zones import (
            ContextMenuHitContext,
            is_context_menu_suppressed,
        )

        session_type = self._active_session_type()
        if session_type is None:
            event.ignore()
            return
        store = getattr(self.runtime_state, "_store", None)
        # Space+RMB is the single-image preview gesture — the host menu must
        # not open on top of it.
        if store is not None and bool(
            store.viewport.interaction_state.space_bar_pressed
        ):
            event.accept()
            return
        if store is not None and is_context_menu_suppressed(
            ContextMenuHitContext(
                store=store,
                canvas=self,
                local_pos=event.pos(),
                session_type=session_type,
            )
        ):
            event.accept()
            return
        slot = self._context_menu_slot_at(event.pos())
        if slot is None:
            event.ignore()
            return
        menu = open_context_menu(
            ContextMenuRequest(
                source_widget=self,
                global_pos=event.globalPos(),
                local_pos=event.pos(),
                session_type=session_type,
                target=ContextMenuTarget(
                    kind=f"{session_type}_slot", id=slot
                ),
            )
        )
        if menu is None:
            event.ignore()
            return
        event.accept()

    def _active_session_type(self) -> str | None:
        store = getattr(self.runtime_state, "_store", None)
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        return session.session_type if session is not None else None

    def _context_menu_slot_at(self, pos):
        store = getattr(self.runtime_state, "_store", None)
        if store is None:
            return None
        view = store.viewport.view_state
        split = float(
            getattr(
                view,
                "split_position_visual",
                getattr(self, "split_position", 0.5),
            )
        )
        split = max(0.0, min(1.0, split))
        if bool(getattr(view, "is_horizontal", getattr(self, "is_horizontal", False))):
            return 1 if pos.y() <= self.height() * split else 2
        return 1 if pos.x() <= self.width() * split else 2

    def mouseReleaseEvent(self, event):
        handle_mouse_release_event(self, event)

    def mouseMoveEvent(self, event):
        handle_mouse_move_event(self, event)

    def keyPressEvent(self, event):
        handle_key_press_event(self, event)

    def keyReleaseEvent(self, event):
        handle_key_release_event(self, event)

    def leaveEvent(self, event):
        handle_leave_event(self, event)


def get_canvas_widget_class():
    return CanvasWidget