from __future__ import annotations

import logging
import time
from types import SimpleNamespace

from PySide6.QtGui import QRhiCommandBuffer, QRhiDepthStencilClearValue, QRhiViewport

from ui.canvas_infra.rhi.rhi_backend import query_max_texture_size
from ui.canvas_infra.rhi.render_common import should_render_blank_white
from ui.canvas_infra.rhi.render_executor import iter_active_render_passes
from shared.rendering.tile_constants import (
    LOD_FETCH_SETTLE_MS,
    MIPS_CASCADE_TIME_BUDGET_MS,
)
from shared.rendering.image_identity import image_uid
from shared.rendering.tile_debug import (
    log_tile_event,
    tile_dump_enabled,
)
from shared.rendering.tile_texture_service import (
    TileTextureService,
    _tile_indices_with_margin,
)
from ..render_context import build_render_runtime_context
from ..texture_parts.tile_geometry import (
    _apron_rect,
    _TILE_APRON_PX,
    _viewport_zoom_offset_for_tile,
    _visible_side_image_rect,
)
from shared.rendering.fallback_lod import resolve_fallback_lod
from shared.rendering.glass_panel import GlassPanelRenderer
from ._debug import rhi_render_debug
from .draw_plan import (
    _covered_fraction,
    _to_common_space,
    build_array_draw_plan,
    drop_covered_fallback_items,
    resolve_lod_texture_keys,
)
from .residency import _TILE_CACHE_BUDGET_BYTES
from .resources import (
    _ARRAY_LAYER_PX,
    _LIVE_TILE_EXTENT,
    RhiResources,
    pack_array_instance,
)
from .uniforms import pack_array_uniforms, pack_base_uniforms

logger = logging.getLogger("ImproveImgSLI")

__all__ = [
    "RhiCanvasRenderer",
    "pack_base_uniforms",
    "_apron_rect",
    "_ARRAY_LAYER_PX",
    "_TILE_APRON_PX",
    "_TILE_CACHE_BUDGET_BYTES",
    "_tile_indices_with_margin",
    "_viewport_zoom_offset_for_tile",
    "_visible_side_image_rect",
]


def _union_capture_uv_rect(overlay) -> tuple[float, float, float, float] | None:
    """Union of every active magnifier slot's capture window
    (``uv_rect``/``uv_rect2``, already a zoom/pan-invariant fraction of the
    full source image -- see ``layout_plan.py``'s ``_capture_geometry``),
    used as the ``capture_uv_rect`` override for the magnifier's ``source_*``
    residency call. Returns ``None`` if there are no slots to union (caller
    then falls back to the canvas-viewport-derived visible rect)."""
    left = top = 1.0
    right = bottom = 0.0
    found = False
    for slot in getattr(overlay, "gpu_slots", ()) or ():
        if not slot:
            continue
        for uv_rect in (slot.get("uv_rect"), slot.get("uv_rect2")):
            if uv_rect is None:
                continue
            l, t, r, b = uv_rect
            left = min(left, l)
            top = min(top, t)
            right = max(right, r)
            bottom = max(bottom, b)
            found = True
    if not found:
        return None
    return (max(0.0, left), max(0.0, top), min(1.0, right), min(1.0, bottom))


