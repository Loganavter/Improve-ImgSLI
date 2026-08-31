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
from .use_cases.coverage import (
    apply_first_paint_hold as _apply_first_paint_hold_impl,
    evaluate_coverage as _evaluate_coverage_impl,
)
from .use_cases.fallback import (
    _is_rekeyed_content_key,
    _is_rekeyed_content_baseline,
    resolve_fallback_plan as _resolve_fallback_plan_impl,
)
from .use_cases.lod_commit import commit_lod_keys
from .use_cases.tile_residency import (
    realize_main_tiles as _realize_main_tiles_impl,
    realize_magnifier_tiles as _realize_magnifier_tiles_impl,
)

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
# Coverage/first_paint throttle lives in use_cases/coverage.py (thin owner).
_last_renderer_sources_raw_sig: tuple | None = None
_last_renderer_sources_committed_sig: tuple | None = None
_last_renderer_fallback_sig: tuple | None = None
_last_renderer_draw_plan_sig: tuple | None = None
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
        """Thin delegator — body lives in use_cases/fallback.py (CODE_PATTERNS)."""
        return _resolve_fallback_plan_impl(
            self,
            tile_service=tile_service,
            texture_keys=texture_keys,
            diff_source_key=diff_source_key,
            base_image=base_image,
            sampler_name=sampler_name,
            viewport_zoom=viewport_zoom,
            viewport_offset=viewport_offset,
            main_more_pending=main_more_pending,
            current_array_plan=current_array_plan,
            source_changed=source_changed,
            rekeyed=rekeyed,
            current_sources_is_same=current_sources_is_same,
        )

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
            texture_keys, source_changed = commit_lod_keys(
                self,
                texture_keys,
                sources,
                base_image,
                (ctx.canvas_width * scale_px, ctx.canvas_height * scale_px),
            )
            diff_source_key = (
                ctx.diff_source_texture_id if ctx.diff_source_ready else None
            )
            sampler_name = (
                "nearest"
                if str(ctx.scene_frame.zoom_interpolation_method).upper() == "NEAREST"
                else "linear"
            )
            main_more_pending = _realize_main_tiles_impl(
                self,
                widget,
                texture_keys,
                base_image,
                updates,
                diff_source_key,
                viewport_zoom,
                viewport_offset,
                dirty_layers,
            )
            _realize_magnifier_tiles_impl(
                self,
                widget,
                ctx,
                texture_keys,
                base_image,
                viewport_zoom,
                viewport_offset,
                dirty_layers,
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
            prev_last_good = self._last_good_texture_keys
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
            # Coverage diagnostics (gap healthy/detected) + first-paint hold — thin delegator (CODE_PATTERNS)
            _covered1, _covered2, _bbox_cov = _evaluate_coverage_impl(
                self,
                self.tile_service,
                texture_keys,
                base_image,
                viewport_zoom,
                viewport_offset,
                array_draw_plan,
                main_more_pending,
            )
            array_draw_plan = _apply_first_paint_hold_impl(
                self,
                array_draw_plan,
                current_array_plan,
                main_more_pending,
                prev_last_good,
                base_image,
                viewport_zoom,
                viewport_offset,
                covered1=_covered1,
                covered2=_covered2,
                bbox_cov=_bbox_cov,
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

        # Draw submit — thin owner (CODE_PATTERNS). Body lives in use_cases/draw.py
        # so feature-pass gating (requires_content) + array pipeline setup +
        # beginPass/draw/endPass stay together and renderer stays sequencing-only.
        from .use_cases.draw import submit_array_draw as _submit_array_draw_impl

        _submit_array_draw_impl(
            self,
            widget,
            command_buffer,
            array_draw_plan,
            ctx=ctx,
            updates=updates,
            target=target,
            clear_color=clear_color,
            base_image=base_image,
            diff_ready=ctx.diff_source_ready if ctx is not None else None,
        )
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
