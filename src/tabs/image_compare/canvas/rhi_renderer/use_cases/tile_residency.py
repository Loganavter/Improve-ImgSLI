# Audit-Meta: pattern=thin-owner size=exempt reason="tile residency extracted from RhiCanvasRenderer — see renderer.py Audit-Meta state-machine"
"""Tile residency extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer.render``'s residency phase (``realize_tile_plan`` main +
magnifier) was ~80 LOC living inside the pre-split ``RhiCanvasRenderer.render``. This module holds
the same bodies as plain functions taking the owning renderer as first arg —
the owner keeps construction/wiring + instance state
(``_last_good_*``, ``tile_service``, ``resources``) per CODE_PATTERNS.md:25.
"""

from __future__ import annotations

import time
from contextlib import nullcontext

from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from engine.frame.context import BudgetStats, make_ids
from engine.cache import residency as _engine_residency
from engine.cache import tile_upload_budget as _tile_upload_budget
from tabs.image_compare.canvas.loupe_trace import (
    frame_context_from_widget,
    trace_loupe,
)
from tabs.image_compare.debug import ic_loupe_debug_enabled


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


def realize_main_tiles(
    renderer,
    widget,
    texture_keys: tuple[object, object],
    base_image,
    updates,
    diff_key: object | None,
    viewport_zoom: tuple[float, float] | None,
    viewport_offset: tuple[float, float] | None,
    dirty_layers: dict[int, set[int]],
) -> bool:
    """Viewport-driven main residency (``realize_tile_plan`` main branch).

    Thin-owner wrapper: identical to the ``fallback_protect_keys`` +
    ``realize_tile_plan`` main call in the pre-split ``RhiCanvasRenderer.render``
    — see this function's inline comments for contract. Takes ``renderer`` as
    owner (CODE_PATTERNS) and reads ``renderer._last_good_*`` / ``renderer.tile_service`` /
    ``renderer.resources.residency`` exactly as before.

    ``extra_protect_keys`` wiring is preserved: previous LOD level's tiles
    (``_last_good_*``) survive this call's eviction pass as a fallback draw
    source while the current level's tiles are still uploading (docs/dev/
    rendering/tile-array-atlas-plan.md Phase 2). Preview QImage stash
    behaviour (src/tabs/image_compare/canvas/rhi_renderer/residency.py:492 ``if pil_source is not None``) stays
    inside ``TileResidencyRealizer.realize_tile_plan`` itself — this wrapper
    only forwards the call and propagates ``more_pending`` to
    ``widget.runtime_state`` for the union letterbox hold.
    """
    fallback_protect_keys = tuple(
        key
        for key in (
            *(renderer._last_good_texture_keys or ()),
            renderer._last_good_diff_key,
        )
        if key is not None
    )
    _debug_timing = tile_dump_enabled()
    _t0 = time.perf_counter() if _debug_timing else 0.0
    # Perf spans (Wave C): realize-main hop of the wheel-to-photon chain.
    # Span/record only — the realize call below is unchanged. None-safe:
    # fakes/widgets without a renderer skip the span, not the work.
    _frame_context = frame_context_from_widget(widget)
    _realize_cm = (
        _frame_context.span(
            "ic.realize_main",
            detail=lambda: {"keys": [str(k) for k in texture_keys]},
        )
        if _frame_context is not None
        else nullcontext()
    )
    with _realize_cm:
        main_more_pending = renderer.resources.residency.realize_tile_plan(
            renderer.tile_service,
            widget,
            texture_keys,
            base_image,
            updates,
            diff_key=diff_key,
            viewport_zoom=viewport_zoom,
            viewport_offset=viewport_offset,
            extra_protect_keys=fallback_protect_keys,
            dirty_layers=dirty_layers,
        )
    # Phase-B2 frame bus: branch duration reuses the gated measurement
    # above (existing tile_dump_enabled pattern only -- 0.0 when the gate
    # is off, never a new unconditional clock on this path).
    _main_dt = 0.0
    if _debug_timing:
        _dt = time.perf_counter() - _t0
        _main_dt = _dt
        if _dt > 0.05:
            log_tile_event(
                "realize_tile_plan.timing", which="main", duration_s=_dt
            )
    # Phase-B2 frame bus: main-branch budget/deadline fact (record only).
    # (``_frame_context`` was fetched above for the ic.realize_main span.)
    if _frame_context is not None:
        _stats = BudgetStats(
            budget=int(_engine_residency.TILE_UPLOAD_BUDGET_PER_CALL),
            time_ms=float(_main_dt),
            budget_ms=float(_tile_upload_budget.TILE_UPLOAD_TIME_BUDGET_MS),
            more_pending=bool(main_more_pending),
        )
        _frame_context.record(
            "realize_main",
            "skipped" if main_more_pending else "ran",
            f"realize_main keys={[str(k) for k in texture_keys]}"
            f" {_stats.describe()}",
            ids=make_ids(
                _frame_context.frame_id,
                tuple(str(k) for k in texture_keys),
                _stats.as_tuple(),
            ),
        )
    # Propagate tile more_pending to canvas runtime_state for union letterbox hold
    try:
        widget.runtime_state._tile_more_pending = bool(main_more_pending)
        if not main_more_pending:
            # more_pending False => early release of union hold (or until timeout)
            try:
                widget.runtime_state._union_letterbox_hold_until = 0.0
            except Exception:
                pass
    except Exception:
        pass
    return bool(main_more_pending)


