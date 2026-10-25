"""Single merged base-images residency pass (plan-engine-tab-migration E2).

Owns the base-image residency stage for both canvas geometries behind the
E1 hook seam (``engine.passes.hooks``), consumed verbatim:

- the tab resolves *what* is resident this call via ``resolve_specs(ctx)``
  (fixed image-pair letterbox set on one side, dynamic N-slot
  pan/fit/zoom set on the other) and uploads one cropped tile per call
  via ``upload_tile(...)``;
- the engine owns *how* residency happens: the per-key
  target/protect/budget/upload loop, the shared upload deadline and count
  budget, eviction over budget, and upload order all live in
  ``TileResidencyRealizerBase.realize_specs`` and are never overridden by
  tab code. This module defines no second loop.

Merge map (whole-owner rule: each tab copy moves entirely here; genuine
tab differences survive only as hook impls behind the seam, never as
second engine copies):

- fixed-pair material: the spec-builder that lived inside the
  fixed-pair ``realize_tile_plan`` entry and its array-only upload dock
  here as ``BaseImagesSpecHooks`` collaborators (bound by the tab, C3
  hook-bundle pattern);
- multi-slot material: the content-swap decision (``SwapSpec`` /
  ``resolve_swap_spec``), the plain-path upload funnel, and the
  preview-backfill reaction dock here as ``SwapApplyHooks``
  collaborators; the swap-apply ordering itself (rekey ordering,
  same-key size-change fallback preservation, 1x1->multi backfill
  trigger) is engine orchestration in ``apply_swap_spec``;
- routing declarations: ``stack_role`` / ``visibility`` carry the same
  stacking-policy role both tab base stages declare, so the later
  routing wave can point consumers at this one pass (the tab A0
  manifest role is absorbed here).

Out of scope for this wave (Phase F flag-day, documented, not done
here): retiring the two tab-local base-pass copies, re-pointing their
consumers (renderers, manifests, gate tests) at this pass, and moving
the draw-level plan builders (array/plain draw plans stay tab-side --
they need tab geometry the engine seal forbids naming).

Fork decisions recorded (ownership only, no redesign):

- upload queue: the whole-image texture-upload queue has exactly one
  live owner (the fixed-pair tab's queue surface over the engine host
  cache); the multi-slot slot-source swap intake is a different stage
  (source-swap decisions feeding ``apply_swap_spec``), not a second
  queue for the same stage. No engine home needed.
- plan application: the legacy render-plan impl in
  ``engine.cache.display_tier_service`` is already the single
  plan-application owner with a thin tab caller; the multi-slot
  composition builder is plan *construction* (state tree to composition
  plan), a different stage sharing no code path. No engine home needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from engine.cache.lod import LevelKey
from engine.cache.residency import (
    RealizeSpecsResult,
    ResidencySpec,
    TileResidencyRealizerBase,
)
from engine.passes.hooks import BaseImagesPassHookBase
from engine.store.tiled_pixel_store import pixel_source_size
from ui.canvas_infra.scene.pass_contract import SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from core.log_names import APP_LOGGER_NAME

if TYPE_CHECKING:  # pragma: no cover - annotation only, no runtime import
    from PySide6.QtGui import QImage

    from engine.store.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger(APP_LOGGER_NAME)

__all__ = [
    "BaseImagesPass",
    "BaseImagesSpecHooks",
    "SwapApplyHooks",
    "SwapSpec",
    "apply_swap_spec",
    "backfill_plain_preview_to_array",
    "resolve_swap_spec",
    "slot_host_key",
    "slot_tile_host_key",
]

# Sentinel level value (real pyramid levels are always >= 1, per
# LevelKey's own docstring) used to rescue a slot's previous-generation
# content under a distinct key before register_source() wipes the bare
# key -- multi-slot swap-machine material, moved verbatim.
_PREVIOUS_GENERATION_LEVEL = -1


def _host_key_repr(key: object) -> str:
    if isinstance(key, LevelKey):
        return f"{int(key.base)}_lvl{int(key.level)}"
    return str(int(key))  # native-resolution keys are plain slot ids


def slot_host_key(key: object) -> str:
    """Host-cache key for a slot's whole-image upload tier."""
    return f"slot_{_host_key_repr(key)}"


def slot_tile_host_key(key: object, row: int, col: int) -> str:
    """Host-cache key for one cropped tile upload."""
    return f"slot_{_host_key_repr(key)}_{int(row)}_{int(col)}"


