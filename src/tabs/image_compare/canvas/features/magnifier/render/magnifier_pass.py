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
"""

from __future__ import annotations

import logging
import struct

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
    tile_uv_slices,
)
from tabs.image_compare.canvas.rhi_feature_common import (
    FULLSCREEN_VERTICES,
    FullscreenUniformPassResources,
    build_fullscreen_quad_pipeline,
    resolve_rhi_scissor,
)
from tabs.image_compare.canvas.rhi_renderer import (
    _ARRAY_LAYER_PX,
    _TILE_APRON_PX,
    _apron_rect,
)
from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled
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
from shared.rendering.uniform_layout import assert_uniform_size

_MAG_UNIFORM_FMT = (
    "<16f 4f 2f 2f f f f f 4f 4f f f i i i i i i i i i i i i i i 4f 4f 4f 4f 4f"
)
assert_uniform_size(_MAG_UNIFORM_FMT, MAG_UNIFORM_SIZE, label="MagnifierPass uniform")

_log = logging.getLogger("ImproveImgSLI.magnifier.pass")


def _content_scale(content_size) -> tuple[float, float]:
    if content_size is None:
        return (1.0, 1.0)
    width, height = content_size
    return (width / _ARRAY_LAYER_PX, height / _ARRAY_LAYER_PX)


def _source_slices(renderer, source_key, uv_rect, frame_context=None):
    """Tile-aware uv_rect slicing for one magnifier source (see tile_capture.py).

    Attaches each slice's array ``layer``/``content_scale`` (looked up via
    ``TileTextureService``) so ``build_tile_records`` can pass them straight
    through to ``MagnifierPass``'s per-record ``tex1``/``tex2``/``texd``
    dicts -- this is the one renderer-dependent hook in the whole capture
    pipeline, everything else in ``tile_capture.py`` is pure geometry.

    P3 residency priorities: the lens first registers its interest rect
    (``uv_rect`` in source-image pixels) and asks the service for the
    level/residency answer (``request_level``) instead of deciding itself.
    Slicing behavior is unchanged -- a non-resident slice is still dropped
    rather than defaulting to layer 0 -- but the drop now carries the
    service's reason as a ``loupe.mag_dropped_slice`` FrameContext record
    instead of staying silent. ``frame_context=None`` keeps every existing
    call site behavior-identical.
    """
    tile_service = getattr(renderer, "tile_service", None) if renderer is not None else None
    grid = tile_service.grid_for(source_key) if tile_service is not None else None
    if tile_dump_enabled() and grid is not None:
        log_tile_event(
            "magnifier.grid_dims",
            source_key=str(source_key),
            total_width=grid.total_width,
            total_height=grid.total_height,
            tile_width=grid.tile_width,
            tile_height=grid.tile_height,
            rows=grid.rows,
            columns=grid.columns,
            uv_rect=list(uv_rect),
        )
    slices = tile_uv_slices(
        grid,
        tile_service.tile_key if tile_service is not None else None,
        source_key,
        uv_rect,
        apron_px=_TILE_APRON_PX,
        apron_rect_fn=_apron_rect,
        visible_tiles_fn=(
            (lambda rect: tile_service.visible_tiles(source_key, rect))
            if tile_service is not None
            else None
        ),
    )
    if tile_service is None:
        return slices
    residency_reason: str | None = None
    if grid is not None:
        try:
            _total_w = float(grid.total_width)
            _total_h = float(grid.total_height)
            _interest_rect = (
                float(uv_rect[0]) * _total_w,
                float(uv_rect[1]) * _total_h,
                float(uv_rect[2]) * _total_w,
                float(uv_rect[3]) * _total_h,
            )
        except (TypeError, ValueError, IndexError):
            _interest_rect = None
        if _interest_rect is not None:
            tile_service.register_interest_rect(source_key, _interest_rect)
            _req_level, _req_status, residency_reason = tile_service.request_level(
                source_key, _interest_rect, quality="high"
            )
    resolved = []
    for sl in slices:
        slot = tile_service.slot_for(source_key, sl["tile_index"])
        if slot is None:
            # Not yet GPU-resident (upload still in flight) -- drop rather
            # than default to layer 0, which would sample whatever
            # unrelated tile happens to occupy that layer right now.
            _drop_reason = (
                "dropped_nonresident_slice tile not GPU-resident"
                + (
                    f" request_level={residency_reason}"
                    if residency_reason is not None
                    else ""
                )
            )
            trace_loupe(
                frame_context,
                "loupe.mag_dropped_slice",
                "skipped",
                _drop_reason,
                ids=(str(source_key), tuple(sl["tile_index"])),
                sig=(str(source_key), tuple(sl["tile_index"]), residency_reason),
            )
            if tile_dump_enabled():
                log_tile_event(
                    "magnifier.dropped_nonresident_slice",
                    source_key=str(source_key),
                    tile_index=list(sl["tile_index"]),
                    uv_rect=list(uv_rect),
                )
            continue
        sl["layer"] = slot[1]
        sl["content_scale"] = _content_scale(
            tile_service.content_size_for(source_key, sl["tile_index"])
        )
        resolved.append(sl)
    return resolved


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
        # ``rhi_renderer/use_cases/fallback.py`` ``_last_renderer_fallback_sig``:
        # emit once per distinct decision signature, not once per frame).
        self._last_no_slot_sig: tuple | None = None

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi
        self._target = target
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
        ``shared.rendering.mip_cascade._ensure_downsample_uniform_buffer``
        and docs/dev/rendering/investigations/multitile-uniform-desync.md):
        a `Dynamic` buffer's multi-frame-in-flight rotation isn't guaranteed
        warmed up on its very first write for every QRhi backend. Growing
        one long-lived buffer and writing every slot pre-pass (never
        recreating it just because the record count went up) sidesteps
        that regardless of whether it's the actual cause here."""
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
        matrix = tuple(float(v) for v in self.rhi.clipSpaceCorrMatrix().data())
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
        array_resources = getattr(rhi_renderer.resources, "array_resources", None) if rhi_renderer else None
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
        tex_key_1 = ctx.source_texture_ids[0] if use_source else ctx.texture_ids[0]
        tex_key_2 = ctx.source_texture_ids[1] if use_source else ctx.texture_ids[1]
        diff_key = (
            ctx.diff_source_texture_id
            if ctx.diff_source_ready and ctx.diff_source_texture_id
            else "placeholder"
        )
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
                        rhi_renderer, key, rect, frame_context
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