def _trace_mag_residency(
    renderer, widget, ctx, capture_uv_rect, diff_key, more_pending
) -> None:
    """One sig-throttled ``loupe.mag_residency`` record per magnifier
    residency call: which capture window resolved, the real diff key, and
    -- when tiles are still missing -- exactly which ``tile_index`` values
    are pending (bounded: first 8 + count), so a loupe-hole repro names its
    tiles instead of printing one identical line per missing tile.

    Index computation runs only with ``IMGSLI_IC_LOUPE_DEBUG`` on; steady
    production pays one env check (``trace_loupe`` itself is a no-op with
    the flag off)."""
    if not ic_loupe_debug_enabled():
        return
    frame_context = frame_context_from_widget(widget)
    pending_by_source: dict[str, str] = {}
    try:
        for source_id in tuple(ctx.source_texture_ids):
            grid = renderer.tile_service.grid_for(source_id)
            if grid is None or capture_uv_rect is None:
                continue
            cap_left, cap_top, cap_right, cap_bottom = capture_uv_rect
            missing = sorted(
                index
                for index in renderer.tile_service.visible_tiles(
                    source_id,
                    (
                        cap_left * grid.total_width,
                        cap_top * grid.total_height,
                        cap_right * grid.total_width,
                        cap_bottom * grid.total_height,
                    ),
                )
                if renderer.tile_service.slot_for(source_id, index) is None
            )
            if missing:
                shown = ",".join(f"{r}x{c}" for r, c in missing[:8])
                suffix = f"+{len(missing) - 8}-more" if len(missing) > 8 else ""
                pending_by_source[str(source_id)] = f"{len(missing)}:[{shown}{suffix}]"
    except Exception:
        pass
    if pending_by_source:
        trace_loupe(
            frame_context,
            "loupe.mag_residency",
            "skipped",
            f"more_pending={bool(more_pending)} diff={diff_key!r}"
            f" capture_uv={list(capture_uv_rect) if capture_uv_rect is not None else None}"
            f" pending_tiles={pending_by_source}",
            ids=tuple(str(k) for k in tuple(ctx.source_texture_ids)),
            sig=(tuple(sorted(pending_by_source.items())), str(diff_key)),
        )
    else:
        trace_loupe(
            frame_context,
            "loupe.mag_residency",
            "ran",
            f"more_pending={bool(more_pending)} diff={diff_key!r}"
            f" capture_uv={list(capture_uv_rect) if capture_uv_rect is not None else None}"
            " lens_capture_resident",
            ids=tuple(str(k) for k in tuple(ctx.source_texture_ids)),
            sig=(bool(more_pending), str(diff_key)),
        )


