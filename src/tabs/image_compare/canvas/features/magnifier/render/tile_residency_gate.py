"""Tile-residency / fallback helpers for the magnifier's QRhi pass.

Extracted from ``magnifier_pass.py`` (docs/dev/CODE_MASS_REDUCTION.md
"Oversized-file triage — Part D"): the frame's residency hold gates
(``_lens_residency_hold``, ``_frame_slices_residency_hold``), the pure
draw-slice enumerator (``_frame_draw_tile_indices``), the source-slice
resolver (``_source_slices``), the low-res fallback slice builder
(``_low_res_fallback_slice``) and the lens capture-union helper
(``_lens_union_uv``). ``magnifier_pass`` re-exports every name so existing
importers/tests keep working unchanged; the pass class and its single
resource lifecycle stay in ``magnifier_pass.py`` (F4 boundary intact).

File-Size-Exempt: one cohesive tile-residency helper surface (capture-window
union -> level gate -> per-slice gate -> fallback slice -> slice resolution)
sharing the magnifier's capture-window geometry; splitting would scatter
tightly-coupled helpers for no cohesion gain.
"""

from __future__ import annotations

from tabs.image_compare.canvas.features.magnifier.render.tile_capture import (
    tile_uv_slices,
)
from tabs.image_compare.canvas.rhi_renderer import (
    _ARRAY_LAYER_PX,
    _TILE_APRON_PX,
    _apron_rect,
)
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from tabs.image_compare.canvas.loupe_trace import trace_loupe


def _lens_union_uv(overlay) -> tuple[float, float, float, float] | None:
    """Union of every active magnifier slot's capture window (``uv_rect``/
    ``uv_rect2``, zoom/pan-invariant fractions of the full source image).

    Local mirror of ``rhi_renderer/use_cases/tile_residency
    ._union_capture_uv_rect`` (kept local: this feature already owns its
    capture-window geometry via ``tile_capture.py``, and a private
    cross-module import would couple the pass to the renderer's use-case
    layout). Returns ``None`` when no slot carries a capture window."""
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


