"""Canvas-owned "liquid glass" HUD backdrop: blur + tint + rounded border,
rendered directly into the canvas's own render pipeline instead of sampled
cross-widget from a separate ``QRhiWidget`` (the old
``sli_ui_toolkit`` ``LiquidGlassFillWidget`` architecture -- see
``ui/widgets/glass_hud/hud.py`` for why that was replaced: sampling a *foreign*
shown ``QRhiWidget``'s ``colorTexture()`` bypasses that widget's own
on-screen compositing blit, which is what normally absorbs a backend's Y-flip
convention for free, so the direct sample got the raw, uncorrected row order
instead -- a whole family of Y-flip/stretch/sub-pixel-popping bugs). Sampling
the canvas's *own* texture from its *own* pipeline avoids that whole class of
bug -- no cross-widget UV mapping, no foreign backend-orientation question.

NOT a Y-flip bug (checked and reverted): a prior investigation concluded
colorTexture()'s row order needed an unconditional flip on read, based on a
GPU-readback debug tool comparing a panel's crop against a "ground truth"
canvas snapshot -- that tool was itself silently mirroring the ground-truth
image (see ``_flush_debug_dumps``'s history/comment), so every comparison
built on it was comparing against an upside-down reference. Confirmed live,
with that mirroring removed, that the raw readback (canvas and crop alike)
already comes out top-down on this backend. No flip is applied anywhere in
this module's crop step; don't reintroduce one without re-confirming against
a non-mirrored reference first -- see git history for the false trail this
took (an added-then-reverted ``sourceTopLeft`` flip, and an
added-then-reverted second flip in ``glass_blur.frag`` compensating for the
first).

Timing: this reads the canvas's own colorTexture() as it stood at the end of
*this same frame's* own main render pass -- ``render_backdrops()`` is called
from ``RhiCanvasRenderer.render()`` *after* that pass's own
``command_buffer.endPass()``, not before it (moved there; an earlier version
ran before the main pass and read the *previous* frame's content instead,
on the theory that reading colorTexture() any later would need to "reopen"
the main render target -- confirmed live that's not actually a constraint
here: nothing in this crop step touches the main render target at all, only
``widget.colorTexture()`` as a plain copy *source*, and the app's own
``shared.rendering.mip_cascade.generate_all_dirty_mips`` already proves this
exact shape works within one frame -- write into a target via a pass,
``copyTexture()`` out of it once that write is *submitted*, not merely
batched, then a *later* pass/copy this same frame safely samples the copy
destination; see that method's own docstring for the submitted-vs-batched
distinction it's built on). ``command_buffer.endPass()`` is what "submits"
the main pass for this purpose; everything recorded after it, including this
module's own copyTexture, is guaranteed to execute only once that pass's own
GPU work precedes it in submission order -- a pass genuinely cannot sample a
texture it is *concurrently* writing into within its own open
beginPass/endPass, but that constraint is about *inside one open pass*, not
about same-frame ordering in general.

The crop step deliberately uses copyTexture, not a shader pass sampling
colorTexture() through a sampler -- an earlier version did the latter (to
also punch out overlapping *other* live panels' rects, replacing them with
this panel's own tint before the blur ever saw them) and it reproducibly
leaked one panel's rendered content into a completely different,
non-overlapping panel's own crop texture on OpenGL (confirmed via GPU
readback dumps and pixel-exact geometry checks -- the two panels' device
rects were ~1000px apart on screen, ruling out any real overlap), and
ghosted/accumulated frame over frame on Vulkan. Swapping the *exact same*
addressing back to a plain copyTexture (no sampler, no pipeline, no SRB)
made both symptoms disappear immediately -- this is a backend-level issue
specific to sampling a QRhiWidget's own colorTexture() through a shader in
many small per-frame render passes, not anything about the coordinates, the
uniform data, or resource sharing between panels (all independently ruled
out first).

Self-reference: even with the Y-flip fixed, a live user re-test found a
*second*, structural bug: every glass panel's own composited sprite used to
get blitted directly into the canvas's own ``colorTexture()`` (via a
``glass_panel`` feature pass, since removed -- see
``ui/widgets/glass_hud/panel_display.py`` for what replaced it). Since a panel's
crop rect is *exactly* its own on-screen footprint, next frame's crop for
that same panel necessarily read back its own previous rendering -- the
panel's backdrop converged to "blurred view of itself" within a couple of
frames, independent of the real content behind it (reproducible at any zoom
level, including >1000%, since the loop dominates regardless of what the
real backdrop is). **The canvas's own render target must never have any
glass panel drawn into it, ever** -- not "the same panel," not "an
overlapping panel," none -- or this same convergence recurs. Sprites are
displayed by a separate small ``GlassPanelDisplayWidget`` per HUD instead
(plain Qt widget compositing, no shared GPU state with the canvas's own
target at all), while this module keeps doing exactly what it did before:
crop/blur/composite from the canvas's ``colorTexture()``, now genuinely
glass-free by construction.

Usage: a ``CanvasWidget`` owns a ``GlassPanelRegistry`` (``widget.glass_panels``)
that HUD widgets (``GlassHUD``/``InfoHUD``/``ZoomIndicator``) register/
unregister themselves into by geometry key. The canvas's ``RhiCanvasRenderer``
owns a ``GlassPanelRenderer`` and calls ``render_backdrops()`` once per frame,
before the main pass opens, populating ``widget._glass_panel_sprites``; each
HUD's own ``GlassPanelDisplayWidget`` reads its entry from that dict and
blits it on its own, entirely outside the canvas's render pipeline.
"""

from __future__ import annotations

import logging
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPen,
    QRhiBuffer,
    QRhiColorAttachment,
    QRhiDepthStencilClearValue,
    QRhiGraphicsPipeline,
    QRhi,
    QRhiReadbackDescription,
    QRhiReadbackResult,
    QRhiRenderPassDescriptor,
    QRhiSampler,
    QRhiShaderResourceBindings,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiTextureCopyDescription,
    QRhiTextureRenderTarget,
    QRhiTextureRenderTargetDescription,
    QRhiViewport,
    QShader,
)