@dataclass
class SwapSpec:
    """Resolved content-swap decision for one ``(sid, source)`` upload.

    Pure decision, no mutation: produced by ``resolve_swap_spec`` (reads
    only the tab's applied-source map plus ``tile_service.grid_for``) and
    consumed by ``apply_swap_spec`` (which performs the
    rekey/register/upload in the original order). Multi-slot
    swap-machine material, engine types only.
    """

    sid: int
    size: tuple[int, int]
    old_source: Any | None
    old_is_multi: bool
    # ``LevelKey(sid, _PREVIOUS_GENERATION_LEVEL)`` when a previous grid
    # exists to rescue, else ``None`` (first upload -- nothing to rekey).
    fallback_key: object | None
    # 1x1-preview -> multi-full backfill condition, evaluated on old state
    # only (the new grid's own multi-ness is re-checked at apply time,
    # where the plain branch returns before this is read).
    needs_backfill: bool


def resolve_swap_spec(
    slot_pixel_sources: dict[int, Any],
    tile_service: Any,
    sid: int,
    source: Any,
) -> SwapSpec | None:
    """Resolve one ``(sid, source)`` upload into a swap decision.

    Pure: reads only ``slot_pixel_sources`` and
    ``tile_service.grid_for`` -- performs no rekey/register/upload, so
    calling it twice (or discarding the result) is always safe. Returns
    ``None`` for a true duplicate upload (same object already applied),
    a ``SwapSpec`` otherwise.
    """
    if slot_pixel_sources.get(sid) is source:
        # A second intake of the exact same source inside one frame must
        # not re-run the rekey logic below: the first call already rekeyed
        # the genuinely-old grid to ``fallback_key`` and registered a
        # fresh, still-empty grid under ``sid``; a second call would treat
        # that fresh empty grid as "old content worth preserving" and
        # rekey it over the real fallback, discarding the one content
        # worth keeping.
        return None
    size = pixel_source_size(source)
    old_source = slot_pixel_sources.get(sid)
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
    return SwapSpec(
        sid=sid,
        size=size,
        old_source=old_source,
        old_is_multi=old_is_multi,
        fallback_key=fallback_key,
        needs_backfill=needs_backfill,
    )


@dataclass
class SwapApplyHooks:
    """Tab-bound effects for the engine swap-apply orchestration.

    Every field mirrors the tab helper ``apply_swap_spec`` replaces, so
    the tab surface binds by reference with no adaptation logic (C3
    hook-bundle pattern):

    - ``forget_stale_lod(sid)`` -- invalidate pyramid levels built
      against the source being replaced (tab owns the LOD bookkeeping
      dicts, passes them in explicitly).
    - ``note_source_applied(sid, source)`` -- record the newly applied
      source in the tab's applied-source map.
    - ``purge_slot_srbs(sid)`` -- drop per-tile shader-resource bindings
      keyed to the old content.
    - ``destroy_slot_plain_textures(sid, keep)`` -- drop plain-path GPU
      textures except ``keep`` (a set of tile keys).
    - ``upload_plain_tile(renderer, tile_key, image, updates)`` --
      single-tile plain-path upload funnel (the E1-pinned funnel shape,
      not the seam residency upload -- never conflate them).
    - ``discard_pending_plain_cleanup(sid)`` -- a same-frame plain
      overwrite subsumes any deferred cleanup from an earlier swap.
    - ``backfill_plain_preview(sid, fallback_key, old_source)`` --
      upload a plain-only 1x1 preview into the array under
      ``fallback_key`` so the slot keeps showing it underneath the new
      grid until covered; ``note_pending_plain_cleanup(sid)`` records
      the deferred release on promotion.
    - ``note_pending_plain_cleanup(sid)`` -- mark the slot for stale
      plain-preview release once the new key promotes.
    - ``note_swap_fallback(sid, fallback_key)`` -- record the rekeyed
      old content as this slot's fallback-LOD baseline and force the new
      generation back to "still pending" (the tab owns both fallback
      maps; the engine only owns the ordering: this fires immediately
      after the rekey, before the new grid registers).
    """

    forget_stale_lod: Callable[[int], None]
    note_source_applied: Callable[[int, Any], None]
    purge_slot_srbs: Callable[[int], None]
    destroy_slot_plain_textures: Callable[[int, frozenset], None]
    upload_plain_tile: Callable[[Any, object, Any, Any], None]
    discard_pending_plain_cleanup: Callable[[int], None]
    backfill_plain_preview: Callable[[int, object, Any], None]
    note_pending_plain_cleanup: Callable[[int], None]
    note_swap_fallback: Callable[[int, object], None]


