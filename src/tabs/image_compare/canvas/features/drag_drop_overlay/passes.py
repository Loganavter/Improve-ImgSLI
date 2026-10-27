"""QRhi render pass for the drag_drop_overlay feature (image_compare, canvas-only).

Rasterizes live drag/drop affordances into their own overlay texture and
draws them through the shared textured engine shell
(``engine.overlay.TexturedOverlayShell``). No GPU allocation, no bespoke
pipeline builders, no draw-recorder calls here -- those live in the
shell; this pass only declares its binding, resolves per-frame raster
bytes through a ctx-first resolver, and stages them.

Live-only, interaction-driven — uses ``TRANSIENT_PREVIEW`` stacking.
Does not require ``SceneVisibility.INTERACTIVE``; ``should_paint`` gates
on ``runtime_state._drag_overlay_visible`` which is set by
``canvas/interaction.set_drag_overlay_state``. Must remain visible even
when ``blank_white`` (no images) so drop hints show on empty canvas.

Two frame-convention rules are stated here and implemented in
``framing.py``, both learned from the 2026-10-27 "drop zone mirrored +
shrinks on HiDPI" report (text/preview read top-to-bottom reversed, and
the zone got *smaller* at a larger interface scale):

* **Orientation.** The shell's quad maps raster row 0 (``v == 0``) to clip
  ``y = +1``, so the quad needs the backend's clip-space correction from
  ``engine/gpu/rt_y_orientation`` — ``composited_clip_correction`` (this
  pass writes into the ``QRhiWidget``'s own composited target). Staging
  identity happens to look right on a y-up NDC backend (GL/D3D) and
  mirrors the raster on a y-down one (Vulkan). The sibling IC overlays
  (``features/guides``, ``features/capture``, ``features/divider``,
  ``features/filename_overlay``) take the same correction; never decide
  it locally, and never "fix" a flip by reversing raster rows.
* **DPR.** image_compare's context carries *logical* ``width/height``
  (``canvas/render_context.py`` ``ViewportContext``), not device px. The
  raster is device px (``logical * DPR``, painted in logical coordinates
  under a painter scale derived from it), so the draw viewport must be
  the same device-px size; sizing it from the logical numbers drew the
  texture into ``1/DPR`` of the framebuffer per axis (a quarter of the
  area at DPR=2). ``framing.framebuffer_size`` is the single place that
  answers "how many device px is the frame", used by both the raster and
  the draw.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from engine.overlay import (
    TexturedOverlayBinding,
    TexturedOverlayResolver,
    TexturedOverlayShell,
)
from tabs.image_compare.canvas.features.drag_drop_overlay import framing
from tabs.image_compare.canvas.features.drag_drop_overlay.render.overlay import (
    paint_drag_drop_overlay,
    should_paint_drag_overlay,
)
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from core.log_names import APP_LOGGER_NAME


def _shader_dir() -> Path:
    # Mirrors the retired ``rhi_overlay_pass_base._shader_dir`` fallback:
    # prefer the local image_compare copy when present, else reuse
    # multi_compare's. (R3b deletes the retired base; this copy stays.)
    local = Path(__file__).resolve().parents[2] / "shaders" / "overlay"
    if local.is_dir():
        return local
    return (
        Path(__file__).resolve().parents[4]
        / "multi_compare"
        / "shaders"
        / "qrhi"
    )


BINDING = TexturedOverlayBinding(
    shader_dir=_shader_dir(),
    shader_stem="overlay",
)


def _resolve_host(widget, ctx):
    """Resolve the canvas host from the prepare arg or the frame context."""
    w = widget
    if w is None:
        w = getattr(ctx, "widget", None)
    if w is None:
        w = getattr(getattr(ctx, "feature_overlay", None), "widget", None)
    return w


def _raster_image(host, ctx) -> QImage | None:
    """Rasterize the drag affordances for ``host`` into a premultiplied image."""
    state = getattr(host, "runtime_state", None)
    if state is None or not bool(getattr(state, "_drag_overlay_visible", False)):
        return None

    fb_w, fb_h = framing.framebuffer_size(host, ctx)

    horizontal = bool(getattr(state, "_drag_overlay_horizontal", False))
    texts = getattr(state, "_drag_overlay_texts", ("", ""))
    text1 = texts[0] if len(texts) > 0 else ""
    text2 = texts[1] if len(texts) > 1 else ""

    # Raster cache: the tiles depend only on (size, orientation, texts),
    # all of which invalidate state._drag_overlay_cache_key on change
    # (state flip in interaction.set_drag_overlay_state, resize in
    # widget.resizeEvent). Without this, every pump frame re-rasters a
    # full-canvas QImage via QPainter (~10-20ms CPU) and re-uploads ~11MB
    # — during a drag that cost dominates the frame and slows the
    # compositor catch-up the tiles need to become visible.
    try:
        key = (int(fb_w), int(fb_h), bool(horizontal), str(text1), str(text2))
    except Exception:
        key = None
    if key is not None:
        try:
            if getattr(state, "_drag_overlay_cache_key", None) == key:
                cached = getattr(state, "_drag_overlay_cached_image", None)
                if cached is not None and not cached.isNull():
                    return cached
        except Exception:
            pass

    img = QImage(max(1, int(fb_w)), max(1, int(fb_h)), QImage.Format.Format_RGBA8888_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    scale = framing.logical_to_framebuffer_scale(host, fb_w, fb_h)
    painter.save()
    painter.scale(scale, scale)
    paint_drag_drop_overlay(painter, host, horizontal, text1, text2)
    painter.restore()
    painter.end()
    img = img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    if key is not None:
        try:
            state._drag_overlay_cache_key = key
            state._drag_overlay_cached_image = img
        except Exception:
            pass
    return img


def _image_to_frame(img: QImage) -> tuple[int, int, bytes] | None:
    """Convert a premultiplied host image to shell bytes (tab-side seam).

    The engine takes bytes, never host images: this snapshot owns its
    copy, so the shell can wrap it for the synchronous upload call
    without holding any host image type.
    """
    width, height = int(img.width()), int(img.height())
    if width <= 0 or height <= 0:
        return None
    stride = width * 4
    try:
        raw = bytes(img.constBits())
    except Exception:
        return None
    bytes_per_line = int(img.bytesPerLine())
    if bytes_per_line == stride:
        pixels = raw[: stride * height]
    else:
        pixels = b"".join(
            raw[y * bytes_per_line : y * bytes_per_line + stride] for y in range(height)
        )
    if len(pixels) != stride * height:
        return None
    return (width, height, pixels)


def resolve(ctx: Any) -> tuple[int, int, bytes] | None:
    """Ctx-first raster resolver: ctx in, framebuffer bytes out (or None)."""
    host = _resolve_host(None, ctx)
    if host is None:
        return None
    img = _raster_image(host, ctx)
    if img is None or img.isNull():
        return None
    return _image_to_frame(img)


def _frame_resolver() -> TexturedOverlayResolver:
    """Resolver factory: the raster arrives via ``ctx``, nothing is captured."""
    return resolve


class DragDropOverlayPass(CanvasRenderPass):
    """Draw live drag/drop affordances through the shared textured shell."""

    stack_role = CanvasStackRole.TRANSIENT_PREVIEW
    visibility = SceneVisibility.ALL
    # Must paint even when no images are loaded (empty canvas drop hint)
    requires_content = False

    def __init__(self) -> None:
        self._shell = TexturedOverlayShell()
        # Framebuffer size (device px) resolved once per frame in prepare().
        # record() must not read the widget (tests/contracts/
        # test_pass_reads_only_ctx.py pins it at zero reads) and must agree
        # with the raster exactly, so the size is resolved here and consumed
        # there.
        self._framebuffer_px: tuple[int, int] = (0, 0)

    def should_paint(self, ctx) -> bool:
        widget = getattr(ctx, "widget", None)
        if widget is None:
            widget = getattr(ctx, "viewport", None)
            # fallback: try widget attribute directly
            if widget is None:
                return False
        # ctx may be RenderRuntimeContext; widget is inside it as well
        w = getattr(ctx, "widget", None)
        if w is None:
            # image_compare's ctx is RenderRuntimeContext with widget inside feature_overlay
            w = getattr(getattr(ctx, "feature_overlay", None), "widget", None)
        if w is None:
            # last fallback: use the widget passed via should_paint's ctx.widget
            w = widget
        # Direct check on runtime_state
        state = getattr(w, "runtime_state", None) if w is not None else None
        if state is not None:
            return bool(getattr(state, "_drag_overlay_visible", False))
        # Fallback to helper
        return should_paint_drag_overlay(w) if w is not None else False

    def _raster(self, widget, ctx) -> QImage | None:
        # Resolve actual widget: prepare passes widget as first arg
        w = _resolve_host(widget, ctx)
        if w is None:
            return None
        return _raster_image(w, ctx)

    def _dnd_edge_debug(self, sig, msg: str, *args) -> None:
        """Edge-triggered pass-stage logging (IMGSLI_IC_DEBUG only).

        Temporary instrumentation for the "SSOT True but no tiles on
        screen" investigation: reports prepare/record stages of the drag
        overlay pass without flooding per-frame logs. Sigs are namespaced
        per call site (dict slot) so prepare/record don't evict each other.
        """
        from shared.debug_flags import env_value as _env_value

        if not _env_value("IMGSLI_IC_DEBUG"):
            return
        seen = getattr(self, "_dnd_dbg_sigs", None)
        if seen is None:
            seen = {}
            self._dnd_dbg_sigs = seen
        if seen.get(sig[0]) == sig:
            return
        seen[sig[0]] = sig
        import logging

        logging.getLogger(APP_LOGGER_NAME).warning("[ic-dnd] %s", msg % args if args else msg)

    def initialize(self, rhi, target) -> None:
        self._shell.mount(rhi, target, BINDING.shader_dir, BINDING.shader_stem)

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._shell.stage_quad(resource_updates)
        # The quad maps raster row 0 to clip y=+1, so the backend's
        # clip-space correction decides whether that row is the top of the
        # screen (image_compare's ctx carries no clip_matrix; see
        # framing.clip_matrix).
        self._shell.stage_clip(
            resource_updates, framing.clip_matrix(ctx, self._shell.rhi)
        )
        # Resolve once: the raster below uses the same helper, so texture and
        # the viewport record() sets cannot disagree (DPR applied once).
        self._framebuffer_px = framing.framebuffer_size(
            _resolve_host(widget, ctx), ctx
        )
        frame = _frame_resolver()(ctx)
        try:
            rt = widget.renderTarget() if widget is not None else None
        except Exception:
            rt = None
        self._shell.upload_frame(resource_updates, rt, frame)
        img_size = getattr(self._shell.texture_size, "toTuple", lambda: self._shell.texture_size)()
        self._dnd_edge_debug(
            ("prepare", self._shell.active, str(img_size)),
            "dnd-prepare raster_fired active=%s texture_size=%s",
            self._shell.active,
            img_size,
        )

    def record(self, command_buffer, widget, ctx) -> None:
        fired = bool(self._shell.active and self._shell.pipeline is not None)
        self._dnd_edge_debug(
            ("record", fired),
            "dnd-record quad_fired=%s",
            fired,
        )
        # Viewport = the raster's own device-px size (resolved in prepare()):
        # the logical ctx.width/height would draw the texture into 1/DPR of
        # the framebuffer per axis on a scaled display.
        fb_w, fb_h = self._framebuffer_px
        if fb_w <= 0 or fb_h <= 0:
            # prepare() staged nothing this frame, so there is no raster (and
            # no per-frame uniform/quad) to draw.
            return
        self._shell.draw(command_buffer, width=float(fb_w), height=float(fb_h))

    def release(self) -> None:
        self._shell.teardown()


RENDER_PASSES: list[CanvasRenderPass] = [DragDropOverlayPass()]
RENDER_PASSES = RENDER_PASSES
