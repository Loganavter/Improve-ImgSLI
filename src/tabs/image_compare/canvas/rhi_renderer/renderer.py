# Audit-Meta: pattern=state-machine reason="one frame sequencing RhiCanvasRenderer.render() — see CODE_PATTERNS When not to split"
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
from shared.rendering.lod import LevelKey
from ._debug import rhi_render_debug, rhi_render_debug_enabled

# [ic-preview] correlation for "placeholder missing" flash (same env flag as
# render_flow's gate). Import lazy-tolerant: debug.py only depends on
# shared.debug_flags, so no cycle.
try:
    from tabs.image_compare.debug import ic_gap_debug as _gap_log  # type: ignore
    from tabs.image_compare.debug import ic_gap_debug_enabled as _gap_enabled  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug as _ic_preview_log  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug_enabled as _ic_preview_enabled  # type: ignore
except Exception:  # pragma: no cover - import-time fallback for tests

    def _gap_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _gap_enabled() -> bool:  # type: ignore
        return False

    def _ic_preview_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _ic_preview_enabled() -> bool:  # type: ignore
        return False

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


def _is_rekeyed_content_key(key: object) -> bool:
    """True for the rekeyed old-content marker keys the residency realizer
    uses to preserve a slot's previous content across a same-slot swap:
    ``("_prev_content", ...)`` (``rekey_stale_content`` -- the eager
    whole-image/diff-role upload path in ``RhiResources.upload_source``) or
    ``("_content_stash", ...)`` (``_rekey_or_restore`` -- the lazy
    TiledPixelStore path in ``realize_tile_plan``). The marker prefix is
    what distinguishes a content swap's fallback baseline from a plain
    LOD/pyramid-level one, whose keys are real ``LevelKey``/slot labels --
    see ``_resolve_fallback_plan``'s docstring for why the two want
    different reveal behavior. ``LevelKey`` is a NamedTuple whose first
    element is the base slot key, so it can never match a marker prefix."""
    # Fix LevelKey mismatch: LevelKey(base, level) where base itself is a
    # marker tuple (e.g. rekeyed stash) would otherwise check LevelKey[0]==base
    # (a tuple) not the marker string. Unwrap to the base first.
    if isinstance(key, LevelKey):
        key = key.base
    return (
        isinstance(key, tuple) and len(key) > 0 and key[0] in ("_prev_content", "_content_stash")
    )


def _is_rekeyed_content_baseline(last_good_key) -> bool:
    """Whether ``last_good_key``'s texture/diff keys carry a rekeyed
    old-content marker anywhere (both sides checked -- either side can be
    the swapped one). ``None`` (no fallback baseline yet) is never a
    content swap."""
    if last_good_key is None:
        return False
    texture_keys, diff_key = last_good_key
    return any(_is_rekeyed_content_key(k) for k in texture_keys) or _is_rekeyed_content_key(diff_key)