def _low_res_fallback_slice(
    tile_service, fallback_key, capture_uv_rect, tc_x, tc_y, core_tc_x, core_tc_y,
    _why=None,
) -> dict | None:
    """One fallback slice sampling ``fallback_key`` (the stored/low-res
    role) over exactly the screen footprint a missing source slice would
    have covered (same ``tc``/``core_tc`` -- scissor unchanged, no hole).

    The capture-uv sub-rect at this slice's ``tc`` range is an absolute
    image fraction, so it maps onto the fallback grid -- which shows the
    same image at a different scale -- by plain fraction arithmetic
    (mirrors ``tile_capture.tile_uv_slices``' own sub-rect/local-uv math,
    including the apron-padded tile-local convention). A multi-tile
    fallback only serves tiles whose exact (apron-free) region fully
    contains the sub-rect, so the kept ``tc`` never samples across a tile
    boundary; otherwise ``None`` (caller keeps the old drop path).
    Returns ``None`` when the fallback grid is unknown or its tile is not
    GPU-resident either.

    H3 loupe-debug (trace-only): every ``None`` return appends its cause
    (``fallback_grid_unknown`` / ``fallback_grid_empty`` /
    ``fallback_tile_uncontained`` / ``fallback_slot_not_resident``) to
    ``_why`` when given a list, so the caller can log WHY no fallback
    covered the slice. Same branches, same returns; ``None`` (all existing
    callers but one) records nothing.
    """
    grid = tile_service.grid_for(fallback_key)
    if grid is None:
        if _why is not None:
            _why.append("fallback_grid_unknown")
        return None
    left, top, right, bottom = capture_uv_rect
    total_w, total_h = float(grid.total_width), float(grid.total_height)
    if total_w <= 0 or total_h <= 0:
        if _why is not None:
            _why.append("fallback_grid_empty")
        return None
    sub_left = left + tc_x[0] * (right - left)
    sub_right = left + tc_x[1] * (right - left)
    sub_top = top + tc_y[0] * (bottom - top)
    sub_bottom = top + tc_y[1] * (bottom - top)
    px_left, px_right = sorted((sub_left * total_w, sub_right * total_w))
    px_top, px_bottom = sorted((sub_top * total_h, sub_bottom * total_h))
    if grid.rows == 1 and grid.columns == 1:
        index = (0, 0)
        region = grid.region_for(0, 0)
    else:
        indices = tile_service.visible_tiles(
            fallback_key, (px_left, px_top, px_right, px_bottom)
        )
        index = None
        region = None
        best_overlap = -1.0
        for row, col in indices:
            candidate = grid.region_for(row, col)
            if (
                candidate.left <= px_left
                and candidate.top <= px_top
                and candidate.right >= px_right
                and candidate.bottom >= px_bottom
            ):
                overlap = (px_right - px_left) * (px_bottom - px_top)
                if overlap > best_overlap:
                    best_overlap = overlap
                    index = (row, col)
                    region = candidate
        if index is None or region is None:
            if _why is not None:
                _why.append("fallback_tile_uncontained")
            return None
    slot = tile_service.slot_for(fallback_key, index)
    if slot is None:
        if _why is not None:
            _why.append("fallback_slot_not_resident")
        return None
    tile_left, tile_top, tile_right, tile_bottom = _apron_rect(
        grid.total_width, grid.total_height, region, _TILE_APRON_PX
    )
    tile_w_px = tile_right - tile_left
    tile_h_px = tile_bottom - tile_top
    if tile_w_px <= 0 or tile_h_px <= 0:
        return None
    # S5: content-scale math lives in the engine draw-plan module (MC
    # src/tabs/multi_compare/scene/passes/base_images.py:786 precedent);
    # function-local import keeps the tab ->
    # engine edge at the call site, never engine -> tab.
    from engine.cache.draw_plans import content_scale_for as _engine_content_scale

    return {
        "tile_key": tile_service.tile_key(fallback_key, index[0], index[1]),
        "tile_index": index,
        "uv_rect": (
            (sub_left * total_w - tile_left) / tile_w_px,
            (sub_top * total_h - tile_top) / tile_h_px,
            (sub_right * total_w - tile_left) / tile_w_px,
            (sub_bottom * total_h - tile_top) / tile_h_px,
        ),
        "tc_x": tc_x,
        "tc_y": tc_y,
        "core_tc_x": core_tc_x,
        "core_tc_y": core_tc_y,
        "layer": slot[1],
        "content_scale": _engine_content_scale(
            tile_service.content_size_for(fallback_key, index), _ARRAY_LAYER_PX
        ),
        "fallback_for": tuple(index),
    }


def _lens_residency_hold(renderer, source_keys, overlay, frame_context=None) -> str | None:
    """Stored-hold gate for the lens source flip (loupe residency gate).

    Returns ``None`` when every ``source_keys`` entry reports
    ``request_level == "resident"`` on the lens's own interest rect (the
    capture-window union in that source's image pixels) -- the caller may
    sample source tiles. Otherwise returns a grep-friendly hold reason and
    the caller keeps sampling ``stored`` (atomic swap instead of
    progressive fill: the lens never shows a half-uploaded source grid).
    ``renderer`` without a tile service (fakes/tests) never holds."""
    tile_service = getattr(renderer, "tile_service", None) if renderer is not None else None
    if tile_service is None:
        return None
    union_uv = _lens_union_uv(overlay)
    if union_uv is None:
        return None
    pending: list[str] = []
    for source_key in source_keys:
        grid = tile_service.grid_for(source_key)
        if grid is None:
            pending.append(f"{source_key}:grid-unregistered")
            continue
        interest_rect = (
            union_uv[0] * grid.total_width,
            union_uv[1] * grid.total_height,
            union_uv[2] * grid.total_width,
            union_uv[3] * grid.total_height,
        )
        tile_service.register_interest_rect(source_key, interest_rect)
        _level, status, reason = tile_service.request_level(
            source_key, interest_rect, quality="high"
        )
        if status != "resident":
            pending.append(f"{source_key}:{reason}")
    if pending:
        hold_reason = f"hold_stored_until_resident {'; '.join(pending)}"
        trace_loupe(
            frame_context,
            "loupe.mag_residency_hold",
            "skipped",
            hold_reason,
            ids=tuple(str(k) for k in source_keys),
            sig=(False, tuple(pending)),
            key="loupe.mag_residency_hold.level",
        )
        return hold_reason
    trace_loupe(
        frame_context,
        "loupe.mag_residency_hold",
        "ran",
        "lens_interest_resident sampling source tiles",
        ids=tuple(str(k) for k in source_keys),
        sig=(True,),
        key="loupe.mag_residency_hold.level",
    )
    return None


