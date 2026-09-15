"""Base image tile QRhi pass for Multi Compare."""
# Audit-Meta: pattern=state-machine reason="single QRhi tile pass — one pipeline + MipCascade + host cache lifecycle"

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

from PySide6.QtGui import QImage, QRhiViewport

from engine.store.tiled_pixel_store import (
    TiledPixelStore,
    pixel_source_size,
)
from engine.cache.fallback_lod import resolve_fallback_lod
from engine.gpu.host_texture_cache import cache_for_host
from engine.cache.lod import LevelKey
from engine.gpu.mip_cascade import MipCascadeGenerator
from engine.cache.render_debug import rhi_render_debug
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from engine.cache.tile_geometry import _TILE_APRON_PX
from engine.cache.tile_texture_service import DEFAULT_MAX_ARRAY_SIZE
from tabs.multi_compare.scene.projection import letterbox_uv
from tabs.multi_compare.scene.resources import (
    FULLSCREEN_VERTICES,
    SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES,
    SLOT_LIVE_TILE_EXTENT,
    SLOT_TILE_CACHE_BUDGET_BYTES,
    SLOT_UNIFORM_SIZE,
    load_shader,
)
from tabs.multi_compare.scene.tile_geometry import (
    SlotArrayTile,
    SlotDrawItem,
    build_slot_array_tiles,
    build_slot_draw_plan,
    drop_covered_fallback_tiles,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

from . import residency
from .array_resources import ArrayResources
from .slot_resources import SlotResources

logger = logging.getLogger("ImproveImgSLI")

# Texture-array instanced-draw path (docs/dev/rendering/
# tile-array-atlas-plan.md Phase 4) -- mirrors image_compare's
# rhi_renderer/resources.py Phase 2 array path, simplified for
# multi_compare's single-image-per-slot model: no cross-image pairing, so
# each instance is exactly one (layer, tile) pair carrying its own
# pan/fit/zoom/slotRect instead of a shared per-draw-call uniform block.
# Every layer of the array must share one pixel size, so tile content (at
# most SLOT_LIVE_TILE_EXTENT + 2*apron px) is uploaded 1:1, unresampled,
# into the top-left corner of a layer this size; the shader always rescales
# UV by each tile's own content-scale before sampling.
_ARRAY_LAYER_PX = SLOT_LIVE_TILE_EXTENT + 2 * _TILE_APRON_PX
_ARRAY_LAYER_BYTES = _ARRAY_LAYER_PX * _ARRAY_LAYER_PX * 4
# Bounds how many layers one array texture should pre-size for -- see
# image_compare resources.py's identical derivation. _MAX_EXPECTED_CANVAS_PX
# bounds one 4K-ish monitor; multi_compare has no image1/image2/diff
# multiplier since there's no cross-image pairing here.
_MAX_EXPECTED_CANVAS_PX = 4096
_MAX_TILES_PER_AXIS = -(-(2 * _MAX_EXPECTED_CANVAS_PX) // SLOT_LIVE_TILE_EXTENT) + 1
_ARRAY_CAPACITY = min(
    DEFAULT_MAX_ARRAY_SIZE,
    max(
        _MAX_TILES_PER_AXIS * _MAX_TILES_PER_AXIS,
        SLOT_TILE_CACHE_BUDGET_BYTES // _ARRAY_LAYER_BYTES,
    ),
)

# Sentinel LevelKey.level value (real pyramid levels are always >= 1, per
# LevelKey's own docstring) used to rescue a slot's previous-generation
# (e.g. preview) residency under a distinct key before register_source()
# wipes the bare `sid` key -- see _upload_slot.
_PREVIOUS_GENERATION_LEVEL = -1


@dataclass
class _SwapSpec:
    """Resolved content-swap decision for one ``(sid, source)`` upload.

    Pure decision, no mutation: produced by ``resolve_swap_spec`` (reads
    only ``slot_pixel_sources`` + ``tile_service.grid_for``) and consumed
    by ``_apply_swap_spec`` (which performs the rekey/register/upload in
    the original order). Splitting the decision from the mutation is the
    swap machine's final thin-client shape -- the spec feeds the engine
    loop (``apply_pending_texture_ops``), the tab only resolves specs,
    funnels uploads through ``upload_tile``, and reacts through the
    backfill/promotion hooks below.
    """

    sid: int
    size: tuple[int, int]
    old_source: TiledPixelStore | QImage | None
    old_is_multi: bool
    # ``LevelKey(sid, _PREVIOUS_GENERATION_LEVEL)`` when a previous grid
    # exists to rescue, else ``None`` (first upload -- nothing to rekey).
    fallback_key: object | None
    # 1x1-preview -> multi-full backfill condition, evaluated on old state
    # only (the new grid's own multi-ness is re-checked at apply time,
    # where the plain branch returns before this is read).
    needs_backfill: bool


def _pack_array_uniforms(
    clip_matrix: tuple[float, ...], letterbox: tuple[float, float, float, float]
) -> bytes:
    return struct.pack("<16f 4f", *clip_matrix, *letterbox)


def _pack_array_instance(
    *,
    pan_fit: tuple[float, float, float, float],
    zoom: float,
    tile_rect: tuple[float, float, float, float],
    slot_rect: tuple[float, float, float, float],
    content_scale: tuple[float, float],
    layer: int,
    bbox: tuple[float, float, float, float],
) -> bytes:
    return struct.pack(
        "<4f f 4f 4f 2f i 4f",
        *pan_fit,
        zoom,
        *tile_rect,
        *slot_rect,
        *content_scale,
        layer,
        *bbox,
    )


def _axis_bbox(
    tile_origin: float,
    tile_size: float,
    pan: float,
    fit: float,
    zoom: float,
    slot_origin: float,
    slot_size: float,
    letterbox_origin: float,
    letterbox_size: float,
) -> tuple[float, float]:
    """One axis of ``_instance_bbox`` -- inverts multi_compare_array.frag's
    forward chain (``letterbox -> slotRect -> fit/zoom/pan -> tileRect``,
    each stage's own discard clamped to [0,1] in the same order the
    fragment shader checks it) to find the screen-space span this tile's
    full [0,1] UV footprint could ever produce non-discarded output for."""
    e0 = max(0.0, min(1.0, tile_origin))
    e1 = max(0.0, min(1.0, tile_origin + tile_size))
    d0 = 0.5 + zoom * (e0 - 0.5 + pan)
    d1 = 0.5 + zoom * (e1 - 0.5 + pan)
    c0 = 0.5 + fit * (d0 - 0.5)
    c1 = 0.5 + fit * (d1 - 0.5)
    c0, c1 = (c0, c1) if c0 <= c1 else (c1, c0)
    c0 = max(0.0, min(1.0, c0))
    c1 = max(0.0, min(1.0, c1))
    b0 = slot_origin + c0 * slot_size
    b1 = slot_origin + c1 * slot_size
    b0, b1 = (b0, b1) if b0 <= b1 else (b1, b0)
    b0 = max(0.0, min(1.0, b0))
    b1 = max(0.0, min(1.0, b1))
    a0 = letterbox_origin + b0 * letterbox_size
    a1 = letterbox_origin + b1 * letterbox_size
    return (a0, a1) if a0 <= a1 else (a1, a0)


def _instance_bbox(
    *,
    pan: tuple[float, float],
    fit: tuple[float, float],
    zoom: float,
    tile_rect: tuple[float, float, float, float],
    slot_rect: tuple[float, float, float, float],
    letterbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """docs/dev/rendering/tile-array-atlas-plan.md Phase 10 port: this
    instance's on-screen bounding box (mirrors image_compare's
    ``_intersection_rect``-derived ``iBBox``, computed CPU-side once per
    instance here since it's cheaper than the GPU running every fragment
    shader invocation across the whole framebuffer only to discard almost
    all of them -- see ``multi_compare_array.vert``'s header comment for
    the inverse-chain derivation this performs)."""
    ax0, ax1 = _axis_bbox(
        tile_rect[0], tile_rect[2], pan[0], fit[0], zoom,
        slot_rect[0], slot_rect[2], letterbox[0], letterbox[2],
    )
    ay0, ay1 = _axis_bbox(
        tile_rect[1], tile_rect[3], pan[1], fit[1], zoom,
        slot_rect[1], slot_rect[3], letterbox[1], letterbox[3],
    )
    return (ax0, ay0, max(0.0, ax1 - ax0), max(0.0, ay1 - ay0))


def _content_scale(content_size: tuple[int, int] | None) -> tuple[float, float]:
    if content_size is None:
        return (1.0, 1.0)
    width, height = content_size
    return (width / _ARRAY_LAYER_PX, height / _ARRAY_LAYER_PX)


def _pack_slot_uniforms(
    clip_matrix: tuple[float, ...],
    layer,
    tile_rect: tuple[float, float, float, float],
    letterbox: tuple[float, float, float, float],
) -> bytes:
    slot_rect = getattr(layer, "slot_rect_uv", (0.0, 0.0, 1.0, 1.0))
    return struct.pack(
        "<16f 2f 2f f 3f 4f 4f 4f",
        *clip_matrix,
        layer.pan_x,
        layer.pan_y,
        max(layer.fit_x, 1e-6),
        max(layer.fit_y, 1e-6),
        layer.zoom,
        0.0,
        0.0,
        0.0,
        *tile_rect,
        *letterbox,
        *slot_rect,
    )


class BaseImagesPass(CanvasRenderPass):
    """Owns image textures, tile pipeline, uniforms, and draw recording.

    Full-res slot pixels live in :class:`TiledPixelStore` (session state).
    This pass keeps GPU residency via ``TileTextureService`` and a bounded
    host-side ``HostTextureUploadCache`` on the canvas widget for decoded
    QImage uploads — never an uncapped full-res QImage dict.

    A slot's source may also be a bounded ``QImage`` progressive preview
    (cached preview tier) while the real ``TiledPixelStore`` is
    still decoding in the background — previews are capped at 1024px, always
    land in a 1x1 tile grid, and upload through the same single-tile branch
    below (``host_cache.qimage_from_source`` already round-trips a QImage as
    a copy). See ``MultiCompareController._load_full_resolution_async``.

    Once a slot's full-res store is registered with the process-wide
    ``pyramid_registry`` (``MultiCompareController._start_pyramid_build``),
    ``residency.lod_key_and_source`` picks the coarsest built mipmap level that still
    covers the slot's on-screen size each frame — mirrors image_compare's
    ``resolve_lod_texture_keys``/``realize_tile_plan``. A selected level is
    addressed by ``LevelKey(sid, level)`` instead of the bare slot id, which
    ``TileTextureService`` (keyed by opaque ``object``) and
    ``build_slot_draw_plan`` already accept unchanged. Level 0 (no pyramid
    yet, or the slot is shown at/above native resolution) keeps the bare
    ``sid`` key, so the eager single-upload fast path in ``_upload_slot``
    stays byte-identical to before pyramids existed.

    Phase-2 pass shape: the engine decides residency (``TileTextureService``
    grids/slots + ``TileResidencyRealizerBase.realize_specs``); this pass
    only resolves per-slot specs (``residency.realize``) and uploads tiles
    (``_SlotUploadRealizer._upload_tile``). Pass order comes from the
    central stacking policy via ``stack_role`` (never local numbers), and
    ``record()`` reads only its context plus this pass's own prepared
    state -- no widget/store access, no export-mode branches
    (snapshot-replay per rendering-model).
    """

    # Routing declaration for ``RENDER_PASSES`` (see scene/renderer.py): no
    # CanvasStackRole maps to RenderPhase.BASE_IMAGE yet, so this declares
    # the nearest content role until the policy gains one. ``visibility``
    # stays explicit ``ALL`` on purpose -- ``MultiCompareRenderContext``
    # carries no render-mode signal, so ``iter_active_render_passes``'
    # resolver defaults to ``PREVIEW`` (see
    # ``canvas/features/drag_drop_overlay/passes.py``); narrowing this to
    # ``INTERACTIVE`` would silently disable the base pass permanently.
    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.slot_pixel_sources: dict[int, TiledPixelStore | QImage] = {}
        self.layer_draw_items: list[list[SlotDrawItem]] = []
        self._resolved_tile_srbs: list[list[object | None]] = []
        self.pending_uploads: list[tuple[int, TiledPixelStore | QImage]] = []
        self.pending_removes: list[int] = []
        self._slot_lod_keys: dict[int, set[LevelKey]] = {}
        # docs/dev/rendering/tile-array-atlas-plan.md Phase 9 fallback-LOD
        # (mirrors image_compare's ``_last_good_texture_keys``, per slot
        # instead of per image1/image2 pair): the last key whose tile
        # target was fully uploaded, kept around so a LOD-level transition
        # that outpaces the upload budget can keep showing this slot's
        # previous level instead of a blank hole -- see
        # ``_realize_tile_residency``/``_prepare_array_plan``. Owned here
        # rather than by ``residency.py`` -- mirrors image_compare's
        # ``RhiCanvasRenderer`` owning ``_last_good_texture_keys`` itself
        # while ``TileResidencyRealizer`` stays stateless across frames.
        self._last_good_key: dict[int, object] = {}
        # Whether this frame's upload pass for ``key`` still has tiles left
        # to fill in (budget-limited) -- set from ``residency.realize``'s
        # return value, read in ``_prepare_array_plan`` to decide whether
        # ``key``'s plan is a stable end state (safe to promote to
        # ``_last_good_key``) or still mid-transition (needs the fallback
        # drawn underneath it).
        self._key_more_pending: dict[object, bool] = {}
        # Slots whose pre-swap plain (1x1) preview texture is still alive
        # underneath the new array-path content -- added in ``_upload_slot``
        # when a swap keeps the old preview drawable instead of destroying
        # it up front, consumed in ``_prepare_array_plan`` once the new
        # key promotes (fully uploaded = array covers the slot, the stale
        # plain texture can go). Only swapped slots are ever in here, so
        # the consumption never touches a steady-state 1x1 slot's own
        # plain texture (which a later plain-path frame may still need).
        self._pending_plain_cleanup: set[int] = set()

        # Plain per-slot pipeline/textures/uniforms/SRBs -- the non-array
        # draw path used while every slot stays a single (1x1) tile.
        self.slot_resources = SlotResources(uniform_size=SLOT_UNIFORM_SIZE)

        # Texture-array instanced-draw path (Phase 4) -- used only for
        # frames where at least one slot's grid is multi-tile; the common
        # all-1x1-slots case stays entirely on slot_resources, untouched.
        # Constructed lazily in `initialize()`, same reason as
        # `_mip_cascade` below (needs a `renderer` reference to close over).
        self.array_resources: ArrayResources | None = None
        self._use_array_this_frame = False
        self.array_draw_instance_count = 0

        # Per-layer mip generation (docs/dev/rendering/tile-array-atlas-plan.md
        # Phase 9) -- replaces a whole-array `updates.generateMips` call with
        # a manual cascade of single-layer downsample passes. Shared with
        # image_compare's RhiResources (identical logic); constructed lazily
        # in `initialize()` since this pass only gets a `renderer` reference
        # per-call, not stored on self, until then.
        self._renderer = None
        self._mip_cascade: MipCascadeGenerator | None = None
        # This frame's (array_index -> {layer, ...}) set touched by
        # _upload_tile_to_array, consumed by the renderer via
        # take_dirty_layers() between the tile-upload submit and the main
        # draw pass.
        self._dirty_layers_this_frame: dict[int, set[int]] = {}
        # This frame's per-slot (key, pixel_source) as resolved by
        # residency.realize()'s own lod_key_and_source call -- stashed so
        # _prepare_array_plan/prepare's plain-path loop reuses it
        # verbatim instead of independently re-resolving it later in the same
        # frame, which could disagree if a background pyramid build landed a
        # new level in between (see residency.py's realize() docstring/the
        # comment at its `resolved_lod` local).
        self._frame_resolved_lod: dict[int, tuple[object, object | None]] = {}

    def should_paint(self, ctx) -> bool:
        """Base content draws whenever the frame has projected layers.

        Reads only ``ctx`` (record-reads-only-ctx direction) -- the
        renderer records ``image_pass`` first explicitly (see
        scene/renderer.py); the shape already fits
        ``iter_active_render_passes`` if routing ever merges.
        """
        return bool(getattr(ctx, "projected_layers", ()))

    def has_slot_texture(self, slot_id: int) -> bool:
        return int(slot_id) in self.slot_pixel_sources

    def slot_texture_ids(self) -> list[int]:
        return list(self.slot_pixel_sources)

    def queue_upload(self, slot_id: int, source: TiledPixelStore | QImage) -> None:
        self.pending_uploads.append((int(slot_id), source))

    def queue_remove(self, slot_id: int) -> None:
        self.pending_removes.append(int(slot_id))

    def _host_cache(self, renderer):
        return cache_for_host(
            renderer.host,
            budget_bytes=SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES,
        )

    def _ensure_array_resources(self, renderer) -> None:
        """Builds ``array_resources``/``_mip_cascade`` against ``renderer``
        the first time either is actually needed. Normally that's from
        ``initialize()``, but tests exercise ``_realize_tile_residency``
        directly against a fake renderer without ever calling
        ``initialize()`` -- lazily building here (idempotent, guarded by
        ``array_resources is not None``) covers both call paths with one
        code path instead of duplicating construction."""
        if self.array_resources is not None:
            return
        assert renderer.rhi is not None and renderer.sampler is not None
        self._renderer = renderer
        self.array_resources = ArrayResources(
            rhi_getter=lambda: self._renderer.rhi if self._renderer else None,
            sampler_getter=lambda name: (
                self._renderer.sampler if self._renderer else None
            ),
            load_shader=load_shader,
            layer_px=_ARRAY_LAYER_PX,
            array_capacity=_ARRAY_CAPACITY,
            name_prefix="multi-compare",
        )
        self._mip_cascade = MipCascadeGenerator(
            rhi_getter=lambda: self._renderer.rhi if self._renderer else None,
            tile_arrays=self.array_resources.tile_arrays,
            ensure_tile_array=lambda index: self.array_resources._ensure_tile_array(index),
            sampler_getter=lambda: (
                self._renderer.sampler if self._renderer else None
            ),
            layer_px=_ARRAY_LAYER_PX,
            name_prefix="multi-compare",
        )

    def initialize(self, rhi, target) -> None:
        """Contract-shape init (mirrors
        ``magnifier_pass.initialize(rhi, target)``): rhi-local work only
        (uniform stride). The sampler/array resources and the slot pipeline
        need renderer-owned objects ``initialize`` never receives, so they
        resolve lazily in ``prepare()`` via ``widget._renderer`` --
        ``prepare`` runs every frame before ``record``.
        """
        self.slot_resources.set_uniform_stride(rhi.ubufAligned(SLOT_UNIFORM_SIZE))

    def release(self) -> None:
        if self._mip_cascade is not None:
            self._mip_cascade.release()
        self.slot_resources.release()
        if self.array_resources is not None:
            self.array_resources.release()
        self.__init__()  # type: ignore[misc]  # resource-reset reinit

    def apply_pending_texture_ops(self, renderer, updates) -> None:
        tile_service = renderer.tile_service
        for sid in self.pending_removes:
            self._release_slot(tile_service, sid)
        self.pending_removes.clear()
        for sid, source in self.pending_uploads:
            self._upload_slot(renderer, tile_service, sid, source, updates)
        self.pending_uploads.clear()

    def take_dirty_layers(self) -> dict[int, set[int]]:
        """Pops this frame's array-index/layer set dirtied by
        ``_upload_tile_to_array`` during ``prepare`` -- read by
        ``MultiCompareRhiRenderer.render`` once, between submitting the tile
        uploads and running ``generate_all_dirty_mips``."""
        dirty_layers = self._dirty_layers_this_frame
        self._dirty_layers_this_frame = {}
        return dirty_layers

    def prepare(self, widget, ctx, updates) -> None:
        """Contract-shape per-frame preparation (mirrors image_compare's
        ``magnifier_pass.prepare(widget, ctx, resource_updates)``).

        Renderer-owned GPU helpers resolve through ``widget._renderer``
        (same reach-through as the magnifier's ``widget._rhi_renderer``) --
        only ``widget``/``ctx``/``updates`` cross the contract boundary.

        Does in one batch what used to be the ``realize_residency`` +
        ``finish_prepare`` pair split around the mip-cascade submit: uploads
        and residency first (must precede ``generate_all_dirty_mips``, which
        samples this frame's just-uploaded tiles -- see
        ``MultiCompareRhiRenderer.render``'s sequencing), then the draw-plan
        uniforms/SRBs below (disjoint buffers with no mip dependency, so
        sharing the pre-mips batch is behavior-identical to the old
        post-mips one). The upload-queue flush
        (``apply_pending_texture_ops``) stays renderer-driven before the ctx
        build -- it feeds ``available_slot_ids``, not the contract.
        """
        renderer = getattr(widget, "_renderer", widget)
        # Match image_compare: refresh pipelines if popup/swapchain restacked
        # the color buffer (stale renderPassDescriptor → wrong present).
        self.slot_resources.ensure_pipeline(renderer, widget.renderTarget())
        self.slot_resources.ensure_slot_resources(renderer, len(ctx.projected_layers))
        # Shared fullscreen quad — letterbox + slot cell are UV uniforms.
        # Also the vertex input generate_all_dirty_mips' downsample pass
        # draws with, so it must be written in this same pre-mips batch.
        if self.slot_resources.slot_vertex_buffers:
            updates.updateDynamicBuffer(
                self.slot_resources.slot_vertex_buffers[0], 0, FULLSCREEN_VERTICES
            )
        self._realize_tile_residency(renderer, ctx, updates)
        # --- draw-plan half (ex-``finish_prepare``): builds this frame's
        # array instances or per-tile uniforms/SRBs into the same batch. ---
        fb_w, fb_h = ctx.framebuffer_size
        composition = ctx.composition
        canvas_w = float(getattr(composition, "canvas_w", 1) or 1)
        canvas_h = float(getattr(composition, "canvas_h", 1) or 1)
        lb = letterbox_uv(
            framebuffer_size=(fb_w, fb_h),
            scale=float(ctx.scale),
            offset=tuple(ctx.offset),
            canvas_size=(canvas_w, canvas_h),
        )
        # docs/dev/rendering/tile-array-atlas-plan.md Phase 4: whichever
        # slot resolved to a multi-tile grid this frame forces the whole
        # draw call onto the texture-array + instanced pipeline (see
        # _realize_tile_residency's `use_array` decision, computed once per
        # frame and reused here so upload and draw agree on which path this
        # frame took). The two paths are mutually exclusive per frame.
        self.layer_draw_items = []
        self._resolved_tile_srbs = []
        if self._use_array_this_frame:
            self._prepare_array_plan(renderer, ctx, updates, lb)
            return
        self.array_draw_instance_count = 0
        # Every tile item's uniforms (own tileRect) are packed into the same
        # pre-pass `updates` batch, one slot per item at stride-spaced
        # offsets, and every item's SRB is resolved here too -- both must
        # happen before beginPass. This used to be a mid-pass
        # resourceUpdate() + SRB creation per draw call, which is
        # backend-defined territory for a shared Dynamic buffer read by
        # multiple draws in the same pass (see image_compare's identical
        # fix and docs/dev/rendering/investigations/multitile-uniform-desync.md
        # for the failure mode: a mismatched tileRect landing on the wrong
        # draw call, which visually collapses a multi-tile slot's image
        # into whichever tile's rect was written last).
        for index, layer in enumerate(ctx.projected_layers):
            sid = int(layer.slot_id)
            resolved = self._frame_resolved_lod.get(sid)
            if resolved is not None:
                key, _source = resolved
            else:
                base_source = self.slot_pixel_sources.get(sid)
                key, _source = residency.lod_key_and_source(
                    sid, base_source, layer, self._slot_lod_keys
                )
            pan = (layer.pan_x, layer.pan_y)
            fit = (max(layer.fit_x, 1e-6), max(layer.fit_y, 1e-6))
            items = build_slot_draw_plan(renderer.tile_service, key, pan, fit, layer.zoom)
            self.layer_draw_items.append(items)
            self.slot_resources.ensure_slot_uniform_capacity(renderer, index, len(items))
            rhi_render_debug(
                "mc-plain-plan sid=%s key=%s index=%s items=%d pan=%s fit=%s "
                "zoom=%s rect_fb=%s slot_rect=%s letterbox=%s",
                sid, key, index, len(items), pan, fit, layer.zoom,
                layer.rect_fb, getattr(layer, "slot_rect_uv", None), lb,
            )
            srbs: list[object | None] = []
            for item_index, item in enumerate(items):
                texture = self.slot_resources.slot_textures.get(item.tile_key)
                rhi_render_debug(
                    "mc-plain-item sid=%s item_index=%s tile_key=%s tile_rect=%s "
                    "texture=%s tex_size=%s",
                    sid, item_index, item.tile_key, item.tile_rect,
                    texture is not None,
                    self.slot_resources.slot_texture_sizes.get(item.tile_key),
                )
                if tile_dump_enabled():
                    tile_key = item.tile_key
                    row, col = (
                        tile_key[1:]
                        if isinstance(tile_key, tuple) and len(tile_key) == 3
                        else (0, 0)
                    )
                    log_tile_event(
                        "plain.item",
                        sid=sid,
                        key=str(key),
                        item_index=item_index,
                        tile_key=str(tile_key),
                        row=row,
                        col=col,
                        row_parity=row % 2,
                        col_parity=col % 2,
                        tile_rect=item.tile_rect,
                        has_texture=texture is not None,
                        tex_size=self.slot_resources.slot_texture_sizes.get(tile_key),
                    )
                if texture is None:
                    srbs.append(None)
                    continue
                srb = self.slot_resources.ensure_tile_srb(
                    renderer, index, item.tile_key, texture
                )
                srbs.append(srb)
                updates.updateDynamicBuffer(
                    self.slot_resources.slot_uniform_buffers[index],
                    item_index * self.slot_resources._slot_uniform_stride,
                    _pack_slot_uniforms(ctx.clip_matrix, layer, item.tile_rect, lb),
                )
            self._resolved_tile_srbs.append(srbs)

    def _prepare_array_plan(self, renderer, ctx, updates, letterbox) -> None:
        """Array-path counterpart of the per-tile loop above (docs/dev/
        rendering/tile-array-atlas-plan.md Phase 4): builds one instance per
        (layer, tile) pair across every visible layer combined, instead of
        one draw call per tile. Writes the frame-constant uniform block and
        the whole instance buffer here (pre-pass, same reasoning as the
        per-tile uniforms above), so ``record`` only needs one draw call."""
        tile_service = renderer.tile_service
        instances: list[bytes] = []
        for layer in ctx.projected_layers:
            sid = int(layer.slot_id)
            resolved = self._frame_resolved_lod.get(sid)
            if resolved is not None:
                key, _source = resolved
            else:
                base_source = self.slot_pixel_sources.get(sid)
                key, _source = residency.lod_key_and_source(
                    sid, base_source, layer, self._slot_lod_keys
                )
            pan = (layer.pan_x, layer.pan_y)
            fit = (max(layer.fit_x, 1e-6), max(layer.fit_y, 1e-6))
            slot_rect = tuple(getattr(layer, "slot_rect_uv", (0.0, 0.0, 1.0, 1.0)))

            # Residency-filtered at the point of construction, mirroring
            # image_compare's build_array_draw_plan (which filters via
            # tile_service.slot_for inside its own pairing loop rather than
            # in a caller-side patch): build_slot_array_tiles itself returns
            # every tile the current viewport *wants* regardless of upload
            # status (needed as-is by its unit tests, which assert against a
            # registered-but-nothing-yet-uploaded grid), so any caller that
            # treats its output as "what's actually drawable" -- both the
            # promotion check below and the fallback-coverage check -- must
            # filter to residency itself. Doing it once here, right after
            # the call, keeps every downstream use (`tiles_for_key`, the
            # promotion check, the coverage denominator) consistent instead
            # of each computing its own filtered view (a previous version of
            # this function only filtered for the coverage check, leaving
            # `tiles_for_key`/the promotion check reading the unfiltered
            # list -- harmless there since the per-instance loop below
            # already re-checks `slot_for` before drawing, but inconsistent
            # with image_compare's stronger single-filtered-list invariant).
            current_tiles = [
                tile
                for tile in build_slot_array_tiles(tile_service, key, pan, fit, layer.zoom)
                if tile_service.slot_for(key, tile.index) is not None
            ]
            current_items: list[tuple[object, SlotArrayTile]] = [
                (key, tile) for tile in current_tiles
            ]
            # Fallback-LOD (docs/dev/rendering/tile-array-atlas-plan.md
            # Phase 9, mirrors the fixed-pair render tab's render() array-path
            # branch): a key promotes to "last good" once its own target is
            # fully uploaded; otherwise, if a previous key's tiles are still
            # around (protected in ``_realize_tile_residency``), draw
            # whatever of its footprint the current (possibly partial)
            # tile set doesn't already cover, underneath the current tiles.
            key_more_pending = self._key_more_pending.get(key, False)
            old_key = self._last_good_key.get(sid)

            def _build_fallback_items(prior_key, _pan=pan, _fit=fit, _zoom=layer.zoom):
                raw = [
                    tile
                    for tile in build_slot_array_tiles(
                        tile_service, prior_key, _pan, _fit, _zoom
                    )
                    if tile_service.slot_for(prior_key, tile.index) is not None
                ]
                return [(prior_key, tile) for tile in raw]

            def _drop_covered(fallback_items, current_items, _old_key=old_key):
                # Coverage must be computed against tiles that are actually
                # GPU-resident, not merely targeted this frame -- see the
                # comment above `current_tiles`. Filtering the fallback set
                # too (not just the current one) matches the fixed-pair
                # render tab's invariant that a plan handed to
                # drop_covered_fallback_* never contains an item that
                # couldn't actually be drawn (found via a log showing
                # instance_count=1 right after a slot-swap: 1599 of 1600
                # "current" tiles had no array slot yet, but still zeroed
                # out the entire 4-tile fallback plan when only the current
                # side was filtered).
                fallback_tiles = [tile for _, tile in fallback_items]
                current_rects = [tile for _, tile in current_items]
                kept = drop_covered_fallback_tiles(fallback_tiles, current_rects)
                return [(_old_key, tile) for tile in kept]

            new_last_good_key, tiles_for_key = resolve_fallback_lod(
                key=key,
                current_items=current_items,
                more_pending=key_more_pending,
                last_good_key=old_key,
                build_fallback_items=_build_fallback_items,
                drop_covered=_drop_covered,
            )
            self._last_good_key[sid] = new_last_good_key
            # A4 swap hardening: a promoted (fully uploaded) new key covers
            # the slot on the array path, so a pre-swap plain preview kept
            # alive by _upload_slot can finally be released (no-op unless
            # this slot actually swapped -- see _pending_plain_cleanup).
            self._release_promoted_plain_preview(sid, new_last_good_key, key)

            rhi_render_debug(
                "mc-array-plan sid=%s key=%s current_tiles=%s fallback_used=%s "
                "tiles_for_key=%s slot_rect=%s",
                sid, key, len(current_tiles), len(tiles_for_key) - len(current_tiles),
                [(k, t.index, t.tile_rect) for k, t in tiles_for_key], slot_rect,
            )
            for item_key, tile in tiles_for_key:
                slot = tile_service.slot_for(item_key, tile.index)
                if slot is None:
                    continue
                array_index, gpu_layer = slot
                if array_index != 0:
                    # Never expected in practice -- see _ARRAY_CAPACITY; this
                    # pass only ever builds/binds tile_arrays[0] (mirrors
                    # image_compare's ensure_array_srb). Dropped tiles are
                    # retried next frame once eviction/upload catches up.
                    continue
                content_size = tile_service.content_size_for(item_key, tile.index)
                content_scale = _content_scale(content_size)
                rhi_render_debug(
                    "mc-array-instance sid=%s item_key=%s index=%s array_index=%s "
                    "layer=%s tile_rect=%s content_size=%s content_scale=%s",
                    sid, item_key, tile.index, array_index, gpu_layer,
                    tile.tile_rect, content_size, content_scale,
                )
                if tile_dump_enabled():
                    row, col = tile.index
                    log_tile_event(
                        "array.instance",
                        sid=sid,
                        item_key=str(item_key),
                        row=row,
                        col=col,
                        row_parity=row % 2,
                        col_parity=col % 2,
                        array_index=array_index,
                        layer=gpu_layer,
                        tile_rect=tile.tile_rect,
                        slot_rect=slot_rect,
                        content_size=content_size,
                        content_scale=content_scale,
                        pan=pan,
                        fit=fit,
                        zoom=float(layer.zoom),
                        instance_ordinal=len(instances),
                    )
                bbox = _instance_bbox(
                    pan=pan,
                    fit=fit,
                    zoom=float(layer.zoom),
                    tile_rect=tile.tile_rect,
                    slot_rect=slot_rect,
                    letterbox=letterbox,
                )
                instances.append(
                    _pack_array_instance(
                        pan_fit=(pan[0], pan[1], fit[0], fit[1]),
                        zoom=float(layer.zoom),
                        tile_rect=tile.tile_rect,
                        slot_rect=slot_rect,
                        content_scale=content_scale,
                        layer=gpu_layer,
                        bbox=bbox,
                    )
                )
        self.array_draw_instance_count = len(instances)
        rhi_render_debug(
            "mc-array-plan-summary instance_count=%d", self.array_draw_instance_count
        )
        if not instances:
            return
        assert self.array_resources is not None
        self.array_resources.ensure_array_pipeline(renderer.host.renderTarget())
        self.array_resources.ensure_array_instance_capacity(len(instances))
        updates.updateDynamicBuffer(
            self.array_resources.array_uniform_buffer,
            0,
            _pack_array_uniforms(ctx.clip_matrix, letterbox),
        )
        updates.updateDynamicBuffer(
            self.array_resources.array_instance_buffer, 0, b"".join(instances)
        )

    def record(self, command_buffer, widget, ctx) -> None:
        """Contract-shape draw (mirrors image_compare's
        ``magnifier_pass.record(command_buffer, widget, ctx)``): reads only
        ``ctx`` plus this pass's own prepared state.
        """
        if not ctx.projected_layers or not self.slot_resources.slot_vertex_buffers:
            return
        fb_w, fb_h = ctx.framebuffer_size
        if self._use_array_this_frame:
            assert self.array_resources is not None
            if (
                self.array_draw_instance_count <= 0
                or self.array_resources.array_pipeline is None
            ):
                return
            command_buffer.setGraphicsPipeline(self.array_resources.array_pipeline)
            command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
            command_buffer.setVertexInput(
                0,
                [
                    (self.slot_resources.slot_vertex_buffers[0], 0),
                    (self.array_resources.array_instance_buffer, 0),
                ],
            )
            command_buffer.setShaderResources(self.array_resources.array_srb)
            command_buffer.draw(4, self.array_draw_instance_count)
            return
        command_buffer.setGraphicsPipeline(self.slot_resources.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
        command_buffer.setVertexInput(
            0, [(self.slot_resources.slot_vertex_buffers[0], 0)]
        )
        stride = self.slot_resources._slot_uniform_stride
        for index in range(len(ctx.projected_layers)):
            srbs = (
                self._resolved_tile_srbs[index]
                if index < len(self._resolved_tile_srbs)
                else []
            )
            for item_index, srb in enumerate(srbs):
                if srb is None:
                    continue
                command_buffer.setShaderResources(srb, 1, (0, item_index * stride))
                command_buffer.draw(4)

    def _release_slot(self, tile_service, sid: int) -> None:
        self.slot_pixel_sources.pop(sid, None)
        self._pending_plain_cleanup.discard(sid)
        tile_service.invalidate_source(sid)
        residency.forget_slot(
            tile_service,
            sid,
            last_good_key=self._last_good_key,
            key_more_pending=self._key_more_pending,
            slot_lod_keys=self._slot_lod_keys,
        )
        self.slot_resources.destroy_slot_textures(sid, keep=frozenset())
        self.slot_resources.purge_tile_srbs_for_slot(sid)

    def upload_tile(self, renderer, tile_key: object, image, updates) -> None:
        """Single plain-path upload funnel for the swap machine.

        Every 1x1 tile upload this pass performs outside the budgeted
        residency loop (the eager single-upload fast path in
        ``_apply_swap_spec``) goes through here, into ``slot_resources``
        -- the tab never mints tile textures itself (see
        ``tests/contracts/test_no_private_grid.py``). The E1 hook seam
        pins this signature alongside ``resolve_swap_spec``.
        """
        self.slot_resources.upload_tile(renderer, tile_key, image, updates)

    def resolve_swap_spec(
        self,
        tile_service,
        sid: int,
        source: TiledPixelStore | QImage,
    ) -> _SwapSpec | None:
        """Resolves one ``(sid, source)`` upload into a swap decision.

        Pure: reads only ``slot_pixel_sources`` and
        ``tile_service.grid_for`` -- performs no rekey/register/upload, so
        calling it twice (or discarding the result) is always safe. Returns
        ``None`` for a true duplicate upload (same object already applied),
        a ``_SwapSpec`` otherwise. The E1 hook seam pins this signature
        alongside ``upload_tile``.
        """
        if self.slot_pixel_sources.get(sid) is source:
            # `pending_uploads` can carry more than one entry for the same
            # (sid, source) pair queued within one frame (canvas_widget can
            # call queue_upload for a slot more than once before the next
            # apply_pending_texture_ops flush) -- already a same-key no-op
            # before the rekey logic below existed, but that logic is NOT
            # idempotent under a duplicate call: the first call rekeys the
            # genuinely-old grid to `fallback_key` and registers a fresh,
            # still-empty grid under `sid`; a second call for the exact same
            # source then sees THAT fresh empty grid as "old content worth
            # preserving" and rekeys it over the real fallback, discarding
            # the one content worth keeping (found via a log showing the
            # rekeyed fallback grid's tiles at native 1/40 resolution
            # instead of the preview's 1/2 -- i.e. the preview never
            # survived to be drawn at all). Skip entirely once this exact
            # source is already applied.
            return None
        size = pixel_source_size(source)
        old_source = self.slot_pixel_sources.get(sid)
        old_grid = tile_service.grid_for(sid)
        old_is_multi = old_grid is not None and (
            old_grid.rows > 1 or old_grid.columns > 1
        )
        if old_grid is not None:
            fallback_key: object | None = LevelKey(sid, _PREVIOUS_GENERATION_LEVEL)
        else:
            fallback_key = None
        needs_backfill = (
            old_grid is not None
            and not old_is_multi
            and old_source is not None
        )
        return _SwapSpec(
            sid=sid,
            size=size,
            old_source=old_source,
            old_is_multi=old_is_multi,
            fallback_key=fallback_key,
            needs_backfill=needs_backfill,
        )

    def _apply_swap_spec(
        self,
        renderer,
        tile_service,
        sid: int,
        source: TiledPixelStore | QImage,
        spec: _SwapSpec,
        updates,
    ) -> None:
        """Performs a resolved swap in the original mutation order.

        Owns the rekey ordering, the same-key size-change fallback
        preservation, and the 1x1->multi backfill trigger -- semantics are
        bit-identical to the pre-split ``_upload_slot`` body; only the
        decision half moved into ``resolve_swap_spec`` and the plain upload
        into ``upload_tile``.
        """
        # A source swap (e.g. preview QImage -> real TiledPixelStore)
        # invalidates any LOD level built against the *old* source below --
        # those pyramids no longer apply. It deliberately does NOT reset
        # `last_good_key[sid]` when that fallback still names bare `sid`
        # itself: image_compare has no equivalent reset on its own source
        # swap, and wiping it here forced every same-key size change (e.g.
        # this exact preview -> full-resolution swap) to go through a fully
        # empty slot instead of being able to fall back to whatever was
        # already resident, unlike image_compare's swap. See
        # `forget_stale_lod_keys` for the corrected, narrower invalidation.
        residency.forget_stale_lod_keys(
            tile_service,
            sid,
            last_good_key=self._last_good_key,
            key_more_pending=self._key_more_pending,
            slot_lod_keys=self._slot_lod_keys,
        )
        if spec.fallback_key is not None:
            # Any same-``sid`` content swap (multi->multi, 1x1->multi,
            # multi->1x1, 1x1->1x1) rekeys the still-good old content
            # under a distinct fallback key first, so the existing
            # fallback-LOD machinery (``_last_good_key`` /
            # ``_prepare_array_plan``) can draw it underneath the new grid
            # until covered -- exactly like a pyramid level transition.
            # (Previously only the multi->multi case rekeyed, and the
            # 1x1->multi case additionally destroyed the only visible
            # content up front -- see below.) For 1x1->1x1 the rekey only
            # moves near-empty bookkeeping: the eager plain upload below
            # redraws the same frame, so there is no blank either way.
            #
            # ``_key_more_pending`` is keyed by the *value* of the resolved
            # LOD key, not by content generation -- and while no pyramid
            # exists yet, both the old preview and the brand-new grid
            # resolve to the same bare ``sid`` key (lod_key_and_source's
            # no-pyramid fallback). Left alone, the previous generation's
            # now-stale "fully uploaded" flag for that same key leaks
            # forward and satisfies _prepare_array_plan's promotion check
            # after just the new grid's first tile lands, discarding the
            # fallback we just set up above before it ever gets to draw
            # (confirmed via log: instance_count=1 the very next frame,
            # zero fallback tiles). Force it back to "still pending" so the
            # promotion can't fire until this frame's own residency pass
            # reports real completion for the new content.
            tile_service.invalidate_source(spec.fallback_key)
            tile_service.rekey_source(sid, spec.fallback_key)
            self._last_good_key[sid] = spec.fallback_key
            self._key_more_pending[spec.fallback_key] = False
            self._key_more_pending[sid] = True
        grid = tile_service.register_source(sid, spec.size)
        self.slot_pixel_sources[sid] = source
        self.slot_resources.purge_tile_srbs_for_slot(sid)
        host_cache = self._host_cache(renderer)
        if grid.rows == 1 and grid.columns == 1:
            tile_key = tile_service.tile_key(sid, 0, 0)
            self.slot_resources.destroy_slot_textures(sid, keep={tile_key})
            qimage = host_cache.qimage_from_source(source, residency._slot_host_key(sid))
            self.upload_tile(renderer, tile_key, qimage, updates)
            # A same-frame plain overwrite subsumes any deferred cleanup
            # from an earlier swap -- the texture now holds new content.
            self._pending_plain_cleanup.discard(sid)
            return
        if spec.needs_backfill:
            # 1x1-preview -> multi-full: the old content was plain-only
            # (never array-resident), so the rekey above preserved
            # bookkeeping but nothing drawable on the array path -- and the
            # new grid's own tiles still trickle in over several budgeted
            # residency passes. Backfill the preview's single tile into the
            # array under the fallback key so the slot keeps showing the
            # preview underneath until the new grid covers it. The stale
            # plain texture itself is deliberately NOT destroyed here
            # (destroy-before-upload was the blank window); it is released
            # once the new key promotes -- see ``_prepare_array_plan``.
            self._backfill_plain_preview_to_array(
                renderer, tile_service, host_cache, updates,
                sid, self._last_good_key[sid], spec.old_source,
            )
            self._pending_plain_cleanup.add(sid)

    def _upload_slot(
        self,
        renderer,
        tile_service,
        sid: int,
        source: TiledPixelStore | QImage,
        updates,
    ) -> None:
        """Thin orchestrator over the swap machine: resolve, then apply.

        The engine loop (``apply_pending_texture_ops``) drives uploads;
        this pass only resolves per-upload specs (``resolve_swap_spec``),
        funnels tile uploads (``upload_tile``), and reacts through the
        backfill/promotion tab hooks -- the machine's semantics (rekey
        ordering, backfill conditions, fallback preservation) live in
        those pieces unchanged.
        """
        spec = self.resolve_swap_spec(tile_service, sid, source)
        if spec is None:
            return
        self._apply_swap_spec(renderer, tile_service, sid, source, spec, updates)

    def _backfill_plain_preview_to_array(
        self,
        renderer,
        tile_service,
        host_cache,
        updates,
        sid: int,
        fallback_key: object,
        old_source,
    ) -> None:
        """Upload a plain-only 1x1 preview into the array under ``fallback_key``.

        Backfill tab hook for the swap machine: called from
        ``_apply_swap_spec`` on a 1x1-preview -> multi-full swap:
        the rekey preserved the old grid's bookkeeping, but a preview that
        only ever lived as a plain ``slot_textures`` entry has no array
        slot, so the fallback-LOD draw in ``_prepare_array_plan`` would
        filter it out and the slot would still go blank. Uploading its
        single tile here makes the preview drawable underneath the new
        grid until covered. Best-effort by design: any failure (headless
        fakes, degenerate image) just skips the backfill and degrades to
        the pre-A4 progressive fill-in -- never breaks the swap itself.
        """
        try:
            if tile_service.slot_for(fallback_key, (0, 0)) is not None:
                # Already array-resident (promoted 1x1 from an array-path
                # frame) -- the rekeyed content draws as-is, nothing to do.
                return
            self._ensure_array_resources(renderer)
            assert self.array_resources is not None
            image = host_cache.qimage_from_source(
                old_source, residency._slot_host_key(fallback_key)
            )
            if image is None or image.isNull():
                return
            host_cache.store(residency._slot_tile_host_key(fallback_key, 0, 0), image)
            self.array_resources.upload_tile_to_array(
                tile_service,
                fallback_key,
                (0, 0),
                image,
                updates,
                dirty_layers=self._dirty_layers_this_frame,
            )
        except Exception:
            logger.debug(
                "mc swap: preview backfill skipped for sid=%s", sid,
                exc_info=True,
            )

    def _release_promoted_plain_preview(
        self, sid: int, promoted_key: object, current_key: object
    ) -> None:
        """Drop a swapped slot's stale plain preview once the array covers it.

        Called from ``_prepare_array_plan`` on promotion
        (``new_last_good_key == key`` = this frame's plan is a stable end
        state): the new content is fully uploaded, so the pre-swap plain
        texture kept alive by ``_upload_slot`` is dead weight. Only slots
        recorded in ``_pending_plain_cleanup`` are touched -- a
        steady-state 1x1 slot's own plain texture (still needed by future
        plain-path frames) is never in that set.
        """
        if promoted_key == current_key and sid in self._pending_plain_cleanup:
            self.slot_resources.destroy_slot_textures(sid, keep=frozenset())
            self._pending_plain_cleanup.discard(sid)

    def generate_all_dirty_mips(
        self,
        renderer,
        command_buffer,
        dirty_layers: dict[int, set[int]],
        time_budget_ms: float | None = None,
    ) -> dict[int, set[int]]:
        if not dirty_layers or not self.slot_resources.slot_vertex_buffers:
            return {}
        assert self._mip_cascade is not None
        return self._mip_cascade.generate_all_dirty_mips(
            command_buffer,
            self.slot_resources.slot_vertex_buffers[0],
            dirty_layers,
            time_budget_ms,
        )

    def _realize_tile_residency(self, renderer, ctx, updates) -> None:
        self._ensure_array_resources(renderer)
        host_cache = self._host_cache(renderer)
        use_array, dirty_layers, key_incomplete_by_key, resolved_lod = residency.realize(
            renderer=renderer,
            ctx=ctx,
            updates=updates,
            slot_pixel_sources=self.slot_pixel_sources,
            array_resources=self.array_resources,
            slot_resources=self.slot_resources,
            host_cache=host_cache,
            slot_lod_keys=self._slot_lod_keys,
            last_good_key=self._last_good_key,
        )
        self._use_array_this_frame = use_array
        self._dirty_layers_this_frame = dirty_layers
        self._key_more_pending.update(key_incomplete_by_key)
        self._frame_resolved_lod = resolved_lod


# Contract-shape manifest for the scene's base pass:
# ``stack_role``/``visibility`` above declare order via stacking_policy.
# The live renderer takes its ``image_pass`` from this list (see
# scene/renderer.py) -- never instantiating ``BaseImagesPass`` directly --
# while still recording it first, ahead of the registry feature passes.
RENDER_PASSES: list[CanvasRenderPass] = [BaseImagesPass()]
