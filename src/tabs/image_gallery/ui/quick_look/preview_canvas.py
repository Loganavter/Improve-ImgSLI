"""Quick Look single-quad GPU preview — gallery tab, deliberately canvas-light.

``QuickLookCanvasWidget`` is a minimal ``QRhiWidget`` showing one
aspect-fit image quad. It is intentionally far lighter than the compare
tabs: no scene tree, no feature passes, no gestures, no overlays, no
labels.

Seam rules (frozen with worker B / worker C):

- One textured quad only, sourced from ``widget._active_composition``
  (a single ``ResolvedLayer``). The composition value is produced only
  through the shared applicator
  (``ui.canvas_presentation.plan_applicator.apply_canvas_render_plan``);
  this module never resolves or builds compositions itself.
- Pixels come from a caller-provided ``TiledPixelStore`` (created via
  ``TiledPixelStore.from_path`` with no crop service — worker B owns
  that call). This widget only adopts the store: the previously held
  store is closed in ``set_source`` / ``clear_source``.
- Per-frame host pixels go through ``HostTextureUploadCache``
  (``cache_for_host``) + ``qimage_from_pixel_source``. GPU objects
  (RGB8/RGBA texture, sampler, buffers, pipeline, bindings) are owned
  exclusively by the engine shell (``engine.overlay.TexturedOverlayShell``):
  this file mints no GPU resources itself.
- Fail open: with no source, no RHI, or no render target the widget
  records nothing (transparent clear at most) and never raises.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRhiDepthStencilClearValue
from PySide6.QtWidgets import QRhiWidget, QSizePolicy

from engine.gpu.host_texture_cache import cache_for_host
from engine.overlay import TexturedOverlayBinding, TexturedOverlayShell
from engine.store.tiled_pixel_store import pixel_source_size, qimage_from_pixel_source
from ui.canvas_infra.rhi.rhi_backend import configure_rhi_widget
from ui.canvas_presentation.composition import LayerNode
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan

logger = logging.getLogger("ImproveImgSLI")

# Host-cache role key for the decoded preview image.
_PREVIEW_ROLE_KEY = "quicklook_preview"

# Identity clip matrix for the fullscreen shell quad (the preview has no
# viewport transform — aspect-fit is baked into the uploaded raster).
_IDENTITY_CLIP = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)

_CLEAR_TRANSPARENT = QColor(0, 0, 0, 0)


def _overlay_shader_dir() -> Path | None:
    """Filesystem location of the shared textured-quad shaders.

    Resolved by path only (no cross-tab import): prefer the
    multi-compare copy, mirroring the retired overlay base fallback.
    Returns ``None`` when neither copy exists — the widget then stays
    inert (fail open) instead of raising.
    """
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


def _packed_bytes(image: QImage) -> tuple[int, int, bytes] | None:
    """Pack a premultiplied host image into shell frame bytes."""
    try:
        width, height = int(image.width()), int(image.height())
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    try:
        stride = width * 4
        raw = bytes(image.constBits())
        row_stride = int(image.bytesPerLine())
    except Exception:
        return None
    try:
        if row_stride == stride:
            pixels = raw[: stride * height]
        else:
            pixels = b"".join(
                raw[y * row_stride: y * row_stride + stride] for y in range(height)
            )
        if len(pixels) != stride * height:
            return None
        return (width, height, pixels)
    except Exception:
        return None


class QuickLookCanvasWidget(QRhiWidget):
    """Minimal single-quad GPU preview for Quick Look.

    Lifecycle: ``set_source(store)`` adopts a pixel store (closing the
    previously held one), ``clear_source()`` releases it. Either call
    schedules a repaint. ``QLabel`` fallback in the overlay stays
    authoritative whenever this canvas cannot initialize.
    """

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
        try:
            configure_rhi_widget(self)
        except Exception:
            logger.debug("QuickLook preview: RHI setup failed; staying inert", exc_info=True)

    # -- source lifetime --------------------------------------------------------

    def set_source(self, store) -> None:
        """Adopt ``store`` (a ``TiledPixelStore`` or ``None``).

        The previously held store is closed first when it is a different
        object. Never raises.
        """
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
            self.update()
        except Exception:
            pass

    def clear_source(self) -> None:
        """Release the held store and drop the composition. Never raises."""
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
        """Rebuild the single-layer composition through the shared applicator.

        The only plan-apply path in this module: a ``CanvasRenderPlan``
        carrying a one-``LayerNode`` ``composition_root`` is handed to
        ``apply_canvas_render_plan``, which resolves and stashes
        ``_active_composition``. Nothing is resolved or stashed here.
        """
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
                    _CLEAR_TRANSPARENT,
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
        """Aspect-fit letterboxed framebuffer raster for the active layer.

        Reads the single ``ResolvedLayer`` from ``_active_composition``,
        decodes through the host upload cache, and letterboxes the image
        (contain) onto a transparent framebuffer-sized surface. Returns
        shell frame bytes, or ``None`` when there is nothing drawable.
        A per-size frame cache skips the QPainter raster on steady frames.
        """
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
            key = (id(source), generation, int(src_w), int(src_h), fb_w, fb_h)
            if key == self._frame_key and self._frame_bytes is not None:
                return self._frame_bytes
            full = self._decoded_image(source, src_w, src_h)
            if full is None or full.isNull():
                return None
            frame = self._letterbox(full, fb_w, fb_h)
            if frame is None:
                return None
            self._frame_key = key
            self._frame_bytes = frame
            return frame
        except Exception:
            logger.debug("QuickLook preview: raster failed open", exc_info=True)
            return None

    def _decoded_image(self, source, src_w: int, src_h: int) -> QImage | None:
        """Full-res host image via the shared upload cache."""
        try:
            cache = cache_for_host(self)
        except Exception:
            cache = None
        role = f"{_PREVIEW_ROLE_KEY}:{id(source)}"
        if cache is not None:
            try:
                hit = cache.touch(role)
                if hit is not None and not hit.isNull():
                    if int(hit.width()) == int(src_w) and int(hit.height()) == int(src_h):
                        return hit
            except Exception:
                pass
        try:
            image = qimage_from_pixel_source(source)
        except Exception:
            return None
        if cache is not None and image is not None:
            try:
                cache.store(role, image)
            except Exception:
                pass
        return image

    @staticmethod
    def _letterbox(full: QImage, fb_w: int, fb_h: int) -> tuple[int, int, bytes] | None:
        """Contain-fit ``full`` onto a transparent ``fb_w`` x ``fb_h`` surface."""
        try:
            src_w, src_h = int(full.width()), int(full.height())
            if src_w <= 0 or src_h <= 0:
                return None
            scale = min(float(fb_w) / float(src_w), float(fb_h) / float(src_h))
            if not (scale > 0):
                return None
            dest_w = max(1, int(round(src_w * scale)))
            dest_h = max(1, int(round(src_h * scale)))
            dest_x = max(0, (fb_w - dest_w) // 2)
            dest_y = max(0, (fb_h - dest_h) // 2)
            canvas = QImage(fb_w, fb_h, QImage.Format.Format_RGBA8888_Premultiplied)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            try:
                painter.setRenderHint(
                    QPainter.RenderHint.SmoothPixmapTransform, True
                )
                painter.drawImage(
                    dest_x, dest_y, dest_w, dest_h, full, 0, 0, src_w, src_h
                )
            finally:
                painter.end()
            premult = canvas.convertToFormat(
                QImage.Format.Format_RGBA8888_Premultiplied
            )
            return _packed_bytes(premult)
        except Exception:
            return None
