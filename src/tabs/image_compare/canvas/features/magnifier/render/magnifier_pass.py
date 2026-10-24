"""The magnifier's own QRhi render pass: disk border + GPU-sampled content.

Split out of ``passes.py`` — this is the one pass in the magnifier feature
that is not further decomposed: it is a single QRhi pipeline (uber ``mag``
shader) plus its border-disk companion pipeline, and the two are only
separable in the sense that they're two draw loops sharing one pass's
resource lifecycle. Splitting the border/content halves into separate
``CanvasRenderPass`` classes would not reduce complexity, only relocate it
behind an extra resource-lifecycle indirection.

File-Size-Exempt: single QRhi pass, one resource lifecycle (border-disk
pipeline + uber mag pipeline); splitting the class would relocate, not
reduce, complexity — see module docstring above.

GPU sampling (``magGpuSampling=1``) reads the same shared tile-array
texture (``ArrayResources.tile_arrays[0]``) the main canvas's
``base_array.frag`` uses -- per-item array ``layer``/content-scale are
resolved via ``TileTextureService`` (see ``_source_slices``) and packed
into the uniform block alongside ``uvRect1``/``uvRect2``. Legacy
raster-overlay entry points remain on ``CanvasWidget`` for compatibility,
but the active magnifier runtime does not use them.

F4-BOUNDARY (PERMANENT BOUNDARY verdict, scale-free-overlays F4): the
content path below STAYS in this file and is never mounted onto
``engine.overlay.OverlayShell`` / ``TexturedOverlayShell``. Proof:

(1) LINES THAT STAY (array-shape GPU sites, each marked F4-BOUNDARY):
``prepare`` array-consume (``array_resources.tile_arrays[0]`` held, not
owned, with ``placeholder_texture_array`` fallback);
``_ensure_mag_uniform_capacity`` strided dynamic-offset uniform buffer
(``rhi.ubufAligned(MAG_UNIFORM_SIZE)``, one long-lived buffer, per-item
slots); ``_build_mag_srb`` single SRB with
``uniformBufferWithDynamicOffset`` + externally-owned ``sampler2DArray``
binding; ``prepare`` per-frame SRB rebuild on backing-array replace;
``initialize`` dual-pipeline lifecycle (``border`` shell + ``mag``
pipeline); ``record`` dynamic-offset draw loop
(``setShaderResources(self.mag_srb, 1, (0, index * stride))``).

(2) UNIQUENESS: no existing engine shell hosts this conjunction --
externally-owned ``sampler2DArray`` (array_resources owns, this pass
holds) + strided dynamic-offset uniforms (``OverlayShell`` is one
uniform buffer + one SRB per item, no textures, no dynamic offsets) +
per-frame SRB rebuild on backing-array replace (``TexturedOverlayShell``
rebuilds only on its own texture resize, never on an external array
replace) + dual pipelines (border_disk + mag) under one resource
lifecycle. ``SemanticOverlayItems``/``pack_arcs`` (F2) covers only the
arc/border decoration path, never array-sampled content.

(3) INVALIDATION: if content ever drops array sampling, this boundary
dissolves -- single raster upload migrates to ``TexturedOverlayShell``,
pure decoration (no texture at all) migrates to ``OverlayShell`` +
``semantic.py`` pack. Until then, the boundary this file documents is pinned
by pixel assertions over a per-tile-colour fixture (which record/layer/uv
lands at a given lens pixel, and the shader's content-extent tap clamp) in
``src/tabs/image_compare/tests/render/test_magnifier_content_boundary.py``.

Record path + hold gates untouched (ruling 4: math moves, gating stays).
The module-level frame/residency helpers (``_lens_union_uv``,
``_low_res_fallback_slice``, ``_lens_residency_hold``,
``_frame_draw_tile_indices``, ``_frame_slices_residency_hold``,
``_source_slices``) now live in the sibling ``tile_residency_gate.py`` and are
re-exported below; no tab-side scale definition -- their
``from engine.cache.draw_plans import content_scale_for`` call is the only
scale math, engine-owned.
"""

from __future__ import annotations

import logging
import struct
import time

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QRhi,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiSampler,
    QRhiShaderResourceBindings,
    QRhiShaderResourceBinding,
    QRhiTexture,
    QRhiViewport,
)

from tabs.image_compare.canvas.features.magnifier.render.tile_capture import (
    build_tile_records,
    is_full_tc,
    tc_rect_to_widget_px,
)
# Part D: the tile-residency/fallback helpers moved to ``tile_residency_gate``;
# re-exported here so every historic importer/test name resolves unchanged.
from tabs.image_compare.canvas.features.magnifier.render.tile_residency_gate import (
    _frame_draw_tile_indices,
    _frame_slices_residency_hold,
    _lens_residency_hold,
    _lens_union_uv,
    _low_res_fallback_slice,
    _source_slices,
)
from tabs.image_compare.canvas.rhi_feature_common import (
    FULLSCREEN_VERTICES,
    FullscreenUniformPassResources,
    build_fullscreen_quad_pipeline,
    resolve_rhi_scissor,
)
from engine.gpu.rt_y_orientation import composited_clip_correction
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.canvas_infra.rhi.render_common import (
    ndc_rect_from_screen_disk,
    widget_px_to_screen_px,
)