def _frame_draw_tile_indices(
    renderer, overlay, tex_key_1, tex_key_2, diff_key
) -> list[tuple] | None:
    """Every ``(key, tile_index)`` this frame's lens would sample.

    Pure geometry (no interest registration, no trace records, no fallback):
    mirrors ``prepare``'s own per-quad key selection (combined / source_mode
    / diff_mode branching in ``build_tile_records``) and slices each active
    ``(key, uv_rect)`` with the same ``tile_uv_slices`` wiring
    ``_source_slices`` draws with. Returns ``None`` when ungatable (no tile
    service -- fakes/tests keep the old behavior exactly); keys with no
    registered grid (e.g. the ``"placeholder"`` diff) are skipped, since the
    draw path drops those quads anyway and there is nothing to gate on.
    """
    tile_service = getattr(renderer, "tile_service", None) if renderer is not None else None
    if tile_service is None:
        return None
    if not bool(getattr(overlay, "gpu_active", False)):
        return []
    quads = getattr(overlay, "quads", ()) or ()
    slots = getattr(overlay, "gpu_slots", ()) or ()
    wanted: list[tuple] = []
    for i, quad in enumerate(quads):
        if not quad:
            continue
        gpu_slot = slots[i] if i < len(slots) else None
        if not gpu_slot:
            continue
        combined = bool(gpu_slot.get("is_combined", False))
        source_mode = int(gpu_slot.get("source", 0) or 0)
        if source_mode == 2 and not combined:
            diff_mode = int(getattr(overlay, "gpu_diff_mode", 0) or 0)
        else:
            diff_mode = 0
        uv_rect1 = gpu_slot.get("uv_rect", (0.0, 0.0, 1.0, 1.0))
        uv_rect2 = gpu_slot.get("uv_rect2", uv_rect1)
        if combined:
            wanted.append((tex_key_1, uv_rect1))
            wanted.append((tex_key_2, uv_rect2))
        elif source_mode == 2 and diff_mode in (1, 2):
            wanted.append((tex_key_1, uv_rect1))
            wanted.append((tex_key_2, uv_rect2))
        elif source_mode == 2 and diff_mode == 3:
            wanted.append((tex_key_1, uv_rect1))
        elif source_mode == 2:
            wanted.append((diff_key, uv_rect1))
        elif source_mode == 1:
            wanted.append((tex_key_2, uv_rect2))
        else:
            wanted.append((tex_key_1, uv_rect1))
    indices: list[tuple] = []
    for key, uv_rect in wanted:
        grid = tile_service.grid_for(key)
        if grid is None:
            continue
        slices = tile_uv_slices(
            grid,
            tile_service.tile_key,
            key,
            uv_rect,
            apron_px=_TILE_APRON_PX,
            apron_rect_fn=_apron_rect,
            visible_tiles_fn=(
                lambda rect, _key=key: tile_service.visible_tiles(_key, rect)
            ),
        )
        for sl in slices:
            indices.append((key, sl["tile_index"]))
    seen: set[tuple] = set()
    ordered: list[tuple] = []
    for pair in indices:
        if pair not in seen:
            seen.add(pair)
            ordered.append(pair)
    return ordered


