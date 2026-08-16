"""Viewport-driven partial tile residency for Multi Compare's base-image
pass (docs/dev/rendering/renderer-unification-plan.md Phase 3).

Split out of ``BaseImagesPass`` -- decides, per frame, which tiles each
visible slot needs resident given its pan/fit/zoom, crops+uploads whichever
of those aren't already (through ``ArrayResources`` or ``SlotResources``
depending on this frame's array/plain-path decision), and evicts whatever
``TileTextureService.evict_over_budget`` decides to reclaim. Mirrors
image_compare's ``rhi_renderer/residency.py`` in role; deliberately ported
its *stateless* shape too -- no cross-frame LOD-fallback state lives here,
only fixed config set at construction of the per-call ``_SlotUploadRealizer``
below, while ``BaseImagesPass`` owns ``_last_good_key``/``_key_more_pending``/
``_slot_lod_keys`` and passes them into ``realize``/``lod_key_and_source``
explicitly.

The per-key target/protect/budget/upload loop lives in
``shared.rendering.residency.TileResidencyRealizerBase.realize_specs``
(docs/dev/rendering/renderer-unification-plan.md Phase 3 step 3) -- this
module only resolves *this call's* list of specs (N-way per-slot pan/fit/zoom,
with its own inline per-slot LOD resolution and array-vs-plain draw-path
decision) and supplies ``_upload_tile`` (which, unlike image_compare's
array-only upload, branches array/plain-path and does host-tile
caching/debug-dump). See that module's docstring for what's shared vs. what's
genuinely different per tab.
"""

from __future__ import annotations

import time

from shared.image_processing.pyramid_registry import pyramid_for
from shared.image_processing.tiled_pixel_store import TiledPixelStore, pixel_source_size
from shared.rendering.lod import LevelKey
from shared.rendering.render_debug import rhi_render_debug
from shared.rendering.residency import ResidencySpec, TileResidencyRealizerBase
from shared.rendering.tile_debug import dump_tile_image, log_tile_event, tile_dump_enabled
from tabs.multi_compare.scene.resources import (
    SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES,
    SLOT_TILE_CACHE_BUDGET_BYTES,
)
from tabs.multi_compare.scene.tile_geometry import _visible_slot_image_rect


def _host_key_repr(key: object) -> str:
    if isinstance(key, LevelKey):
        return f"{int(key.base)}_lvl{int(key.level)}"
    return str(int(key))  # type: ignore[call-overload]  # key is a native-resolution int or LevelKey


def _slot_host_key(key: object) -> str:
    return f"slot_{_host_key_repr(key)}"


def _slot_tile_host_key(key: object, row: int, col: int) -> str:
    return f"slot_{_host_key_repr(key)}_{int(row)}_{int(col)}"


def _sid_from_key(key: object) -> int:
    """Recovers the slot id a residency ``key`` belongs to -- either the
    plain ``sid`` itself (native-resolution keys are just ``int``) or a
    ``LevelKey(sid, level)``'s ``.base``. Used by ``_SlotUploadRealizer``
    to rebuild the debug-dump/host-cache naming the old inline loop had
    ``sid`` for directly, now that ``_upload_tile`` only receives ``key``."""
    return int(key.base) if isinstance(key, LevelKey) else int(key)  # type: ignore[call-overload]