from tabs.image_compare.canvas.features.magnifier.render.passes_common import ensure_qcolor, pack_border_disk_uniform
from tabs.image_compare.canvas.features.magnifier.render.shader_layout import BORDER_DISK_UNIFORM_SIZE, MAG_UNIFORM_SIZE, SHADER_DIR
from tabs.image_compare.canvas.loupe_trace import (
    frame_context_from_widget,
    trace_loupe,
)
from tabs.image_compare.debug import ic_loupe_debug_enabled
from engine.cache.uniform_layout import assert_uniform_size

_MAG_UNIFORM_FMT = (
    "<16f 4f 2f 2f f f f f 4f 4f f f i i i i i i i i i i i i i i 4f 4f 4f 4f 4f"
)
assert_uniform_size(_MAG_UNIFORM_FMT, MAG_UNIFORM_SIZE, label="MagnifierPass uniform")

_log = logging.getLogger("ImproveImgSLI.magnifier.pass")

#: H3 loupe-debug: steady-state heartbeat cadence while the lens is active
#: (``loupe.mag_heartbeat``). One line per second max -- quiet frames read
#: as held/resident counts, not maybe-suppressed throttle silence.
_LOUPE_HEARTBEAT_INTERVAL_S = 1.0


def _comb_divider_thickness_uv(
    params, content_radius: float, fallback: float = 0.005
) -> float:
    if not params:
        return 0.0
    dpx = float(params.get("divider_thickness_px", 0.0) or 0.0)
    if dpx <= 0.0:
        return float(params.get("divider_thickness_uv", 0.0) or 0.0)
    diam = max(1.0, content_radius * 2.0)
    return (dpx / diam) * 0.5 if diam > 0.0 else fallback