def _frame_slices_residency_hold(renderer, indices, frame_context=None, _stats=None) -> str | None:
    """Stored-hold gate on the frame's own draw slices (loupe no-holes).

    Returns ``None`` when every ``(key, tile_index)`` in ``indices`` (as
    computed by ``_frame_draw_tile_indices``) has a GPU slot -- the caller
    may sample source tiles. Otherwise returns a grep-friendly hold reason
    and the caller keeps sampling ``stored``. ``None`` indices (no tile
    service) never hold. This is the same ``slot_for`` condition
    ``_source_slices`` draws with, so a released hold structurally implies
    zero ``mag_dropped_slice`` on the swap frame for every array-owned key
    (the low-res fallback stays as belt-and-suspenders for post-hold
    races).

    H3 loupe-debug (trace-only): ``_stats``, when given a dict, receives
    ``{"total": N, "missing": M}`` for the heartbeat line -- same branches,
    same returns, ``None`` (all existing callers) fills nothing."""
    if indices is None:
        return None
    tile_service = getattr(renderer, "tile_service", None) if renderer is not None else None
    if tile_service is None:
        return None
    missing = [
        (key, index) for key, index in indices if tile_service.slot_for(key, index) is None
    ]
    if _stats is not None:
        _stats["total"] = len(indices)
        _stats["missing"] = len(missing)
    if not missing:
        trace_loupe(
            frame_context,
            "loupe.mag_residency_hold",
            "ran",
            f"frame_slices_resident sampling source tiles slices={len(indices)}",
            ids=tuple(str(k) for k, _ in indices[:8]),
            sig=(True, len(indices)),
            key="loupe.mag_residency_hold.slices",
        )
        return None
    shown = ",".join(f"{k}:{r}x{c}" for k, (r, c) in missing[:8])
    suffix = f"+{len(missing) - 8}-more" if len(missing) > 8 else ""
    hold_reason = (
        f"hold_stored_until_slices_resident {len(missing)}-of-{len(indices)}-slices-missing"
        f" [{shown}{suffix}]"
    )
    trace_loupe(
        frame_context,
        "loupe.mag_residency_hold",
        "skipped",
        hold_reason,
        ids=tuple(str(k) for k, _ in missing[:8]),
        sig=(False, tuple(sorted((str(k), tuple(idx)) for k, idx in missing))),
        key="loupe.mag_residency_hold.slices",
    )
    return hold_reason