_logger = logging.getLogger("ImproveImgSLI")

# IMGSLI_GLASS_PANEL_DEBUG-gated tracing (same convention as
# ui/widgets/flyout_debug.py's IMGSLI_FLYOUT_DEBUG) -- logs, per panel key,
# every GPU object identity and geometry value involved in one
# render_backdrops() call, to chase down cross-panel data showing up in the
# wrong panel's own texture (see the "reflection" investigation this was
# added for: a panel's composite output visually matching *another* live
# panel's size/shape, not its own).
_GLASS_PANEL_DEBUG = os.environ.get("IMGSLI_GLASS_PANEL_DEBUG", "").strip().lower() not in (
    "",
    "0",
    "false",
    "no",
    "off",
)



def _debug(message: str, *args) -> None:
    if _GLASS_PANEL_DEBUG:
        _logger.debug("[glass-panel-debug] " + message, *args)


_SHADER_DIR = Path(__file__).resolve().parent / "shaders" / "glass_panel"

_BLUR_UBUF_SIZE = 16  # std140: vec2 direction + float radiusPx + pad
# std140: vec2 direction + float radiusPx + float cornerRadiusPx + vec4 tint
# + vec2 panelSizePx + float borderWidthPx + float pad + vec4 borderColor
# + vec4 debugTint
_COMPOSITE_UBUF_SIZE = 80

# Must match `ui.widgets.glass_hud.text_mask._TEXT_MASK_SUPERSAMPLE` (and
# `shaders/glass_panel/glass_text_downsample.frag`'s own `SCALE` constant) --
# that module rasterizes each panel's text mask oversized by this factor and
# uploads it *undownscaled*; this module creates `text_mask_tex` at that same
# oversized resolution and a dedicated Lanczos-2 shader pass
# (`_ensure_panel`'s `text_mask_downsample_pipeline`, run from
# `render_backdrops()` right after each upload) resolves it down to
# `text_mask_downsampled_tex` at the panel's own device resolution, which is
# what `glass_composite.frag` actually samples. Downscaling on the GPU at
# all (rather than a CPU round-trip -- Qt SmoothTransformation, then a PIL
# LANCZOS pass, both tried and dropped, see
# docs/dev/rendering/glass-panel-text-vibrancy-plan.md Phase 3) is for being
# real, measurable per-call cost on a path that runs several times/sec; a
# custom Lanczos-2 pass rather than QRhi's hardware `generateMips()` (tried
# and dropped too, see that doc's bug 17) is because box-filtered mips read
# visibly softer ("trilinear, not Lanczos") on the sharp alpha edges a
# glyph mask is made of. Not imported from `glass_hud/text_mask.py` to avoid a
# `shared.rendering` -> `ui.widgets` layering violation (wrong direction);
# duplicated here deliberately, kept in sync by this comment on both sides.
_TEXT_MASK_SUPERSAMPLE = 4

# IMGSLI_GLASS_PANEL_DEBUG_TINT=1: replaces each panel's composite output
# with one of these flat, maximally-distinct colors (assigned by first-seen
# order, see GlassPanelRenderer._debug_tint_for) -- a fast screenshot-level
# test for "which panel's texture is actually showing up where" (see the
# cross-panel-reflection investigation in git history/chat).
_DEBUG_TINT_ENABLED = os.environ.get("IMGSLI_GLASS_PANEL_DEBUG_TINT", "").strip().lower() not in (
    "",
    "0",
    "false",
    "no",
    "off",
)
_DEBUG_TINT_PALETTE = [
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.2, 0.4, 1.0),
    (1.0, 1.0, 0.0),
    (1.0, 0.0, 1.0),
    (0.0, 1.0, 1.0),
]

# IMGSLI_GLASS_PANEL_DEBUG_DUMP=<dir>: GPU readback dump, ground truth for
# "what pixels are actually in each panel's own crop/blur/composite texture,
# and in the canvas's own colorTexture() at the moment we cropped from it" --
# a screenshot of the running app goes through the compositor, whatever
# window-capture tool, and (for anything shared/pasted) usually recompression
# too, none of which this dump does. Every _DEBUG_DUMP_EVERY_N_FRAMES-th
# frame, dumps each live panel's crop_tex/blur_tex/composite_tex plus one
# full colorTexture() capture annotated with every live panel's crop rect
# outlined -- directly answers "does colorTexture() itself already contain
# the other panel's sprite at this rect" vs. "does our own crop/blur
# introduce it downstream of a correct source read."
_DEBUG_DUMP_DIR = os.environ.get("IMGSLI_GLASS_PANEL_DEBUG_DUMP")
_DEBUG_DUMP_EVERY_N_FRAMES = 5


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


@dataclass
class GlassPanelSpec:
    """Everything one glass panel needs for its backdrop to be rendered.

    ``rect_logical`` is the panel's on-screen rect in the *canvas widget's*
    own logical (DIP) pixel space -- the coordinate space
    ``ui/canvas_infra``'s render context (``ctx.width``/``ctx.height``) uses
    for screen-positioned quads (see ``filename_overlay``'s
    ``build_quad_vertices``). Computed by the HUD via
    ``mapToGlobal``/``mapFromGlobal`` against the canvas widget -- the same
    technique the old cross-widget ``LiquidGlassFillWidget`` used for its UV
    mapping, just for a destination rect now instead of a source one.
    ``corner_radius_px``/``border_width_px`` are device px (this panel's own
    scratch textures are sized in device px -- see ``dpr``).
    """

    rect_logical: QRect
    dpr: float
    corner_radius_px: float
    border_width_px: float
    border_color: QColor
    tint: QColor
    blur_radius_px: float
    # Panel-local alpha mask of this HUD's registered text widgets'
    # glyphs, built by ``ui/widgets/glass_hud/text_mask.py``'s
    # ``_rebuild_text_mask()`` -- ``_TEXT_MASK_SUPERSAMPLE`` x the panel's
    # own device px (see ``device_rects`` in ``render_backdrops``), *not*
    # 1:1 with it: this module uploads it undownscaled into a mipmapped
    # texture and lets the GPU generate the downscaled levels
    # (``glass_composite.frag`` reads it back via ``textureLod()`` at the
    # mip level matching device px exactly). ``None`` disables per-pixel
    # text recoloring for this panel entirely (no registered text
    # widgets). See ``docs/dev/rendering/glass-panel-text-vibrancy-plan.md``.
    text_mask_image: QImage | None = None