def lod_key_and_source(
    sid: int,
    base_source: TiledPixelStore | object | None,
    layer,
    slot_lod_keys: dict[int, set[LevelKey]],
) -> tuple[object, object | None]:
    """Resolve this frame's texture key + pixel source for ``sid``.

    Returns ``(sid, base_source)`` unchanged unless a built pyramid level
    covers the layer's current on-screen scale better than the native
    store. ``slot_lod_keys`` is the caller's (``BaseImagesPass``) own dict
    of every ``LevelKey`` ever resolved for a slot, used by ``forget_slot``
    to invalidate them on slot removal -- mutated in place here rather than
    owned by this module, same reasoning as every other explicit-dependency
    argument in this file."""
    if not isinstance(base_source, TiledPixelStore):
        return sid, base_source
    pyramid = pyramid_for(base_source)
    if pyramid is None or pyramid.level_count <= 1:
        return sid, base_source
    src_w, src_h = base_source.size
    if src_w <= 0 or src_h <= 0:
        return sid, base_source
    _lx, _ly, rect_w, rect_h = layer.rect_fb
    disp_w = rect_w * max(layer.fit_x, 1e-6) * layer.zoom
    disp_h = rect_h * max(layer.fit_y, 1e-6) * layer.zoom
    dest_scale = max(disp_w / src_w, disp_h / src_h)
    level = pyramid.best_level_for_scale(dest_scale)
    if level <= 0:
        return sid, base_source
    level_store = pyramid.level(level)
    key = LevelKey(sid, level)
    slot_lod_keys.setdefault(sid, set()).add(key)
    return key, level_store


def forget_slot(
    tile_service,
    sid: int,
    *,
    last_good_key: dict[int, object],
    key_more_pending: dict[object, bool],
    slot_lod_keys: dict[int, set[LevelKey]],
) -> None:
    """Drops every fallback-LOD bookkeeping entry for ``sid`` -- called when
    a slot's pixel source is removed entirely, since no state pointing at
    it is a valid fallback anymore. The three dicts are ``BaseImagesPass``'s
    own state, passed in rather than owned here (mirrors image_compare's
    ``RhiCanvasRenderer`` owning ``_last_good_texture_keys`` itself)."""
    old_key = last_good_key.pop(sid, None)
    key_more_pending.pop(old_key, None)
    for stale_key in slot_lod_keys.pop(sid, ()):
        tile_service.invalidate_source(stale_key)
        key_more_pending.pop(stale_key, None)


def forget_stale_lod_keys(
    tile_service,
    sid: int,
    *,
    last_good_key: dict[int, object],
    key_more_pending: dict[object, bool],
    slot_lod_keys: dict[int, set[LevelKey]],
) -> None:
    """Invalidates only ``sid``'s stale ``LevelKey`` bookkeeping on a source
    *swap* (as opposed to ``forget_slot``'s full reset on slot *removal*) --
    those levels were built against the pixel source that's about to be
    replaced, so their pyramids are no longer valid regardless of what
    happens to ``sid`` itself.

    Unlike ``forget_slot``, this does NOT unconditionally pop
    ``last_good_key[sid]``/``key_more_pending`` for the bare ``sid`` key --
    a same-key size change (e.g. progressive-preview -> full-resolution,
    which keeps resolving to plain ``sid`` until a pyramid actually gets
    built) has nothing to gain from wiping that fallback pointer, and doing
    so was an asymmetry against image_compare's ``RhiCanvasRenderer``, which
    never explicitly resets ``_last_good_texture_keys`` on a source change
    either -- it only ever gets overwritten by the next successful
    promotion. ``last_good_key[sid]`` is still popped here if it happens to
    equal one of the just-invalidated stale ``LevelKey``s, since that
    fallback target genuinely no longer exists."""
    for stale_key in slot_lod_keys.pop(sid, ()):
        tile_service.invalidate_source(stale_key)
        key_more_pending.pop(stale_key, None)
        if last_good_key.get(sid) == stale_key:
            last_good_key.pop(sid, None)


