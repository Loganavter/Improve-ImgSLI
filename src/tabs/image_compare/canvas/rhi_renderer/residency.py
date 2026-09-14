# Audit-Meta: pattern=tile-residency size=exempt reason="viewport-driven rekey+stash/restore + residency (IC) — single TileResidencyRealizer, see docs/dev/TILED_RENDERING_DESIGN.md Phase 2"
"""Viewport-driven partial tile residency for the image_compare base-image
renderer (docs/dev/TILED_RENDERING_DESIGN.md Phase 2).

Split out of ``RhiResources`` -- decides, per frame, which tiles a
multi-tile grid needs resident given the current viewport, crops+uploads
whichever of those aren't already (through ``ArrayResources``), and evicts
whatever ``TileTextureService.evict_over_budget`` decides to reclaim. This
class only reads residency *decisions* from ``TileTextureService`` and
performs them against real QRhi resources -- it never decides on its own
which indices should be resident.

The actual per-key target/protect/budget/upload loop lives in
``engine.cache.residency.TileResidencyRealizerBase.realize_specs``
(docs/dev/rendering/renderer-unification-plan.md Phase 3 step 3) -- this
class only resolves *this call's* list of specs (fixed image1/image2/diff
letterbox pairs, whose LOD level the caller already picked) and supplies
``_upload_tile``. See that module's docstring for what's shared vs. what's
genuinely different per tab.
"""

from __future__ import annotations

import itertools
import time

from engine.store.pyramid_registry import pyramid_for
from engine.store.tiled_pixel_store import TiledPixelStore
from engine.cache.image_identity import image_uid
from engine.cache.lod import LevelKey, select_level
from engine.cache.residency import ResidencySpec, TileResidencyRealizerBase
from engine.cache.stash import ContentStash
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from engine.cache.tile_texture_service import TileTextureService
from engine.frame.context import BudgetStats, make_ids
from engine.cache import residency as _engine_residency
from engine.cache import tile_upload_budget as _tile_upload_budget

from tabs.image_compare.canvas.loupe_trace import frame_context_from_widget

from ..texture_parts.tile_geometry import resolve_side_visible_rect
from ..texture_parts.crop_clip import (
    BoxCroppedStoreView,
    path_for_texture_key,
    resolve_slot_boxes,
    scaled_box_for_source,
    slot_for_texture_key,
)
from ..texture_parts.upload_queue import (
    cache_texture_upload,
    evict_texture_upload_cache_over_budget,
    qimage_from_pil,
    touch_texture_upload_cache,
)
from ._debug import rhi_render_debug

try:
    from tabs.image_compare.debug import ic_preview_debug as _ic_preview_log  # type: ignore
except Exception:  # pragma: no cover - import-time fallback

    def _ic_preview_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

try:
    from tabs.image_compare.debug import ic_gap_debug as _gap_log, ic_gap_debug_enabled as _gap_enabled  # type: ignore
except Exception:  # pragma: no cover - import-time fallback

    def _gap_log(msg: str, *a, **kw) -> None:  # type: ignore
        return None

    def _gap_enabled() -> bool:  # type: ignore
        return False

# docs/dev/TILED_RENDERING_DESIGN.md Phase 2 "Open questions: Cache budget"
# -- byte budget over resident-tile pixel bytes (RGBA8, post-apron), not a
# tile count: matches how production tile caches (image editors, tiled map
# renderers) bound GPU memory, since per-tile byte cost varies at grid
# edges. Global across all resident tiles (image1/image2/diff sides
# combined) since GPU memory is one shared resource, not three independent
# ones. At today's LIVE_TILE_EXTENT=512 (tile_constants.py), one RGBA8 tile
# is ~1 MB, so even the worst case -- a 4K-canvas view straddling tile
# boundaries on both sides plus diff, while an old LOD level's tiles stay
# protected as a fallback alongside the new level's -- stays under ~2 GB
# (see tile_constants.py's LIVE_TILE_EXTENT comment for why this used to
# need 8 GB+ at the old 8192px tile size). The budget must exceed the
# visible working set or eviction thrashes (evict + re-crop + re-upload
# every frame).
_TILE_CACHE_BUDGET_BYTES = 2 * 1024 * 1024 * 1024
# docs/dev/rendering/tile-rendering-system.md Phase 2 -- byte budget over the
# *full-resolution* host-side QImage residents in
# ``widget.runtime_state._texture_upload_cache`` (stored_0/1, source_0/1,
# diff), as opposed to _TILE_CACHE_BUDGET_BYTES above which bounds cropped
# GPU tiles. Sized to comfortably hold the entries actually needed to
# render *this* frame (both stored sides + an active diff -- up to ~3x one
# full image) without forcing eviction of something still on screen; only
# the currently-unused role (typically the hi-res source_N pair, resident
# only for the magnifier) gets evicted once it's the oldest-touched entry
# over budget. Evicted entries are lazily rebuilt from the still-retained
# PIL image on next use (see the cache-miss fallback in
# ``realize_tile_plan`` below), so eviction here is a memory/recompute
# tradeoff, never a correctness one.
# Budget shared with ``engine/gpu/host_texture_cache.py`` (one
# canonical 3 GiB value; keep them in sync via the shared constant).
from engine.gpu.host_texture_cache import (
    DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES as _HOST_TEXTURE_CACHE_BUDGET_BYTES,
)