def _source_slices(renderer, source_key, uv_rect, frame_context=None, fallback_key=None):
    """Tile-aware uv_rect slicing for one magnifier source (see tile_capture.py).

    Attaches each slice's array ``layer``/``content_scale`` (looked up via
    ``TileTextureService``) so ``build_tile_records`` can pass them straight
    through to ``MagnifierPass``'s per-record ``tex1``/``tex2``/``texd``
    dicts -- this is the one renderer-dependent hook in the whole capture
    pipeline, everything else in ``tile_capture.py`` is pure geometry.

    P3 residency priorities: the lens first registers its interest rect
    (``uv_rect`` in source-image pixels) and asks the service for the
    level/residency answer (``request_level``) instead of deciding itself.
    Slicing behavior is unchanged -- a non-resident slice is still dropped
    rather than defaulting to layer 0 -- but the drop now carries the
    service's reason as a ``loupe.mag_dropped_slice`` FrameContext record
    instead of staying silent. ``frame_context=None`` keeps every existing
    call site behavior-identical.

    Loupe residency gate: when ``fallback_key`` (the stored/low-res role
    for this source) is given, a non-resident source slice samples the
    fallback's resident tile over the same footprint (blur, not holes)
    instead of dropping; only a slice with no resident fallback anywhere
    still drops. ``fallback_key=None`` keeps the old drop path exactly.
    """
    tile_service = getattr(renderer, "tile_service", None) if renderer is not None else None
    grid = tile_service.grid_for(source_key) if tile_service is not None else None
    if tile_dump_enabled() and grid is not None:
        log_tile_event(
            "magnifier.grid_dims",
            source_key=str(source_key),
            total_width=grid.total_width,
            total_height=grid.total_height,
            tile_width=grid.tile_width,
            tile_height=grid.tile_height,
            rows=grid.rows,
            columns=grid.columns,
            uv_rect=list(uv_rect),
        )
    slices = tile_uv_slices(
        grid,
        tile_service.tile_key if tile_service is not None else None,
        source_key,
        uv_rect,
        apron_px=_TILE_APRON_PX,
        apron_rect_fn=_apron_rect,
        visible_tiles_fn=(
            (lambda rect: tile_service.visible_tiles(source_key, rect))
            if tile_service is not None
            else None
        ),
    )
    if tile_service is None:
        return slices
    residency_reason: str | None = None
    if grid is not None:
        try:
            _total_w = float(grid.total_width)
            _total_h = float(grid.total_height)
            _interest_rect = (
                float(uv_rect[0]) * _total_w,
                float(uv_rect[1]) * _total_h,
                float(uv_rect[2]) * _total_w,
                float(uv_rect[3]) * _total_h,
            )
        except (TypeError, ValueError, IndexError):
            _interest_rect = None
        if _interest_rect is not None:
            tile_service.register_interest_rect(source_key, _interest_rect)
            _req_level, _req_status, residency_reason = tile_service.request_level(
                source_key, _interest_rect, quality="high"
            )
    resolved = []
    for sl in slices:
        slot = tile_service.slot_for(source_key, sl["tile_index"])
        if slot is None:
            # Not yet GPU-resident (upload still in flight) -- sample the
            # stored/low-res fallback over the same footprint when one is
            # resident (blur, not holes); drop only when no fallback
            # covers this slice either.
            # H3 loupe-debug (trace-only): remember WHY no fallback covered
            # this slice -- the 2026-09-16 frame dropped 24 slices with zero
            # fallback lines and nothing said the diff key simply HAS no
            # fallback entry. The cause rides on the drop reason below (one
            # event, one line, same aggregation as before).
            _no_fb_why: str | None = None
            if fallback_key is None:
                _no_fb_why = "no_fallback_key"
            else:
                _why_codes: list = []
                fallback_slice = _low_res_fallback_slice(
                    tile_service,
                    fallback_key,
                    uv_rect,
                    sl["tc_x"],
                    sl["tc_y"],
                    sl["core_tc_x"],
                    sl["core_tc_y"],
                    _why_codes,
                )
                if _why_codes:
                    _no_fb_why = _why_codes[0]
                if fallback_slice is not None:
                    trace_loupe(
                        frame_context,
                        "loupe.mag_fallback_slice",
                        "ran",
                        "low_res_fallback source not GPU-resident"
                        f" sampling fallback={fallback_key!r}",
                        ids=(str(source_key), tuple(sl["tile_index"])),
                        sig=(str(source_key), tuple(sl["tile_index"]), str(fallback_key)),
                    )
                    resolved.append(fallback_slice)
                    continue
            # Defaulting to layer 0 would sample whatever unrelated tile
            # happens to occupy that layer right now -- drop instead.
            # NOTE (supervisor seam fix, Phase 1 integration): per-tile identity
            # travels in `ids=` (rendered as ids=%r), NOT in the reason.
            # Reasons stay per-event stable so loupe_trace's (pass, verdict,
            # reason) aggregation collapses N tiles into one line (1D bar:
            # N drops => <=2 lines). Embedding tile_index here broke that.
            _drop_reason = (
                "dropped_nonresident_slice not GPU-resident"
                + (
                    f" request_level={residency_reason}"
                    if residency_reason is not None
                    else ""
                )
                + (f" nofallback={_no_fb_why}" if _no_fb_why is not None else "")
            )
            trace_loupe(
                frame_context,
                "loupe.mag_dropped_slice",
                "skipped",
                _drop_reason,
                ids=(str(source_key), tuple(sl["tile_index"])),
                sig=(str(source_key), tuple(sl["tile_index"]), residency_reason, _no_fb_why),
            )
            if tile_dump_enabled():
                log_tile_event(
                    "magnifier.dropped_nonresident_slice",
                    source_key=str(source_key),
                    tile_index=list(sl["tile_index"]),
                    uv_rect=list(uv_rect),
                )
            continue
        sl["layer"] = slot[1]
        # S5: same engine entry as the fallback slice above (MC precedent).
        from engine.cache.draw_plans import content_scale_for as _engine_content_scale

        sl["content_scale"] = _engine_content_scale(
            tile_service.content_size_for(source_key, sl["tile_index"]),
            _ARRAY_LAYER_PX,
        )
        resolved.append(sl)
    return resolved