class _SlotUploadRealizer(TileResidencyRealizerBase):
    """Per-call throwaway instance (mirrors image_compare's per-``RhiResources``
    ``TileResidencyRealizer``, except this one is cheap enough -- no GPU
    resource ownership of its own, just closures over this call's already-
    live ``array_resources``/``slot_resources``/``host_cache`` -- to build
    fresh each ``realize()`` call rather than caching across frames) that
    supplies the array-vs-plain-path branch, host-tile caching, and
    debug-dump ``_upload_tile`` needs, which is genuinely different from
    image_compare's array-only upload."""

    def __init__(self, *, renderer, array_resources, slot_resources, host_cache, use_array) -> None:
        super().__init__(tile_cache_budget_bytes=SLOT_TILE_CACHE_BUDGET_BYTES)
        self._renderer = renderer
        self._array_resources = array_resources
        self._slot_resources = slot_resources
        self._host_cache = host_cache
        self._use_array = use_array

    def _upload_tile(self, tile_service, key, index, tile_image, updates, dirty_layers, region) -> None:
        row, col = index
        sid = _sid_from_key(key)
        if tile_dump_enabled():
            dump_name = (
                f"crop_sid{sid}_{_host_key_repr(key)}_r{row}c{col}_"
                f"{'arr' if self._use_array else 'plain'}_t{time.monotonic_ns()}"
            )
            image_path = dump_tile_image(tile_image, dump_name)
            log_tile_event(
                "tile.crop",
                sid=sid,
                key=str(key),
                row=row,
                col=col,
                row_parity=row % 2,
                col_parity=col % 2,
                region=(region.left, region.top, region.right, region.bottom),
                use_array=self._use_array,
                tile_w=tile_image.width(),
                tile_h=tile_image.height(),
                image_path=image_path,
            )
        self._host_cache.store(_slot_tile_host_key(key, row, col), tile_image)
        if self._use_array:
            self._array_resources.upload_tile_to_array(
                tile_service, key, index, tile_image, updates, dirty_layers=dirty_layers
            )
        else:
            tile_key = tile_service.tile_key(key, row, col)
            self._slot_resources.upload_tile(self._renderer, tile_key, tile_image, updates)
            tile_service.mark_resident(key, index, tile_image.width() * tile_image.height() * 4)


