# Audit-Meta: pattern=thin-owner reason="RhiCanvasRenderer thin owner delegates to use_cases/* per CODE_PATTERNS — frame sequencing only"
from __future__ import annotations

import logging
import time

from PySide6.QtGui import QRhiCommandBuffer, QRhiDepthStencilClearValue, QRhiViewport

from ui.canvas_infra.rhi.rhi_backend import query_max_texture_size
from ui.canvas_infra.rhi.render_executor import iter_active_render_passes
from engine.cache.tile_constants import MIPS_CASCADE_TIME_BUDGET_MS
from shared.debug_flags import env_value as _env_value
from engine.cache.tile_debug import (
    log_tile_event,
    tile_dump_enabled,
)
from engine.cache.tile_texture_service import (
    TileTextureService,
    _tile_indices_with_margin,
)
from ..texture_parts.tile_geometry import (
    _apron_rect,
    _TILE_APRON_PX,
    _viewport_zoom_offset_for_tile,
    _visible_side_image_rect,
)
from engine.gpu.glass_panel import GlassPanelRenderer
from ._debug import rhi_render_debug, rhi_render_debug_enabled
from engine.frame.context import (
    BudgetStats,
    FrameContext,
    make_ids,
    snapshot_last_frame,
)
from engine.frame.trace_export import maybe_dump_trace
from tabs.image_compare.canvas.loupe_trace import throttle_emit as _throttle_emit
from core.log_names import APP_LOGGER_NAME

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
    build_array_draw_plan,
    resolve_lod_texture_keys,
)
from .residency import _TILE_CACHE_BUDGET_BYTES
from .resources import (
    _ARRAY_CAPACITY,
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
from .use_cases.frame_setup import prepare_frame as _prepare_frame_impl
from .use_cases.tile_residency import (
    realize_main_tiles as _realize_main_tiles_impl,
    realize_magnifier_tiles as _realize_magnifier_tiles_impl,
)

logger = logging.getLogger(APP_LOGGER_NAME)


def _skip_mip_cascade_requested(raw: str) -> bool:
    """Parse ``IMGSLI_SKIP_MIP_CASCADE`` exactly like Multi Compare does.

    Kept byte-identical on purpose (``""``/``0``/``false``/``no``/``off`` are
    off, anything else is on): one env var must A/B the same cascade toggle in
    both canvas tabs, and importing the other tab's constant is forbidden.
    """
    return raw.strip().lower() not in ("", "0", "false", "no", "off")


# Debug-only bisection toggle, shared semantics with Multi Compare's renderer:
# skips the manual per-layer mip-downsample cascade entirely, leaving every
# array layer's mip levels 1+ stale/uninitialized while level 0 still uploads
# normally. If a flip/shrink artifact disappears with this set, the bug is in
# the cascade; if it persists, the cascade is innocent. Never set outside
# manual debugging -- coarser LOD levels will look wrong (stale or blank) by
# design when this is on.
_SKIP_MIP_CASCADE = _skip_mip_cascade_requested(
    _env_value("IMGSLI_SKIP_MIP_CASCADE", "")
)

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


# _union_capture_uv_rect moved to use_cases/tile_residency.py (CODE_PATTERNS)


# _is_rekeyed_content_key re-exported from use_cases/fallback.py (CODE_PATTERNS)


# _is_rekeyed_content_baseline re-exported from use_cases/fallback.py (CODE_PATTERNS)


# Throttle per-frame draw_plan log: render() at 60Hz would otherwise
# spam. Emit only when sig changes. State lives in loupe_trace's
# centralized throttle store (stream "renderer.draw_plan"); other
# throttles live in use_cases/* (thin owner).


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
        # Same capacity the pool sizes its SRB-bound array from: the service
        # must never hand out a layer `tile_arrays[0]` cannot address.
        self.tile_service = TileTextureService(max_array_size=_ARRAY_CAPACITY)
        self.feature_passes: list[object] = []
        # Set only after every feature pass initialized successfully (see
        # initialize()). Gates the same-rhi early return on *completed* init,
        # not on a merely non-empty ``feature_passes`` list: one raising pass
        # used to leave a half-initialized list that the guard treated as
        # "already done", so the retry never happened. ``release()`` ends with
        # ``self.__init__()``, which resets this to False.
        self.initialized = False
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
        # P1A frame-context: per-frame decision collector, reused across
        # frames (reset in render()). Pilot writers record additively.
        self.frame_context = FrameContext()

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
        if new_rhi is self.rhi and self.initialized:
            return
        self.release()
        self.rhi = new_rhi
        # docs/dev/TILED_RENDERING_DESIGN.md Phase 2: fixed tile size
        # (_LIVE_TILE_EXTENT), clamped by the backend's real max texture size
        # as a defensive floor only — real backends support far more than
        # 2048px, so this clamp should never actually bind in practice.
        self.tile_service = TileTextureService(
            max_tile_extent=min(_LIVE_TILE_EXTENT, query_max_texture_size(self.rhi)),
            max_array_size=_ARRAY_CAPACITY,
        )
        self.resources.initialize(self.rhi, widget, command_buffer)
        self.glass_panel_renderer.initialize(self.rhi)

        from tabs.image_compare.canvas.registry import registry

        passes = [type(render_pass)() for render_pass in registry().get_render_passes()]
        target = widget.renderTarget()
        rhi_render_debug(
            "initialize widget=%s size=%dx%d target_px=%s api=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target.pixelSize() if target is not None else None,
            getattr(widget.api(), "name", "unknown"),
        )
        # Publish only on full success: a pass that raises mid-loop must not
        # leave ``feature_passes`` non-empty, or the same-rhi early return
        # above could latch the renderer into drawing with a half-initialized
        # pass set. Release just the passes whose initialize() returned (an
        # uninitialized pass may own no GPU objects); a failing cleanup never
        # masks the original exception.
        initialized: list[object] = []
        try:
            for render_pass in passes:
                render_pass.initialize(self.rhi, target)
                initialized.append(render_pass)
        except BaseException:
            for done in initialized:
                try:
                    done.release()
                except Exception:
                    pass
            raise
        self.feature_passes = passes
        self.initialized = True
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
        frame_context: FrameContext | None = None,
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
            frame_context=frame_context,
        )

    def _run_mips_cascade(
        self,
        command_buffer,
        dirty_layers: dict[int, set[int]],
        dirty_layer_count: int,
    ) -> tuple[dict[int, set[int]], float]:
        """Cascade this frame's dirty layers into their mips.

        Returns ``(deferred_groups, cpu_submit_ms)`` -- the pairs the time
        budget pushed out, so ``render()`` can carry them into the next frame.
        Honours ``_SKIP_MIP_CASCADE`` (same reset of the carried-over groups
        and zeroed timing Multi Compare does) so a single env var can A/B the
        cascade in both tabs without rebuilding either renderer's logic.
        """
        if _SKIP_MIP_CASCADE:
            return {}, 0.0
        start = time.monotonic()
        with self.frame_context.span(
            "ic.mips",
            detail=lambda: {"dirty_layers": dirty_layer_count},
        ):
            pending = self.resources.generate_all_dirty_mips(
                command_buffer,
                dirty_layers,
                time_budget_ms=MIPS_CASCADE_TIME_BUDGET_MS,
            )
        return pending, (time.monotonic() - start) * 1000.0

    def _request_cascade_rekick(self, widget) -> bool:
        """Ask for exactly one follow-up repaint if the cascade deferred work.

        Both canvases are on-demand, so a group deferred by the time budget
        would otherwise get no further ``render()`` to finish in: that array
        layer's upper mip levels stay permanently stale (still whatever a
        previously-evicted, unrelated tile last wrote there), and under the
        Linear mipmap filter anything below 1:1 trilinear-blends fresh level-0
        content against the previous occupant. That is why this is one bounded
        ``update()`` per frame -- never a timer or a loop: if the next frame's
        cascade defers again, it re-arms exactly one more repaint here.
        """
        if not self._pending_dirty_layers:
            return False
        self.frame_context.record_invalidation(
            "cascade_deferred",
            "mip cascade group deferred by time budget"
            f" array_index_batches={len(self._pending_dirty_layers)}"
            " -- re-kicking render for the next cascade slice",
            ids=make_ids(
                self.frame_context.frame_id, len(self._pending_dirty_layers)
            ),
        )
        widget.update()
        return True

    def render(self, widget, command_buffer, clear_color) -> bool:
        """Record one frame. Returns True after a completed beginPass/endPass.

        Early skips (no target / no rhi) return False so callers must not
        treat the frame as presented — Image Compare startup gates and the
        Windows D3D first-present path depend on this.
        """
        # P1A frame-context is born here: reset the reused collector so every
        # frame starts empty; pilot points below record into it additively.
        self.frame_context.reset()
        # Perf spans (Wave C, plan-engine-perf-debugger-2026-09-20):
        # wheel-to-photon sub-spans live on this owner context (the IC
        # FrameContext owner); lazy detail factories only, no draw change.
        with self.frame_context.span(
            "ic.prepare",
            detail=lambda: {
                "widget": type(widget).__name__,
                "size": [widget.width(), widget.height()],
            },
        ):
            _frame = _prepare_frame_impl(self, widget, command_buffer, clear_color)
        if _frame is None:
            snapshot_last_frame(self.frame_context)
            return False
        (
            ctx,
            base_image,
            should_draw,
            target_size,
            target,
            updates,
            viewport_zoom,
            viewport_offset,
            texture_keys,
            sources,
            source_changed,
            diff_source_key,
            sampler_name,
        ) = _frame
        array_draw_plan: list = []
        dirty_layers: dict[int, set[int]] = {}
        if should_draw:
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
                updates,
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
                frame_context=self.frame_context,
            )
            # fallback LOD: previous level then current (atomic for content swap)
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
                frame_context=self.frame_context,
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
                    _dp_sig = (tuple(str(k) for k in texture_keys), len(array_draw_plan), tuple(getattr(it, "layer1", None) for it in array_draw_plan[:2]), tuple(getattr(it, "layer2", None) for it in array_draw_plan[:2]))  # type: ignore[has-type]
                    if _throttle_emit("renderer.draw_plan", _dp_sig):
                        _ic_preview_log(
                            "draw_plan tex_keys=%s entries=%d layers1_sample=%s layers2_sample=%s bboxes=%s idx1_sample=%s idx2_sample=%s",
                            list(texture_keys),
                            len(array_draw_plan),
                            [getattr(it, "layer1", None) for it in array_draw_plan[:3]],
                            [getattr(it, "layer2", None) for it in array_draw_plan[:3]],
                            [getattr(it, "bbox", None) for it in array_draw_plan[:2]],
                            [getattr(it, "index1", None) for it in array_draw_plan[:3]],
                            [getattr(it, "index2", None) for it in array_draw_plan[:3]],
                        )
                except Exception:
                    _ic_preview_log(
                        "draw_plan tex_keys=%s entries=%d layers1_sample=%s layers2_sample=%s bboxes=%s idx1_sample=%s idx2_sample=%s",
                        list(texture_keys),
                        len(array_draw_plan),
                        [getattr(it, "layer1", None) for it in array_draw_plan[:3]],
                        [getattr(it, "layer2", None) for it in array_draw_plan[:3]],
                        [getattr(it, "bbox", None) for it in array_draw_plan[:2]],
                        [getattr(it, "index1", None) for it in array_draw_plan[:3]],
                        [getattr(it, "index2", None) for it in array_draw_plan[:3]],
                    )
            # coverage gap check: visible rect vs letterbox (see docs)
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
                frame_context=self.frame_context,
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
                frame_context=self.frame_context,
            )

        # submit uploads before mips cascade (Phase 9)
        command_buffer.resourceUpdate(updates)
        # Phase-2 frame bus: resourceUpdate fact (record only, never instead).
        self.frame_context.record(
            "resourceUpdate",
            "ran",
            "resourceUpdate submitted upload batch"
            f" array_index_batches={len(dirty_layers)}",
            ids=make_ids(self.frame_context.frame_id, len(dirty_layers)),
        )
        for array_index, layers in self._pending_dirty_layers.items():
            dirty_layers.setdefault(array_index, set()).update(layers)
        dirty_layer_count = sum(len(layers) for layers in dirty_layers.values())
        self._pending_dirty_layers, mips_cascade_ms = self._run_mips_cascade(
            command_buffer, dirty_layers, dirty_layer_count
        )
        deferred_count = sum(
            len(layers) for layers in self._pending_dirty_layers.values()
        )
        if dirty_layer_count:
            rhi_render_debug(
                "render MIPS_CASCADE dirty_layers=%d deferred=%d cpu_submit=%.2fms",
                dirty_layer_count,
                deferred_count,
                mips_cascade_ms,
            )
        # Phase-2 frame bus: mips cascade fact (record only, never instead).
        _mips_stats = BudgetStats(
            budget=dirty_layer_count,
            uploaded=dirty_layer_count - deferred_count,
            skipped=deferred_count,
            time_ms=mips_cascade_ms,
            budget_ms=float(MIPS_CASCADE_TIME_BUDGET_MS),
            more_pending=bool(self._pending_dirty_layers),
        )
        self.frame_context.record(
            "mips",
            "ran" if dirty_layer_count else "skipped",
            f"mips dirty_layers={dirty_layer_count}"
            f" deferred={deferred_count} {_mips_stats.describe()}",
            ids=make_ids(
                self.frame_context.frame_id,
                dirty_layer_count,
                _mips_stats.as_tuple(),
            ),
        )
        # Bounded re-kick: one update() at most, and only while a cascade
        # group is still deferred (IC has no other retry for the 8 ms budget).
        self._request_cascade_rekick(widget)
        updates = self.rhi.nextResourceUpdateBatch()

        # Draw submit — thin owner (CODE_PATTERNS). Body lives in use_cases/draw.py
        # so feature-pass gating (requires_content) + array pipeline setup +
        # beginPass/draw/endPass stay together and renderer stays sequencing-only.
        from .use_cases.draw import submit_array_draw as _submit_array_draw_impl

        _submit_array_draw_impl(
            renderer=self,
            widget=widget,
            command_buffer=command_buffer,
            array_draw_plan=array_draw_plan,
            ctx=ctx,
            updates=updates,
            target=target,
            clear_color=clear_color,
            base_image=base_image,
            diff_ready=ctx.diff_source_ready if ctx is not None else None,
            frame_context=self.frame_context,
        )
        rhi_render_debug(
            "render end widget=%s target_px=%dx%d should_draw=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            target_size.width(),
            target_size.height(),
            should_draw,
        )

        # glass backdrops: copy colorTexture after main pass (see glass_panel docs)
        glass_panels = getattr(widget, "glass_panels", None)
        if glass_panels is not None:
            self.glass_panel_renderer.render_backdrops(
                command_buffer, widget.colorTexture(), dict(glass_panels.items())
            )
            widget._glass_panel_sprites = self.glass_panel_renderer.ready_sprites
            widget._glass_panel_images = self.glass_panel_renderer.ready_images

        snapshot_last_frame(self.frame_context)
        # Perf trace dump (gated inside): serializes the span ring every
        # Nth frame so IMGSLI_PERF_TRACE=1 runs leave a Perfetto-openable
        # trace behind. Off means no file, return 0 — zero prod impact.
        maybe_dump_trace(self.frame_context)
        return True