def apply_swap_spec(
    *,
    tile_service: Any,
    renderer: Any,
    sid: int,
    source: Any,
    spec: SwapSpec,
    updates: Any,
    host_cache: Any,
    hooks: SwapApplyHooks,
) -> None:
    """Perform a resolved swap in the original mutation order.

    Engine orchestration over the tab effects in ``hooks``: owns the
    rekey ordering, the same-key size-change fallback preservation, and
    the 1x1->multi backfill trigger. Semantics are bit-identical to the
    multi-slot swap machine's pre-merge body; only the decision half
    moved into ``resolve_swap_spec`` and the plain upload into the
    ``upload_plain_tile`` funnel.
    """
    # A source swap invalidates LOD levels built against the *old* source
    # below -- those pyramids no longer apply. The bare-key fallback
    # pointer itself is left alone (same posture as the fixed-pair tab,
    # which never resets its last-good baseline on a source change):
    # wiping it would force every same-key size change through a fully
    # empty slot instead of falling back to whatever is resident.
    hooks.forget_stale_lod(sid)
    if spec.fallback_key is not None:
        # Any same-``sid`` content swap rekeys the still-good old content
        # under a distinct fallback key first, so the existing
        # fallback-LOD machinery can draw it underneath the new grid
        # until covered. The new generation is forced back to "still
        # pending" through the tab-owned fallback maps (while no pyramid
        # exists yet, old and new content resolve to the same bare
        # ``sid`` key, so the previous generation's "fully uploaded" flag
        # must not leak forward and promote the fallback away before it
        # ever draws).
        tile_service.invalidate_source(spec.fallback_key)
        tile_service.rekey_source(sid, spec.fallback_key)
        hooks.note_swap_fallback(sid, spec.fallback_key)
    grid = tile_service.register_source(sid, spec.size)
    hooks.note_source_applied(sid, source)
    hooks.purge_slot_srbs(sid)
    if grid.rows == 1 and grid.columns == 1:
        tile_key = tile_service.tile_key(sid, 0, 0)
        hooks.destroy_slot_plain_textures(sid, frozenset({tile_key}))
        qimage = host_cache.qimage_from_source(source, slot_host_key(sid))
        hooks.upload_plain_tile(renderer, tile_key, qimage, updates)
        # A same-frame plain overwrite subsumes any deferred cleanup
        # from an earlier swap -- the texture now holds new content.
        hooks.discard_pending_plain_cleanup(sid)
        return
    if spec.needs_backfill:
        # 1x1-preview -> multi-full: the old content was plain-only
        # (never array-resident), so the rekey above preserved
        # bookkeeping but nothing drawable on the array path -- and the
        # new grid's own tiles still trickle in over several budgeted
        # residency passes. The stale plain texture itself is deliberately
        # NOT destroyed here (destroy-before-upload was the blank
        # window); it is released once the new key promotes.
        hooks.backfill_plain_preview(sid, spec.fallback_key, spec.old_source)
        hooks.note_pending_plain_cleanup(sid)


def backfill_plain_preview_to_array(
    *,
    tile_service: Any,
    upload_to_array: Callable[[object, tuple[int, int], Any, Any, dict], None],
    host_cache: Any,
    updates: Any,
    dirty_layers: dict,
    fallback_key: object,
    old_source: Any,
) -> bool:
    """Upload a plain-only 1x1 preview into the array under ``fallback_key``.

    Backfill reaction for the swap machine, called on a 1x1-preview ->
    multi-full swap: the rekey preserved the old grid's bookkeeping, but
    a preview that only ever lived as a plain texture has no array slot,
    so the fallback-LOD draw would filter it out and the slot would
    still go blank. Uploading its single tile here makes the preview
    drawable underneath the new grid until covered.

    ``upload_to_array(key, index, image, updates, dirty_layers)`` is the
    tab-bound array upload (the tab ensures its array resources first).
    Best-effort by design: any failure just skips the backfill and
    degrades to progressive fill-in -- never breaks the swap itself.
    Returns whether the backfill upload happened.
    """
    try:
        if tile_service.slot_for(fallback_key, (0, 0)) is not None:
            # Already array-resident (promoted 1x1 from an array-path
            # frame) -- the rekeyed content draws as-is, nothing to do.
            return False
        image = host_cache.qimage_from_source(old_source, slot_host_key(fallback_key))
        if image is None or image.isNull():
            return False
        host_cache.store(slot_tile_host_key(fallback_key, 0, 0), image)
        upload_to_array(fallback_key, (0, 0), image, updates, dirty_layers)
        return True
    except Exception:
        logger.debug("base-images pass: preview backfill skipped", exc_info=True)
        return False


