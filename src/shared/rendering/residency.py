"""Shared per-call tile-residency realize loop (docs/dev/rendering/
renderer-unification-plan.md Phase 3 step 3) -- factors out the "per key:
resolve target tiles, protect them, plan+upload a budgeted batch, evict
whatever's over budget" shape that both render tabs' residency realizers
still duplicated around the Phase-3-step-2 ``UploadDeadline``/
``plan_key_upload`` helpers (deadline bookkeeping and batch selection only;
the loop that walks each key and drives them was still copy-pasted).

What's genuinely different per tab, and stays out of this base class:

- **Resolving this call's list of specs** (grid/pixel-source/visible-rect):
  the fixed-pair render tab processes a fixed image1/image2/(diff)
  letterbox-paired set whose LOD level was already chosen by the caller
  before this call starts; multi_compare processes a dynamic N-slot
  pan/fit/zoom set and resolves each slot's own LOD level *inside* its own
  per-frame walk (also deciding the array-vs-plain draw path along the
  way). Each tab's subclass builds its own ``list[ResidencySpec]`` however
  fits its own geometry/LOD model.
- **Uploading one cropped tile** (``_upload_tile``): the fixed-pair render
  tab always uploads through the shared texture array; multi_compare
  branches array/plain-path, stores into its own per-tile host cache, and
  emits debug-dump events.
- **Host-side cache eviction**: the two tabs' host caches are different
  *shapes*, not just different budgets -- a whole-image QImage cache keyed
  by texture key (fixed-pair render tab) vs. a per-tile-crop cache keyed by
  a synthesized string (multi_compare) -- so each tab evicts its own host
  cache itself, using whatever "protected" set makes sense for its own
  cache's key namespace, after calling ``realize_specs``.
- **Mip-regen fallback for callers with no ``dirty_layers`` of their own**:
  only the fixed-pair render tab's realizer supports being called without
  an external ``dirty_layers`` dict (kept for tests/callers not on the
  per-layer mip scheme); multi_compare's caller always owns and drives its
  own ``dirty_layers``. This stays in that tab's own wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.image_processing.regions import UniformTileGrid
from shared.rendering.render_debug import rhi_render_debug
from shared.rendering.tile_constants import TILE_UPLOAD_BUDGET_PER_CALL
from shared.rendering.tile_geometry import _TILE_APRON_PX, _TILE_RESIDENCY_MARGIN, crop_apron_tile
from shared.rendering.tile_prefetch import TilePrefetcher
from shared.rendering.tile_upload_budget import UploadDeadline, plan_key_upload

# Background warm requests are real memmap reads competing with the render
# thread for the GIL/CPU -- capped low and separately from
# TILE_UPLOAD_BUDGET_PER_CALL (the *synchronous* upload budget) so a sudden
# jump in `target`'s size (e.g. a magnifier activating and needing a whole
# previously-untouched tile grid) can't fire dozens of concurrent background
# reads in one call, which measurably stalled the very activation that
# triggered them.
_TILE_PREFETCH_BUDGET_PER_CALL = 8


@dataclass(frozen=True)
class ResidencySpec:
    """One key's worth of residency work for this call, resolved by the
    tab-specific subclass before handing off to ``realize_specs``."""

    key: object
    grid: UniformTileGrid
    visible_rect: object
    crop_source: object


@dataclass
class RealizeSpecsResult:
    protected_by_key: dict[object, set[tuple[int, int]]]
    more_tiles_pending: bool
    key_incomplete_by_key: dict[object, bool]
    evicted: list[tuple[object, tuple[int, int]]]


class TileResidencyRealizerBase:
    """Owns ``realize_specs`` -- one instance per resources owner (mirrors
    the existing per-``RhiResources``/per-``BaseImagesPass`` construction
    pattern), holding no cross-frame LOD/fallback state itself (that stays
    with the caller, passed in explicitly each call -- see
    docs/dev/rendering/renderer-unification-plan.md Phase 3 step 1's
    state-ownership correction), only fixed config set at construction."""

    def __init__(self, *, tile_cache_budget_bytes: int) -> None:
        self._tile_cache_budget_bytes = tile_cache_budget_bytes
        self._prefetcher = TilePrefetcher()

    def _upload_tile(
        self,
        tile_service,
        key: object,
        index: tuple[int, int],
        tile_image,
        updates,
        dirty_layers: dict[int, set[int]],
        region: object,
    ) -> None:
        raise NotImplementedError

    def realize_specs(
        self,
        tile_service,
        specs: list[ResidencySpec],
        updates,
        *,
        extra_protect_keys: tuple[object, ...] = (),
        dirty_layers: dict[int, set[int]],
        budget_per_call: int | None = None,
    ) -> RealizeSpecsResult:
        """For each spec, crops+uploads whichever tiles ``tile_service``
        decides should be resident (its visible rect plus a
        ``_TILE_RESIDENCY_MARGIN`` ring) and aren't already, budgeted by a
        shared ``UploadDeadline`` across every spec in this call. Evicts
        whatever ``tile_service.evict_over_budget`` decides to reclaim from
        the GPU tile cache (host-side cache eviction is each tab's own
        concern -- see module docstring). Reads residency decisions from
        ``tile_service`` and performs them -- never decides on its own
        which indices should be resident.

        ``extra_protect_keys``: keys whose already-resident tiles should be
        protected from this call's eviction pass without doing any upload
        work for them -- used to keep a previous LOD level's tiles alive as
        a fallback draw source while the current target level's tiles are
        still uploading.

        ``dirty_layers``: mutated in place with every ``(array_index,
        layer)`` pair this call's uploads touched, for the caller to run
        ``generate_all_dirty_mips`` against once ``updates`` has actually
        been submitted (mip generation reads the just-uploaded pixels, so
        it must run after they've landed on the GPU, not just been
        enqueued).

        The returned ``evicted`` list is ``tile_service.evict_over_budget``'s
        own return value, passed through unchanged -- an array-only upload
        path has nothing else to clean up per evicted tile and ignores it,
        but a plain (non-array) upload path holding its own per-tile GPU
        textures outside the shared array needs it to know which textures
        to destroy."""
        if budget_per_call is None:
            # Read as a live module global, not a def-time-bound default, so
            # tests can `monkeypatch.setattr(residency_module,
            # "TILE_UPLOAD_BUDGET_PER_CALL", ...)` the way both tabs' own
            # pre-merge realizers let their local budget constant be patched.
            budget_per_call = TILE_UPLOAD_BUDGET_PER_CALL
        protected_by_key: dict[object, set[tuple[int, int]]] = {}
        more_tiles_pending = False
        key_incomplete_by_key: dict[object, bool] = {}
        deadline = UploadDeadline()

        for spec in specs:
            target = tile_service.resolve_visible_tiles(
                spec.key, spec.visible_rect, _TILE_RESIDENCY_MARGIN
            )
            rhi_render_debug(
                "realize_specs key=%s grid=%dx%d(%dx%d) visible_rect=%s target=%s",
                spec.key,
                spec.grid.rows,
                spec.grid.columns,
                spec.grid.total_width,
                spec.grid.total_height,
                spec.visible_rect,
                target,
            )
            # Full `target` stays protected even though only a budgeted
            # subset uploads this call -- tiles still pending upload must
            # not be evicted, or a budget-starved source could never make
            # progress (evict-then-reselect thrash).
            protected_by_key[spec.key] = target
            batch, missing_count = plan_key_upload(
                tile_service, spec.key, target, spec.visible_rect, budget_per_call
            )
            key_incomplete = len(batch) < missing_count
            if key_incomplete:
                more_tiles_pending = True
                rhi_render_debug(
                    "realize_specs BUDGET_CAP key=%s missing=%d batch=%d cap=%d",
                    spec.key,
                    missing_count,
                    len(batch),
                    budget_per_call,
                )
            uploaded_this_call: set[tuple[int, int]] = set()
            for batch_offset, index in enumerate(batch):
                if deadline.stop_before(batch_offset):
                    # Time budget exhausted mid-batch: whatever's left in
                    # `batch` stays un-uploaded and gets reconsidered on the
                    # next call via `protected_by_key` (already set to the
                    # full `target` above).
                    more_tiles_pending = True
                    key_incomplete = True
                    rhi_render_debug(
                        "realize_specs TIME_DEADLINE key=%s uploaded=%d/%d deferred=%d",
                        spec.key,
                        batch_offset,
                        len(batch),
                        len(batch) - batch_offset,
                    )
                    break
                row, col = index
                if row < 0 or row >= spec.grid.rows or col < 0 or col >= spec.grid.columns:
                    continue
                region = spec.grid.region_for(row, col)
                tile_image = crop_apron_tile(
                    spec.crop_source, region.left, region.top, region.right, region.bottom, _TILE_APRON_PX
                )
                self._upload_tile(tile_service, spec.key, index, tile_image, updates, dirty_layers, region)
                uploaded_this_call.add(index)
            key_incomplete_by_key[spec.key] = key_incomplete

            # Warm, off-thread, the pages of whatever's still in `target`
            # but didn't get uploaded this call (budget/deadline deferred,
            # or not yet even selected into `batch`) -- see
            # ``tile_prefetch.py`` for why this matters: a fresh tile's
            # first crop is a synchronous disk read today, and this gives
            # it a head start before its own budgeted turn comes up.
            # Capped per call like the upload batch itself: an event that
            # suddenly makes `target` huge (e.g. a magnifier turning on and
            # needing a whole previously-untouched tile grid) must not fire
            # dozens of background reads in one call -- each is a real
            # memmap read competing for the GIL/CPU with the render thread,
            # and firing them all at once measurably stalled the very
            # activation that triggered them.
            if spec.crop_source is not None:
                prefetch_budget = _TILE_PREFETCH_BUDGET_PER_CALL
                for index in target:
                    if prefetch_budget <= 0:
                        break
                    if index in uploaded_this_call:
                        continue
                    row, col = index
                    if row < 0 or row >= spec.grid.rows or col < 0 or col >= spec.grid.columns:
                        continue
                    if tile_service.is_resident(spec.key, index):
                        continue
                    region = spec.grid.region_for(row, col)
                    if self._prefetcher.warm(
                        spec.key, index, spec.crop_source, region, _TILE_APRON_PX
                    ):
                        prefetch_budget -= 1

        for key in extra_protect_keys:
            resident = tile_service.resident_tiles(key)
            if resident:
                protected_by_key.setdefault(key, set()).update(resident)
        evicted = tile_service.evict_over_budget(protected_by_key, self._tile_cache_budget_bytes)

        return RealizeSpecsResult(protected_by_key, more_tiles_pending, key_incomplete_by_key, evicted)