class RhiCanvasRenderer:
    """Composition root: constructs/tears down ``RhiResources`` +
    ``TileTextureService`` + feature passes, and sequences each frame's
    render(). Every line here is sequencing, not logic -- decisions
    (residency, eviction, geometry, uniform layout, SRB caching) live in
    exactly one of ``RhiResources``/``TileTextureService``/``draw_plan``/
    ``uniforms``, never partially here. See docs/dev/RHI_RENDERER_REFACTOR.md.
    """

    def __init__(self) -> None:
        self.rhi = None
        self.resources = RhiResources()
        self.tile_service = TileTextureService()
        self.feature_passes: list[object] = []
        self.glass_panel_renderer = GlassPanelRenderer(name_prefix="image_compare")
        # docs/dev/rendering/tile-array-atlas-plan.md Phase 2 fallback-LOD
        # finding: the last texture_keys/diff_key combo that produced a
        # non-empty array_draw_plan, kept around so a rapid LOD-level
        # transition that outpaces the tile upload budget can keep showing
        # this previous level's content instead of a blank frame -- see
        # render()'s array-path branch.
        self._last_good_texture_keys: tuple[object, object] | None = None
        self._last_good_diff_key: object | None = None
        # docs/dev/rendering/tile-array-atlas-plan.md Phase 9: mip-cascade
        # groups deferred past MIPS_CASCADE_TIME_BUDGET_MS by
        # generate_all_dirty_mips, carried forward and retried on the next
        # render() call (merged into that frame's own dirty_layers).
        self._pending_dirty_layers: dict[int, set[int]] = {}
        # docs/dev/rendering/tile-array-atlas-plan.md Phase 9 "reduce data
        # volume per transition": the LOD target actually committed for
        # fetching, held at its last value until resolve_lod_texture_keys'
        # raw per-frame answer has been stable for LOD_FETCH_SETTLE_MS (see
        # that constant's docstring) -- see render()'s commit logic below.
        self._lod_pending_keys: tuple[object, object] | None = None
        self._lod_pending_since: float = 0.0
        self._lod_committed_keys: tuple[object, object] | None = None
        # Identity (id()) of the PIL/TiledPixelStore objects `texture_keys`
        # resolved against when _lod_committed_keys was last set. Detects an
        # actual image replacement (not just a LOD level change on the same
        # still-loaded image) so the settle delay below can be bypassed for
        # it -- see render()'s commit logic.
        self._lod_committed_source_ids: tuple[int, int] | None = None

    # -- backward-compatible views onto RhiResources' GPU state, used by
    # feature passes (e.g. magnifier) that read tile textures directly. --
    @property
    def textures(self) -> dict[object, object]:
        return self.resources.textures

    @property
    def texture_sizes(self) -> dict[object, object]:
        return self.resources.texture_sizes

    def initialize(self, widget, command_buffer: QRhiCommandBuffer) -> None:
        new_rhi = widget.rhi()
        if new_rhi is None:
            raise RuntimeError("QRhiWidget.initialize called without QRhi")
        # Qt calls initialize() again whenever the widget resizes (its own
        # backing render target needs reallocating at the new pixel size),
        # not only on a genuine context loss/backend change. Every prior
        # resize paid for a full self.release() + rebuild here: the entire
        # tile array, every tile's residency bookkeeping, and (most
        # expensively -- ~1s+, confirmed via cProfile) the mip-cascade's
        # scratch QRhiTextureRenderTargets, none of which depend on the
        # widget's own output size at all. Skip all of that when `rhi` is
        # the same object we already initialized against -- see
        # docs/dev/rendering/qrhi-gotchas.md
        # #canvas-resize-tears-down-the-whole-tile-array-on-every-resize.
        if new_rhi is self.rhi and self.feature_passes:
            return
        self.release()
        self.rhi = new_rhi
        # docs/dev/TILED_RENDERING_DESIGN.md Phase 2: fixed tile size
        # (_LIVE_TILE_EXTENT), clamped by the backend's real max texture size
        # as a defensive floor only — real backends support far more than
        # 2048px, so this clamp should never actually bind in practice.
        self.tile_service = TileTextureService(
            max_tile_extent=min(_LIVE_TILE_EXTENT, query_max_texture_size(self.rhi))
        )
        self.resources.initialize(self.rhi, widget, command_buffer)
        self.glass_panel_renderer.initialize(self.rhi)

        from tabs.image_compare.canvas.registry import registry

        self.feature_passes = [
            type(render_pass)() for render_pass in registry().get_render_passes()
        ]
        target = widget.renderTarget()
        rhi_render_debug(
            "initialize widget=%s size=%dx%d target_px=%s api=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target.pixelSize() if target is not None else None,
            getattr(widget.api(), "name", "unknown"),
        )
        for render_pass in self.feature_passes:
            render_pass.initialize(self.rhi, target)
        self.resources.restore_texture_uploads(widget)

    def release(self) -> None:
        self.resources.release()
        self.glass_panel_renderer.release()
        for render_pass in self.feature_passes:
            render_pass.release()
        self.__init__()

    def render(self, widget, command_buffer, clear_color) -> bool:
        """Record one frame. Returns True after a completed beginPass/endPass.

        Early skips (no target / no rhi) return False so callers must not
        treat the frame as presented — Image Compare startup gates and the
        Windows D3D first-present path depend on this.
        """
        target = widget.renderTarget()
        if target is None or self.rhi is None:
            rhi_render_debug(
                "render skip widget=%s target=%r rhi=%r",
                f"{type(widget).__name__}@{id(widget):x}",
                target,
                self.rhi,
            )
            return False

        updates = self.rhi.nextResourceUpdateBatch()
        # Reset once per frame, not inside realize_tile_plan itself: a
        # same-slot content swap can be rekeyed either by apply_pending_uploads
        # below (RhiResources.upload_source, the eager whole-image/diff-role
        # upload path) or by realize_tile_plan further down (the lazy
        # TiledPixelStore path) -- both write into this same dict so the
        # fallback-LOD substitution below sees whichever one fired this frame.
        self.resources.residency.last_rekeyed_keys = {}
        self.resources.apply_pending_uploads(widget, self.tile_service, updates)
        ctx = build_render_runtime_context(widget)
        base_image = getattr(ctx.render_list, "base_image", None)
        should_draw = (
            base_image is not None
            and any(ctx.images_uploaded)
            and not should_render_blank_white(ctx.scene_frame)
        )
        target_size = target.pixelSize()
        rhi_render_debug(
            "render begin widget=%s widget=%dx%d target_px=%dx%d clear=rgba(%d,%d,%d,%d) "
            "images=%s should_draw=%s passes=%d fixed=%dx%d",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target_size.width(),
            target_size.height(),
            clear_color.red(),
            clear_color.green(),
            clear_color.blue(),
            clear_color.alpha(),
            list(ctx.images_uploaded),
            should_draw,
            len(self.feature_passes),
            widget.fixedColorBufferSize().width(),
            widget.fixedColorBufferSize().height(),
        )

        # Phase 3 (docs/dev/TILED_RENDERING_DESIGN.md): resolves to exactly
        # (base_image.zoom, base_image.zoom)/(pan_x, pan_y) — a no-op — when
        # ctx.canvas_* equals widget.width()/height()/0/0 (every render
        # outside tiled export). Safe to always compute and pass through.
        viewport_zoom, viewport_offset = _viewport_zoom_offset_for_tile(
            ctx.canvas_width,
            ctx.canvas_height,
            (
                ctx.canvas_offset_x,
                ctx.canvas_offset_y,
                ctx.canvas_offset_x + widget.width(),
                ctx.canvas_offset_y + widget.height(),
            ),
            base_zoom=(base_image.zoom, base_image.zoom) if base_image else (1.0, 1.0),
            base_offset=(
                (base_image.pan_offset_x, base_image.pan_offset_y)
                if base_image
                else (0.0, 0.0)
            ),
        )

        array_draw_plan: list = []
        dirty_layers: dict[int, set[int]] = {}
        if should_draw:
            texture_keys = (
                tuple(ctx.source_texture_ids)
                if base_image.use_hires
                else tuple(ctx.texture_ids)
            )
            sources = (
                tuple(widget.runtime_state._source_pil_images)
                if base_image.use_hires
                else tuple(ctx.stored_pil_images)
            )
            # Device px per logical px: DPR in live render, 1.0 during tiled
            # export (widget is sized to the tile's pixel footprint).
            scale_px = target_size.width() / float(max(1, widget.width()))
            raw_texture_keys = resolve_lod_texture_keys(
                texture_keys,
                sources,
                base_image,
                (ctx.canvas_width * scale_px, ctx.canvas_height * scale_px),
            )
            now = time.monotonic()
            if raw_texture_keys != self._lod_pending_keys:
                self._lod_pending_keys = raw_texture_keys
                self._lod_pending_since = now
            # image_uid, not id(): id() is a memory address that CPython can
            # (and does) reuse once the old source object is garbage
            # collected -- exactly what tends to happen right after a swap
            # discards the old source -- so a *second* swap could coincide
            # with the freed old address being handed to the new source
            # object, making source_changed below false-negative and commit
            # skip the immediate re-fetch it exists for, showing the stale
            # image under a doubly-stale key until the settle window and
            # residency catch up. image_uid tags each object with a
            # monotonic counter value once (via .info/an attribute) that
            # persists for that object's lifetime and is never reused.
            source_ids = (image_uid(sources[0]), image_uid(sources[1]))
            # An actual image replacement (not just a LOD level change on the
            # still-loaded image) must commit immediately rather than wait
            # out the settle delay: the settle delay's premise is that the
            # *previously committed* key's tiles are still valid, real
            # content worth protecting from a premature re-fetch churn (see
            # LOD_FETCH_SETTLE_MS's docstring) -- that premise is false the
            # instant the underlying source object changes, since the old
            # committed key (e.g. a bare, pre-pyramid key from the prior
            # image) then points at stale content. Holding it anyway made
            # realize_tile_plan re-register and tile the *new* image at full
            # source resolution under that stale bare key for the whole
            # settle window, instead of the small pyramid level
            # resolve_lod_texture_keys had already picked (docs/dev/
            # rendering/tile-array-atlas-plan.md Phase 9 "image swap tiles
            # full source under stale committed key" finding).
            source_changed = source_ids != self._lod_committed_source_ids
            if (
                self._lod_committed_keys is None
                or source_changed
                or (now - self._lod_pending_since) * 1000.0 >= LOD_FETCH_SETTLE_MS
            ):
                self._lod_committed_keys = raw_texture_keys
                self._lod_committed_source_ids = source_ids
            texture_keys = self._lod_committed_keys
            if tile_dump_enabled():
                log_tile_event(
                    "lod_commit",
                    source_ids=list(source_ids),
                    source_changed=source_changed,
                    raw_texture_keys=[str(k) for k in raw_texture_keys],
                    committed_texture_keys=[str(k) for k in texture_keys],
                    pending_since_ms=(now - self._lod_pending_since) * 1000.0,
                )
            diff_source_key = (
                ctx.diff_source_texture_id if ctx.diff_source_ready else None
            )
            sampler_name = (
                "nearest"
                if str(ctx.scene_frame.zoom_interpolation_method).upper() == "NEAREST"
                else "linear"
            )
            fallback_protect_keys = tuple(
                key
                for key in (
                    *(self._last_good_texture_keys or ()),
                    self._last_good_diff_key,
                )
                if key is not None
            )
            _debug_timing = tile_dump_enabled()
            _t0 = time.perf_counter() if _debug_timing else 0.0
            main_more_pending = self.resources.residency.realize_tile_plan(
                self.tile_service,
                widget,
                texture_keys,
                base_image,
                updates,
                diff_key=diff_source_key,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
                extra_protect_keys=fallback_protect_keys,
                dirty_layers=dirty_layers,
            )
            if _debug_timing:
                _dt = time.perf_counter() - _t0
                if _dt > 0.05:
                    log_tile_event(
                        "realize_tile_plan.timing", which="main", duration_s=_dt
                    )
            # Magnifier always samples source_* at level 0 when letterbox
            # sources are ready (see MagnifierPass.prepare), even while the
            # base canvas draws stored_* or a coarser pyramid LevelKey.
            # TiledPixelStore sources skip eager whole-image upload, so
            # realize the bare source keys whenever the overlay will bind
            # them and the base pass didn't already — otherwise content
            # binds the transparent placeholder while the border disk still
            # draws.
            overlay = getattr(ctx, "feature_overlay", None)
            _mag_branch_active = bool(
                texture_keys != tuple(ctx.source_texture_ids)
                and overlay is not None
                and overlay.gpu_active
                and ctx.source_images_ready
                and ctx.source_texture_ids[0]
                and ctx.source_texture_ids[1]
            )
            if tile_dump_enabled():
                _cap_uv = _union_capture_uv_rect(overlay) if overlay is not None else None
                log_tile_event(
                    "magnifier.residency_branch",
                    branch_active=_mag_branch_active,
                    texture_keys=[str(k) for k in texture_keys],
                    source_texture_ids=[str(k) for k in ctx.source_texture_ids],
                    viewport_zoom=list(viewport_zoom) if viewport_zoom is not None else None,
                    viewport_offset=list(viewport_offset) if viewport_offset is not None else None,
                    capture_uv_rect=list(_cap_uv) if _cap_uv is not None else None,
                )
            if _mag_branch_active:
                _t1 = time.perf_counter() if _debug_timing else 0.0
                self.resources.residency.realize_tile_plan(
                    self.tile_service,
                    widget,
                    tuple(ctx.source_texture_ids),
                    base_image,
                    updates,
                    diff_key=None,
                    capture_uv_rect=_union_capture_uv_rect(overlay),
                    dirty_layers=dirty_layers,
                )
                if _debug_timing:
                    _dt1 = time.perf_counter() - _t1
                    if _dt1 > 0.05:
                        log_tile_event(
                            "realize_tile_plan.timing",
                            which="magnifier_source",
                            duration_s=_dt1,
                        )
            # docs/dev/rendering/tile-array-atlas-plan.md: every grid,
            # including a 1x1 one, renders through the texture-array +
            # instanced pipeline (see build_array_draw_plan's docstring).
            current_array_plan = build_array_draw_plan(
                self.tile_service,
                texture_keys,
                base_image,
                diff_key=diff_source_key,
                sampler_name=sampler_name,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
            )
            # docs/dev/rendering/tile-array-atlas-plan.md Phase 2
            # fallback-LOD finding: a rapid mouse-wheel zoom burst can
            # cross a pyramid-level boundary faster than the upload
            # budget fills the new level's tiles in (see
            # realize_tile_plan's upload_deadline comment) -- not just to
            # fully empty (nothing co-resident on either side yet), but
            # also to a *partial* current_array_plan (e.g. only 1 of 4
            # needed tile pairs uploaded), which left the rest of the
            # screen blank and read as the camera "jumping" to wherever
            # that one tile happened to land. resolve_fallback_lod draws
            # the previous level's still-resident tiles (kept alive by
            # this frame's extra_protect_keys above) first, then the
            # current level's (possibly partial) tiles on top: with the
            # array pipeline's alpha-over blend and no depth test, draw
            # order alone decides the final pixel, so any tile the new
            # level has already uploaded replaces the stale one, and only
            # the still-missing regions fall back to the old level
            # instead of blanking.
            old_texture_keys = self._last_good_texture_keys
            last_good_key = (
                (old_texture_keys, self._last_good_diff_key)
                if old_texture_keys is not None
                else None
            )
            # A same-slot content swap (e.g. loading a new image into an
            # already-loaded side) never changes texture_keys/diff_source_key
            # themselves -- they're stable slot labels, not per-image
            # identity -- so the plain old_texture_keys comparison above
            # can't see it and last_good_key above is a no-op here. When
            # realize_tile_plan rekeys a slot's stale-sized old content
            # instead of dropping it (residency.py's last_rekeyed_keys),
            # substitute that key so resolve_fallback_lod treats this frame
            # as a genuine key change and draws the old content underneath
            # while the new content at the reused slot fills in.
            rekeyed = self.resources.residency.last_rekeyed_keys
            if rekeyed:
                last_good_key = (
                    tuple(rekeyed.get(k, k) for k in texture_keys),
                    rekeyed.get(diff_source_key, diff_source_key),
                )
            # A content swap's fallback baseline is always a rekeyed
            # "_prev_content" marker key (see rekey_stale_content) -- once
            # substituted in above (whether this frame or a still-pending
            # earlier one, since old_texture_keys/`self._last_good_diff_key`
            # persist it forward until promotion), that marker survives in
            # `last_good_key` for every frame of the transition. A plain
            # LOD/pyramid-level fallback never has one (its keys are real
            # `LevelKey`/slot labels), so this distinguishes "the user swapped
            # in new content" from "the same content is refining to a finer
            # zoom level" without extra persisted state -- see
            # resolve_fallback_lod's `atomic` param docstring for why the two
            # cases want different reveal behavior.
            is_content_swap = last_good_key is not None and (
                any(
                    isinstance(k, tuple) and k and k[0] == "_prev_content"
                    for k in last_good_key[0]
                )
                or (
                    isinstance(last_good_key[1], tuple)
                    and last_good_key[1]
                    and last_good_key[1][0] == "_prev_content"
                )
            )
            fallback_diag: dict[str, int] = {}

            def _build_fallback_items(prior_key):
                prior_texture_keys, prior_diff_key = prior_key
                items = build_array_draw_plan(
                    self.tile_service,
                    prior_texture_keys,
                    base_image,
                    diff_key=prior_diff_key,
                    sampler_name=sampler_name,
                    viewport_zoom=viewport_zoom,
                    viewport_offset=viewport_offset,
                )
                fallback_diag["raw"] = len(items)
                # In atomic mode drop_covered never runs (the whole point is
                # that current_items stays out of the draw plan entirely),
                # so this is the only place "kept" gets set -- default it to
                # "everything survives", then let _drop_covered overwrite it
                # in non-atomic mode.
                fallback_diag["kept"] = len(items)
                return items

            def _drop_covered(fallback_items, current_items):
                dropped = drop_covered_fallback_items(
                    fallback_items, current_items, base_image
                )
                fallback_diag["kept"] = len(dropped)
                return dropped

            new_last_good_key, array_draw_plan = resolve_fallback_lod(
                key=(texture_keys, diff_source_key),
                current_items=current_array_plan,
                more_pending=main_more_pending,
                last_good_key=last_good_key,
                build_fallback_items=_build_fallback_items,
                drop_covered=_drop_covered,
                atomic=is_content_swap,
            )
            self._last_good_texture_keys, self._last_good_diff_key = (
                new_last_good_key if new_last_good_key is not None else (None, None)
            )
            if fallback_diag:
                rhi_render_debug(
                    "render FALLBACK_ACTIVE old_keys=%s new_keys=%s "
                    "fallback_raw=%d fallback_entries=%d current_entries=%d main_more_pending=%s",
                    old_texture_keys,
                    texture_keys,
                    fallback_diag["raw"],
                    fallback_diag["kept"],
                    len(current_array_plan),
                    main_more_pending,
                )
            if tile_dump_enabled():
                log_tile_event(
                    "fallback_lod",
                    old_texture_keys=[str(k) for k in old_texture_keys]
                    if old_texture_keys is not None
                    else None,
                    new_texture_keys=[str(k) for k in texture_keys],
                    diff_source_key=str(diff_source_key)
                    if diff_source_key is not None
                    else None,
                    fallback_raw=fallback_diag.get("raw"),
                    fallback_kept=fallback_diag.get("kept"),
                    current_entries=len(current_array_plan),
                    resolved_entries=len(array_draw_plan),
                    main_more_pending=main_more_pending,
                    fallback_active=bool(fallback_diag),
                    rekeyed_same_slot_swap={
                        str(k): str(v) for k, v in rekeyed.items()
                    }
                    if rekeyed
                    else None,
                )
            rhi_render_debug(
                "render array_draw_plan=%d entries", len(array_draw_plan)
            )
            # docs/dev/rendering/tile-array-atlas-plan.md Phase 9: ground
            # truth for whether *this exact frame* actually has a blank
            # hole on screen, independent of which internal mechanism
            # (fallback vs. current, budget vs. debounce) was supposed to
            # prevent it -- every earlier fix in this investigation
            # improved some indirect metric (fallback_entries, cpu_submit
            # time, etc.) without the user's perceived flash actually going
            # away, so this checks the one thing that would prove or
            # disprove "there is a real coverage gap" directly instead of
            # inferring it.
            #
            # Coverage is measured against the currently *visible* (zoom/pan
            # -cropped) rect, not the whole letterbox -- at zoom>1 only a
            # shrunk sub-rect of the letterbox is ever on screen, so the rest
            # of the letterbox having no draw item over it is correct, not a
            # hole. An earlier version of this check compared against the
            # full letterbox and flagged a false "gap" at every zoom level
            # >1x (e.g. covered=0.55 at zoom=6.857, stable for over a second,
            # main_more_pending=False -- not a transient bug, just fewer than
            # 100% of the unzoomed image being on screen).
            letterbox1 = tuple(base_image.letterbox1)
            letterbox2 = tuple(base_image.letterbox2)
            unit_grid = SimpleNamespace(total_width=1.0, total_height=1.0)
            visible1 = _visible_side_image_rect(
                base_image,
                letterbox1,
                unit_grid,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
            )
            visible2 = _visible_side_image_rect(
                base_image,
                letterbox2,
                unit_grid,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
            )
            visible1_common = _to_common_space(
                (visible1[0], visible1[1], visible1[2] - visible1[0], visible1[3] - visible1[1]),
                letterbox1,
            )
            visible2_common = _to_common_space(
                (visible2[0], visible2[1], visible2[2] - visible2[0], visible2[3] - visible2[1]),
                letterbox2,
            )
            covered1 = _covered_fraction(
                visible1_common,
                [_to_common_space(item.rect1, letterbox1) for item in array_draw_plan],
            )
            covered2 = _covered_fraction(
                visible2_common,
                [_to_common_space(item.rect2, letterbox2) for item in array_draw_plan],
            )
            if covered1 < 0.999 or covered2 < 0.999:
                rhi_render_debug(
                    "render GAP_DETECTED covered1=%.4f covered2=%.4f entries=%d "
                    "main_more_pending=%s",
                    covered1,
                    covered2,
                    len(array_draw_plan),
                    main_more_pending,
                )

        # Submit this frame's tile uploads now (rather than folding them into
        # the main pass's own resourceUpdates below) so generate_all_dirty_mips
        # can safely sample the just-uploaded pixels -- a write enqueued in
        # the same batch a later read pass consumes is not guaranteed
        # visible to that read (docs/dev/rendering/tile-array-atlas-plan.md
        # Phase 9). All dirtied (array_index, layer) pairs are then cascaded
        # together, one extra beginPass/endPass pair per (layer, level), all
        # before the main pass opens below (new render targets/pipelines
        # can't be created inside an open pass).
        command_buffer.resourceUpdate(updates)
        for array_index, layers in self._pending_dirty_layers.items():
            dirty_layers.setdefault(array_index, set()).update(layers)
        dirty_layer_count = sum(len(layers) for layers in dirty_layers.values())
        mips_cascade_start = time.monotonic()
        self._pending_dirty_layers = self.resources.generate_all_dirty_mips(
            command_buffer, dirty_layers, time_budget_ms=MIPS_CASCADE_TIME_BUDGET_MS
        )
        mips_cascade_ms = (time.monotonic() - mips_cascade_start) * 1000.0
        if dirty_layer_count:
            deferred_count = sum(
                len(layers) for layers in self._pending_dirty_layers.values()
            )
            rhi_render_debug(
                "render MIPS_CASCADE dirty_layers=%d deferred=%d cpu_submit=%.2fms",
                dirty_layer_count,
                deferred_count,
                mips_cascade_ms,
            )
        updates = self.rhi.nextResourceUpdateBatch()

        active_feature_passes = iter_active_render_passes(ctx, self.feature_passes)
        for render_pass in active_feature_passes:
            render_pass.prepare(widget, ctx, updates)
        # Any pass's own extra beginPass/endPass pairs into textures of its
        # own (e.g. filename_overlay's label-downsample GPU pass) must run
        # here, before the main pass opens below -- QRhi passes can't nest,
        # same reason generate_all_dirty_mips above also runs pre-beginPass.
        for render_pass in active_feature_passes:
            render_pass.record_pre_pass(command_buffer, widget, ctx)

        # One fixed-size uniform block (no per-item dynamic offsets --
        # array-path uniforms carry no per-item data, see
        # pack_array_uniforms) plus one per-instance vertex buffer, both
        # written pre-pass so they land in the same frame-in-flight
        # rotation slot a same-pass read would use (writing mid-pass is not
        # guaranteed to, on Vulkan/D3D/Metal backends -- see the
        # investigation this avoided in docs/dev/rendering/investigations/
        # multitile-uniform-desync.md). ensure_array_pipeline/ensure_array_srb
        # must also run before beginPass -- resource creation is illegal
        # inside an open pass.
        array_srb = None
        if array_draw_plan:
            self.resources.array_resources.ensure_array_pipeline(widget.renderTarget())
            self.resources.array_resources.ensure_array_instance_capacity(len(array_draw_plan))
            updates.updateDynamicBuffer(
                self.resources.array_resources.array_uniform_buffer,
                0,
                pack_array_uniforms(
                    self.rhi, base_image, diff_source_ready=ctx.diff_source_ready
                ),
            )
            instance_bytes = b"".join(
                pack_array_instance(
                    rect1=item.rect1,
                    rect2=item.rect2,
                    content_scale=item.content_scale,
                    content_scale_diff=item.content_scale_diff,
                    layer1=item.layer1,
                    layer2=item.layer2,
                    layer_diff=item.layer_diff,
                    # docs/dev/rendering/tile-array-atlas-plan.md Phase 10:
                    # every other instance is clipped to its own tile's
                    # bbox, but canvasLetterbox/letterboxFill's pillarbox
                    # background-fill depends only on uniforms (not any
                    # instance's own tile rect), so it still needs at least
                    # one fullscreen instance to paint it -- index 0 is
                    # forced full regardless of its real footprint.
                    bbox=(0.0, 0.0, 1.0, 1.0) if index == 0 else item.bbox,
                    rect_diff=item.rect_diff,
                )
                for index, item in enumerate(array_draw_plan)
            )
            updates.updateDynamicBuffer(
                self.resources.array_resources.array_instance_buffer, 0, instance_bytes
            )
            array_srb = self.resources.array_resources.ensure_array_srb(
                array_draw_plan[0].sampler_name
            )

        command_buffer.beginPass(
            target,
            clear_color,
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )
        if array_draw_plan:
            # docs/dev/rendering/tile-array-atlas-plan.md Phase 2: the whole
            # multi-tile scene in one instanced draw call, instead of one
            # draw call per (image1 tile, image2 tile) pair -- the
            # draw-call-count fix this plan exists for.
            size = target.pixelSize()
            command_buffer.setGraphicsPipeline(self.resources.array_resources.array_pipeline)
            command_buffer.setViewport(
                QRhiViewport(0.0, 0.0, float(size.width()), float(size.height()))
            )
            command_buffer.setVertexInput(
                0,
                [
                    (self.resources.vertex_buffer, 0),
                    (self.resources.array_resources.array_instance_buffer, 0),
                ],
            )
            command_buffer.setShaderResources(array_srb)
            command_buffer.draw(4, len(array_draw_plan))
        for render_pass in active_feature_passes:
            render_pass.record(command_buffer, widget, ctx)
        command_buffer.endPass()
        rhi_render_debug(
            "render end widget=%s target_px=%dx%d should_draw=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            target_size.width(),
            target_size.height(),
            should_draw,
        )

        # Regenerate every registered GlassHUD's backdrop sprite from this
        # canvas's OWN colorTexture() -- as it stood at the end of *this*
        # frame's own main pass, which just closed above, not the previous
        # frame's (moved here from before the main pass, see git history
        # for that version, once documented as unavoidable -- confirmed
        # live it wasn't: this app's mip cascade
        # (shared.rendering.mip_cascade.generate_all_dirty_mips) already
        # proves the shape this needs works within one frame -- write into
        # a target via a pass, `copyTexture()` out of it once that write is
        # *submitted* (not merely batched), then a *later* pass/copy this
        # same frame safely samples the copy destination; see that
        # method's own docstring for the exact submitted-vs-batched
        # distinction. `render_backdrops()`'s own crop step already uses
        # `copyTexture()`, not a sampled pass, into a wholly separate
        # scratch texture (`panel.crop_tex`) -- structurally identical to
        # mip_cascade's own copy-then-later-sample step, just with the
        # roles (which resource is the pass output vs. the copy source)
        # swapped. `command_buffer.endPass()` above is what "submits" this
        # frame's scene draw for this purpose -- everything recorded after
        # it, including this copy, executes only once that pass's own GPU
        # work is behind it in submission order.
        #
        # No feature pass draws any glass panel *into* this canvas's own
        # target -- colorTexture() is always scene-only by construction
        # (see shared.rendering.glass_panel's module docstring for why
        # that's load-bearing on its own, independent of *when* this runs:
        # a panel reading back its own previous rendering as "backdrop"
        # converges to a blurred view of itself, independent of the real
        # content behind it -- that failure mode was about *what* gets
        # copied, not *when* the copy happens, and remains fully avoided
        # here since this still never draws anything back into
        # colorTexture() itself). Stashed on `widget` (not `ctx`, which is
        # a slots=True dataclass) for each GlassHUD's own
        # GlassPanelDisplayWidget to read.
        glass_panels = getattr(widget, "glass_panels", None)
        if glass_panels is not None:
            self.glass_panel_renderer.render_backdrops(
                command_buffer, widget.colorTexture(), dict(glass_panels.items())
            )
            widget._glass_panel_sprites = self.glass_panel_renderer.ready_sprites
            widget._glass_panel_images = self.glass_panel_renderer.ready_images

        return True