@dataclass
class BaseImagesSpecHooks:
    """Tab-bound collaborators for the merged base-images pass.

    C3 hook-bundle pattern: the tab surface binds by reference with no
    adaptation logic. ``ctx`` is the tab's own per-frame pass context,
    passed through opaque -- the engine never interprets it.

    - ``resolve_specs(ctx)`` -- build this call's residency spec list
      from the tab's own geometry/LOD model (E1 seam, verbatim).
    - ``upload_tile(tile_service, key, index, tile_image, updates,
      dirty_layers, region)`` -- upload one cropped tile from the engine
      loop (E1 seam, verbatim; same parameter shape as
      ``TileResidencyRealizerBase._upload_tile``).
    """

    resolve_specs: Callable[[Any], list[ResidencySpec]]
    upload_tile: Callable[
        [Any, object, tuple[int, int], Any, Any, dict[int, set[int]], object],
        None,
    ]


class BaseImagesPass(BaseImagesPassHookBase):
    """Single merged base-images residency pass (E2).

    Fills in both E1 tab hooks from the bound ``BaseImagesSpecHooks``
    bundle and adds no loop, budget, eviction, or ordering logic of its
    own: ``realize`` feeds the resolved specs into the inherited
    ``realize_specs`` engine loop and returns its result unchanged.

    Routing declarations (``stack_role`` / ``visibility``) match both
    tab base stages so the later routing wave orders this pass
    identically through the central stacking policy. ``visibility``
    stays explicit ``ALL`` on purpose -- a modeless pass context
    carries no render-mode signal, so narrowing this would silently
    disable the base pass.
    """

    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT
    visibility = SceneVisibility.ALL

    def __init__(
        self,
        *,
        tile_cache_budget_bytes: int,
        hooks: BaseImagesSpecHooks,
    ) -> None:
        super().__init__(tile_cache_budget_bytes=tile_cache_budget_bytes)
        self._hooks = hooks

    def resolve_specs(self, ctx: Any) -> list[ResidencySpec]:
        """Build this call's residency spec list from the tab's own model."""
        return self._hooks.resolve_specs(ctx)

    def upload_tile(
        self,
        tile_service: Any,
        key: object,
        index: tuple[int, int],
        tile_image: Any,
        updates: Any,
        dirty_layers: dict[int, set[int]],
        region: object,
    ) -> None:
        """Upload one cropped tile; called by the engine realize loop."""
        self._hooks.upload_tile(
            tile_service, key, index, tile_image, updates, dirty_layers, region
        )

    def _upload_tile(
        self,
        tile_service: Any,
        key: object,
        index: tuple[int, int],
        tile_image: Any,
        updates: Any,
        dirty_layers: dict[int, set[int]],
        region: object,
    ) -> None:
        # Rename-only promotion of the realizer-base override to the
        # public seam name (identical parameter shape per the E1 seam).
        self.upload_tile(
            tile_service, key, index, tile_image, updates, dirty_layers, region
        )

    def realize(
        self,
        ctx: Any,
        tile_service: Any,
        updates: Any,
        *,
        dirty_layers: dict[int, set[int]],
        extra_protect_keys: tuple[object, ...] = (),
        budget_per_call: int | None = None,
    ) -> RealizeSpecsResult:
        """Resolve this call's specs and realize them through the engine loop.

        Engine-owned feed: resolve -> ``realize_specs`` -> return. Tab
        code never overrides this; per-call protection beyond the specs
        themselves (previous-generation fallbacks, preview holds) arrives
        via ``extra_protect_keys``, computed by the tab from its own
        fallback bookkeeping.
        """
        specs = self.resolve_specs(ctx)
        return self.realize_specs(
            tile_service,
            specs,
            updates,
            extra_protect_keys=extra_protect_keys,
            dirty_layers=dirty_layers,
            budget_per_call=budget_per_call,
        )