def realize(
    *,
    renderer,
    ctx,
    updates,
    slot_pixel_sources: dict[int, object],
    array_resources,
    slot_resources,
    host_cache,
    slot_lod_keys: dict[int, set[LevelKey]],
    last_good_key: dict[int, object],
) -> tuple[bool, dict[int, set[int]], dict[object, bool], dict[int, tuple[object, object | None]]]:
    """Viewport-driven partial residency for every visible slot this frame:
    for each slot whose grid is multi-tile (or whenever any slot forces the
    whole frame onto the array path), crops+uploads whichever tiles
    ``tile_service`` decides should be resident and aren't already, and
    evicts whatever ``tile_service.evict_over_budget`` decides to reclaim.
    Reads residency decisions from ``tile_service`` and performs them -- it
    never decides on its own which indices should be resident.

    ``last_good_key`` (docs/dev/rendering/tile-array-atlas-plan.md Phase 9
    fallback-LOD, mirrors image_compare's ``extra_protect_keys``): read-only
    here, used per slot to protect the previous LOD level's resident tiles
    from this call's eviction pass while the current level is still
    uploading -- ``BaseImagesPass`` owns writing to it (promotion happens in
    ``_prepare_array_plan``, once a key's plan is known to be a stable end
    state, exactly like image_compare's render() promotes
    ``_last_good_texture_keys`` only after checking this call's returned
    per-key "more pending" state).

    Returns ``(use_array_this_frame, dirty_layers, key_incomplete_by_key,
    resolved_lod)``: whether this frame's draw call must use the
    texture-array + instanced pipeline, the per-layer mip-dirty set for
    ``generate_all_dirty_mips``, for every key touched this call whether its
    upload target still has tiles left pending (budget-limited, for the
    caller to fold into its own ``_key_more_pending``), and -- per slot id --
    the exact ``(key, pixel_source)`` this call's ``lod_key_and_source``
    resolved to, for the caller to reuse verbatim in this same frame's later
    draw-plan phase instead of independently re-resolving it there (see the
    comment at this function's ``resolved_lod`` local for why a second,
    independent resolution is unsafe)."""
    tile_service = renderer.tile_service
    protected_host: set[str] = set()
    dirty_layers: dict[int, set[int]] = {}

    # Resolve every visible layer's LOD key/pixel-source exactly once, up
    # front, in a tight loop that does nothing else -- both the `use_array`
    # decision below and the specs-building pass further down used to each
    # call `lod_key_and_source` independently for the same sid, which could
    # already disagree with each other *within this one realize() call* if a
    # background PyramidPixelStore.build_next_level() call landed a new
    # level (mutating pyramid.level_count) in the GIL-switch gap between the
    # two loops -- the same desync class as the one fixed between this
    # function and BaseImagesPass's later draw-plan phase (see the
    # `resolved_lod` return value below), just one level shallower. Every
    # other read of a slot's key this call must go through this dict, never
    # call `lod_key_and_source` a second time for the same sid.
    resolved_lod: dict[int, tuple[object, object | None]] = {}
    for layer in ctx.projected_layers:
        sid = int(layer.slot_id)
        base_source = slot_pixel_sources.get(sid)
        resolved_lod[sid] = lod_key_and_source(sid, base_source, layer, slot_lod_keys)

    # docs/dev/rendering/tile-array-atlas-plan.md Phase 4: whichever layer
    # resolved to a multi-tile grid this frame forces the *whole* frame's
    # draw call onto the texture-array + instanced pipeline -- both upload
    # (here) and draw (record) must agree on this per-frame decision, so it
    # is computed once, up front, and returned for the caller to stash.
    use_array = False
    for layer in ctx.projected_layers:
        sid = int(layer.slot_id)
        key, pixel_source = resolved_lod[sid]
        if key == sid:
            grid = tile_service.grid_for(sid)
        else:
            # A LOD-level key that hasn't been registered yet (this is its
            # first frame) has no grid in the service at all -- ``grid_for``
            # would return None here even though the underlying pixel
            # source is multi-tile, which used to make this decision
            # silently fall back to "not array" for that one frame while
            # the upload loop below (which *does* register the grid) still
            # marks the tiles resident under an allocated array slot. That
            # mismatch left the array slot allocated-but-never-written --
            # the next frame's array-path draw then sampled whatever stale
            # content a previous key left in that layer. Registering here
            # too (idempotent: the upload loop's own registration below
            # sees a matching size and skips) keeps this decision and the
            # upload loop's own grid in agreement on every frame, including
            # the first.
            if pixel_source is None:
                continue
            size = pixel_source_size(pixel_source)
            grid = tile_service.grid_for(key)
            if grid is None or (grid.total_width, grid.total_height) != size:
                grid = tile_service.register_source(key, size)
        if grid is not None and (grid.rows > 1 or grid.columns > 1):
            use_array = True
            break

    # First pass (genuinely tab-specific: N-way per-slot pan/fit/zoom, own
    # inline LOD resolution, above `use_array` decision already made) --
    # resolve every visible slot's spec without doing any upload work.
    specs: list[ResidencySpec] = []
    extra_protect_keys: list[object] = []
    # `resolved_lod` (built above) is also stashed in this function's return
    # value for the caller (BaseImagesPass) to reuse verbatim in this same
    # frame's later draw-plan phase (_prepare_array_plan/finish_prepare's
    # plain-path loop) instead of re-resolving lod_key_and_source there --
    # that second, independent resolution used to be able to pick a
    # *different* pyramid level than this one did, if a background
    # PyramidPixelStore.build_next_level() call landed a new level (mutating
    # pyramid.level_count) in the gap between this call and the draw-plan
    # phase (which runs after generate_all_dirty_mips's own time-budgeted
    # work -- a real gap, not a same-tick race). That desync uploaded tiles
    # for one level but drew a different, barely-populated one, collapsing
    # the slot to blank/partial for a frame. See docs/dev/rendering/
    # investigations/ for the log trace that caught this.
    for layer in ctx.projected_layers:
        sid = int(layer.slot_id)
        protected_host.add(_slot_host_key(sid))
        key, pixel_source = resolved_lod[sid]
        if key == sid:
            # Native resolution: the eager single-upload fast path in
            # ``_upload_slot`` already handled the 1x1-grid case; only a
            # >max_tile_extent source, or an array-path frame that needs
            # this still-1x1 slot uploaded into the shared array too
            # (mirrors image_compare's identical promotion), needs this
            # per-frame residency walk.
            grid = tile_service.grid_for(sid)
            if grid is None:
                continue
            if not use_array and grid.rows == 1 and grid.columns == 1:
                continue
        else:
            # A pyramid level was selected for this frame: register (or
            # refresh) its own grid under LevelKey(sid, level) so it gets
            # independent residency/eviction bookkeeping from the native
            # store, then fall through to the same crop+upload loop below
            # regardless of whether this level is 1x1 or multi-tile.
            protected_host.add(_slot_host_key(key))
            size = pixel_source_size(pixel_source)
            grid = tile_service.grid_for(key)
            if grid is None or (grid.total_width, grid.total_height) != size:
                grid = tile_service.register_source(key, size)
        if pixel_source is None:
            continue
        # Fallback-LOD protection (docs/dev/rendering/
        # tile-array-atlas-plan.md Phase 9, mirrors image_compare's
        # ``extra_protect_keys``): if this slot's last fully-uploaded key
        # differs from this frame's key (a LOD level just changed), keep
        # its tiles resident/protected from eviction so the array
        # draw-plan builder can still draw them underneath the new,
        # possibly-still-loading level -- otherwise the old level's tiles
        # get evicted the instant the level changes, the same frame the
        # new level has nothing to show yet.
        old_key = last_good_key.get(sid)
        if old_key is not None and old_key != key:
            extra_protect_keys.append(old_key)
        pan = (layer.pan_x, layer.pan_y)
        fit = (max(layer.fit_x, 1e-6), max(layer.fit_y, 1e-6))
        visible_rect = _visible_slot_image_rect(pan, fit, layer.zoom, grid)
        rhi_render_debug(
            "mc-residency sid=%s key=%s grid=%sx%s tile_px=%sx%s pan=%s fit=%s zoom=%s visible_rect=%s",
            sid, key, grid.columns, grid.rows, grid.tile_width, grid.tile_height,
            pan, fit, layer.zoom, visible_rect,
        )
        specs.append(ResidencySpec(key=key, grid=grid, visible_rect=visible_rect, crop_source=pixel_source))

    realizer = _SlotUploadRealizer(
        renderer=renderer,
        array_resources=array_resources,
        slot_resources=slot_resources,
        host_cache=host_cache,
        use_array=use_array,
    )
    result = realizer.realize_specs(
        tile_service,
        specs,
        updates,
        extra_protect_keys=tuple(extra_protect_keys),
        dirty_layers=dirty_layers,
    )

    for key, indices in result.protected_by_key.items():
        for row, col in indices:
            protected_host.add(_slot_tile_host_key(key, row, col))

    for key, index in result.evicted:
        tile_key = tile_service.tile_key(key, *index)
        texture = slot_resources.slot_textures.pop(tile_key, None)
        if texture is not None:
            try:
                texture.destroy()
            except RuntimeError:
                pass
        slot_resources.slot_texture_sizes.pop(tile_key, None)
        slot_resources.purge_tile_srb_entry(tile_key)
    host_cache.evict_over_budget(protected_host, SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES)
    if result.more_tiles_pending:
        # Budget left tiles un-uploaded this call; nothing else would
        # otherwise trigger another paint, so schedule the next frame
        # ourselves to keep the progressive fill-in moving.
        renderer.host.update()
    return use_array, dirty_layers, result.key_incomplete_by_key, resolved_lod