class MagnifierPass(CanvasRenderPass):
    """Renders magnifier disks: slot frame (border) + circle content.

    The active magnifier path samples canvas textures on the GPU.
    """

    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.rhi: QRhi | None = None
        self.border = FullscreenUniformPassResources(BORDER_DISK_UNIFORM_SIZE)
        self._border_items: list[bytes] = []
        self.mag_vertex_buffer: QRhiBuffer | None = None
        self.mag_uniform_buffer: QRhiBuffer | None = None
        self.mag_uniform_stride = 0
        self.mag_uniform_capacity = 0
        self.mag_srb: QRhiShaderResourceBindings | None = None
        self.mag_pipeline: QRhiGraphicsPipeline | None = None
        self.sampler_linear: QRhiSampler | None = None
        self.sampler_nearest: QRhiSampler | None = None
        self.placeholder_texture: QRhiTexture | None = None
        self.placeholder_texture_array: QRhiTexture | None = None
        self._mag_items: list[dict] = []
        self._target = None
        self._prepare_call_seq = 0
        # P1B explicit-state verdict: sig-throttle for the gpu_sampling=0
        # fallback log below (per-frame path — same recipe as
        # ``rhi_renderer/use_cases/fallback.py``'s ``_last_is_same_sig``:
        # emit once per distinct decision signature, not once per frame).
        self._last_no_slot_sig: tuple | None = None
        # H3 loupe-debug (trace-only): hold->swap timing + heartbeat gate.
        # Never read by any draw branch -- emission scaffolding only, so
        # behavior is identical whether the loupe flag is on or off.
        self._loupe_was_holding = False
        self._loupe_hold_start_seq: int | None = None
        self._loupe_hold_start_t: float | None = None
        self._loupe_hb_last_t = 0.0

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi
        self._target = target
        # F4-BOUNDARY (dual pipelines): border-disk companion pipeline plus
        # the uber mag pipeline share this pass's resource lifecycle --
        # never split into two CanvasRenderPass classes (see module
        # docstring); only the arc/border decoration half is F2-migrated.
        self.border.initialize(rhi, target, SHADER_DIR, "border_disk")

        self.mag_vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.mag_vertex_buffer.create():
            raise RuntimeError("Failed to create magnifier vertex buffer")

        self.sampler_linear = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        self.sampler_linear.create()
        self.sampler_nearest = rhi.newSampler(
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        self.sampler_nearest.create()

        self.placeholder_texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        self.placeholder_texture.create()
        self.placeholder_texture_array = rhi.newTextureArray(
            QRhiTexture.Format.RGBA8, 1, QSize(1, 1)
        )
        self.placeholder_texture_array.create()

        self.mag_pipeline = build_fullscreen_quad_pipeline(
            rhi, target, SHADER_DIR, "mag"
        )

        self._ensure_mag_uniform_capacity(1)
        first_srb = self._build_mag_srb(self.placeholder_texture_array)
        self.mag_srb = first_srb
        self.mag_pipeline.setShaderResourceBindings(first_srb)
        if not self.mag_pipeline.create():
            raise RuntimeError("Failed to create magnifier QRhi pipeline")

    def _ensure_mag_uniform_capacity(self, slot_count: int) -> None:
        """Growable, multi-slot uniform buffer -- one slot per tile-record
        draw needed this frame, strided via ``rhi.ubufAligned`` so each draw
        selects its own slot with a dynamic offset instead of each new tile
        count creating a brand-new ``Dynamic`` buffer object. A per-record
        buffer object that's freshly created and written only once, then
        immediately bound and drawn the same frame, is exactly the shape of
        bug this project already hit twice for mip generation (see
        ``engine.gpu.mip_cascade._ensure_downsample_uniform_buffer``
        and docs/dev/rendering/investigations/multitile-uniform-desync.md):
        a `Dynamic` buffer's multi-frame-in-flight rotation isn't guaranteed
        warmed up on its very first write for every QRhi backend. Growing
        one long-lived buffer and writing every slot pre-pass (never
        recreating it just because the record count went up) sidesteps
        that regardless of whether it's the actual cause here."""
        # F4-BOUNDARY (strided buffer): one long-lived buffer, per-item
        # slots via ubufAligned stride + dynamic offsets -- no engine shell
        # hosts this shape (OverlayShell is one buffer + one SRB per item).
        rhi = self.rhi
        assert rhi is not None
        stride = rhi.ubufAligned(MAG_UNIFORM_SIZE)
        self.mag_uniform_stride = stride
        slot_count = max(1, slot_count)
        if (
            self.mag_uniform_buffer is not None
            and slot_count <= self.mag_uniform_capacity
        ):
            return
        new_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            stride * slot_count,
        )
        if not new_buffer.create():
            raise RuntimeError("Failed to create magnifier uniform buffer")
        old_buffer = self.mag_uniform_buffer
        self.mag_uniform_buffer = new_buffer
        self.mag_uniform_capacity = slot_count
        if self.mag_srb is not None:
            try:
                self.mag_srb.destroy()
            except RuntimeError:
                pass
            self.mag_srb = None
        if old_buffer is not None:
            try:
                old_buffer.destroy()
            except RuntimeError:
                pass

    def _build_mag_srb(self, bg_array):
        # F4-BOUNDARY (dynamic-offset SRB): binding 0 is a strided uniform
        # buffer with dynamic offset; binding 1 is the EXTERNALLY-OWNED
        # sampler2DArray (array_resources.tile_arrays[0], held not owned --
        # mag.frag ``layout(binding = 1) uniform sampler2DArray bgArray``).
        # TexturedOverlayShell binds its OWN single raster texture with a
        # plain uniformBuffer -- this conjunction lives only here.
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        bindings = [
            QRhiShaderResourceBinding.uniformBufferWithDynamicOffset(
                0, stages, self.mag_uniform_buffer, MAG_UNIFORM_SIZE
            )
        ]
        bindings.extend(
            [
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, bg_array, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    4, fragment, self.placeholder_texture, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    5, fragment, self.placeholder_texture, self.sampler_linear
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    6, fragment, self.placeholder_texture, self.sampler_linear
                ),
            ]
        )
        srb.setBindings(bindings)
        if not srb.create():
            raise RuntimeError("Failed to create magnifier SRB")
        return srb

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None or not bool(getattr(overlay, "render_enabled", False)):
            return False
        return bool(getattr(overlay, "quads", ()))

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._border_items = []
        self._mag_items = []
        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None:
            return
        self._prepare_call_seq += 1
        prepare_call_seq = self._prepare_call_seq
        assert self.rhi is not None
        matrix = composited_clip_correction(self.rhi)
        w, h = float(ctx.width), float(ctx.height)
        zoom = float(ctx.zoom_level or 1.0)
        pan_x = float(ctx.pan_offset_x or 0.0)
        pan_y = float(ctx.pan_offset_y or 0.0)
        if tile_dump_enabled():
            log_tile_event(
                "magnifier.prepare_call",
                prepare_call_seq=prepare_call_seq,
                zoom=zoom,
                pan_x=pan_x,
                pan_y=pan_y,
            )

        rhi_renderer = getattr(widget, "_rhi_renderer", None)
        # P3: live FrameContext read through the widget -- no renderer
        # rewiring (see loupe_trace.frame_context_from_widget). None for
        # fakes/tests without a renderer: records stay silent, rendering
        # behavior identical.
        frame_context = frame_context_from_widget(widget)
        # H3 loupe-debug (trace-only): per-frame diagnostic horizon. One
        # live length snapshot so the end-of-prepare swap/heartbeat lines
        # can count this frame's own drops/fallbacks/holds without keeping
        # counters on the hot draw path. Flag off -> the end block is
        # skipped and this is one env check + one len(); steady production
        # pays nothing else.
        _loupe_diag = frame_context is not None and ic_loupe_debug_enabled()
        _loupe_n0 = len(frame_context) if _loupe_diag else 0
        array_resources = getattr(rhi_renderer.resources, "array_resources", None) if rhi_renderer else None
        # F4-BOUNDARY (array consume): the shared tile-array texture is HELD
        # (array_resources owns it), never created here -- the 1x1
        # placeholder array below is the no-renderer fallback only. A shell
        # migration must preserve held-not-owned array sampling.
        if array_resources is not None:
            array_resources._ensure_tile_array(0)
            bg_array = array_resources.tile_arrays[0]
        else:
            bg_array = self.placeholder_texture_array
        use_source = bool(
            overlay.gpu_active
            and ctx.shader_letterbox_mode
            and ctx.source_images_ready
            and ctx.source_texture_ids[0]
            and ctx.source_texture_ids[1]
        )
        # H3 loupe-debug (trace-only): hold tracking for the swap summary.
        # ``_loupe_preconditions`` is the pre-gate value: when the lens is
        # not even attempting source, any tracked hold start is stale (lens
        # off) and is cleared -- trace state only, never read by draws.
        _loupe_preconditions = use_source
        if not _loupe_preconditions:
            self._loupe_was_holding = False
            self._loupe_hold_start_seq = None
            self._loupe_hold_start_t = None
        # Loupe residency gate: HOLD stored until the lens may sample source
        # tiles -- first ``request_level`` on the lens interest rect for both
        # sources (registers the interest rect that prioritizes uploads),
        # then the frame's own draw slices (every ``(key, tile_index)`` the
        # frame below would sample, including the diff key in diff-lens
        # modes the level gate never covered). The flip is one atomic swap
        # instead of a progressive tile-by-tile fill (the 24-of-30-missing
        # first-frame holes): release implies every drawn slice is
        # GPU-resident, so ``mag_dropped_slice`` is unreachable on the swap
        # frame. A held frame samples stored (already resident under the
        # main canvas) and needs no fallback.
        _fallback_by_source: dict = {}
        # H3 loupe-debug (trace-only): slice counts for the swap/heartbeat
        # lines (filled by the slice gate below) + the swap arming flag.
        # The gate runs only when the lens attempts source, so an empty
        # stats dict at the end means the lens never got that far.
        _loupe_slice_stats: dict = {}
        _loupe_swap_armed = False
        _diff_key_for_hold = (
            ctx.diff_source_texture_id
            if ctx.diff_source_ready and ctx.diff_source_texture_id
            else "placeholder"
        )
        if use_source:
            _hold_reason = _lens_residency_hold(
                rhi_renderer,
                (ctx.source_texture_ids[0], ctx.source_texture_ids[1]),
                overlay,
                frame_context,
            )
            if _hold_reason is None:
                _hold_reason = _frame_slices_residency_hold(
                    rhi_renderer,
                    _frame_draw_tile_indices(
                        rhi_renderer,
                        overlay,
                        ctx.source_texture_ids[0],
                        ctx.source_texture_ids[1],
                        _diff_key_for_hold,
                    ),
                    frame_context,
                    _loupe_slice_stats,
                )
            if _hold_reason is not None:
                use_source = False
                if not self._loupe_was_holding:
                    self._loupe_was_holding = True
                    self._loupe_hold_start_seq = prepare_call_seq
                    self._loupe_hold_start_t = time.monotonic()
            else:
                if self._loupe_was_holding:
                    # Hold -> release transition: the atomic swap frame. The
                    # drop/fallback counts are only known after the quad
                    # loop below, so arm the end-of-prepare summary here
                    # and consume the transition now.
                    _loupe_swap_armed = True
                    self._loupe_was_holding = False
                _fallback_by_source = {
                    ctx.source_texture_ids[0]: ctx.texture_ids[0],
                    ctx.source_texture_ids[1]: ctx.texture_ids[1],
                }
        tex_key_1 = ctx.source_texture_ids[0] if use_source else ctx.texture_ids[0]
        tex_key_2 = ctx.source_texture_ids[1] if use_source else ctx.texture_ids[1]
        diff_key = _diff_key_for_hold
        # P3: the texture choice (base vs source images, diff source) was a
        # silent branch -- record which keys this frame samples (sig-throttled,
        # so steady frames stay quiet while any flip gets its reason).
        trace_loupe(
            frame_context,
            "loupe.mag_texture_choice",
            "ran",
            f"texture_choice use_source={use_source} gpu_active={bool(overlay.gpu_active)}"
            f" keys={tex_key_1!r}/{tex_key_2!r} diff={diff_key!r}",
            ids=(str(tex_key_1), str(tex_key_2), str(diff_key)),
            sig=(bool(use_source), str(tex_key_1), str(tex_key_2), str(diff_key)),
        )

        _no_slot_quad_indexes: list[int] = []
        for i, quad in enumerate(overlay.quads):
            if not quad:
                continue
            x0, y0, x1, y1, cx_px, cy_px, r_px = quad
            # Border and content must share one screen position. Border has
            # always projected cx_px/cy_px through widget_px_to_screen_px
            # (the same zoom-around-center + pan formula the base image
            # uses); content built its NDC quad from raw cx_px/cy_px
            # instead, so it never tracked live zoom/pan the way the border
            # ring around it did -- the two drifted apart from each other on
            # any zoom or pan, worse the more either changed. Project once,
            # use for both.
            bcx, bcy = widget_px_to_screen_px(widget, float(cx_px), float(cy_px))
            gpu_slot = (
                overlay.gpu_slots[i]
                if overlay.gpu_active and i < len(overlay.gpu_slots)
                else None
            )
            combined = bool(gpu_slot.get("is_combined", False)) if gpu_slot else False

            slot_border_width = (
                float(gpu_slot.get("border_width", overlay.border_width))
                if gpu_slot
                else float(overlay.border_width)
            )
            border_width = max(0.0, slot_border_width)
            content_radius = max(1.0, r_px - border_width + 1.0)

            if border_width > 0.0:
                slot_border_color = (
                    gpu_slot.get("border_color", overlay.border_color)
                    if gpu_slot
                    else overlay.border_color
                )
                self._border_items.append(
                    pack_border_disk_uniform(
                        matrix,
                        w,
                        h,
                        float(bcx),
                        float(bcy),
                        float(r_px) * zoom,
                        float(border_width) * zoom,
                        ensure_qcolor(slot_border_color),
                    )
                )
                if tile_dump_enabled():
                    log_tile_event(
                        "magnifier.border_record",
                        prepare_call_seq=prepare_call_seq,
                        quad_index=i,
                        cx_px=float(cx_px),
                        cy_px=float(cy_px),
                        bcx=float(bcx),
                        bcy=float(bcy),
                        r_px=float(r_px),
                        zoom=zoom,
                        pan_x=pan_x,
                        pan_y=pan_y,
                        border_radius_px=float(r_px) * zoom,
                    )

            if gpu_slot:
                gpu_sampling = 1
                source_mode = int(gpu_slot.get("source", 0) or 0)
                interp_mode = (
                    int(getattr(overlay, "gpu_interp_mode", 1))
                    if getattr(overlay, "gpu_interp_mode", None) is not None
                    else 1
                )
                channel_mode = int(getattr(overlay, "gpu_channel_mode", 0) or 0)
                diff_mode = (
                    int(getattr(overlay, "gpu_diff_mode", 0) or 0)
                    if source_mode == 2 and not combined
                    else 0
                )
                uv_rect1 = gpu_slot.get("uv_rect", (0.0, 0.0, 1.0, 1.0))
                uv_rect2 = gpu_slot.get("uv_rect2", uv_rect1)
            else:
                # P1B explicit state (NOT dead — reachable in production):
                # any raster quad without matching gpu params lands here,
                # e.g. presenters/image_canvas/view.py set_pil_layers /
                # set_layers -> texture_parts/layers.set_feature_overlay_content
                # sets overlay._quads[0] with gpu_active False, and this pass
                # still paints it via the mag.frag magTex/magTex2 path below.
                gpu_sampling = 0
                source_mode = 0
                interp_mode = 1
                channel_mode = 0
                diff_mode = 0
                uv_rect1 = (0.0, 0.0, 1.0, 1.0)
                uv_rect2 = (0.0, 0.0, 1.0, 1.0)
                _no_slot_quad_indexes.append(i)

            if gpu_slot and combined:
                internal_split = float(gpu_slot.get("internal_split", 0.5))
                comb_horizontal = int(gpu_slot.get("horizontal", False))
                show_comb_divider = int(gpu_slot.get("divider_visible", True))
                comb_div_color = gpu_slot.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                comb_div_thickness = _comb_divider_thickness_uv(
                    gpu_slot, content_radius
                )
            else:
                internal_split = 0.5
                comb_horizontal = 0
                show_comb_divider = 0
                comb_div_color = (1.0, 1.0, 1.0, 0.9)
                comb_div_thickness = 0.0

            content_x0, content_y0, content_x1, content_y1 = ndc_rect_from_screen_disk(
                bcx, bcy, content_radius, w, h
            )

            if gpu_slot:
                records = build_tile_records(
                    source_slices_fn=lambda key, rect: _source_slices(
                        rhi_renderer,
                        key,
                        rect,
                        frame_context,
                        fallback_key=_fallback_by_source.get(key),
                    ),
                    combined=combined,
                    source_mode=source_mode,
                    diff_mode=diff_mode,
                    uv_rect1=uv_rect1,
                    uv_rect2=uv_rect2,
                    tex_key_1=tex_key_1,
                    tex_key_2=tex_key_2,
                    diff_key=diff_key,
                    internal_split=internal_split,
                    comb_horizontal=bool(comb_horizontal),
                )
            else:
                # gpu_sampling=0 here (no gpu_slot): mag.frag falls back to the
                # legacy raster ``magTex``/``magTex2`` path, so the array
                # layer/scale bound below is never actually sampled. P1B: this
                # fallback is reachable (raster overlay quads) and now emits
                # an explicit sig-throttled verdict above instead of silently
                # downgrading.
                _no_tex = {"key": None, "layer": 0, "scale": (1.0, 1.0)}
                records = [
                    {
                        "tc_x": (0.0, 1.0),
                        "tc_y": (0.0, 1.0),
                        "core_tc_x": (0.0, 1.0),
                        "core_tc_y": (0.0, 1.0),
                        "uv_rect1": uv_rect1,
                        "uv_rect2": uv_rect2,
                        "tex1": _no_tex,
                        "tex2": _no_tex,
                        "texd": _no_tex,
                    }
                ]
            if not records:
                continue

            for record in records:
                rec_uv1 = record["uv_rect1"]
                rec_uv2 = record["uv_rect2"]
                rec_tex1 = record["tex1"]
                rec_tex2 = record["tex2"]
                rec_texd = record["texd"] or {"layer": 0, "scale": (1.0, 1.0)}
                scale1 = rec_tex1["scale"]
                scale2 = rec_tex2["scale"]
                scaled = rec_texd["scale"]
                block = struct.pack(
                    _MAG_UNIFORM_FMT,
                    *matrix,
                    content_x0,
                    content_y0,
                    content_x1,
                    content_y1,
                    pan_x,
                    pan_y,
                    0.0,
                    0.0,
                    zoom,
                    content_radius * zoom,
                    0.0,
                    internal_split,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    float(comb_div_color[0]),
                    float(comb_div_color[1]),
                    float(comb_div_color[2]),
                    float(comb_div_color[3]),
                    float(comb_div_thickness),
                    float(getattr(overlay, "gpu_diff_threshold", 20.0 / 255.0) or 0.0),
                    int(comb_horizontal),
                    int(show_comb_divider),
                    1,
                    int(gpu_sampling),
                    int(combined),
                    int(source_mode),
                    int(diff_mode),
                    int(channel_mode),
                    int(interp_mode),
                    int(rec_tex1["layer"]),
                    int(rec_tex2["layer"]),
                    int(rec_texd["layer"]),
                    0,
                    0,
                    float(rec_uv1[0]),
                    float(rec_uv1[1]),
                    float(rec_uv1[2]),
                    float(rec_uv1[3]),
                    float(rec_uv2[0]),
                    float(rec_uv2[1]),
                    float(rec_uv2[2]),
                    float(rec_uv2[3]),
                    float(scale1[0]),
                    float(scale1[1]),
                    float(scale2[0]),
                    float(scale2[1]),
                    float(scaled[0]),
                    float(scaled[1]),
                    0.0,
                    0.0,
                    float(record["core_tc_x"][0]),
                    float(record["core_tc_y"][0]),
                    float(record["core_tc_x"][1]),
                    float(record["core_tc_y"][1]),
                )
                if tile_dump_enabled():
                    scissor_px = (
                        None
                        if is_full_tc(record["core_tc_x"], record["core_tc_y"])
                        else tc_rect_to_widget_px(
                            float(bcx),
                            float(bcy),
                            content_radius * zoom,
                            record["core_tc_x"],
                            record["core_tc_y"],
                        )
                    )
                    # Replicates mag.vert's own transform in Python so the
                    # log shows what the GPU *should* be drawing without
                    # needing a screenshot -- centerX/Y match the shader's
                    # own quadBounds-midpoint pivot; final_screen_rect is
                    # that result converted back to widget-px, directly
                    # comparable to scissor_px (same units/origin).
                    center_ndc_x = (content_x0 + content_x1) * 0.5
                    center_ndc_y = (content_y0 + content_y1) * 0.5
                    final_x0 = center_ndc_x + (content_x0 - center_ndc_x) * zoom
                    final_x1 = center_ndc_x + (content_x1 - center_ndc_x) * zoom
                    final_y0 = center_ndc_y + (content_y0 - center_ndc_y) * zoom
                    final_y1 = center_ndc_y + (content_y1 - center_ndc_y) * zoom
                    left_px = w * (final_x0 + 1.0) * 0.5
                    right_px = w * (final_x1 + 1.0) * 0.5
                    top_px = h * (1.0 - final_y1) * 0.5
                    bottom_px = h * (1.0 - final_y0) * 0.5
                    log_tile_event(
                        "magnifier.record",
                        prepare_call_seq=prepare_call_seq,
                        quad_index=i,
                        cx_px=float(cx_px),
                        cy_px=float(cy_px),
                        bcx=float(bcx),
                        bcy=float(bcy),
                        content_radius=float(content_radius),
                        zoom=zoom,
                        pan_x=pan_x,
                        pan_y=pan_y,
                        tex1_key=str(rec_tex1["key"]),
                        tex2_key=str(rec_tex2["key"]),
                        layer1=int(rec_tex1["layer"]),
                        layer2=int(rec_tex2["layer"]),
                        tc_x=record["tc_x"],
                        tc_y=record["tc_y"],
                        core_tc_x=record["core_tc_x"],
                        core_tc_y=record["core_tc_y"],
                        uv_rect1=rec_uv1,
                        uv_rect2=rec_uv2,
                        scissor_px=scissor_px,
                        final_content_screen_rect=(
                            left_px,
                            top_px,
                            right_px - left_px,
                            bottom_px - top_px,
                        ),
                    )
                self._mag_items.append({"block": block})

        if _no_slot_quad_indexes:
            _no_slot_sig = (
                tuple(_no_slot_quad_indexes),
                bool(overlay.gpu_active),
                len(getattr(overlay, "gpu_slots", ()) or ()),
            )
            if _no_slot_sig != self._last_no_slot_sig:
                self._last_no_slot_sig = _no_slot_sig
                _log.debug(
                    "magnifier no_gpu_slot: verdict=legacy_raster_magtex"
                    " reason=no gpu_slot for quad (raster overlay quad without"
                    " gpu params -> mag.frag magTex/magTex2 fallback)"
                    " quads=%s gpu_active=%s gpu_slots=%d",
                    list(_no_slot_quad_indexes),
                    bool(overlay.gpu_active),
                    len(getattr(overlay, "gpu_slots", ()) or ()),
                )
            # P3: raster quads without gpu params are the legacy/dead path --
            # once-per-quad log (live_handles recipe), record every frame.
            for _quad_index in _no_slot_quad_indexes:
                trace_loupe(
                    frame_context,
                    "loupe.mag_no_slot",
                    "skipped",
                    "no_gpu_slot quad without gpu params -> mag.frag magTex/magTex2"
                    " legacy raster fallback (gpu_sampling=0)",
                    ids=(_quad_index,),
                    throttle="once",
                    key=("loupe.mag_no_slot", _quad_index),
                )

        # H3 loupe-debug (trace-only): swap summary + heartbeat. The swap
        # frame (hold -> release, armed above) is always logged UNTHROTTLED
        # -- hold duration, drops/total, fallback/total, fallback_key map --
        # via a per-frame-unique sig, so the 2026-09-16 shape (swap then
        # throttled silence) can never read as ambiguous again. The
        # heartbeat fires at most ~1/sec while the lens is active so quiet
        # reads as held/resident counts. Both count this frame's own
        # records (snapshot at prepare top); hot-path cost is one clock
        # read, and the record scan runs only on swap/heartbeat frames.
        # Same draws either way -- this block only emits trace records.
        _loupe_now = time.monotonic() if _loupe_diag else 0.0
        _loupe_lens_active = bool(
            getattr(overlay, "gpu_active", False)
        ) and bool(getattr(overlay, "quads", ()))
        _loupe_hb_due = (
            _loupe_diag
            and _loupe_lens_active
            and (_loupe_now - self._loupe_hb_last_t) >= _LOUPE_HEARTBEAT_INTERVAL_S
        )
        if _loupe_diag and (_loupe_swap_armed or _loupe_hb_due):
            _loupe_drops = _loupe_fb = _loupe_holds = 0
            for _decision in list(frame_context)[_loupe_n0:]:
                if _decision.pass_name == "loupe.mag_dropped_slice":
                    _loupe_drops += 1
                elif _decision.pass_name == "loupe.mag_fallback_slice":
                    _loupe_fb += 1
                elif (
                    _decision.pass_name == "loupe.mag_residency_hold"
                    and _decision.verdict == "skipped"
                ):
                    _loupe_holds += 1
            if _loupe_swap_armed:
                _start_seq = self._loupe_hold_start_seq
                _start_t = self._loupe_hold_start_t
                _hold_frames = (
                    prepare_call_seq - _start_seq if _start_seq is not None else 0
                )
                _hold_ms = (
                    (_loupe_now - _start_t) * 1000.0 if _start_t is not None else 0.0
                )
                self._loupe_hold_start_seq = None
                self._loupe_hold_start_t = None
                _swap_total = _loupe_slice_stats.get("total")
                _swap_total_txt = (
                    str(_swap_total) if _swap_total is not None else "n/a"
                )
                _fbmap = ",".join(
                    f"{k}=>{v}"
                    for k, v in sorted(_fallback_by_source.items(), key=repr)
                )
                trace_loupe(
                    frame_context,
                    "loupe.mag_swap",
                    "ran",
                    f"swap_stored_to_source hold_frames={_hold_frames}"
                    f" hold_ms={_hold_ms:.1f} drops={_loupe_drops}/{_swap_total_txt}"
                    f" fallback={_loupe_fb}/{_swap_total_txt}"
                    f" fallback_keys={{{_fbmap}}}",
                    ids=(str(tex_key_1), str(tex_key_2), str(diff_key)),
                    sig=("swap", prepare_call_seq),
                )
            if _loupe_hb_due:
                self._loupe_hb_last_t = _loupe_now
                _hb_total = _loupe_slice_stats.get("total")
                _hb_missing = _loupe_slice_stats.get("missing")
                if _hb_total is not None and _hb_missing is not None:
                    _slices_txt = f"{_hb_total - _hb_missing}/{_hb_total}"
                else:
                    _slices_txt = "n/a"
                trace_loupe(
                    frame_context,
                    "loupe.mag_heartbeat",
                    "ran",
                    f"heartbeat use_source={use_source} slices={_slices_txt}"
                    f" holds={_loupe_holds} drops={_loupe_drops}"
                    f" fallback={_loupe_fb}",
                    ids=(str(tex_key_1), str(tex_key_2)),
                    sig=("heartbeat", prepare_call_seq),
                )

        self.border.ensure_items(len(self._border_items))
        if self._border_items:
            self.border.prepare_vertex_buffer(resource_updates)
            for index, block in enumerate(self._border_items):
                resource_updates.updateDynamicBuffer(
                    self.border.uniform_buffers[index], 0, block
                )

        self._ensure_mag_uniform_capacity(len(self._mag_items))

        # All items share one array texture (``bg_array``), but the array
        # object itself can be replaced when ``_ensure_tile_array`` grows a
        # new backing texture, so the SRB is rebuilt every frame regardless
        # (``_ensure_mag_uniform_capacity`` above already tore it down when
        # the buffer itself grew).
        # F4-BOUNDARY (SRB rebuild): per-frame rebuild tracks the
        # EXTERNAL backing-array replace -- TexturedOverlayShell rebuilds
        # only on its own texture resize, never on an external replace.
        if self.mag_srb is not None:
            try:
                self.mag_srb.destroy()
            except RuntimeError:
                pass
        self.mag_srb = self._build_mag_srb(bg_array)

        if self._mag_items:
            resource_updates.updateDynamicBuffer(
                self.mag_vertex_buffer, 0, FULLSCREEN_VERTICES
            )
            stride = self.mag_uniform_stride
            for index, item in enumerate(self._mag_items):
                resource_updates.updateDynamicBuffer(
                    self.mag_uniform_buffer, index * stride, item["block"]
                )

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        target_size = widget.renderTarget().pixelSize()
        viewport = QRhiViewport(
            0.0, 0.0, float(target_size.width()), float(target_size.height())
        )
        scissor = resolve_rhi_scissor(
            widget,
            self.rhi,
            ctx,
            clip_to_content=bool(
                getattr(widget.runtime_state, "_clip_overlays_to_content_rect", False)
            ),
        )
        if self._border_items:
            command_buffer.setGraphicsPipeline(self.border.pipeline)
            command_buffer.setViewport(viewport)
            command_buffer.setScissor(scissor)
            command_buffer.setVertexInput(0, [(self.border.vertex_buffer, 0)])
            for index in range(len(self._border_items)):
                command_buffer.setShaderResources(self.border.srbs[index])
                command_buffer.draw(4)

        if self._mag_items:
            assert self.mag_pipeline is not None
            command_buffer.setGraphicsPipeline(self.mag_pipeline)
            command_buffer.setViewport(viewport)
            command_buffer.setScissor(scissor)
            assert self.mag_vertex_buffer is not None
            command_buffer.setVertexInput(0, [(self.mag_vertex_buffer, 0)])
            stride = self.mag_uniform_stride
            # F4-BOUNDARY (dynamic-offset draw): one shared SRB rebound per
            # item with its strided dynamic offset -- record path is math
            # routing only (ruling 4: gating lives in prepare's hold gates
            # above, never here).
            for index, item in enumerate(self._mag_items):
                command_buffer.setShaderResources(
                    self.mag_srb, 1, (0, index * stride)
                )
                command_buffer.draw(4)

    def release(self) -> None:
        self.border.release()
        for res in (
            self.mag_pipeline,
            self.mag_srb,
            self.mag_uniform_buffer,
            self.mag_vertex_buffer,
            self.sampler_linear,
            self.sampler_nearest,
            self.placeholder_texture,
            self.placeholder_texture_array,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.mag_pipeline = None
        self.mag_srb = None
        self.mag_uniform_buffer = None
        self.mag_uniform_stride = 0
        self.mag_uniform_capacity = 0
        self.mag_vertex_buffer = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.placeholder_texture = None
        self.placeholder_texture_array = None
        self.rhi = None
        self._target = None
        self._border_items = []
        self._mag_items = []