def realize_magnifier_tiles(
    renderer,
    widget,
    ctx,
    texture_keys: tuple[object, object],
    base_image,
    updates,
    viewport_zoom: tuple[float, float] | None,
    viewport_offset: tuple[float, float] | None,
    dirty_layers: dict[int, set[int]],
) -> None:
    """Magnifier source residency (``realize_tile_plan`` magnifier branch).

    Thin-owner wrapper: identical to the magnifier branch in the pre-split
    ``RhiCanvasRenderer.render`` — see this function's inline comments for
    contract. Takes
    ``renderer`` as owner and ``ctx`` (``build_render_runtime_context``
    result) for ``source_texture_ids`` / ``feature_overlay`` /
    ``source_images_ready`` exactly as before.

    ``_union_capture_uv_rect`` override is preserved: the magnifier's
    ``source_*`` realize call resolves tiles under the overlay's capture
    window rather than the base canvas's viewport, otherwise at canvas zoom
    <=1 the whole image would be requested vastly exceeding the per-frame
    upload budget and leaving the magnifier's actual capture area
    perpetually non-resident.
    """
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
        _debug_timing = tile_dump_enabled()
        _t1 = time.perf_counter() if _debug_timing else 0.0
        _mag_dt = 0.0
        # Loupe residency gate: the magnifier samples the diff overlay too
        # (diff modes read it alongside source tiles), so its tiles resolve
        # under the same capture window -- not diff_key=None, which left
        # the lens's diff permanently non-resident on tiled diffs.
        _mag_diff_key = (
            ctx.diff_source_texture_id
            if getattr(ctx, "diff_source_ready", False)
            and ctx.diff_source_texture_id
            else None
        )
        # Perf spans (Wave C): magnifier-residency hop (span/record only).
        _mag_frame_context = frame_context_from_widget(widget)
        _mag_cm = (
            _mag_frame_context.span(
                "ic.realize_magnifier",
                detail=lambda: {
                    "keys": [str(k) for k in tuple(ctx.source_texture_ids)]
                },
            )
            if _mag_frame_context is not None
            else nullcontext()
        )
        with _mag_cm:
            mag_more_pending = renderer.resources.residency.realize_tile_plan(
                renderer.tile_service,
                widget,
                tuple(ctx.source_texture_ids),
                base_image,
                updates,
                diff_key=_mag_diff_key,
                capture_uv_rect=_cap_uv,
                dirty_layers=dirty_layers,
            )
        # Coarsest LOD stays pinned against eviction: each source's deepest
        # pyramid level is the fallback-LOD baseline and the loupe's low-res
        # sampling source -- finer levels filling in around it must never
        # reclaim it under budget pressure. No-op for base-only sources.
        for _source_id in tuple(ctx.source_texture_ids):
            try:
                renderer.tile_service.pin_coarsest_level(_source_id)
            except Exception:
                pass
        if _debug_timing:
            _dt1 = time.perf_counter() - _t1
            _mag_dt = _dt1
            if _dt1 > 0.05:
                log_tile_event(
                    "realize_tile_plan.timing",
                    which="magnifier_source",
                    duration_s=_dt1,
                )
        _trace_mag_residency(
            renderer, widget, ctx, _cap_uv, _mag_diff_key, mag_more_pending
        )
        # Phase-B2 frame bus: magnifier-branch budget/deadline fact
        # (record only; duration reuses the gated measurement above).
        # (``_mag_frame_context`` was fetched above for ic.realize_magnifier.)
        if _mag_frame_context is not None:
            _mag_stats = BudgetStats(
                budget=int(_engine_residency.TILE_UPLOAD_BUDGET_PER_CALL),
                time_ms=float(_mag_dt),
                budget_ms=float(_tile_upload_budget.TILE_UPLOAD_TIME_BUDGET_MS),
                more_pending=bool(mag_more_pending),
            )
            _mag_frame_context.record(
                "realize_magnifier",
                "skipped" if mag_more_pending else "ran",
                f"realize_magnifier keys={[str(k) for k in ctx.source_texture_ids]}"
                f" {_mag_stats.describe()}",
                ids=make_ids(
                    _mag_frame_context.frame_id,
                    tuple(str(k) for k in ctx.source_texture_ids),
                    _mag_stats.as_tuple(),
                ),
            )