# Throttle per-frame ic-preview/gap logs: render() at 60Hz would otherwise
# spam >10 lines/frame. Emit only when the tuple that the line reports
# actually changes (same sig as fallback decision, sources, draw plan).
_last_renderer_sources_raw_sig: tuple | None = None
_last_renderer_sources_committed_sig: tuple | None = None
_last_renderer_fallback_sig: tuple | None = None
_last_renderer_draw_plan_sig: tuple | None = None
_last_renderer_coverage_sig: tuple | None = None
_last_renderer_rekeyed_sig: tuple | None = None


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
        # Whether the current fallback baseline is a genuine content
        # replacement (preview->store flip, same-slot image swap, source-role
        # switch) rather than a LOD/pyramid-level churn on the same content:
        # while set, ``_resolve_fallback_plan`` runs ``resolve_fallback_lod``
        # in atomic mode so the old content stays on screen in full until the
        # new content's current-view tiles are all resident, then the whole
        # draw plan flips in one frame -- never a per-tile pop-in mixing old
        # and new. Set on the frame a source identity change commits (a
        # one-frame fact that must persist for the whole transition); cleared
        # on promotion. The rekeyed-marker signal (``_is_rekeyed_content_key``)
        # persists on its own via ``self._last_good_*`` and needs no flag.
        self._content_swap_active = False
        # Duplicate-left-on-both fallback guard: single-image mode (display_single_image_on_label)
        # uploads the same pil_image to both stored slots, so fallback's old baseline
        # is left-on-both duplicate. Holding it atomically after second image arrives
        # shows left on right as "placeholder" — obviously wrong. Track whether
        # previous frame's sources were same object to bypass that baseline.
        self._prev_sources_is_same: bool | None = None
        # Snapshots for consistent [ic-preview] logging across SET/CLEAR/result/tile_dump/gap
        self._fallback_atomic_snapshot: bool | None = None
        self._fallback_more_pending_snapshot: bool | None = None

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

    def _resolve_fallback_plan(
        self,
        *,
        tile_service: TileTextureService,
        texture_keys: tuple[object, object],
        diff_source_key: object | None,
        base_image,
        sampler_name: str,
        viewport_zoom: tuple[float, float] | None,
        viewport_offset: tuple[float, float] | None,
        main_more_pending: bool,
        current_array_plan: list,
        source_changed: bool,
        rekeyed: dict[object, object],
        current_sources_is_same: bool | None = None,
    ) -> tuple[object | None, list]:
        """Decides this frame's draw plan across a LOD-churn or content-swap
        transition and returns ``(new_last_good_key, array_draw_plan)`` --
        the caller stores ``new_last_good_key`` back onto
        ``self._last_good_*``. Owns the two pieces of caller-side fallback
        state that live in this class: ``self._last_good_*`` (the last key
        set whose tiles were fully drawable) and ``self._content_swap_active``
        (see its docstring). Extracted from render() so the content-swap
        atomicity decision is testable without a live QRhi.

        docs/dev/rendering/tile-rendering-system.md "Fallback-LOD": a plain
        LOD/pyramid-level transition progressively reveals the new level's
        tiles over the old level's still-resident ones. A genuine content
        replacement (preview->store flip, a same-slot image swap, a
        source-role switch) must instead be atomic -- every non-resident
        region of the new content keeps drawing the OLD content until the
        new content's current-view tiles are all resident, then the whole
        draw plan flips over in one frame -- via ``resolve_fallback_lod``'s
        ``atomic`` mode (docs/dev/rendering/tile-rendering-system.md
        "Fallback-LOD" / ``shared/rendering/fallback_lod.py``). The two
        signals identifying a content swap (vs. a same-content level churn)
        are:

        (1) a rekeyed old-content marker key in the fallback baseline --
        ``("_prev_content", ...)`` (eager whole-image path) or
        ``("_content_stash", ...)`` (lazy TiledPixelStore path). The marker
        survives in ``self._last_good_*`` for every frame of the transition
        (a still-pending earlier frame's substitution is carried forward
        until promotion), so it needs no extra state -- but the marker check
        itself must recognize BOTH forms: the lazy path's
        ``_content_stash`` marker used to fall through the ``_prev_content``-
        only check, leaving the swap in progressive (mixed-frame) mode.

        (2) a source identity change (``source_changed`` -- set once, on
        the frame the new source commits). The preview->store flip
        re-registers the store under a fresh ``LevelKey`` and rekeys
        nothing, so its fallback baseline (the plain old bare slot keys in
        ``self._last_good_texture_keys``) carries no marker at all; the
        source-identity change is the only signal. It is a one-frame fact,
        so it is persisted into ``self._content_swap_active`` until
        promotion, and only when a real baseline change exists (the flip
        frame's committed keys differ from the previous frame's keys --
        ``last_good_key != key``); a source change with an identical
        baseline sets nothing.
        """
        old_texture_keys = self._last_good_texture_keys
        last_good_key = (
            (old_texture_keys, self._last_good_diff_key)
            if old_texture_keys is not None
            else None
        )
        key = (texture_keys, diff_source_key)
        # A same-slot content swap (e.g. loading a new image into an
        # already-loaded side) never changes texture_keys/diff_source_key
        # themselves -- they're stable slot labels, not per-image
        # identity -- so the plain old_texture_keys comparison above can't
        # see it and last_good_key's plain form is a no-op here. When
        # realize_tile_plan rekeys a slot's stale old content instead of
        # dropping it (residency.py's last_rekeyed_keys), substitute that
        # key so resolve_fallback_lod treats this frame as a genuine key
        # change and draws the old content underneath while the new content
        # at the reused slot fills in.
        if rekeyed:
            # Fix LevelKey mismatch: rekeyed map is keyed by bare slot labels
            # ("stored_0") but texture_keys may be LevelKey("stored_0", lvl).
            # Look up via .base for LevelKeys so the marker is actually applied
            # and the log shows the real substituted marker.
            def _rekeyed_lookup(k):
                if k is None:
                    return None
                if k in rekeyed:
                    return rekeyed[k]
                if isinstance(k, LevelKey) and k.base in rekeyed:
                    # Preserve level but substitute base marker for visibility
                    try:
                        return LevelKey(rekeyed[k.base], k.level)  # type: ignore[arg-type]
                    except Exception:
                        return rekeyed[k.base]
                return k

            last_good_key = (
                tuple(_rekeyed_lookup(k) for k in texture_keys),
                _rekeyed_lookup(diff_source_key),
            )
            # throttle: rekeyed only during content swap, but still 60Hz
            try:
                global _last_renderer_rekeyed_sig  # type: ignore[used-before-def]
                _rk_sig = (tuple(str(k) for k in texture_keys), tuple(sorted((str(k), str(v)) for k, v in rekeyed.items())), str(last_good_key))  # type: ignore[has-type]
                if _rk_sig != _last_renderer_rekeyed_sig:  # type: ignore[has-type]
                    _last_renderer_rekeyed_sig = _rk_sig  # type: ignore[has-type]
                    _ic_preview_log(
                        "rekeyed LevelKey lookup: texture_keys=%s rekeyed_map=%s -> last_good=%s",
                        [str(k) for k in texture_keys],
                        {str(k): str(v) for k, v in rekeyed.items()},
                        last_good_key,
                    )
            except Exception:
                _ic_preview_log(
                    "rekeyed LevelKey lookup: texture_keys=%s rekeyed_map=%s -> last_good=%s",
                    [str(k) for k in texture_keys],
                    {str(k): str(v) for k, v in rekeyed.items()},
                    last_good_key,
                )
        # Single-image duplicate guard (left on both halves): if previous frame's
        # sources were same object (display_single_image_on_label dup) and current
        # are distinct (preview/full_res distinct distinct after second load), the
        # old baseline is left-on-both duplicate — holding it atomically would
        # show left on right as "placeholder", obviously wrong.
        # Fix is_same lag: log both prev and current, decision uses current frame's is_same.
        _prev_is_same = self._prev_sources_is_same
        if current_sources_is_same is False and _prev_is_same is True:
            _ic_preview_log(
                "fallback SKIP_DUPLICATE_BASELINE: prev=%s current=%s last_good=%s -> drop baseline",
                _prev_is_same,
                current_sources_is_same,
                last_good_key,
            )
            last_good_key = None
            # Don't keep content_swap_active for duplicate baseline
            self._content_swap_active = False
        elif _prev_is_same is not None or current_sources_is_same is not None:
            # throttle: logged every frame after first image — dedup
            try:
                _is_same_sig = (_prev_is_same, current_sources_is_same, str(last_good_key))  # type: ignore[has-type]
                # reuse fallback sig holder for this sub-line
                if not hasattr(self, "_last_is_same_sig"):
                    self._last_is_same_sig = None  # type: ignore[attr-defined]
                if _is_same_sig != self._last_is_same_sig:  # type: ignore[attr-defined]
                    self._last_is_same_sig = _is_same_sig  # type: ignore[attr-defined]
                    _ic_preview_log(
                        "fallback is_same_check: prev=%s current=%s last_good=%s keep=%s",
                        _prev_is_same,
                        current_sources_is_same,
                        last_good_key,
                        last_good_key is not None,
                    )
            except Exception:
                _ic_preview_log(
                    "fallback is_same_check: prev=%s current=%s last_good=%s keep=%s",
                    _prev_is_same,
                    current_sources_is_same,
                    last_good_key,
                    last_good_key is not None,
                )
        _prev_swap = self._content_swap_active
        if source_changed and last_good_key is not None and last_good_key != key:
            # A content replacement just committed (see the flag's
            # docstring for which cases). Hold the old content on screen
            # for the whole transition, not just this frame.
            self._content_swap_active = True
            _ic_preview_log(
                "fallback content_swap_active: SET (source_changed=%s last_good=%s key=%s prev=%s -> True)",
                source_changed,
                last_good_key,
                key,
                _prev_swap,
            )
        is_content_swap = self._content_swap_active or _is_rekeyed_content_baseline(
            last_good_key
        )
        # Capture decision snapshot for consistent logging across SET/CLEAR/result/tile_dump/gap
        decision_is_content_swap = is_content_swap
        decision_content_swap_flag = self._content_swap_active
        decision_last_good_has_marker = _is_rekeyed_content_baseline(last_good_key)
        # Throttle: fallback decision at 60Hz — emit only when sig changes.
        # Previously always emitted so grep could correlate, now sig includes
        # the tuple that the decision reports; steady state (same key/pending)
        # no longer spams.
        global _last_renderer_fallback_sig  # type: ignore[used-before-def]
        _fallback_sig = (str(key), str(last_good_key), decision_is_content_swap, main_more_pending, len(current_array_plan), str(dict(rekeyed) if rekeyed else None))  # type: ignore[has-type]
        _should_emit_fallback = _fallback_sig != _last_renderer_fallback_sig  # type: ignore[has-type]
        if _should_emit_fallback:
            _last_renderer_fallback_sig = _fallback_sig  # type: ignore[has-type]
            _ic_preview_log(
                "fallback decision: source_changed=%s last_good=%s key=%s rekeyed=%s is_content_swap=%s atomic=%s more_pending=%s current_entries=%d last_good_has_marker=%s content_swap_flag=%s decision_atomic=%s",
                source_changed,
                last_good_key,
                key,
                dict(rekeyed) if rekeyed else None,
                decision_is_content_swap,
                decision_is_content_swap,
                main_more_pending,
                len(current_array_plan),
                decision_last_good_has_marker,
                decision_content_swap_flag,
                decision_is_content_swap,
            )
            if _gap_enabled():
                try:
                    _gap_log(
                        "gap fallback decision key=%s last_good=%s atomic=%s more_pending=%s current=%d letterbox1=%s letterbox2=%s grid1=%sx%s grid2=%sx%s",
                        key,
                        last_good_key,
                        decision_is_content_swap,
                        main_more_pending,
                        len(current_array_plan),
                        tuple(base_image.letterbox1),
                        tuple(base_image.letterbox2),
                        tile_service.grid_for(texture_keys[0]).rows if tile_service.grid_for(texture_keys[0]) else 1,
                        tile_service.grid_for(texture_keys[0]).columns if tile_service.grid_for(texture_keys[0]) else 1,
                        tile_service.grid_for(texture_keys[1]).rows if tile_service.grid_for(texture_keys[1]) else 1,
                        tile_service.grid_for(texture_keys[1]).columns if tile_service.grid_for(texture_keys[1]) else 1,
                    )
                except Exception:
                    pass
        # Stash snapshot for render() gap log (same frame, after promotion clears flag)
        self._fallback_atomic_snapshot = decision_is_content_swap
        self._fallback_more_pending_snapshot = main_more_pending
        fallback_diag: dict[str, int] = {}
        # Fast path: promotion without fallback — avoid closure alloc per frame
        # Guard: sliver-contaminated plan (float seam 0.00078) reports
        # coverage healthy but is visually gapped. If >50% of bboxes are
        # narrow (<0.001), treat as not ready — don't promote on
        # more_pending=False, fall through to fallback/keep old baseline.
        _narrow_blocked = False
        if not main_more_pending and current_array_plan:
            try:
                _narrow_cnt = sum(
                    1
                    for _it in current_array_plan
                    if _it.bbox[2] < 0.001 or _it.bbox[3] < 0.001
                )
                if _narrow_cnt / len(current_array_plan) > 0.5:
                    _narrow_blocked = True
                    if _gap_enabled():
                        try:
                            _gap_log(
                                "gap promotion_blocked narrow=%d/%d ratio=%.2f entries=%d more_pending=False",
                                _narrow_cnt,
                                len(current_array_plan),
                                _narrow_cnt / len(current_array_plan),
                                len(current_array_plan),
                            )
                        except Exception:
                            pass
            except Exception:
                _narrow_blocked = False
        if not main_more_pending and current_array_plan and not _narrow_blocked:
            new_last_good_key, array_draw_plan = key, current_array_plan
        else:

            def _build_fallback_items(prior_key):
                prior_texture_keys, prior_diff_key = prior_key
                items = build_array_draw_plan(
                    tile_service,
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
                key=key,
                current_items=current_array_plan,
                more_pending=main_more_pending,
                last_good_key=last_good_key,
                build_fallback_items=_build_fallback_items,
                drop_covered=_drop_covered,
                atomic=is_content_swap,
            )
        if new_last_good_key == key:
            # Promotion: the new content's current-view tiles are all
            # resident; the transition is over. From here on, further
            # LOD-level churn on the (now committed) content is a plain
            # progressive reveal again.
            if decision_content_swap_flag:
                # content_swap cleared is a one-shot event — always log
                _ic_preview_log(
                    "fallback content_swap_active: CLEARED on promotion (new_last_good==key %s) decision_atomic_was=%s",
                    key,
                    decision_is_content_swap,
                )
            self._content_swap_active = False
            # Promotion vs fallback explicit — throttled via _should_emit_fallback
            if _should_emit_fallback:
                _ic_preview_log(
                    "fallback promotion: promoted=True key=%s more_pending_at_decision=%s coverage_will_be_checked_in_render",
                    key,
                    self._fallback_more_pending_snapshot,
                )
        else:
            if _should_emit_fallback:
                _ic_preview_log(
                    "fallback no_promotion: promoted=False fallback_kept=%s current=%d more_pending=%s atomic=%s",
                    fallback_diag.get("kept"),
                    len(current_array_plan),
                    main_more_pending,
                    decision_is_content_swap,
                )
        # Result line: throttled — steady-state promoted frames would otherwise spam
        if _should_emit_fallback:
            _ic_preview_log(
                "fallback result: atomic=%s fallback_raw=%s fallback_kept=%s resolved=%d current=%d more_pending=%s last_good=%s new_last_good=%s promoted=%s decision_atomic=%s",
                decision_is_content_swap,
                fallback_diag.get("raw"),
                fallback_diag.get("kept"),
                len(array_draw_plan),
                len(current_array_plan),
                self._fallback_more_pending_snapshot,
                last_good_key,
                new_last_good_key,
                new_last_good_key == key,
                decision_is_content_swap,
            )
        if fallback_diag and fallback_diag.get("raw") == 0 and _should_emit_fallback:
            _ic_preview_log(
                "fallback EMPTY: atomic=%s old_keys=%s — placeholder had no resident tiles, degraded to partial new content",
                decision_is_content_swap,
                old_texture_keys,
            )
        elif not fallback_diag and last_good_key is not None and last_good_key != key:
            # resolve_fallback_lod returned last_good_key without building fallback
            # (e.g. no fallback path taken because last_good == key?) — log so
            # missing placeholder is not silent.
            pass  # covered by fallback result above
        elif last_good_key is None and _should_emit_fallback:
            _ic_preview_log(
                "fallback NO_BASELINE: last_good is None (first paint or after eviction) — no placeholder possible for key=%s",
                key,
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
                main_more_pending=self._fallback_more_pending_snapshot,
                fallback_active=bool(fallback_diag),
                rekeyed_same_slot_swap={str(k): str(v) for k, v in rekeyed.items()}
                if rekeyed
                else None,
                content_swap_active=decision_is_content_swap,
                decision_atomic=decision_is_content_swap,
                decision_flag=decision_content_swap_flag,
            )
        return new_last_good_key, array_draw_plan

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
            # Gated debug: avoid 4× image_uid + type + closure alloc per frame when off
            # sources vs draw_plan stale fix: this is raw (pre-LOD) log; the
            # committed log after LOD commit below reflects what was actually drawn.
            if _ic_preview_enabled():
                # throttle: raw sources at 60Hz — emit only when sig changes
                try:
                    global _last_renderer_sources_raw_sig  # type: ignore[used-before-def]
                    _raw_sig = (base_image.use_hires, tuple(str(k) for k in texture_keys), tuple(image_uid(s) if s is not None else None for s in sources), tuple(type(s).__name__ if s is not None else None for s in sources))  # type: ignore[has-type]
                    if _raw_sig != _last_renderer_sources_raw_sig:  # type: ignore[has-type]
                        _last_renderer_sources_raw_sig = _raw_sig  # type: ignore[has-type]
                        def _sz(o):
                            if o is None:
                                return None
                            try:
                                from shared.image_processing.tiled_pixel_store import (
                                    pixel_source_size,
                                )

                                w, h = pixel_source_size(o)
                                if w == 0 and h == 0:
                                    return None
                                return (w, h)
                            except Exception:
                                return None
                            # Legacy path kept for reference (hasattr now raises
                            # RuntimeError on closed TiledPixelStore under Python 3.14):
                            # if hasattr(o, "size"): ...
                        _ic_preview_log(
                            "sources raw use_hires=%s tex_keys_raw=%s src_tex_ids=%s src_uids=%s types=%s sizes=%s ids=0x%x/0x%x stored_uids=%s source_pil_uids=%s is_same_object_raw=%s",
                            base_image.use_hires,
                            list(texture_keys),
                            list(ctx.source_texture_ids),
                            [image_uid(s) if s is not None else None for s in sources],
                            [type(s).__name__ if s is not None else None for s in sources],
                            [_sz(s) for s in sources],
                            id(sources[0]) if len(sources) > 0 and sources[0] is not None else 0,
                            id(sources[1]) if len(sources) > 1 and sources[1] is not None else 0,
                            [image_uid(s) if s is not None else None for s in ctx.stored_pil_images],
                            [image_uid(s) if s is not None else None for s in getattr(widget.runtime_state, "_source_pil_images", ())],
                            (len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]),
                        )
                except Exception:
                    # fallback: log without throttle
                    def _sz(o):
                        if o is None:
                            return None
                        try:
                            from shared.image_processing.tiled_pixel_store import (
                                pixel_source_size,
                            )

                            w, h = pixel_source_size(o)
                            if w == 0 and h == 0:
                                return None
                            return (w, h)
                        except Exception:
                            return None
                    _ic_preview_log(
                        "sources raw use_hires=%s tex_keys_raw=%s src_tex_ids=%s src_uids=%s types=%s sizes=%s ids=0x%x/0x%x stored_uids=%s source_pil_uids=%s is_same_object_raw=%s",
                        base_image.use_hires,
                        list(texture_keys),
                        list(ctx.source_texture_ids),
                        [image_uid(s) if s is not None else None for s in sources],
                        [type(s).__name__ if s is not None else None for s in sources],
                        [_sz(s) for s in sources],
                        id(sources[0]) if len(sources) > 0 and sources[0] is not None else 0,
                        id(sources[1]) if len(sources) > 1 and sources[1] is not None else 0,
                        [image_uid(s) if s is not None else None for s in ctx.stored_pil_images],
                        [image_uid(s) if s is not None else None for s in getattr(widget.runtime_state, "_source_pil_images", ())],
                        (len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]),
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
            # sources vs draw_plan stale fix: log after LOD commit so is_same and tex_keys reflect committed draw.
            if _ic_preview_enabled():
                # throttle committed sources — 60Hz spam
                try:
                    global _last_renderer_sources_committed_sig  # type: ignore[used-before-def]
                    _is_same_committed = len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]
                    _comm_sig = (base_image.use_hires, tuple(str(k) for k in raw_texture_keys), tuple(str(k) for k in texture_keys), _is_same_committed, tuple(image_uid(s) if s is not None else None for s in sources))  # type: ignore[has-type]
                    if _comm_sig != _last_renderer_sources_committed_sig:  # type: ignore[has-type]
                        _last_renderer_sources_committed_sig = _comm_sig  # type: ignore[has-type]
                        _ic_preview_log(
                            "sources committed use_hires=%s tex_keys_raw=%s tex_keys_committed=%s is_same_object_committed=%s src_uids=%s committed_uids_src=%s",
                            base_image.use_hires,
                            [str(k) for k in raw_texture_keys],
                            [str(k) for k in texture_keys],
                            _is_same_committed,
                            [image_uid(s) if s is not None else None for s in sources],
                            list(source_ids),
                        )
                        _ic_preview_log(
                            "draw_sources committed tex_keys=%s is_same=%s committed_src_ids=%s raw_src_ids=%s",
                            [str(k) for k in texture_keys],
                            _is_same_committed,
                            list(source_ids),
                            [str(k) for k in raw_texture_keys],
                        )
                except Exception:
                    _is_same_committed = len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]
                    _ic_preview_log(
                        "sources committed use_hires=%s tex_keys_raw=%s tex_keys_committed=%s is_same_object_committed=%s src_uids=%s committed_uids_src=%s",
                        base_image.use_hires,
                        [str(k) for k in raw_texture_keys],
                        [str(k) for k in texture_keys],
                        _is_same_committed,
                        [image_uid(s) if s is not None else None for s in sources],
                        list(source_ids),
                    )
                    _ic_preview_log(
                        "draw_sources committed tex_keys=%s is_same=%s committed_src_ids=%s raw_src_ids=%s",
                        [str(k) for k in texture_keys],
                        _is_same_committed,
                        list(source_ids),
                        [str(k) for k in raw_texture_keys],
                    )
            if source_changed:
                _ic_preview_log(
                    "lod_commit source_changed=True src_ids=%s raw=%s committed=%s pending_ms=%.1f",
                    list(source_ids),
                    [str(k) for k in raw_texture_keys],
                    [str(k) for k in texture_keys],
                    (now - self._lod_pending_since) * 1000.0,
                )
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
            # Cache union once — used for both diagnostic and residency
            _cap_uv = None
            if _mag_branch_active or tile_dump_enabled():
                _cap_uv = _union_capture_uv_rect(overlay) if overlay is not None else None
            if tile_dump_enabled():
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
                    capture_uv_rect=_cap_uv,
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
            # instead of blanking. For a genuine content swap the same
            # mechanism runs in atomic mode (current tiles stay hidden
            # until the new content is fully resident) -- see
            # ``_resolve_fallback_plan``.
            _cur_is_same = len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]
            new_last_good_key, array_draw_plan = self._resolve_fallback_plan(
                tile_service=self.tile_service,
                texture_keys=texture_keys,
                diff_source_key=diff_source_key,
                base_image=base_image,
                sampler_name=sampler_name,
                viewport_zoom=viewport_zoom,
                viewport_offset=viewport_offset,
                main_more_pending=main_more_pending,
                current_array_plan=current_array_plan,
                source_changed=source_changed,
                rekeyed=self.resources.residency.last_rekeyed_keys,
                current_sources_is_same=_cur_is_same,
            )
            # Remember for next frame's duplicate-baseline guard
            self._prev_sources_is_same = _cur_is_same
            self._last_good_texture_keys, self._last_good_diff_key = (
                new_last_good_key if new_last_good_key is not None else (None, None)
            )
            rhi_render_debug(
                "render array_draw_plan=%d entries", len(array_draw_plan)
            )
            # Real draw content (not wishful sources): per-tile layers/bbox — if
            # fallback holds old duplicate, both layers will be same _prev_content
            # even when sources already distinct.
            if array_draw_plan and _ic_preview_enabled():
                # throttle: draw_plan at 60Hz — same plan every steady frame
                try:
                    global _last_renderer_draw_plan_sig  # type: ignore[used-before-def]
                    _dp_sig = (tuple(str(k) for k in texture_keys), len(array_draw_plan), tuple(getattr(it, "layer1", None) for it in array_draw_plan[:2]), tuple(getattr(it, "layer2", None) for it in array_draw_plan[:2]))  # type: ignore[has-type]
                    if _dp_sig != _last_renderer_draw_plan_sig:  # type: ignore[has-type]
                        _last_renderer_draw_plan_sig = _dp_sig  # type: ignore[has-type]
                        _ic_preview_log(
                            "draw_plan tex_keys=%s entries=%d layers1_sample=%s layers2_sample=%s bboxes=%s",
                            list(texture_keys),
                            len(array_draw_plan),
                            [getattr(it, "layer1", None) for it in array_draw_plan[:3]],
                            [getattr(it, "layer2", None) for it in array_draw_plan[:3]],
                            [getattr(it, "bbox", None) for it in array_draw_plan[:2]],
                        )
                except Exception:
                    _ic_preview_log(
                        "draw_plan tex_keys=%s entries=%d layers1_sample=%s layers2_sample=%s bboxes=%s",
                        list(texture_keys),
                        len(array_draw_plan),
                        [getattr(it, "layer1", None) for it in array_draw_plan[:3]],
                        [getattr(it, "layer2", None) for it in array_draw_plan[:3]],
                        [getattr(it, "bbox", None) for it in array_draw_plan[:2]],
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
            if rhi_render_debug_enabled() or _ic_preview_enabled():
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
                # [ic-gap] bbox distribution + bbox coverage for central strip
                _bbox_min = _bbox_med = _bbox_max = 0.0
                _bbox_narrow = 0
                _bbox_cov = 1.0
                if _gap_enabled() and array_draw_plan:
                    try:
                        _bws = [b[2] for b in (it.bbox for it in array_draw_plan)]
                        _bhs = [b[3] for b in (it.bbox for it in array_draw_plan)]
                        _bws_sorted = sorted(_bws)
                        _bbox_min = min(_bws) if _bws else 0.0
                        _bbox_max = max(_bws) if _bws else 0.0
                        _bbox_med = _bws_sorted[len(_bws_sorted)//2] if _bws_sorted else 0.0
                        _bbox_narrow = sum(1 for w in _bws if w < 0.01)
                        # bbox coverage over overlap of visibles
                        from shared.rendering.tile_coverage import intersection_rect as _gap_int, rects_overlap as _gap_overlap
                        if _gap_overlap(visible1_common, visible2_common):
                            _overlap = _gap_int(visible1_common, visible2_common)
                            _bbox_cov = _covered_fraction(_overlap, [it.bbox for it in array_draw_plan])
                        else:
                            _bbox_cov = 0.0
                        if _bbox_narrow > 0 or _bbox_cov < 0.999:
                            _gap_log(
                                "gap bbox_dist entries=%d bbox w min=%.5f med=%.5f max=%.5f narrow<0.01=%d bbox_cov=%.4f covered=%.4f/%.4f letterbox1=%s letterbox2=%s grid1=%sx%s grid2=%sx%s",
                                len(array_draw_plan),
                                _bbox_min,
                                _bbox_med,
                                _bbox_max,
                                _bbox_narrow,
                                _bbox_cov,
                                covered1,
                                covered2,
                                letterbox1,
                                letterbox2,
                                tile_service.grid_for(texture_keys[0]).rows if tile_service.grid_for(texture_keys[0]) else 1,
                                tile_service.grid_for(texture_keys[0]).columns if tile_service.grid_for(texture_keys[0]) else 1,
                                tile_service.grid_for(texture_keys[1]).rows if tile_service.grid_for(texture_keys[1]) else 1,
                                tile_service.grid_for(texture_keys[1]).columns if tile_service.grid_for(texture_keys[1]) else 1,
                            )
                            if _bbox_min < 0.005 and _bbox_narrow > 0:
                                try:
                                    from core.tracing.tracer import Tracer as _Tracer2
                                    if _Tracer2.enabled():
                                        _Tracer2.instance().record("ic.gap.narrow_bbox", f"narrow bbox min {_bbox_min:.5f} narrow {_bbox_narrow}/{len(array_draw_plan)}", {"min_w": _bbox_min, "narrow": _bbox_narrow, "bbox_cov": _bbox_cov}, caller_skip=1)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                # Make more_pending vs coverage gap explicit: more_pending tells
                # whether residency still has tiles to upload, covered tells
                # whether the current draw plan actually covers the visible
                # rect. A gap with more_pending=True is expected progressive
                # fill-in; a gap with more_pending=False is the real bug (fallback
                # failed to cover the hole). Use decision snapshot for atomic
                # so SET/CLEAR/result/tile_dump/gap share one value.
                _gap_atomic = getattr(self, "_fallback_atomic_snapshot", self._content_swap_active)
                _gap_more = getattr(self, "_fallback_more_pending_snapshot", False)
                # Fallback to local main_more_pending if snapshot missing but variable exists
                if _gap_more is None:
                    try:
                        _gap_more = main_more_pending
                    except NameError:
                        _gap_more = False
                _bbox_cov_for_gap = locals().get("_bbox_cov", 1.0)
                _bbox_min_for_gap = locals().get("_bbox_min", 0.0)
                if covered1 < 0.999 or covered2 < 0.999 or _bbox_cov_for_gap < 0.999:
                    rhi_render_debug(
                        "render GAP_DETECTED covered1=%.4f covered2=%.4f bbox=%.4f entries=%d "
                        "main_more_pending=%s decision_atomic=%s coverage_gap=True",
                        covered1,
                        covered2,
                        _bbox_cov_for_gap,
                        len(array_draw_plan),
                        _gap_more,
                        _gap_atomic,
                    )
                    _ic_preview_log(
                        "gap_detected covered1=%.4f covered2=%.4f bbox=%.4f entries=%d more_pending=%s atomic=%s decision_atomic=%s coverage=%.4f/%.4f/%.4f gap_vs_pending=%s",
                        covered1,
                        covered2,
                        _bbox_cov_for_gap,
                        len(array_draw_plan),
                        _gap_more,
                        self._content_swap_active,
                        _gap_atomic,
                        covered1,
                        covered2,
                        _bbox_cov_for_gap,
                        "expected_more_pending" if _gap_more else "BUG_no_more_pending_but_gap",
                    )
                    if _gap_enabled():
                        try:
                            _gap_log(
                                "gap GAP_DETECTED covered=%.4f/%.4f bbox=%.4f min_w=%.5f entries=%d more_pending=%s atomic=%s letterbox1=%s letterbox2=%s",
                                covered1,
                                covered2,
                                _bbox_cov_for_gap,
                                _bbox_min_for_gap,
                                len(array_draw_plan),
                                _gap_more,
                                _gap_atomic,
                                letterbox1,
                                letterbox2,
                            )
                            try:
                                from core.tracing.tracer import Tracer as _Tracer3
                                if _Tracer3.enabled():
                                    _Tracer3.instance().record("ic.gap.detected", f"GAP covered {covered1:.3f}/{covered2:.3f} bbox {_bbox_cov_for_gap:.3f}", {"covered1": covered1, "covered2": covered2, "bbox_cov": _bbox_cov_for_gap, "entries": len(array_draw_plan), "more_pending": _gap_more, "atomic": _gap_atomic, "letterbox1": str(letterbox1), "letterbox2": str(letterbox2)}, caller_skip=1)
                            except Exception:
                                pass
                        except Exception:
                            pass
                elif _ic_preview_enabled():
                    # Log healthy coverage explicitly so more_pending vs coverage
                    # correlation is visible even without a gap — throttled.
                    try:
                        global _last_renderer_coverage_sig  # type: ignore[used-before-def]
                        _cov_sig = (round(covered1, 3), round(covered2, 3), round(_bbox_cov_for_gap, 3), len(array_draw_plan), bool(_gap_more), bool(_gap_atomic))  # type: ignore[has-type,has-type]
                        if _cov_sig != _last_renderer_coverage_sig:  # type: ignore[has-type]
                            _last_renderer_coverage_sig = _cov_sig  # type: ignore[has-type]
                            _ic_preview_log(
                                "coverage_healthy covered1=%.4f covered2=%.4f bbox=%.4f entries=%d more_pending=%s atomic=%s decision_atomic=%s",
                                covered1,
                                covered2,
                                _bbox_cov_for_gap,
                                len(array_draw_plan),
                                _gap_more,
                                self._content_swap_active,
                                _gap_atomic,
                            )
                            if _gap_enabled():
                                try:
                                    _gap_log(
                                        "gap healthy covered=%.4f/%.4f bbox=%.4f entries=%d more_pending=%s atomic=%s",
                                        covered1,
                                        covered2,
                                        _bbox_cov_for_gap,
                                        len(array_draw_plan),
                                        _gap_more,
                                        _gap_atomic,
                                    )
                                except Exception:
                                    pass
                    except Exception:
                        _ic_preview_log(
                            "coverage_healthy covered1=%.4f covered2=%.4f bbox=%.4f entries=%d more_pending=%s atomic=%s decision_atomic=%s",
                            covered1,
                            covered2,
                            _bbox_cov_for_gap,
                            len(array_draw_plan),
                            _gap_more,
                            self._content_swap_active,
                            _gap_atomic,
                        )
                        if _gap_enabled():
                            try:
                                _gap_log(
                                    "gap healthy covered=%.4f/%.4f bbox=%.4f entries=%d more_pending=%s atomic=%s",
                                    covered1,
                                    covered2,
                                    _bbox_cov_for_gap,
                                    len(array_draw_plan),
                                    _gap_more,
                                    _gap_atomic,
                                )
                            except Exception:
                                pass

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
