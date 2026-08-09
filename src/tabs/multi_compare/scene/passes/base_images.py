"""Base image tile QRhi pass for Multi Compare."""

from __future__ import annotations

import logging
import struct

from PySide6.QtGui import QImage, QRhiViewport

from shared.image_processing.tiled_pixel_store import (
    TiledPixelStore,
    pixel_source_size,
)
from shared.rendering.fallback_lod import resolve_fallback_lod
from shared.rendering.host_texture_cache import cache_for_host
from shared.rendering.lod import LevelKey
from shared.rendering.mip_cascade import MipCascadeGenerator
from shared.rendering.render_debug import rhi_render_debug
from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled
from shared.rendering.tile_geometry import _TILE_APRON_PX
from shared.rendering.tile_texture_service import DEFAULT_MAX_ARRAY_SIZE
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
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass

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


def _host_key_repr(key: object) -> str:
    if isinstance(key, LevelKey):
        return f"{int(key.base)}_lvl{int(key.level)}"
    return str(int(key))


def _slot_host_key(key: object) -> str:
    return f"slot_{_host_key_repr(key)}"


class BaseImagesPass(CanvasRenderPass):
    """Owns image textures, tile pipeline, uniforms, and draw recording.

    Full-res slot pixels live in :class:`TiledPixelStore` (session state).
    This pass keeps GPU residency via ``TileTextureService`` and a bounded
    host-side ``HostTextureUploadCache`` on the canvas widget for decoded
    QImage uploads — never an uncapped full-res QImage dict.

    A slot's source may also be a bounded ``QImage`` progressive preview
    (``CompareSlot.is_preview_only``) while the real ``TiledPixelStore`` is
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
    """

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
        # _prepare_array_plan/finish_prepare's plain-path loop reuse it
        # verbatim instead of independently re-resolving it later in the same
        # frame, which could disagree if a background pyramid build landed a
        # new level in between (see residency.py's realize() docstring/the
        # comment at its `resolved_lod` local).
        self._frame_resolved_lod: dict[int, tuple[object, object | None]] = {}

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
        self._renderer = renderer
        self.array_resources = ArrayResources(
            rhi_getter=lambda: self._renderer.rhi,
            sampler_getter=lambda name: self._renderer.sampler,
            load_shader=load_shader,
            layer_px=_ARRAY_LAYER_PX,
            array_capacity=_ARRAY_CAPACITY,
            name_prefix="multi-compare",
        )
        self._mip_cascade = MipCascadeGenerator(
            rhi_getter=lambda: self._renderer.rhi,
            tile_arrays=self.array_resources.tile_arrays,
            ensure_tile_array=lambda index: self.array_resources._ensure_tile_array(index),
            sampler_getter=lambda: self._renderer.sampler,
            layer_px=_ARRAY_LAYER_PX,
            name_prefix="multi-compare",
        )

    def initialize(self, renderer, target) -> None:
        self.slot_resources.set_uniform_stride(renderer.rhi.ubufAligned(SLOT_UNIFORM_SIZE))
        self._ensure_array_resources(renderer)
        self.slot_resources.ensure_pipeline(renderer, target)

    def release(self) -> None:
        if self._mip_cascade is not None:
            self._mip_cascade.release()
        self.slot_resources.release()
        if self.array_resources is not None:
            self.array_resources.release()
        self.__init__()

    def apply_pending_texture_ops(self, renderer, updates) -> None:
        tile_service = renderer.tile_service
        for sid in self.pending_removes:
            self._release_slot(tile_service, sid)
        self.pending_removes.clear()
        for sid, source in self.pending_uploads:
            self._upload_slot(renderer, tile_service, sid, source, updates)
        self.pending_uploads.clear()

    def realize_residency(self, renderer, ctx, updates) -> None:
        """First half of the old ``prepare()``: everything that must be
        submitted to the GPU (``command_buffer.resourceUpdate``) before
        ``generate_all_dirty_mips`` can safely sample this frame's
        just-uploaded tile content -- see ``MultiCompareRhiRenderer.render``'s
        sequencing and ``generate_all_dirty_mips``'s docstring."""
        self.slot_resources.ensure_slot_resources(renderer, len(ctx.projected_layers))
        # Shared fullscreen quad — letterbox + slot cell are UV uniforms.
        # Also the vertex input generate_all_dirty_mips' downsample pass
        # draws with, so it must be written in this same pre-mips batch.
        if self.slot_resources.slot_vertex_buffers:
            updates.updateDynamicBuffer(
                self.slot_resources.slot_vertex_buffers[0], 0, FULLSCREEN_VERTICES
            )
        self._realize_tile_residency(renderer, ctx, updates)

    def take_dirty_layers(self) -> dict[int, set[int]]:
        """Pops this frame's array-index/layer set dirtied by
        ``_upload_tile_to_array`` during ``realize_residency`` -- read by
        ``MultiCompareRhiRenderer.render`` once, between submitting the tile
        uploads and running ``generate_all_dirty_mips``."""
        dirty_layers = self._dirty_layers_this_frame
        self._dirty_layers_this_frame = {}
        return dirty_layers

    def finish_prepare(self, renderer, ctx, updates) -> None:
        """Second half of the old ``prepare()``: builds this frame's draw
        plan (array instances or per-tile uniforms/SRBs) -- called with a
        fresh ``updates`` batch, after ``realize_residency``'s batch has
        been submitted and any dirty mips regenerated."""
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

    def record(self, renderer, ctx, command_buffer) -> None:
        if not ctx.projected_layers or not self.slot_resources.slot_vertex_buffers:
            return
        fb_w, fb_h = ctx.framebuffer_size
        if self._use_array_this_frame:
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

    def _upload_slot(
        self,
        renderer,
        tile_service,
        sid: int,
        source: TiledPixelStore | QImage,
        updates,
    ) -> None:
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
            return
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
        size = pixel_source_size(source)
        old_grid = tile_service.grid_for(sid)
        if old_grid is not None and (old_grid.rows > 1 or old_grid.columns > 1):
            # The sid-keyed grid about to be replaced (typically a small
            # preview QImage already past LIVE_TILE_EXTENT, so already on
            # the array path -- see module comment on _ARRAY_LAYER_PX) is
            # otherwise wiped instantly by register_source's reset_source
            # below, with nothing shown while the replacement source's own
            # tiles trickle in over several budgeted _realize_tile_residency
            # calls (the [slot-swap] log further down used to flag exactly
            # this gap). forget_stale_lod_keys above only protects genuine
            # LevelKey transitions -- it's blind to this same-key ``sid``
            # content swap, since last_good_key[sid] stays literally equal
            # to sid before and after, so _prepare_array_plan's `old_key !=
            # key` fallback check never fires for it. Rekey the still-good
            # old content under a distinct key first so the existing
            # fallback-LOD machinery (_last_good_key / _prepare_array_plan)
            # draws it underneath the new grid until covered, exactly like
            # a pyramid level transition.
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
            fallback_key = LevelKey(sid, _PREVIOUS_GENERATION_LEVEL)
            tile_service.invalidate_source(fallback_key)
            tile_service.rekey_source(sid, fallback_key)
            self._last_good_key[sid] = fallback_key
            self._key_more_pending[fallback_key] = False
            self._key_more_pending[sid] = True
        grid = tile_service.register_source(sid, size)
        self.slot_pixel_sources[sid] = source
        self.slot_resources.purge_tile_srbs_for_slot(sid)
        host_cache = self._host_cache(renderer)
        if grid.rows == 1 and grid.columns == 1:
            tile_key = tile_service.tile_key(sid, 0, 0)
            self.slot_resources.destroy_slot_textures(sid, keep={tile_key})
            qimage = host_cache.qimage_from_source(source, _slot_host_key(sid))
            self.slot_resources.upload_tile(renderer, tile_key, qimage, updates)
            return
        textures_before = len(self.slot_resources.slot_textures)
        self.slot_resources.destroy_slot_textures(sid, keep=frozenset())
        textures_after = len(self.slot_resources.slot_textures)
        logger.debug(
            "[slot-swap] sid=%s new %dx%d grid: destroyed %d pre-existing plain "
            "texture(s) (slot_textures %d -> %d) before this frame's array-path "
            "content has any tile uploaded -- slot renders blank until "
            "_realize_tile_residency's budgeted upload (this same call) lands "
            "the first tile(s)",
            sid, grid.rows, grid.columns, textures_before - textures_after,
            textures_before, textures_after,
        )

    def generate_all_dirty_mips(
        self,
        renderer,
        command_buffer,
        dirty_layers: dict[int, set[int]],
        time_budget_ms: float | None = None,
    ) -> dict[int, set[int]]:
        if not dirty_layers or not self.slot_resources.slot_vertex_buffers:
            return {}
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