class GlassPanelRegistry:
    """Per-canvas registry of live glass panels, keyed by an opaque id the
    caller controls (``id(hud)``) -- explicit register/unregister, no
    implied widget-tree lookup."""

    def __init__(self) -> None:
        self._specs: dict[int, GlassPanelSpec] = {}

    def register(self, key: int, spec: GlassPanelSpec) -> None:
        self._specs[key] = spec

    def unregister(self, key: int) -> None:
        self._specs.pop(key, None)

    def items(self) -> list[tuple[int, GlassPanelSpec]]:
        return list(self._specs.items())


class _PanelGpu:
    """Fully self-contained GPU resources for one glass panel -- pipelines
    included. Earlier versions of this class shared one pipeline (and its
    render-pass descriptor) across *every* panel, re-pointing it at whichever
    panel's differently-sized scratch target was being drawn into that
    moment. That was cheap but backend-fragile: confirmed to actually leak
    one panel's rendered content into an unrelated, non-overlapping panel's
    own texture on OpenGL, and to accumulate/ghost frame over frame on
    Vulkan (see git history / chat -- pixel-level proof ruled out any
    geometry/UV bug: the two panels' device rects were ~1000px apart on
    screen). Giving every panel its own independent pipeline+rpdesc (mirrors
    how the old cross-widget LiquidGlassFillWidget worked -- one fully
    separate instance per HUD, no shared GPU state at all) helped rule out
    resource sharing as the cause, but the actual root cause turned out to
    be one level deeper still: sampling colorTexture() through a shader pass
    *at all* (see GlassPanelRenderer.render_backdrops's crop step, now a
    plain copyTexture instead) -- so ``crop_tex`` here has no pipeline/rpdesc
    of its own, only blur and composite do. Only the sampler stays shared on
    GlassPanelRenderer -- it's stateless/read-only."""

    def __init__(self) -> None:
        self.size: tuple[int, int] | None = None
        self.crop_tex: QRhiTexture | None = None
        self.blur_tex: QRhiTexture | None = None
        self.blur_target: QRhiTextureRenderTarget | None = None
        self.blur_rpdesc: QRhiRenderPassDescriptor | None = None
        self.blur_pipeline: QRhiGraphicsPipeline | None = None
        self.composite_tex: QRhiTexture | None = None
        self.composite_target: QRhiTextureRenderTarget | None = None
        self.composite_rpdesc: QRhiRenderPassDescriptor | None = None
        self.composite_pipeline: QRhiGraphicsPipeline | None = None
        self.blur_ubuf: QRhiBuffer | None = None
        self.composite_ubuf: QRhiBuffer | None = None
        self.srb_blur: QRhiShaderResourceBindings | None = None
        self.srb_composite: QRhiShaderResourceBindings | None = None
        # Alpha mask of this panel's HUD text glyphs -- see
        # GlassPanelSpec.text_mask_image / render_backdrops. Not a render
        # target: content only ever arrives via uploadTexture() from a
        # CPU-side QImage, never rendered into by a pipeline of its own.
        self.text_mask_tex: QRhiTexture | None = None
        # Lanczos-2-downsampled copy of text_mask_tex at this panel's own
        # device resolution -- see glass_text_downsample.frag and
        # GlassPanelRenderer._ensure_panel. Regenerated only when
        # text_mask_image_id changes (same gate as the upload itself), not
        # every render_backdrops() call.
        self.text_mask_downsampled_tex: QRhiTexture | None = None
        self.text_mask_downsample_target: QRhiTextureRenderTarget | None = None
        self.text_mask_downsample_rpdesc: QRhiRenderPassDescriptor | None = None
        self.text_mask_downsample_pipeline: QRhiGraphicsPipeline | None = None
        self.srb_text_mask_downsample: QRhiShaderResourceBindings | None = None
        # id() of the last QImage actually uploaded into text_mask_tex (or
        # the sentinel 0 for "uploaded the blank fallback", see
        # render_backdrops), so render_backdrops (called every frame) can
        # skip re-uploading identical content -- the mask itself only
        # changes a few times a second at most (see glass_hud/text_mask.py's
        # _TEXT_MASK_UPDATE_INTERVAL_S). Starts at None (never a real id()
        # or the 0 sentinel) so the very first frame after this texture is
        # (re)created always uploads *something* -- sampling it
        # uninitialized otherwise.
        self.text_mask_image_id: int | None = None

    def release(self) -> None:
        for res in (
            self.srb_blur,
            self.srb_composite,
            self.srb_text_mask_downsample,
            self.blur_ubuf,
            self.composite_ubuf,
            self.crop_tex,
            self.blur_pipeline,
            self.blur_rpdesc,
            self.blur_target,
            self.blur_tex,
            self.composite_pipeline,
            self.composite_rpdesc,
            self.composite_target,
            self.composite_tex,
            self.text_mask_downsample_pipeline,
            self.text_mask_downsample_rpdesc,
            self.text_mask_downsample_target,
            self.text_mask_downsampled_tex,
            self.text_mask_tex,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.__init__()  # type: ignore[misc]  # resource-reset reinit


class GlassPanelRenderer:
    """Owns the QRhi pipelines + per-panel scratch resources for
    ``render_backdrops()``. One instance per canvas renderer (see
    ``RhiCanvasRenderer``) -- not shared across canvases."""

    def __init__(self, name_prefix: str = "canvas") -> None:
        self._name_prefix = name_prefix
        self.rhi: QRhi | None = None
        self._sampler: QRhiSampler | None = None
        self._panels: dict[int, _PanelGpu] = {}
        self.ready_sprites: dict[int, tuple[object, QRect]] = {}
        # CPU-side copy of each panel's composite_tex, for the CPU/QPainter
        # display path (see ui/widgets/glass_hud/panel_display.py) -- a plain
        # QWidget honors real per-pixel alpha against its siblings the way a
        # QRhiWidget-hosted display does not (QOpenGLWidget/QRhiWidget-class
        # widgets are always composited as their own base layer, never
        # blended into arbitrary sibling z-order -- confirmed via a flat
        # premultiplied semi-transparent debug fill rendering fully *opaque*
        # regardless of QRhi backend or windowing platform; see the "still
        # open" section of
        # docs/dev/rendering/investigations/glass-panel-backdrop-self-reference.md).
        # Format_RGBA8888_Premultiplied matches composite_tex's own
        # premultiplied output (glass_composite.frag's `color*alpha, alpha`)
        # byte-for-byte -- no conversion needed, and QPainter blends a
        # premultiplied QImage's alpha correctly by construction.
        self.ready_images: dict[int, QImage] = {}
        # Every composite_tex readback issued in a render_backdrops() call is
        # now collected synchronously in that *same* call via a single
        # `rhi.finish()` after all panels' readbacks are issued (measured via
        # IMGSLI_GLASS_PANEL_SYNC_PROBE during development: ~0.1-1.7ms cost,
        # data always ready, see
        # docs/dev/rendering/glass-panel-text-vibrancy-plan.md Phase 3) --
        # there is no cross-call pending state to track any more.
        self._debug_render_backdrops_call_count = 0
        self._debug_tint_colors: dict[int, tuple[float, float, float]] = {}
        self._debug_dump_frame = 0
        self._debug_dump_seq = 0
        # (result, label, annotate_rects) tuples awaiting readback completion
        # -- same "poll on the next call" idiom as
        # shared.rendering.mip_cascade's _flush_debug_readbacks (QRhi's
        # Python bindings don't expose QRhiReadbackResult.completed).
        # annotate_rects is a list of (x, y, w, h) device-px rects to
        # outline in red (used only for the full-canvas dump, so every live
        # panel's *intended* crop rect is visible directly on the same
        # image the crop was sourced from), or None.
        self._debug_dump_pending: list[tuple[QRhiReadbackResult, str, list | None]] = []

    def _flush_debug_dumps(self) -> None:
        if not self._debug_dump_pending or _DEBUG_DUMP_DIR is None:
            return
        still_pending: list[tuple[QRhiReadbackResult, str, list | None]] = []
        for result, label, annotate_rects in self._debug_dump_pending:
            data = result.data
            if not data:
                still_pending.append((result, label, annotate_rects))
                continue
            size = result.pixelSize
            # No .mirrored() here -- confirmed live that this backend's raw
            # QRhiReadbackResult data already comes out in normal top-down
            # row order (matching what's actually on screen), for every
            # texture dumped here (canvas colorTexture() included). An
            # earlier version of this method mirrored unconditionally,
            # copying the old sli_ui_toolkit LiquidGlassFillWidget debug
            # dump's convention -- confirmed WRONG for this dump: it silently
            # flipped the "ground truth" canvas reference image upside down,
            # which made every crop-vs-canvas comparison during this
            # investigation compare against an inverted reference. Don't
            # reintroduce this without re-confirming against the real
            # on-screen image first.
            image = QImage(
                bytes(data),  # type: ignore[call-overload]  # QByteArray supports buffer protocol
                size.width(),
                size.height(),
                QImage.Format.Format_RGBA8888,
            )
            if annotate_rects:
                image = image.convertToFormat(QImage.Format.Format_RGB32)
                painter = QPainter(image)
                painter.setPen(QPen(QColor(255, 0, 0), 3))
                for x, y, w, h in annotate_rects:
                    painter.drawRect(int(x), int(y), int(w), int(h))
                painter.end()
            try:
                os.makedirs(_DEBUG_DUMP_DIR, exist_ok=True)
                path = os.path.join(_DEBUG_DUMP_DIR, f"{label}.png")
                image.save(path, "PNG")  # type: ignore[call-overload]  # PySide6 runtime wants str format
                _debug("debug-dump saved %s (%dx%d)", path, size.width(), size.height())
            except OSError:
                _logger.exception(
                    "GlassPanelRenderer: failed to write debug dump %s", label
                )
        self._debug_dump_pending = still_pending

    def _request_dump(
        self, rhi, command_buffer, texture, label: str, annotate_rects: list | None = None
    ) -> None:
        result = QRhiReadbackResult()
        updates = rhi.nextResourceUpdateBatch()
        updates.readBackTexture(QRhiReadbackDescription(texture), result)
        command_buffer.resourceUpdate(updates)
        self._debug_dump_seq += 1
        self._debug_dump_pending.append(
            (result, f"{self._debug_dump_seq:06d}_{label}", annotate_rects)
        )

    def _debug_tint_for(self, key: int) -> tuple[float, float, float, float]:
        if not _DEBUG_TINT_ENABLED:
            return (0.0, 0.0, 0.0, 0.0)
        color = self._debug_tint_colors.get(key)
        if color is None:
            color = _DEBUG_TINT_PALETTE[len(self._debug_tint_colors) % len(_DEBUG_TINT_PALETTE)]
            self._debug_tint_colors[key] = color
            _debug("debug-tint assigned key=%#x -> rgb=%s", key, color)
        return (*color, 1.0)

    def initialize(self, rhi) -> None:
        self.release()
        self.rhi = rhi
        self._sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        assert self._sampler is not None
        if not self._sampler.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel sampler")

    def release(self) -> None:
        for panel in self._panels.values():
            panel.release()
        self._panels.clear()
        self.ready_sprites.clear()
        self.ready_images.clear()
        self._debug_dump_pending.clear()
        if self._sampler is not None:
            try:
                self._sampler.destroy()
            except RuntimeError:
                pass
        self._sampler = None
        self.rhi = None

    def _ensure_panel(self, key: int, size: QSize) -> _PanelGpu:
        assert self._sampler is not None
        """(Re)builds one panel's *entire* GPU resource set -- textures,
        render targets, render-pass descriptors, pipelines, uniform buffers,
        SRBs -- fully independent of every other panel's. See
        ``_PanelGpu``'s docstring for why nothing here is shared across
        panels (besides the stateless sampler)."""
        panel = self._panels.get(key)
        if panel is not None and panel.size == (size.width(), size.height()):
            _debug(
                "_ensure_panel key=%#x REUSE size=%dx%d panel_id=%#x "
                "crop_tex=%#x blur_tex=%#x composite_tex=%#x",
                key,
                size.width(),
                size.height(),
                id(panel),
                id(panel.crop_tex),
                id(panel.blur_tex),
                id(panel.composite_tex),
            )
            return panel
        was_new = panel is None
        if panel is None:
            panel = _PanelGpu()
            self._panels[key] = panel
        else:
            panel.release()
        rhi = self.rhi
        assert rhi is not None
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        _debug(
            "_ensure_panel key=%#x %s size=%dx%d (previous_size=%s) panel_id=%#x "
            "live_keys=%s",
            key,
            "CREATE" if was_new else "RECREATE",
            size.width(),
            size.height(),
            panel.size,
            id(panel),
            [f"{k:#x}" for k in self._panels],
        )

        # --- crop stage: just a copyTexture destination, no pipeline of its
        # own -- see _PanelGpu's docstring for why the shader-sampling
        # version of this stage was replaced.
        panel.crop_tex = rhi.newTexture(QRhiTexture.Format.RGBA8, size)
        if not panel.crop_tex.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel crop texture")

        # --- blur stage ---
        panel.blur_tex = rhi.newTexture(
            QRhiTexture.Format.RGBA8, size, 1, QRhiTexture.Flag.RenderTarget
        )
        if not panel.blur_tex.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel blur texture")
        panel.blur_target = rhi.newTextureRenderTarget(
            QRhiTextureRenderTargetDescription(QRhiColorAttachment(panel.blur_tex))
        )
        panel.blur_rpdesc = panel.blur_target.newCompatibleRenderPassDescriptor()
        panel.blur_target.setRenderPassDescriptor(panel.blur_rpdesc)
        if not panel.blur_target.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel blur target")
        # Each panel gets its own uniform buffers rather than sharing one
        # rewritten between draws -- a shared Dynamic buffer rewritten
        # between two beginPass/endPass pairs in the same frame is not
        # guaranteed visible only to the pass it was meant for on every QRhi
        # backend (see shared.rendering.mip_cascade's
        # _ensure_downsample_uniform_buffer docstring for the investigation
        # this avoided). At most a handful of panels exist at once, so one
        # tiny buffer pair each is cheap.
        panel.blur_ubuf = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic, QRhiBuffer.UsageFlag.UniformBuffer, _BLUR_UBUF_SIZE
        )
        if not panel.blur_ubuf.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel blur ubuf")
        panel.srb_blur = rhi.newShaderResourceBindings()
        panel.srb_blur.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, fragment, panel.blur_ubuf),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, panel.crop_tex, self._sampler
                ),
            ]
        )
        if not panel.srb_blur.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel blur SRB")
        panel.blur_pipeline = rhi.newGraphicsPipeline()
        panel.blur_pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("glass_panel_pass.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, _load_shader("glass_blur.frag.qsb")
                ),
            ]
        )
        panel.blur_pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
        panel.blur_pipeline.setRenderPassDescriptor(panel.blur_rpdesc)
        panel.blur_pipeline.setShaderResourceBindings(panel.srb_blur)
        if not panel.blur_pipeline.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel blur pipeline")

        # --- composite stage ---
        panel.composite_tex = rhi.newTexture(
            QRhiTexture.Format.RGBA8, size, 1, QRhiTexture.Flag.RenderTarget
        )
        if not panel.composite_tex.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel composite texture"
            )
        panel.composite_target = rhi.newTextureRenderTarget(
            QRhiTextureRenderTargetDescription(QRhiColorAttachment(panel.composite_tex))
        )
        panel.composite_rpdesc = panel.composite_target.newCompatibleRenderPassDescriptor()
        panel.composite_target.setRenderPassDescriptor(panel.composite_rpdesc)
        if not panel.composite_target.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel composite target"
            )
        panel.composite_ubuf = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic, QRhiBuffer.UsageFlag.UniformBuffer, _COMPOSITE_UBUF_SIZE
        )
        if not panel.composite_ubuf.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} glass-panel composite ubuf")

        # --- text mask: CPU-uploaded only (see _PanelGpu docstring), sized
        # _TEXT_MASK_SUPERSAMPLE x the other scratch textures -- ui.widgets.
        # glass_hud/text_mask.py rasterizes it oversized and uploads it undownscaled.
        # Plain (non-mipmapped) texture: the downscale to device resolution
        # is done by the dedicated Lanczos-2 pass below into
        # text_mask_downsampled_tex, not by sampling this texture's own mip
        # chain (see this module's `_TEXT_MASK_SUPERSAMPLE` docstring for why
        # -- GPU hardware `generateMips()` box-filtering read visibly softer
        # than Lanczos here). text_mask_image_id reset to None here (via
        # __init__ inside release(), and it's already None on first
        # creation) forces render_backdrops's very first upload (and
        # downsample) for this (re)created texture even if the spec's image
        # is unchanged.
        text_mask_size = QSize(
            size.width() * _TEXT_MASK_SUPERSAMPLE, size.height() * _TEXT_MASK_SUPERSAMPLE
        )
        panel.text_mask_tex = rhi.newTexture(QRhiTexture.Format.RGBA8, text_mask_size)
        if not panel.text_mask_tex.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel text mask texture"
            )

        # --- text mask downsample stage: one Lanczos-2 fragment pass,
        # text_mask_tex (supersampled) -> text_mask_downsampled_tex (this
        # panel's own device resolution, what glass_composite.frag actually
        # samples). Re-run only when text_mask_image_id changes (see
        # render_backdrops), not every frame.
        panel.text_mask_downsampled_tex = rhi.newTexture(
            QRhiTexture.Format.RGBA8, size, 1, QRhiTexture.Flag.RenderTarget
        )
        if not panel.text_mask_downsampled_tex.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel text mask downsample texture"
            )
        panel.text_mask_downsample_target = rhi.newTextureRenderTarget(
            QRhiTextureRenderTargetDescription(
                QRhiColorAttachment(panel.text_mask_downsampled_tex)
            )
        )
        panel.text_mask_downsample_rpdesc = (
            panel.text_mask_downsample_target.newCompatibleRenderPassDescriptor()
        )
        panel.text_mask_downsample_target.setRenderPassDescriptor(
            panel.text_mask_downsample_rpdesc
        )
        if not panel.text_mask_downsample_target.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel text mask downsample target"
            )
        panel.srb_text_mask_downsample = rhi.newShaderResourceBindings()
        panel.srb_text_mask_downsample.setBindings(
            [
                QRhiShaderResourceBinding.sampledTexture(
                    0, fragment, panel.text_mask_tex, self._sampler
                ),
            ]
        )
        if not panel.srb_text_mask_downsample.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel text mask downsample SRB"
            )
        panel.text_mask_downsample_pipeline = rhi.newGraphicsPipeline()
        panel.text_mask_downsample_pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("glass_panel_pass.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    _load_shader("glass_text_downsample.frag.qsb"),
                ),
            ]
        )
        panel.text_mask_downsample_pipeline.setTopology(
            QRhiGraphicsPipeline.Topology.Triangles
        )
        panel.text_mask_downsample_pipeline.setRenderPassDescriptor(
            panel.text_mask_downsample_rpdesc
        )
        panel.text_mask_downsample_pipeline.setShaderResourceBindings(
            panel.srb_text_mask_downsample
        )
        if not panel.text_mask_downsample_pipeline.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel text mask downsample pipeline"
            )

        panel.srb_composite = rhi.newShaderResourceBindings()
        panel.srb_composite.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, fragment, panel.composite_ubuf),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, panel.blur_tex, self._sampler
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    2, fragment, panel.text_mask_downsampled_tex, self._sampler
                ),
            ]
        )
        if not panel.srb_composite.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel composite SRB"
            )
        panel.composite_pipeline = rhi.newGraphicsPipeline()
        panel.composite_pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("glass_panel_pass.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, _load_shader("glass_composite.frag.qsb")
                ),
            ]
        )
        panel.composite_pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
        panel.composite_pipeline.setRenderPassDescriptor(panel.composite_rpdesc)
        panel.composite_pipeline.setShaderResourceBindings(panel.srb_composite)
        # Disabled blend (default TargetBlend()): this pass writes into its
        # own fresh, transparently-cleared scratch texture -- a plain
        # overwrite of fragColor, not a blend against existing content.
        if not panel.composite_pipeline.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} glass-panel composite pipeline"
            )

        panel.size = (size.width(), size.height())
        _debug(
            "_ensure_panel key=%#x DONE panel_id=%#x crop_tex=%#x blur_tex=%#x "
            "composite_tex=%#x srb_blur=%#x srb_composite=%#x",
            key,
            id(panel),
            id(panel.crop_tex),
            id(panel.blur_tex),
            id(panel.composite_tex),
            id(panel.srb_blur),
            id(panel.srb_composite),
        )
        return panel

    def render_backdrops(
        self,
        command_buffer,
        color_texture,
        specs_by_key: dict[int, GlassPanelSpec],
    ) -> None:
        assert self._sampler is not None
        """Regenerates every registered panel's backdrop sprite from
        ``color_texture`` (the canvas's own ``colorTexture()`` for the
        *current* frame -- see module docstring's "Timing" section). Called
        after the caller's own main ``endPass``, so ``color_texture`` already
        holds this frame's fully-drawn scene.

        Every live panel's composite_tex readback issued this call is
        collected synchronously before returning (see the single
        ``rhi.finish()`` below) -- ``ready_images`` reflects this exact
        frame's composite by the time this call returns, no next-call
        polling involved."""
        self._debug_render_backdrops_call_count += 1
        if _DEBUG_DUMP_DIR:
            self._flush_debug_dumps()
        stale = set(self._panels) - set(specs_by_key)
        for key in stale:
            self.ready_images.pop(key, None)
            self._panels.pop(key).release()
            self.ready_sprites.pop(key, None)
        if not specs_by_key:
            return
        rhi = self.rhi
        assert rhi is not None

        # Every live panel's own device-px rect: crop copies from
        # colorTexture() at this rect, and sizes *our own* scratch textures
        # to match (this app fully controls their resolution, so this is
        # unaffected by whatever colorTexture()'s real pixel size turns out
        # to be).
        device_rects: dict[int, tuple[QPoint, QSize]] = {}
        for key, spec in specs_by_key.items():
            rect = spec.rect_logical
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            dpr = max(1.0, float(spec.dpr))
            device_rects[key] = (
                QPoint(round(rect.x() * dpr), round(rect.y() * dpr)),
                QSize(max(1, round(rect.width() * dpr)), max(1, round(rect.height() * dpr))),
            )

        should_dump = False
        if _DEBUG_DUMP_DIR:
            should_dump = self._debug_dump_frame % _DEBUG_DUMP_EVERY_N_FRAMES == 0
            self._debug_dump_frame += 1
            if should_dump:
                self._request_dump(
                    rhi,
                    command_buffer,
                    color_texture,
                    "canvas_colorTexture",
                    annotate_rects=[
                        (top_left.x(), top_left.y(), size.width(), size.height())
                        for top_left, size in device_rects.values()
                    ],
                )

        if _GLASS_PANEL_DEBUG:
            _debug(
                "render_backdrops frame: live_keys=%s",
                [f"{k:#x}" for k in specs_by_key],
            )
            for key, spec in specs_by_key.items():
                top_left, size = device_rects.get(key, (None, None))
                _debug(
                    "  key=%#x rect_logical=%s dpr=%.3f device_top_left=%s "
                    "device_size=%s corner_radius_px=%.2f border_width_px=%.2f "
                    "tint_alpha=%.3f blur_radius_px=%.2f",
                    key,
                    spec.rect_logical,
                    spec.dpr,
                    top_left,
                    size,
                    spec.corner_radius_px,
                    spec.border_width_px,
                    spec.tint.alphaF(),
                    spec.blur_radius_px,
                )

        # (result, dpr) per key, collected synchronously right after this
        # loop via one `rhi.finish()` -- local to this call, not carried
        # across frames (see render_backdrops's docstring).
        pending_readbacks: dict[int, tuple[QRhiReadbackResult, float]] = {}
        for key, spec in specs_by_key.items():
            if key not in device_rects:
                self.ready_sprites.pop(key, None)
                continue
            rect = spec.rect_logical
            dpr = max(1.0, float(spec.dpr))
            device_top_left, device_size = device_rects[key]
            panel = self._ensure_panel(key, device_size)

            # No Y-flip here: an earlier version of this code flipped
            # sourceTopLeft on the theory that colorTexture()'s row order is
            # backend-native (bottom-up on OpenGL) -- that conclusion was
            # built on a debug-dump tool that (see _flush_debug_dumps) was
            # itself silently mirroring its "ground truth" canvas reference
            # image, invalidating the crop-vs-canvas comparisons that
            # conclusion rested on. Confirmed live that the raw readback
            # (canvas and crop alike) already comes out top-down. Don't
            # reintroduce a flip here without re-confirming against a
            # non-mirrored reference first.
            copy_updates = rhi.nextResourceUpdateBatch()
            copy_desc = QRhiTextureCopyDescription()
            copy_desc.setSourceTopLeft(device_top_left)
            copy_desc.setPixelSize(device_size)
            assert panel.crop_tex is not None
            copy_updates.copyTexture(panel.crop_tex, color_texture, copy_desc)
            command_buffer.resourceUpdate(copy_updates)
            if should_dump:
                self._request_dump(rhi, command_buffer, panel.crop_tex, f"key{key:x}_1crop")

            blur_updates = rhi.nextResourceUpdateBatch()
            assert panel.blur_ubuf is not None
            blur_updates.updateDynamicBuffer(
                panel.blur_ubuf,
                0,
                struct.pack("<4f", 1.0, 0.0, spec.blur_radius_px, 0.0),
            )
            command_buffer.beginPass(
                panel.blur_target,
                QColor(0, 0, 0, 0),
                QRhiDepthStencilClearValue(1.0, 0),
                blur_updates,
            )
            command_buffer.setGraphicsPipeline(panel.blur_pipeline)
            command_buffer.setViewport(
                QRhiViewport(0.0, 0.0, float(device_size.width()), float(device_size.height()))
            )
            command_buffer.setShaderResources(panel.srb_blur)
            command_buffer.draw(3)
            command_buffer.endPass()
            if should_dump:
                self._request_dump(rhi, command_buffer, panel.blur_tex, f"key{key:x}_2blur")

            # Text mask upload -- only when the image identity actually
            # changed since last frame (glass_hud/text_mask.py rebuilds it at most a
            # few times/sec, not every frame; see text_mask_image_id's
            # docstring on _PanelGpu for why a freshly-(re)created texture
            # always uploads at least once even with no spec image). The
            # no-mask case uses the sentinel id 0 (never a real object's
            # id() in CPython) rather than building + re-uploading a fresh
            # blank QImage every single frame for panels with no registered
            # text. text_mask_tex is _TEXT_MASK_SUPERSAMPLE x device_size
            # (see _ensure_panel) -- the blank fallback and the size-mismatch
            # guard both target that same oversized size, not device_size.
            text_mask_size = QSize(
                device_size.width() * _TEXT_MASK_SUPERSAMPLE,
                device_size.height() * _TEXT_MASK_SUPERSAMPLE,
            )
            mask_target_id = 0 if spec.text_mask_image is None else id(spec.text_mask_image)
            if panel.text_mask_image_id != mask_target_id:
                if spec.text_mask_image is None:
                    mask_image = QImage(
                        text_mask_size, QImage.Format.Format_RGBA8888_Premultiplied
                    )
                    mask_image.fill(0)
                elif spec.text_mask_image.size() != text_mask_size:
                    # Defensive only -- glass_hud/text_mask.py's _rebuild_text_mask()
                    # and this method compute device_size from the same
                    # container.size()/devicePixelRatioF() formula, so this
                    # should be rare (a resize landing between the mask's
                    # own rebuild and this frame's render_backdrops() call).
                    # `.scaled()` with NO explicit TransformationMode
                    # defaults to FastTransformation (nearest-neighbor) --
                    # confirmed live as the source of a text mask reading
                    # as "интерлейсинг" (interlaced-looking noise) on any
                    # frame this branch fired: nearest-neighbor resampling
                    # a thin-stroke text mask produces exactly that kind of
                    # aliased garbage. Match the real rebuild path's own
                    # quality intent explicitly instead of relying on Qt's
                    # low-quality default.
                    _debug(
                        "text mask SIZE MISMATCH key=%#x image_size=%s "
                        "expected=%s -- falling back to a resample this "
                        "frame",
                        key,
                        spec.text_mask_image.size(),
                        text_mask_size,
                    )
                    mask_image = spec.text_mask_image.scaled(
                        text_mask_size,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                else:
                    mask_image = spec.text_mask_image
                mask_updates = rhi.nextResourceUpdateBatch()
                assert panel.text_mask_tex is not None
                mask_updates.uploadTexture(panel.text_mask_tex, mask_image)
                command_buffer.resourceUpdate(mask_updates)
                panel.text_mask_image_id = mask_target_id

                # Lanczos-2 downsample: text_mask_tex (supersampled) ->
                # text_mask_downsampled_tex (device res) -- see
                # _ensure_panel and glass_text_downsample.frag. Only run
                # when the mask content just changed, same gate as the
                # upload above.
                command_buffer.beginPass(
                    panel.text_mask_downsample_target,
                    QColor(0, 0, 0, 0),
                    QRhiDepthStencilClearValue(1.0, 0),
                )
                command_buffer.setGraphicsPipeline(panel.text_mask_downsample_pipeline)
                command_buffer.setViewport(
                    QRhiViewport(
                        0.0, 0.0, float(device_size.width()), float(device_size.height())
                    )
                )
                command_buffer.setShaderResources(panel.srb_text_mask_downsample)
                command_buffer.draw(3)
                command_buffer.endPass()

            t = spec.tint
            b = spec.border_color
            debug_tint = self._debug_tint_for(key)
            composite_updates = rhi.nextResourceUpdateBatch()
            assert panel.composite_ubuf is not None
            composite_updates.updateDynamicBuffer(
                panel.composite_ubuf,
                0,
                struct.pack(
                    "<20f",
                    0.0,
                    1.0,
                    spec.blur_radius_px,
                    spec.corner_radius_px,
                    t.redF(),
                    t.greenF(),
                    t.blueF(),
                    t.alphaF(),
                    float(device_size.width()),
                    float(device_size.height()),
                    spec.border_width_px,
                    0.0,
                    b.redF(),
                    b.greenF(),
                    b.blueF(),
                    b.alphaF(),
                    *debug_tint,
                ),
            )
            _debug(
                "  composite key=%#x panel_id=%#x composite_tex=%#x "
                "panelSizePx=(%.0f,%.0f) cornerRadiusPx=%.2f borderWidthPx=%.2f "
                "srb_composite=%#x srb_blur=%#x",
                key,
                id(panel),
                id(panel.composite_tex),
                float(device_size.width()),
                float(device_size.height()),
                spec.corner_radius_px,
                spec.border_width_px,
                id(panel.srb_composite),
                id(panel.srb_blur),
            )
            command_buffer.beginPass(
                panel.composite_target,
                QColor(0, 0, 0, 0),
                QRhiDepthStencilClearValue(1.0, 0),
                composite_updates,
            )
            command_buffer.setGraphicsPipeline(panel.composite_pipeline)
            command_buffer.setViewport(
                QRhiViewport(0.0, 0.0, float(device_size.width()), float(device_size.height()))
            )
            command_buffer.setShaderResources(panel.srb_composite)
            command_buffer.draw(3)
            command_buffer.endPass()
            if should_dump:
                self._request_dump(
                    rhi, command_buffer, panel.composite_tex, f"key{key:x}_3composite"
                )

            # CPU-side copy for the QPainter display path -- see
            # ready_images's docstring. Collected synchronously right after
            # this loop (one rhi.finish() for all panels, not one per panel)
            # instead of polled on next call -- see render_backdrops's
            # docstring and pending_readbacks above.
            image_result = QRhiReadbackResult()
            image_updates = rhi.nextResourceUpdateBatch()
            assert panel.composite_tex is not None
            image_updates.readBackTexture(
                QRhiReadbackDescription(panel.composite_tex), image_result
            )
            command_buffer.resourceUpdate(image_updates)
            pending_readbacks[key] = (image_result, dpr)

            self.ready_sprites[key] = (panel.composite_tex, rect)
            _debug(
                "  ready_sprites[%#x] = (composite_tex=%#x, rect=%s)",
                key,
                id(panel.composite_tex),
                rect,
            )

        if not pending_readbacks:
            return

        # One full GPU sync for every panel's readback issued above, then
        # collect all of them immediately -- confirmed via
        # IMGSLI_GLASS_PANEL_SYNC_PROBE (799/799 sampled calls: data always
        # ready right after finish(), cost ~0.1-1.7ms) that this is cheap
        # enough to do unconditionally rather than polling .data on next
        # call, which is what previously left ready_images exactly one
        # render_backdrops() call stale (see
        # docs/dev/rendering/glass-panel-text-vibrancy-plan.md Phase 3).
        t_finish_start = time.perf_counter() if _GLASS_PANEL_DEBUG else 0.0
        rhi.finish()
        finish_ms = (time.perf_counter() - t_finish_start) * 1000.0 if _GLASS_PANEL_DEBUG else 0.0

        for key, (image_result, dpr) in pending_readbacks.items():
            data = image_result.data
            if not data:
                # Should not happen post-finish(), but ready_images simply
                # keeps last frame's image one extra call if it ever does.
                continue
            t_start = time.perf_counter() if _GLASS_PANEL_DEBUG else 0.0
            size = image_result.pixelSize
            image = QImage(
                bytes(data),  # type: ignore[call-overload]  # QByteArray supports buffer protocol
                size.width(),
                size.height(),
                QImage.Format.Format_RGBA8888_Premultiplied,
            ).copy()
            image.setDevicePixelRatio(dpr)
            self.ready_images[key] = image
            if _GLASS_PANEL_DEBUG:
                _debug(
                    "readback collected key=%#x rhi.finish()=%.3fms construct=%.3fms "
                    "size=%dx%d",
                    key,
                    finish_ms,
                    (time.perf_counter() - t_start) * 1000.0,
                    size.width(),
                    size.height(),
                )
