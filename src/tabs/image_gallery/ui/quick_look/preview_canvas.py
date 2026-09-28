"""Quick Look single-quad GPU preview — gallery tab, deliberately canvas-light.

``QuickLookCanvasWidget`` is a minimal ``QRhiWidget`` showing one
aspect-fit image quad. It is intentionally far lighter than the compare
tabs: no scene tree, no feature passes, no gestures, no overlays, no
labels.

Seam rules (frozen with host/tests): one quad from _active_composition
via the shared applicator only; pixels from the caller-provided store
 sampled verbatim through ``PyramidPixelStore.best_pixels`` (bounded
 ``read_array`` only — never ``qimage_from_pixel_source``, never a host
 upload cache, never a full-frame materialize); GPU objects belong to
 TexturedOverlayShell only. The host hands this widget a bounded coarse
 store (``preview_canvas_host._coarse_store_for``); a miss samples to
 None and the frame is skipped. Fail open; previewFailed → QLabel
 fallback, firstFramePresented (settled present + restack, MC parity)
 → cover drop.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QRhiDepthStencilClearValue
from PySide6.QtWidgets import QRhiWidget, QSizePolicy

from engine.overlay import TexturedOverlayBinding, TexturedOverlayShell
from engine.store.tiled_pixel_store import pixel_source_size
from ui.canvas_infra.rhi.rhi_backend import configure_rhi_widget
from ui.canvas_presentation.composition import LayerNode
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan
from tabs.image_gallery.ui.quick_look.preview_canvas_host import settle_first_frame

logger = logging.getLogger("ImproveImgSLI")

# Identity clip matrix for the fullscreen shell quad (the preview has no
# viewport transform — aspect-fit is baked into the uploaded raster).
_IDENTITY_CLIP = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)

_CLEAR_OPAQUE = QColor(0, 0, 0, 255)

# No-present watchdog: a canvas that shows no frame within this window is
# presumed broken (dead RHI, missing shaders) and must yield to QLabel —
# a transparent widget shows the windows behind it as "garbage".
_NO_FRAME_TIMEOUT_MS = 1500

# Host decode cap: the letterbox only needs framebuffer resolution; a full
# 40k decode here would repeat the QLabel-path OOM this canvas replaces.
_DECODE_EDGE_CAP = 2048


def _overlay_shader_dir() -> Path | None:
    """Shared quad shaders by path (no cross-tab import); None = inert."""
    try:
        tabs = Path(__file__).resolve().parents[3]
    except Exception:
        return None
    candidates = (
        tabs / "multi_compare" / "shaders" / "qrhi",
        tabs / "image_compare" / "canvas" / "shaders" / "overlay",
    )
    for cand in candidates:
        try:
            if (cand / "overlay.vert.qsb").is_file() and (cand / "overlay.frag.qsb").is_file():
                return cand
        except OSError:
            continue
    return None




class QuickLookCanvasWidget(QRhiWidget):
    """Minimal single-quad GPU preview (set_source/clear_source + repaint)."""

    previewFailed = Signal()
    firstFramePresented = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        try:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        self._store = None
        self._active_composition = None
        self._active_render_plan = None
        self._shell = TexturedOverlayShell()
        self._shell_ready = False
        self._frame_key = None
        self._frame_bytes: tuple[int, int, bytes] | None = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_last = None
        self._frame_ok = False
        self._watchdog_armed = False
        try:
            configure_rhi_widget(self)
        except Exception:
            logger.debug("QuickLook preview: RHI setup failed; staying inert", exc_info=True)

    # -- source lifetime --------------------------------------------------------

    def set_source(self, store) -> None:
        """Adopt ``store`` (closes the previous one). Never raises."""
        try:
            if store is self._store:
                self._refresh_plan()
            else:
                self._close_held_store()
                self._store = store
                self._frame_key = None
                self._frame_bytes = None
                self._refresh_plan()
        except Exception:
            logger.debug("QuickLook preview: set_source failed open", exc_info=True)
        try:
            self._frame_ok = False
            self._settle_pumped = False
            self._settle_scheduled = False
            self._zoom = 1.0
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._drag_last = None
            self._frame_key = None
            self._arm_watchdog()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _arm_watchdog(self) -> None:
        """Yield to QLabel when no frame presents in time (never raises)."""
        try:
            if self._watchdog_armed:
                return
            self._watchdog_armed = True
        except Exception:
            return
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(_NO_FRAME_TIMEOUT_MS, self._on_watchdog)
        except Exception:
            try:
                self._watchdog_armed = False
            except Exception:
                pass

    def _on_watchdog(self) -> None:
        try:
            self._watchdog_armed = False
            if self._frame_ok:
                return
            try:
                import shiboken6

                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            try:
                self.previewFailed.emit()
            except Exception:
                pass
        except Exception:
            pass

    def clear_source(self) -> None:
        """Release the held store + composition. Never raises."""
        try:
            self._close_held_store()
            self._active_composition = None
            self._active_render_plan = None
            self._frame_key = None
            self._frame_bytes = None
        except Exception:
            logger.debug("QuickLook preview: clear_source failed open", exc_info=True)
        try:
            self.update()
        except Exception:
            pass

    def _close_held_store(self) -> None:
        held = self._store
        self._store = None
        if held is None:
            return
        try:
            held.close()
        except Exception:
            pass

    # -- shared-applicator plan -------------------------------------------------

    def _refresh_plan(self) -> None:
        """Single-LayerNode plan via the shared applicator (only apply path)."""
        try:
            store = self._store
            if store is None:
                self._active_composition = None
                self._active_render_plan = None
                return
            try:
                canvas_w = max(1, int(self.width()))
                canvas_h = max(1, int(self.height()))
            except Exception:
                canvas_w, canvas_h = 1, 1
            plan = CanvasRenderPlan(
                image1=None,
                image2=None,
                source_image1=None,
                source_image2=None,
                source_key=(),
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                render_scene=None,
                overlay_layout=None,
                capture_visible=False,
                capture_color=None,
                guides_enabled=False,
                guides_color=None,
                guides_thickness=0,
                composition_root=LayerNode(layer_id=0, image=store, fit_mode="contain"),
            )
            apply_canvas_render_plan(self, plan)
        except Exception:
            logger.debug("QuickLook preview: plan refresh failed open", exc_info=True)

    # -- QRhiWidget entry points ------------------------------------------------

    def initialize(self, command_buffer) -> None:  # noqa: N802
        try:
            rhi = self.rhi()
            target = self.renderTarget()
            shader_dir = _overlay_shader_dir()
            if rhi is None or target is None or shader_dir is None:
                self._shell_ready = False
                return
            binding = TexturedOverlayBinding(shader_dir=shader_dir, shader_stem="overlay")
            self._shell.mount(rhi, target, binding.shader_dir, binding.shader_stem)
            self._shell_ready = True
        except Exception:
            logger.debug("QuickLook preview: shell mount failed open", exc_info=True)
            self._shell_ready = False

    def releaseResources(self) -> None:  # noqa: N802
        try:
            self._shell.teardown()
        except Exception:
            pass
        self._shell_ready = False

    def render(self, command_buffer) -> None:  # noqa: N802
        try:
            if not self._shell_ready or command_buffer is None:
                return
            try:  # letterbox tone = host Window color (QLabel bars parity)
                from PySide6.QtGui import QPalette as _QP

                clear = self.palette().color(_QP.ColorRole.Window)
                clear.setAlpha(255)
            except Exception:
                clear = QColor(_CLEAR_OPAQUE)
            try:
                rhi = self.rhi()
                target = self.renderTarget()
            except Exception:
                return
            if rhi is None or target is None:
                return
            try:
                updates = rhi.nextResourceUpdateBatch()
            except Exception:
                return
            try:
                self._shell.stage_quad(updates)
                self._shell.stage_clip(updates, _IDENTITY_CLIP)
            except Exception:
                return
            frame = self._raster_frame(target)
            try:
                self._shell.upload_frame(updates, target, frame)
            except Exception:
                return
            try:
                command_buffer.beginPass(
                    target,
                    clear,
                    QRhiDepthStencilClearValue(1.0, 0),
                    updates,
                )
            except Exception:
                return
            try:
                if frame is not None:
                    try:
                        size = target.pixelSize()
                        fb_w, fb_h = float(size.width()), float(size.height())
                    except Exception:
                        fb_w, fb_h = 1.0, 1.0
                    self._shell.draw(command_buffer, width=fb_w, height=fb_h)
                    # Settle gate (MC parity): present #1 pumps one more frame
                    # (the compositor may still show the untouched surface);
                    # the cover drops only on the settled present #2.
                    pumped = bool(getattr(self, "_settle_pumped", False))
                    if not self._frame_ok and not pumped:
                        self._settle_pumped = True
                        try:
                            self.update()
                        except Exception:
                            pass
                    elif pumped and not self._frame_ok:
                        settle_first_frame(self)
            finally:
                try:
                    command_buffer.endPass()
                except Exception:
                    pass
        except Exception:
            logger.debug("QuickLook preview: frame failed open", exc_info=True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self._refresh_plan()
        except Exception:
            pass

    # -- frame raster -----------------------------------------------------------

    def _raster_frame(self, target) -> tuple[int, int, bytes] | None:
        """Frame raster: single ResolvedLayer → cache → zoom/pan crop."""
        try:
            composition = self._active_composition
            layers = getattr(composition, "layers", ()) or ()
            if not layers:
                return None
            source = getattr(layers[0], "image", None)
            if source is None:
                return None
            src_w, src_h = pixel_source_size(source)
            if src_w <= 0 or src_h <= 0:
                return None
            try:
                size = target.pixelSize()
                fb_w, fb_h = max(1, int(size.width())), max(1, int(size.height()))
            except Exception:
                return None
            try:
                generation = int(getattr(source, "generation", 0))
            except Exception:
                generation = 0
            key = (id(source), generation, int(src_w), int(src_h), fb_w, fb_h,
                   round(self._zoom, 4), round(self._pan_x, 4), round(self._pan_y, 4))
            if key == self._frame_key and self._frame_bytes is not None:
                return self._frame_bytes
            full = self._decoded_image(source, src_w, src_h)
            if full is None or full.isNull():
                return None
            try:
                from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame
            except Exception:
                return None
            frame = zoomed_frame(full, fb_w, fb_h, self._zoom, self._pan_x, self._pan_y)
            if frame is None:
                return None
            self._frame_key = key
            self._frame_bytes = frame
            return frame
        except Exception:
            logger.debug("QuickLook preview: raster failed open", exc_info=True)
            return None

    def _decoded_image(self, source, src_w: int, src_h: int) -> QImage | None:
        """Host image via the frozen pyramid seam (bounded, no full frame).

        Samples the held (coarse, edge-capped by the host) store verbatim
        through ``PyramidPixelStore.best_pixels`` — ``read_array`` only, so
        no full-frame materialize and no second cache. Miss (stale/unbuilt
        level, unreadable box) fails closed to None; the frame is skipped
        and the QLabel fallback owns the pane.
        """
        try:
            from engine.store.pyramid_pixel_store import PyramidPixelStore
        except Exception:
            return None
        try:
            w, h = int(src_w), int(src_h)
            if w <= 0 or h <= 0:
                return None
            pyramid = PyramidPixelStore(source)
            try:
                image = pyramid.best_pixels((0, 0, w, h), 1.0)
            finally:
                try:
                    pyramid.close()  # derived levels only; base owned by host
                except Exception:
                    pass
        except Exception:
            return None
        if image is None or image.isNull():
            return None
        try:
            # Never hold a 40k host image for a ~640px pane: downscale once.
            edge = max(int(image.width()), int(image.height()))
            if edge > _DECODE_EDGE_CAP and edge > 0:
                small = image.scaled(
                    _DECODE_EDGE_CAP,
                    _DECODE_EDGE_CAP,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if small is not None and not small.isNull():
                    image = small
        except Exception:
            pass
        return image

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Wheel = cursor-anchored zoom (MC parity); floor snaps pan to origin."""
        try:
            from tabs.image_gallery.ui.quick_look.preview_zoom import wheel_zoom_pan

            pos = event.position()
            got = wheel_zoom_pan(
                getattr(self, "_zoom", 1.0), getattr(self, "_pan_x", 0.0),
                getattr(self, "_pan_y", 0.0), event.angleDelta().y(),
                float(pos.x()) / max(1, int(self.width())),
                float(pos.y()) / max(1, int(self.height())),
            )
            if got is not None:
                self._zoom, self._pan_x, self._pan_y = got
                self._frame_key = None
                self.update()
            event.accept()
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import Qt as _Qt

            if event.button() == _Qt.MouseButton.MiddleButton:
                pos = event.position()
                self._drag_last = (float(pos.x()), float(pos.y()))
                self.setCursor(_Qt.CursorShape.ClosedHandCursor)
            super().mousePressEvent(event)
        except Exception:
            pass

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        try:
            last = getattr(self, "_drag_last", None)
            if last is not None:
                from tabs.image_gallery.ui.quick_look.preview_zoom import drag_pan

                pos = event.position()
                got = drag_pan(
                    getattr(self, "_pan_x", 0.0), getattr(self, "_pan_y", 0.0),
                    float(pos.x()) - last[0], float(pos.y()) - last[1],
                    max(1, int(self.width())), max(1, int(self.height())),
                    getattr(self, "_zoom", 1.0),
                )
                if got is not None:
                    self._pan_x, self._pan_y = got
                    self._frame_key = None
                    self.update()
                self._drag_last = (float(pos.x()), float(pos.y()))
            super().mouseMoveEvent(event)
        except Exception:
            pass

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import Qt as _Qt

            if event.button() == _Qt.MouseButton.MiddleButton:
                self._drag_last = None
                self.setCursor(_Qt.CursorShape.ArrowCursor)
            super().mouseReleaseEvent(event)
        except Exception:
            pass