def _pil_image_for_texture_key(widget, key):
    """Maps a texture key back to the PIL image it was decoded from, for
    ``realize_tile_plan``'s cache-miss fallback. These PIL images (``state.
    _stored_pil_images``/``_source_pil_images``/``_diff_source_pil_image``)
    are retained for the widget's whole lifetime independent of
    ``_texture_upload_cache``, so this never misses for a key that was
    ever legitimately uploaded. A ``LevelKey`` resolves through the pyramid
    registry to that mipmap level's own ``TiledPixelStore`` (None while the
    level is not built or the pyramid was invalidated — callers then skip
    the key for this frame; the next frame re-resolves to a live key)."""
    if isinstance(key, LevelKey):
        base_source = _pil_image_for_texture_key(widget, key.base)
        pyramid = pyramid_for(base_source)
        if pyramid is not None and key.level < pyramid.level_count:
            return pyramid.level(key.level)
        return None
    state = widget.runtime_state
    if key in widget.texture_ids:
        return state._stored_pil_images[widget.texture_ids.index(key)]
    if key in widget._source_texture_ids:
        return state._source_pil_images[widget._source_texture_ids.index(key)]
    if key == widget._diff_source_texture_id:
        return state._diff_source_pil_image
    return None


def resolve_lod_texture_keys(
    texture_keys: tuple[object, object],
    sources: tuple[object, object],
    base_image,
    canvas_size_px: tuple[float, float],
) -> tuple[object, object]:
    """Substitutes each side's texture key with a ``LevelKey`` for the
    pyramid mipmap level matching the current on-screen scale.

    Tab-side spec resolution (mirrors multi_compare's
    ``residency.lod_key_and_source``): the engine decides the level via
    ``select_level``; this only translates this call's (keys, sources,
    letterboxes, canvas size) into the resolved keys the residency pass
    registers grids for and the draw plan builds tiles from. Lives here --
    next to ``realize_tile_plan``'s grid registration -- rather than in
    ``draw_plan.py`` so LOD-key resolution and grid registration can't
    drift apart; ``draw_plan`` re-exports it for existing callers.

    ``canvas_size_px`` is the full logical canvas in *device* pixels (live:
    widget size x DPR; tiled export: the whole export canvas), so live
    render, snapshot and export resolve identical levels for the same
    document+zoom (rendering-model.md parity). Per-tile export zoom is
    deliberately not used here — all tiles of one export must sample one
    level or seams appear. Sides without a registered pyramid (plain PIL,
    preview tier, pyramid not yet built/invalidated) keep their bare key,
    which is byte-identical to the pre-pyramid path."""
    canvas_w_px, canvas_h_px = canvas_size_px
    zoom = float(base_image.zoom) or 1.0
    letterboxes = (base_image.letterbox1, base_image.letterbox2)
    pyramids = [
        pyramid_for(source) if isinstance(source, TiledPixelStore) else None
        for source in sources
    ]
    # Both sides' pyramids build their levels asynchronously in the
    # background and can finish a level at different times. Clamping each
    # side to its own pyramid.level_count independently (as
    # best_level_for_scale does) lets one side pick a level the other
    # hasn't built yet whenever both are multi-tile -- their tile rects are
    # fractions of that side's own grid dimensions, which are only
    # comparable between sides when both grids have the same row/column
    # count. A shared level_count cap keeps both sides' clamped level (and
    # thus grid dimensions) identical whenever they'd otherwise want the
    # same level (the common case, since compared images are unified to
    # matching sizes/letterboxes).
    # Effective level count per TiledPixelStore source: missing pyramid
    # (still TiledPixelStore, not pyramid-built yet) is treated as 1
    # (only base level) so a [3, None] pair clamps to 1 rather than 3
    # — otherwise the ready side picks a coarse level whose grid mismatches
    # the bare side's grid and produces 0.0007 sliver bboxes.
    effective_counts: list[int] = []
    for src, pyr in zip(sources, pyramids):
        if isinstance(src, TiledPixelStore):
            effective_counts.append(pyr.level_count if pyr is not None else 1)
    shared_level_count = min(effective_counts) if effective_counts else 0
    ready_count = sum(1 for pyr in pyramids if pyr is not None)
    if _gap_enabled():
        try:
            _gap_log(
                "gap resolve_lod shared_level=%d ready=%d canvas=%.0fx%.0f zoom=%.3f letterbox1=(%.3f,%.3f,%.3f,%.3f) letterbox2=(%.3f,%.3f,%.3f,%.3f) keys=%s src_types=%s pyr_counts=%s",
                shared_level_count,
                ready_count,
                canvas_w_px,
                canvas_h_px,
                zoom,
                *letterboxes[0],
                *letterboxes[1],
                [str(k) for k in texture_keys],
                [type(s).__name__ if s is not None else None for s in sources],
                [p.level_count if p else None for p in pyramids],
            )
        except Exception:
            pass
    resolved = []
    for key, letterbox, source, pyramid in zip(
        texture_keys, letterboxes, sources, pyramids
    ):
        if not isinstance(source, TiledPixelStore):
            resolved.append(key)
            continue
        if pyramid is None:
            resolved.append(key)
            continue
        src_w, src_h = source.size
        disp_w = canvas_w_px * float(letterbox[2] or 1.0) * zoom
        disp_h = canvas_h_px * float(letterbox[3] or 1.0) * zoom
        dest_scale = max(
            disp_w / float(max(1, src_w)), disp_h / float(max(1, src_h))
        )
        level = select_level(dest_scale, shared_level_count)
        rhi_render_debug(
            "resolve_lod key=%s use_hires=%s zoom=%.3f src=%dx%d disp=%.1fx%.1f "
            "dest_scale=%.5f level=%d/%d",
            key,
            getattr(base_image, "use_hires", None),
            zoom,
            src_w,
            src_h,
            disp_w,
            disp_h,
            dest_scale,
            level,
            pyramid.level_count - 1,
        )
        resolved.append(key if level == 0 else LevelKey(key, level))
    return tuple(resolved)  # type: ignore[return-value]  # tuple of key|LevelKey


