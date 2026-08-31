# Audit-Meta: pattern=thin-owner size=exempt reason="tile residency extracted from RhiCanvasRenderer — see renderer.py Audit-Meta state-machine"
"""Tile residency extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer.render``'s residency phase (``realize_tile_plan`` main +
magnifier) was ~80 LOC living inside ``renderer.py:986``. This module holds
the same bodies as plain functions taking the owning renderer as first arg —
the owner keeps construction/wiring + instance state
(``_last_good_*``, ``tile_service``, ``resources``) per CODE_PATTERNS.md:25.
"""

from __future__ import annotations

import time

from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled


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
    ``realize_tile_plan`` main call in ``renderer.py:986`` — see its inline
    comments for contract. Takes ``renderer`` as owner (CODE_PATTERNS) and
    reads ``renderer._last_good_*`` / ``renderer.tile_service`` /
    ``renderer.resources.residency`` exactly as before.

    ``extra_protect_keys`` wiring is preserved: previous LOD level's tiles
    (``_last_good_*``) survive this call's eviction pass as a fallback draw
    source while the current level's tiles are still uploading (docs/dev/
    rendering/tile-array-atlas-plan.md Phase 2). Preview QImage stash
    behaviour (``residency.py:394`` ``if pil_source is not None``) stays
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
    if _debug_timing:
        _dt = time.perf_counter() - _t0
        if _dt > 0.05:
            log_tile_event(
                "realize_tile_plan.timing", which="main", duration_s=_dt
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

    Thin-owner wrapper: identical to the magnifier branch in
    ``renderer.py:986`` — see its inline comments for contract. Takes
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
        renderer.resources.residency.realize_tile_plan(
            renderer.tile_service,
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
