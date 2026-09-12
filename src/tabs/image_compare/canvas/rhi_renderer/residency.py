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
``shared.rendering.residency.TileResidencyRealizerBase.realize_specs``
(docs/dev/rendering/renderer-unification-plan.md Phase 3 step 3) -- this
class only resolves *this call's* list of specs (fixed image1/image2/diff
letterbox pairs, whose LOD level the caller already picked) and supplies
``_upload_tile``. See that module's docstring for what's shared vs. what's
genuinely different per tab.
"""

from __future__ import annotations

import itertools

from shared.image_processing.pyramid_registry import pyramid_for
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.image_identity import image_uid
from shared.rendering.lod import LevelKey
from shared.rendering.residency import ResidencySpec, TileResidencyRealizerBase
from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled
from shared.rendering.tile_texture_service import TileTextureService

from ..texture_parts.tile_geometry import _visible_side_image_rect
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
# Budget shared with ``shared/rendering/host_texture_cache.py`` (one
# canonical 3 GiB value; keep them in sync via the shared constant).
from shared.rendering.host_texture_cache import (
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
        # Last-seen `image_uid()` of the live pil_source per key, so a
        # same-size content swap (grid dimensions unchanged) can still be
        # detected -- see the content_changed comment in realize_tile_plan.
        self._pil_source_uid_by_key: dict[object, int] = {}
        # Per-key memo of {content_uid: stash_key} for content this key has
        # already shown before. A role that keeps toggling between a small
        # fixed set of distinct contents under the *same* slot key -- e.g.
        # "stored_0"/"stored_1" alternating between the normal comparison
        # pair and a single-image-mode preview on rapid Space+click -- would
        # otherwise re-register (register_source resets residency) and
        # fully re-crop+re-upload every tile on every single toggle, even
        # though the content it's toggling back to was fully resident a
        # moment ago. `realize_tile_plan`'s re-register branch checks this
        # memo before registering a blank grid: if the incoming content was
        # stashed here, `rekey_source` swaps it straight back onto `key`
        # with zero GPU work instead. Entries live only as long as
        # `tile_service` still has them resident (budget eviction can still
        # reclaim a stashed entry between toggles -- then it's just a normal
        # cache miss, not a correctness issue).
        self._content_stash: dict[object, dict[int, object]] = {}
        # Preview baseline that must survive until BOTH halves have complete
        # tile replacement (UX: preview never deleted until both sides'
        # final hires tiles fully resident). The first QImage preview stashed
        # for a slot is kept here and always added to extra_protect_keys,
        # so intermediate low-res stores (1024/1440 unified) never evict it
        # before the final hires (5760) is fully resident and promoted.
        self._preview_stash: dict[object, object] = {}
        # Whether previous pil_source for key was a QImage preview (not TiledPixelStore)
        self._prev_is_preview_by_key: dict[object, bool] = {}

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

    def _rekey_or_restore(
        self,
        tile_service: TileTextureService,
        key: object,
        prev_uid: int | None,
        src_uid: int,
        src_w: int,
        src_h: int,
        prev_is_preview: bool = False,
    ):
        """Same-slot content swap for ``key`` (``prev_uid``'s content ->
        ``src_uid``'s). If ``src_uid`` was stashed here from an earlier
        swap *and* is still resident, restores it onto ``key`` via
        ``rekey_source`` with zero GPU work instead of registering a blank
        grid and re-cropping+re-uploading every tile -- the toggle-between-
        a-few-known-contents case (see ``self._content_stash``'s docstring).
        Otherwise behaves like the old unconditional ``rekey_stale_content``
        + ``register_source``, except the outgoing content is stashed under
        a key stable per ``(key, prev_uid)`` rather than a disposable
        one-shot key, so a later swap back to it can be recognized."""
        if prev_uid is not None and prev_uid == src_uid:
            # Same object, different size -- a mutated/resized source, not
            # a swap between two known contents. Nothing to stash or
            # restore; drop straight through to a fresh register below.
            return tile_service.register_source(key, (src_w, src_h))

        stash = self._content_stash.setdefault(key, {})
        if prev_uid is not None and tile_service.resident_tiles(key):
            stash_key = ("_content_stash", key, prev_uid)
            tile_service.rekey_source(key, stash_key)
            stash[prev_uid] = stash_key
            if prev_is_preview:
                # Keep QImage preview baseline until BOTH halves have complete
                # tile replacement (joint hold). Intermediate low-res stores
                # must not overwrite it as fallback baseline.
                self._preview_stash[key] = stash_key
                self.last_rekeyed_keys[key] = stash_key
                _ic_preview_log(
                    "rekey _content_stash preview hold: key=%s prev_uid=%s -> stash_key=%s resident=%d (preview baseline kept)",
                    key,
                    prev_uid,
                    stash_key,
                    len(tile_service.resident_tiles(stash_key) or ()),
                )
            else:
                # If preview baseline still resident, keep it as fallback
                # instead of overwriting with intermediate low-res store.
                _preview_key = self._preview_stash.get(key)
                if _preview_key is not None and tile_service.resident_tiles(_preview_key):
                    _ic_preview_log(
                        "rekey _content_stash: key=%s prev_uid=%s -> stash_key=%s resident=%d (preview baseline kept, not promoted)",
                        key,
                        prev_uid,
                        stash_key,
                        len(tile_service.resident_tiles(stash_key) or ()),
                    )
                    # keep last_rekeyed pointing to preview, not intermediate
                    self.last_rekeyed_keys[key] = _preview_key
                else:
                    # no preview hold, promote intermediate as usual; clear stale preview hold
                    if _preview_key is not None:
                        self._preview_stash.pop(key, None)
                    self.last_rekeyed_keys[key] = stash_key
                    _ic_preview_log(
                        "rekey _content_stash: key=%s prev_uid=%s -> stash_key=%s resident=%d",
                        key,
                        prev_uid,
                        stash_key,
                        len(tile_service.resident_tiles(stash_key) or ()),
                    )
            if tile_dump_enabled():
                log_tile_event(
                    "rekey_stale_content",
                    key=str(key),
                    prev_key=str(stash_key),
                    resident_tile_count=len(tile_service.resident_tiles(stash_key)),
                )

        restore_key = stash.get(src_uid)
        if restore_key is not None and tile_service.resident_tiles(restore_key):
            _ic_preview_log(
                "restore_stashed_content: key=%s src_uid=%s <- restore_key=%s resident=%d",
                key,
                src_uid,
                restore_key,
                len(tile_service.resident_tiles(restore_key) or ()),
            )
            tile_service.rekey_source(restore_key, key)
            del stash[src_uid]
            if tile_dump_enabled():
                log_tile_event(
                    "restore_stashed_content",
                    key=str(key),
                    restore_key=str(restore_key),
                    resident_tile_count=len(tile_service.resident_tiles(key)),
                )
            return tile_service.grid_for(key)
        elif restore_key is not None:
            _ic_preview_log(
                "restore_stashed_content: SKIP key=%s src_uid=%s restore_key=%s — evicted, cache miss",
                key,
                src_uid,
                restore_key,
            )

        return tile_service.register_source(key, (src_w, src_h))

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
    ) -> bool:
        """Viewport-driven partial residency (docs/dev/
        TILED_RENDERING_DESIGN.md Phase 2): for each side whose grid is
        multi-tile, crops+uploads whichever tiles ``tile_service`` decides
        should be resident (visible rect plus a residency margin ring) and
        aren't already, and evicts whatever
        ``tile_service.evict_over_budget()`` decides to reclaim -- see
        ``shared.rendering.residency.realize_specs`` for the shared loop
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
        they check state right after the call they care about."""
        letterboxes = (tuple(base_image.letterbox1), tuple(base_image.letterbox2))
        pairs = list(zip(texture_keys, letterboxes))
        if diff_key is not None:
            pairs.append((diff_key, letterboxes[0]))
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
                    from shared.image_processing.tiled_pixel_store import (
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
                prev_uid = self._pil_source_uid_by_key.get(key)
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
                content_changed = prev_uid is not None and prev_uid != src_uid
                # remember whether previous source was QImage preview for preview-hold
                prev_is_preview = bool(self._prev_is_preview_by_key.get(key, False))
                self._pil_source_uid_by_key[key] = src_uid
                self._prev_is_preview_by_key[key] = not is_tiled_store
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
                        grid = self._rekey_or_restore(
                            tile_service, key, prev_uid, src_uid, src_w, src_h, prev_is_preview=prev_is_preview
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
            if capture_uv_rect is not None:
                cap_left, cap_top, cap_right, cap_bottom = capture_uv_rect
                visible_rect = (
                    cap_left * grid.total_width,
                    cap_top * grid.total_height,
                    cap_right * grid.total_width,
                    cap_bottom * grid.total_height,
                )
            else:
                visible_rect = _visible_side_image_rect(
                    base_image,
                    letterbox,
                    grid,
                    viewport_zoom=viewport_zoom,
                    viewport_offset=viewport_offset,
                )
            crop_source = pil_source if is_tiled_store else full_image
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
        # is fully resident.
        if self._preview_stash:
            _preview_protect = tuple(
                k for k in self._preview_stash.values() if tile_service.resident_tiles(k)
            )
            if _preview_protect:
                extra_protect_keys = tuple(extra_protect_keys) + _preview_protect
                _ic_preview_log(
                    "preview protect hold: keys=%s resident=%s",
                    list(self._preview_stash.keys()),
                    [len(tile_service.resident_tiles(k) or ()) for k in _preview_protect],
                )

        result = self.realize_specs(
            tile_service,
            specs,
            updates,
            extra_protect_keys=extra_protect_keys,
            dirty_layers=dirty_layers,
        )

        if owns_dirty_layers:
            # No caller-supplied dict: nobody downstream will call
            # generate_all_dirty_mips for us, so fall back to the old
            # whole-array behavior rather than silently never regenerating
            # mips (this path exists for any caller/test that hasn't been
            # updated to the per-layer scheme, not the live render() path).
            for array_index in dirty_layers:
                updates.generateMips(self._array_resources.tile_arrays[array_index])

        evict_texture_upload_cache_over_budget(
            widget, {key for key, _ in pairs}, _HOST_TEXTURE_CACHE_BUDGET_BYTES
        )

        if result.more_tiles_pending:
            # Budget left tiles un-uploaded this call; nothing else would
            # otherwise trigger another paint (QRhiWidget only repaints on
            # update()), so schedule the next frame ourselves to keep the
            # progressive fill-in moving without user input.
            widget.update()
        return result.more_tiles_pending