class TileResidencyRealizer(TileResidencyRealizerBase):
    """Owns ``realize_tile_plan`` -- one instance per ``RhiResources``,
    wired to that instance's ``ArrayResources`` (for uploading tiles into
    the shared texture array) and its whole-image-texture eviction
    (``_evict_stale_tiles``, which stays in ``RhiResources`` since it
    operates on the non-array upload path's own ``textures`` dict)."""

    def __init__(self, *, array_resources, evict_stale_tiles) -> None:
        super().__init__(tile_cache_budget_bytes=_TILE_CACHE_BUDGET_BYTES)
        self._array_resources = array_resources
        self._evict_stale_tiles = evict_stale_tiles
        self._prev_key_counter = itertools.count()
        # Populated by the most recent `realize_tile_plan` call: maps a
        # texture key that got re-registered this call (its live source
        # object changed size, e.g. an image swap into an already-loaded
        # slot) to the fresh, distinct key its *previous* content was moved
        # to via `rekey_source` -- see the re-register branch below. Read by
        # `RhiCanvasRenderer.render` right after the call to fold into this
        # frame's fallback-LOD baseline, so the old content stays drawable
        # underneath the new (still-uploading) content at the reused key
        # instead of `register_source` silently dropping it from residency
        # (docs/dev/rendering/qrhi-gotchas.md same-slot-swap finding).
        self.last_rekeyed_keys: dict[object, object] = {}
        # Stash/hold tile storage lives in the engine contract
        # (``engine.cache.stash.ContentStash``) -- this realizer only feeds
        # it per-call specs and records its rekeyed-old-content map above
        # for the renderer to fold into the frame's fallback-LOD baseline.
        # ``_pil_source_uid_by_key``/``_prev_is_preview_by_key`` moved with
        # it (``ContentStash.note_source``); the per-(key, uid) content
        # memo and the joint preview holds moved as the stash's own
        # ``_contents``/``_preview_holds``.
        self._stash = ContentStash(log=_ic_preview_log)

    @property
    def _preview_stash(self):
        """Read-through view of the engine stash's joint preview holds.

        Compatibility for the frozen preview-hold tripwire test
        (``test_preview_hold_host_eviction`` asserts membership on
        ``residency._preview_stash``). Storage is owned solely by
        ``self._stash`` -- this returns its live view, never a copy.
        """
        return self._stash.preview_holds_view()

    def _upload_tile(self, tile_service, key, index, tile_image, updates, dirty_layers, region) -> None:
        self._array_resources.upload_tile_to_array(
            tile_service, key, index, tile_image, updates, dirty_layers
        )

    def rekey_stale_content(self, tile_service: TileTextureService, key: object) -> None:
        """If ``key`` currently has resident tiles, moves them to a fresh,
        distinct key via ``rekey_source`` and records the mapping in
        ``last_rekeyed_keys``, before the caller reuses ``key`` for
        different content (``register_source``, which resets ``key``'s own
        residency bookkeeping). Shared by ``realize_tile_plan``'s lazy
        TiledPixelStore re-register branch and
        ``RhiResources.upload_source``'s eager whole-image/diff-role upload
        path -- both reuse the same stable slot key
        (`"stored_0"`/`"diff"`/...) across a content swap, and both need
        the swap's old content preserved as a fallback-LOD draw source
        instead of silently dropped (docs/dev/rendering/qrhi-gotchas.md
        same-slot-swap finding). No-op if ``key`` has no resident tiles
        (nothing worth preserving -- e.g. first-ever registration, or a
        role that's never gone through the tile-array path at all)."""
        resident = tile_service.resident_tiles(key)
        if not resident:
            _ic_preview_log(
                "rekey_stale_content: SKIP key=%s — no resident tiles, nothing to preserve",
                key,
            )
            return
        prev_key = ("_prev_content", key, next(self._prev_key_counter))
        if tile_dump_enabled():
            log_tile_event(
                "rekey_stale_content",
                key=str(key),
                prev_key=str(prev_key),
                resident_tile_count=len(resident),
            )
        _ic_preview_log(
            "rekey_stale_content: key=%s -> prev_key=%s resident=%d",
            key,
            prev_key,
            len(resident),
        )
        tile_service.rekey_source(key, prev_key)
        self.last_rekeyed_keys[key] = prev_key

    def realize_tile_plan(
        self,
        tile_service: TileTextureService,
        widget,
        texture_keys: tuple[object, object],
        base_image,
        updates,
        *,
        diff_key: object | None = None,
        viewport_zoom: tuple[float, float] | None = None,
        viewport_offset: tuple[float, float] | None = None,
        capture_uv_rect: tuple[float, float, float, float] | None = None,
        extra_protect_keys: tuple[object, ...] = (),
        dirty_layers: dict[int, set[int]] | None = None,
        crop_service: object | None = None,
        crop_boxes: tuple[object | None, object | None] | None = None,
    ) -> bool:
        """Viewport-driven partial residency (docs/dev/
        TILED_RENDERING_DESIGN.md Phase 2): for each side whose grid is
        multi-tile, crops+uploads whichever tiles ``tile_service`` decides
        should be resident (visible rect plus a residency margin ring) and
        aren't already, and evicts whatever
        ``tile_service.evict_over_budget()`` decides to reclaim -- see
        ``engine.cache.residency.realize_specs`` for the shared loop
        this delegates to. Tiles are cropped from the full-resolution
        QImage cached at ``widget.runtime_state._texture_upload_cache``
        (the same cache ``restore_texture_uploads`` uses to survive context
        loss). That cache is bounded (docs/dev/rendering/
        tile-rendering-system.md Phase 2) and can evict an unused side/diff
        entry between frames; if this side's entry was evicted, it's
        transparently re-decoded here from the still-retained PIL source
        before cropping -- see ``_pil_image_for_texture_key``.

        ``diff_key`` (Phase 4): the diff overlay is treated as a third
        "side" positioned like image1 (same letterbox), since diff is
        always computed at image1's aspect/content window regardless of
        which pixel resolution either happens to be at right now.

        ``extra_protect_keys`` (docs/dev/rendering/tile-array-atlas-plan.md
        Phase 2 fallback-LOD finding): keys whose already-resident tiles
        should be protected from this call's eviction pass without doing
        any upload/visibility work for them -- used to keep a previous LOD
        level's tiles alive as a fallback draw source while the current
        target level's tiles are still uploading, instead of evicting the
        old level's tiles the moment the new level's keys take over
        ``texture_keys``/``diff_key``.

        ``capture_uv_rect`` (magnifier fallback-LOD/black-tile fix): overrides
        the viewport-derived visible rect with an explicit ``(left, top,
        right, bottom)`` fraction of the *target key's own* full image (0..1),
        bypassing letterbox mapping entirely. Used when the caller already
        knows precisely which region of a texture role will be sampled
        independent of the main canvas's own zoom/pan -- e.g. the magnifier's
        ``source_*`` realize call, which must resolve tiles under the
        overlay's capture window (``OverlaySlot.uv_rect``) rather than
        whatever the base canvas's ``viewport_zoom``/``viewport_offset``
        would imply (at canvas zoom <= 1 that spans the whole image, vastly
        exceeding the per-frame upload budget and leaving the magnifier's
        actual capture area perpetually non-resident).

        ``dirty_layers`` (Phase 9): pass a shared ``dict[int, set[int]]``
        across every ``realize_tile_plan`` call this frame and, once
        ``updates`` has been submitted (mip generation reads the just-uploaded
        pixels, so it must run after they've actually landed on the GPU, not
        just been enqueued), call ``generate_all_dirty_mips`` for each dirtied
        ``(array_index, layer)`` pair. Omit it (the default) to get the old,
        simpler but O(_ARRAY_CAPACITY)-per-dirty-tile whole-array
        ``generateMips`` behavior instead -- only ``RhiCanvasRenderer.render``
        needs the per-layer path; anything else calling this directly (tests)
        is unaffected.

        Returns ``True`` if any key still has tiles left to upload after
        this call (budget-limited) -- callers use this to know whether the
        current call's residency is a stable, fully-realized end state or
        still mid-transition (see ``RhiCanvasRenderer``'s last-good-level
        promotion, which only promotes once this is ``False``).

        ``self.last_rekeyed_keys`` is *not* reset at the top of this call:
        ``RhiResources.upload_source`` (the eager whole-image/diff-role
        upload path, run earlier in the same frame via
        ``apply_pending_uploads``) can also rekey a same-slot swap into this
        same dict, and both must survive until the frame's caller
        (``RhiCanvasRenderer.render``) has read them. That caller resets the
        dict once at the top of each frame, before either upload path runs;
        callers of this method directly (tests, tools) that skip that reset
        get an accumulating dict across calls instead -- harmless as long as
        they check state right after the call they care about.

        W3a (crop): ``crop_service`` selects the session crop service
        (auto-resolved from the widget's Store when ``None``);
        ``crop_boxes`` optionally overrides the resolved raw
        ``(box1, box2)`` pair (full-source coords; ``None`` per slot). Each
        stored/source key's grid registers on its *box-clipped* size and
        tiles crop through a ``BoxCroppedStoreView`` (stores) or a
        box-cropped QImage, so full-frame memmaps need no bake. A ``None``
        box keeps today's behavior identically. The magnifier path
        (``capture_uv_rect`` set) stays full-frame: its capture UVs are
        full-frame fractions owned by another crew. The diff role has no
        file path and is never clipped."""
        letterboxes = (tuple(base_image.letterbox1), tuple(base_image.letterbox2))
        pairs = list(zip(texture_keys, letterboxes))
        if diff_key is not None:
            pairs.append((diff_key, letterboxes[0]))
        # W3a: resolve raw boxes once per call (warmed-cache lookup, no IO).
        # Magnifier capture path stays full-frame (see docstring).
        _crop_enabled = capture_uv_rect is None
        if _crop_enabled and crop_boxes is None:
            try:
                crop_boxes = resolve_slot_boxes(widget, crop_service=crop_service)
            except Exception:
                crop_boxes = (None, None)
        if not _crop_enabled:
            crop_boxes = (None, None)
        try:
            _raw_box1, _raw_box2 = crop_boxes[0], crop_boxes[1]
        except Exception:
            _raw_box1 = _raw_box2 = None
        # Per-key scaled boxes (live-source coords) + pre-box live sizes,
        # filled by the first pass and read by the spec-building pass.
        _box_by_key: dict[object, tuple[int, int, int, int]] = {}
        _full_size_by_key: dict[object, tuple[int, int]] = {}
        # Callers that need to defer mip regeneration until after `updates`
        # is submitted (see generate_all_dirty_mips) pass their own dict in and
        # read it back; anyone else gets the old whole-array-generateMips
        # behavior for free below.
        owns_dirty_layers = dirty_layers is None
        if dirty_layers is None:
            dirty_layers = {}

        # First pass: resolve/re-register every key's grid without doing any
        # upload work.
        contexts = []
        for key, letterbox in pairs:
            pil_source = _pil_image_for_texture_key(widget, key)
            is_tiled_store = isinstance(pil_source, TiledPixelStore)
            grid = tile_service.grid_for(key)
            from tabs.image_compare.first_frame_debug import ic_first_frame_debug
            ic_first_frame_debug(
                widget,
                "realize_tile_plan key=%s pil_source=%s tiled=%s grid=%s",
                key,
                "None" if pil_source is None else type(pil_source).__name__,
                is_tiled_store,
                "None" if grid is None else f"{grid.total_width}x{grid.total_height}",
            )
            # Both TiledPixelStore and QImage preview sources share the same
            # stable slot keys ("stored_0"/"stored_1"). The preview QImage
            # (≤1024) must be stashed as a fallback baseline when the full
            # TiledPixelStore replaces it — otherwise the preview is dropped
            # and the canvas blanks until the store's tiles land (the
            # "qimage should stay until all tiles drawn" UX). Always
            # re-register when the live source size disagrees with the cached
            # grid, or its own identity changed (see content_changed below).
            # is_tiled_store was the old gate (lazy TiledPixelStore sources
            # skip upload_source()), but QImage previews need the same
            # stash/restore path.
            if pil_source is not None:
                try:
                    try:  # Phase-A: engine.store root (A1); fallback until it lands
                        from engine.store.tiled_pixel_store import (
                            pixel_source_size,
                        )
                    except ImportError:
                        from engine.store.tiled_pixel_store import (
                            pixel_source_size,
                        )

                    src_w, src_h = pixel_source_size(pil_source)
                    if src_w == 0 or src_h == 0:
                        # Closed or empty store (race with unify closing old store
                        # while tile_service still references old key) — skip this
                        # key this frame; next frame's _pil_image_for_texture_key
                        # will resolve the live store.
                        continue
                except Exception:
                    continue
                try:
                    src_uid = image_uid(pil_source)
                except Exception:
                    continue
                # W3a: intersect with the effective box. The grid registers
                # on the box-clipped size and the box joins the content
                # identity so a late box arrival re-registers like a swap.
                # None box -> src_w/src_h/src_uid untouched (parity).
                _scaled_box: tuple[int, int, int, int] | None = None
                if _crop_enabled:
                    try:
                        _key_path = path_for_texture_key(widget, key)
                        _slot_idx = slot_for_texture_key(widget, key)
                        _raw = None
                        if _slot_idx == 0:
                            _raw = _raw_box1
                        elif _slot_idx == 1:
                            _raw = _raw_box2
                        if _raw is not None:
                            _scaled_box = scaled_box_for_source(
                                _raw, path=_key_path, live_size=(src_w, src_h)
                            )
                    except Exception:
                        _scaled_box = None
                if _scaled_box is not None:
                    _full_size_by_key[key] = (src_w, src_h)
                    _box_by_key[key] = _scaled_box
                    src_w, src_h = (
                        int(_scaled_box[2] - _scaled_box[0]),
                        int(_scaled_box[3] - _scaled_box[1]),
                    )
                    src_uid = (src_uid, _scaled_box)
                prev_uid: object | None
                prev_is_preview: bool
                content_changed: bool
                prev_uid, prev_is_preview, content_changed = self._stash.note_source(
                    key, src_uid, is_preview=not is_tiled_store
                )
                # A same-size image swap into an already-loaded slot (the
                # common case: two photos being compared are rarely the
                # exact same resolution, but it does happen, and every
                # letterboxed slot swap in general is size-agnostic from
                # the caller's perspective) leaves grid.total_width/height
                # unchanged, so the size check below alone never re-fires --
                # is_resident stays true for every already-uploaded index
                # forever, and plan_key_upload only uploads indices that
                # aren't resident, so the old content simply never gets
                # replaced except by incidental LRU eviction (e.g. panning
                # to a not-yet-visited tile), producing a persistent,
                # patchwork mix of old and new content rather than a clean
                # transition. Tracking the live source's own identity
                # (image_uid, not id() -- see the source_ids comment in
                # rhi_renderer/__init__.py for why) catches this alongside
                # the size check (docs/dev/rendering/qrhi-gotchas.md
                # same-slot-swap finding, same-size follow-up).
                if (
                    grid is None
                    or int(grid.total_width) != int(src_w)
                    or int(grid.total_height) != int(src_h)
                    or content_changed
                ):
                    rhi_render_debug(
                        "realize_tile_plan re-register key=%s old_grid=%s new_src=%dx%d content_changed=%s",
                        key,
                        None
                        if grid is None
                        else f"{grid.total_width}x{grid.total_height} ({grid.rows}x{grid.columns})",
                        src_w,
                        src_h,
                        content_changed,
                    )
                    if grid is not None:
                        self._evict_stale_tiles(key, set())
                        grid = self._stash.rekey_or_restore(
                            tile_service,
                            key,
                            src_uid,
                            (src_w, src_h),
                            prev_uid=prev_uid,
                            prev_is_preview=prev_is_preview,
                            rekeyed=self.last_rekeyed_keys,
                        )
                    else:
                        grid = tile_service.register_source(key, (src_w, src_h))
            elif grid is None:
                continue
            contexts.append((key, letterbox, pil_source, is_tiled_store, grid))

        from tabs.image_compare.first_frame_debug import ic_first_frame_debug
        ic_first_frame_debug(
            widget,
            "realize_tile_plan grids=%d resident=%s",
            len(contexts),
            {
                str(k): len(tile_service.resident_tiles(k) or ())
                for k in texture_keys
            },
        )

        # docs/dev/rendering/tile-array-atlas-plan.md: every grid, including
        # a still-1x1 side, renders through the shared texture-array pipeline
        # -- the array shader has one shared sampler2DArray for both sides
        # plus diff (base_array.frag), so a 1x1 side just gets one array slot
        # instead of its own whole-image QRhiTexture.
        specs: list[ResidencySpec] = []
        for key, letterbox, pil_source, is_tiled_store, grid in contexts:
            full_image = None
            if not is_tiled_store:
                full_image = touch_texture_upload_cache(widget, key)
                if full_image is None:
                    if pil_source is None:
                        continue
                    full_image = qimage_from_pil(pil_source)
                    cache_texture_upload(widget, key, full_image)
                # W3a: the cached/decoded tier is box-clipped in the same
                # coords the grid registered on (upload clipped it, or it is
                # the decoded tier the box was scaled against). Guard on size
                # equality so a stale cache tier never mis-clips.
                _spec_box = _box_by_key.get(key)
                if _spec_box is not None and full_image is not None:
                    try:
                        _live = _full_size_by_key.get(key)
                        if _live is not None and (
                            int(full_image.width()), int(full_image.height())
                        ) == (int(_live[0]), int(_live[1])):
                            try:  # Phase-A: engine.store root (A1); fallback until it lands
                                from engine.store.tiled_pixel_store import (
                                    qimage_from_pixel_source,
                                )
                            except ImportError:
                                from engine.store.tiled_pixel_store import (
                                    qimage_from_pixel_source,
                                )

                            full_image = qimage_from_pixel_source(
                                full_image, _spec_box
                            )
                    except Exception:
                        pass
            # Visible rect shares one derivation with the draw plan
            # (texture_parts.tile_geometry.resolve_side_visible_rect, incl.
            # the magnifier capture_uv_rect override) -- "what's uploaded"
            # and "what's drawn" agree by construction, never by parallel
            # implementations.
            visible_rect = resolve_side_visible_rect(
                base_image,
                letterbox,
                grid,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
                capture_uv_rect=capture_uv_rect,
            )
            crop_source = pil_source if is_tiled_store else full_image
            # W3a: grid and crop source share the box-clipped coordinate
            # space. Stores stay lazy through an offset view (no bake, no
            # materialization); QImage/PIL tiers were cropped above.
            _tile_box = _box_by_key.get(key)
            if _tile_box is not None and is_tiled_store and pil_source is not None:
                try:
                    crop_source = BoxCroppedStoreView(pil_source, _tile_box)
                except Exception:
                    crop_source = pil_source
            specs.append(
                ResidencySpec(key=key, grid=grid, visible_rect=visible_rect, crop_source=crop_source)
            )

        if self.last_rekeyed_keys:
            # Protect this call's freshly rekeyed old-content keys from its
            # own eviction pass -- they were just as resident a moment ago
            # under the original key and must survive at least this frame
            # to be usable as a fallback-LOD draw source (see
            # last_rekeyed_keys's docstring).
            extra_protect_keys = tuple(extra_protect_keys) + tuple(
                self.last_rekeyed_keys.values()
            )
        # Joint preview hold: keep QImage preview stash alive until BOTH halves
        # have complete tile replacement. Without this, intermediate 1024/1440
        # stores would evict the preview baseline before final hires (5760)
        # is fully resident. Hold keys contributed by the engine stash.
        extra_protect_keys = (
            tuple(extra_protect_keys)
            + self._stash.preview_extra_protect_keys(tile_service)
        )

        # Phase-B2 frame bus: snapshot pre-call residency (pure reads) and
        # the wall clock so the record below carries measured values, not
        # placeholders. Reads only -- budget/eviction decisions are untouched.
        _resident_before = {
            spec.key: tile_service.resident_tiles(spec.key) for spec in specs
        }
        # Live module-global reads (same namespaces ``realize_specs`` /
        # ``UploadDeadline`` read at call time), so tuned/patched budgets
        # flow into the record instead of a stale import-time copy.
        _live_count_budget = _engine_residency.TILE_UPLOAD_BUDGET_PER_CALL
        _live_time_budget_ms = _tile_upload_budget.TILE_UPLOAD_TIME_BUDGET_MS
        _realize_t0 = time.perf_counter()
        result = self.realize_specs(
            tile_service,
            specs,
            updates,
            extra_protect_keys=extra_protect_keys,
            dirty_layers=dirty_layers,
        )
        # Phase-B2 frame bus: realize budget/deadline/residency fact
        # (record only -- the loop above is behavior-identical).
        _frame_context = frame_context_from_widget(widget)
        if _frame_context is not None:
            _realize_ms = (time.perf_counter() - _realize_t0) * 1000.0
            _uploaded = 0
            _skipped = 0
            for _spec in specs:
                _after = tile_service.resident_tiles(_spec.key)
                _uploaded += len(
                    _after - _resident_before.get(_spec.key, set())
                )
                _skipped += len(
                    set(result.protected_by_key.get(_spec.key, set())) - _after
                )
            _stats = BudgetStats(
                budget=int(_live_count_budget),
                uploaded=int(_uploaded),
                skipped=int(_skipped),
                time_ms=float(_realize_ms),
                budget_ms=float(_live_time_budget_ms),
                more_pending=bool(result.more_tiles_pending),
            )
            _frame_context.record(
                "realize_tile_plan",
                "skipped" if result.more_tiles_pending else "ran",
                f"realize_tile_plan keys={[str(s.key) for s in specs]}"
                f" {_stats.describe()}",
                ids=make_ids(
                    _frame_context.frame_id,
                    tuple(str(s.key) for s in specs),
                    _stats.as_tuple(),
                ),
            )

        if owns_dirty_layers:
            # No caller-supplied dict: nobody downstream will call
            # generate_all_dirty_mips for us, so fall back to the old
            # whole-array behavior rather than silently never regenerating
            # mips (this path exists for any caller/test that hasn't been
            # updated to the per-layer scheme, not the live render() path).
            for array_index in dirty_layers:
                updates.generateMips(self._array_resources.tile_arrays[array_index])

        host_protected = self._stash.release_and_protect_preview_holds(
            tile_service, pairs, texture_keys, result
        )
        evict_texture_upload_cache_over_budget(
            widget, host_protected, _HOST_TEXTURE_CACHE_BUDGET_BYTES
        )

        if result.more_tiles_pending:
            # Budget left tiles un-uploaded this call; nothing else would
            # otherwise trigger another paint (QRhiWidget only repaints on
            # update()), so schedule the next frame ourselves to keep the
            # progressive fill-in moving without user input.
            widget.update()
        return result.more_tiles_pending
