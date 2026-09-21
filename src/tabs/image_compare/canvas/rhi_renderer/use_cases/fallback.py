# Audit-Meta: pattern=thin-owner-target size=exempt reason="fallback LOD extracted from RhiCanvasRenderer — see renderer.py Audit-Meta state-machine"
"""Fallback-LOD plan extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer._resolve_fallback_plan`` was ~410 LOC of decision/logic
living inside ``renderer.py:291`` (part of the 1611-line state-machine).
This module holds the same bodies as plain functions taking the owning
renderer as first arg — the owner keeps construction/wiring + instance state
(``_last_good_*``, ``_content_swap_active``) per CODE_PATTERNS.md:25, thin
delegator keeps Qt-required name.
"""

from __future__ import annotations

import logging

from engine.cache.fallback_lod import resolve_fallback_lod
from engine.cache.lod import LevelKey
from engine.cache.tile_coverage import drop_covered_fallback_items
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled

from ..draw_plan import (
    build_array_draw_plan,
)

try:
    from tabs.image_compare.debug import ic_gap_debug as _gap_log  # type: ignore
    from tabs.image_compare.debug import ic_gap_debug_enabled as _gap_enabled  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug as _ic_preview_log  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug_enabled as _ic_preview_enabled  # type: ignore
except Exception:  # pragma: no cover

    def _gap_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _gap_enabled() -> bool:  # type: ignore
        return False

    def _ic_preview_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _ic_preview_enabled() -> bool:  # type: ignore
        return False

from .._debug import rhi_render_debug
from engine.frame.context import FrameContext, make_ids
from tabs.image_compare.canvas.loupe_trace import throttle_emit as _throttle_emit

logger = logging.getLogger("ImproveImgSLI")

# Throttle state moved from renderer.py into loupe_trace's centralized
# store — owned here via streams "fallback.decision" + "fallback.rekeyed"
# + "fallback.first_paint_hold".


def _is_rekeyed_content_key(key: object) -> bool:
    if isinstance(key, LevelKey):
        key = key.base
    return isinstance(key, tuple) and len(key) > 0 and key[0] in ("_prev_content", "_content_stash")


def _is_rekeyed_content_baseline(last_good_key) -> bool:
    if last_good_key is None:
        return False
    texture_keys, diff_key = last_good_key
    return any(_is_rekeyed_content_key(k) for k in texture_keys) or _is_rekeyed_content_key(diff_key)


def _is_hires_flip_baseline(last_good_key, key) -> bool:
    """stored_* <-> source_* tier switch = hires flip (use_hires path).

    Same atomic rationale as a LevelKey transition: the old tier is a
    complete resident image while the new one streams in partial, so the
    old tier held whole for 1-3 frames beats a mixed sharp/stretched grid
    (live trace 2026-09-20 frame 90: 33 current + 7 fallback drawn on the
    flip frame). Symmetric in both directions (zoom across 1.0, diff-mode
    toggles); first paint (last_good None) stays fail-open downstream.
    Name-based (frame_setup mints exactly stored_N/source_N); anything
    else fails closed to False.
    """
    try:
        old_tex = (last_good_key or (None,))[0] or ()
        new_tex = (key or (None,))[0] or ()
        old = {str(getattr(k, "base", k)) for k in old_tex}
        new = {str(getattr(k, "base", k)) for k in new_tex}
    except Exception:
        return False
    _flips = ({"stored_0", "stored_1"}, {"source_0", "source_1"})
    return (old, new) in (_flips, _flips[::-1]) and old != new


def resolve_fallback_plan(
    renderer,
    *,
    tile_service,
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
    """Thin-owner wrapper: identical to ``RhiCanvasRenderer._resolve_fallback_plan``
    in ``renderer.py:291`` — see its docstring for contract. Takes ``renderer``
    as owner (CODE_PATTERNS) and mutates ``renderer._last_good_*`` /
    ``renderer._content_swap_active`` exactly as before.
    """
    # Copy-pasted body from renderer.py:291 — keep log throttling identical.
    old_texture_keys = renderer._last_good_texture_keys
    last_good_key = (
        (old_texture_keys, renderer._last_good_diff_key)
        if old_texture_keys is not None
        else None
    )
    key = (texture_keys, diff_source_key)
    if rekeyed:

        def _rekeyed_lookup(k):
            if k is None:
                return None
            if k in rekeyed:
                return rekeyed[k]
            if isinstance(k, LevelKey) and k.base in rekeyed:
                try:
                    return LevelKey(rekeyed[k.base], k.level)  # type: ignore[arg-type]
                except Exception:
                    return rekeyed[k.base]
            return k

        last_good_key = (
            tuple(_rekeyed_lookup(k) for k in texture_keys),
            _rekeyed_lookup(diff_source_key),
        )
        try:
            _rk_sig = (tuple(str(k) for k in texture_keys), tuple(sorted((str(k), str(v)) for k, v in rekeyed.items())), str(last_good_key))
            if _throttle_emit("fallback.rekeyed", _rk_sig):
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
    _prev_is_same = renderer._prev_sources_is_same
    if current_sources_is_same is False and _prev_is_same is True:
        if _is_rekeyed_content_baseline(last_good_key):
            # Own stashed preview hold (flip frame): the rekey lookup above
            # mapped the pair's previous content to _content_stash keys, so
            # this baseline is the intentional atomic placeholder — NOT a
            # stale duplicate. Dropping it blanks one frame (flip flicker:
            # preview -> GAP entries=0 -> store). Spare it; the plain-key
            # duplicate case below still drops.
            _ic_preview_log(
                "fallback SKIP_DUPLICATE_BASELINE spared: last_good=%s is own stashed preview hold, keeping atomic baseline",
                last_good_key,
            )
        else:
            _ic_preview_log(
                "fallback SKIP_DUPLICATE_BASELINE: prev=%s current=%s last_good=%s -> drop baseline",
                _prev_is_same,
                current_sources_is_same,
                last_good_key,
            )
            last_good_key = None
            renderer._content_swap_active = False
    elif _prev_is_same is not None or current_sources_is_same is not None:
        try:
            _is_same_sig = (_prev_is_same, current_sources_is_same, str(last_good_key))
            if not hasattr(renderer, "_last_is_same_sig"):
                renderer._last_is_same_sig = None  # type: ignore[attr-defined]
            if _is_same_sig != renderer._last_is_same_sig:  # type: ignore[attr-defined]
                renderer._last_is_same_sig = _is_same_sig  # type: ignore[attr-defined]
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
    _prev_swap = renderer._content_swap_active
    if source_changed and last_good_key is not None and last_good_key != key:
        renderer._content_swap_active = True
        _ic_preview_log(
            "fallback content_swap_active: SET (source_changed=%s last_good=%s key=%s prev=%s -> True)",
            source_changed,
            last_good_key,
            key,
            _prev_swap,
        )
    is_content_swap = (
        renderer._content_swap_active
        or _is_rekeyed_content_baseline(last_good_key)
        or tuple(base_image.letterbox1) != tuple(base_image.letterbox2)
    )
    decision_is_content_swap = is_content_swap
    decision_content_swap_flag = renderer._content_swap_active
    decision_last_good_has_marker = _is_rekeyed_content_baseline(last_good_key)
    # Atomic-tier invariant (plan-atomic-lod-transitions): one tier per
    # frame also for LOD level changes AND hires flips, not just content
    # swaps. A level transition key carries LevelKey entries, a hires flip
    # switches stored_*<->source_* keys, while the last-good baseline
    # is a complete older tier — hold the old tier whole until the new one
    # promotes instead of layering partial grids (shimmer/seams). Opt-in at
    # this IC call site only: engine default stays atomic=False so
    # multi_compare rendering is unchanged. Fail-open preserved in the
    # engine (empty fallback -> partial current, never blank).
    _atomic_level_hold = (
        not is_content_swap
        and last_good_key is not None
        and last_good_key != key
        and any(isinstance(k, LevelKey) for k in texture_keys)
    )
    _hires_flip_hold = (
        not is_content_swap
        and last_good_key is not None
        and last_good_key != key
        and _is_hires_flip_baseline(last_good_key, key)
    )
    decision_atomic = (
        decision_is_content_swap or _atomic_level_hold or _hires_flip_hold
    )
    _fallback_sig = (str(key), str(last_good_key), decision_is_content_swap, decision_atomic, main_more_pending, len(current_array_plan), str(dict(rekeyed) if rekeyed else None))
    _should_emit_fallback = _throttle_emit("fallback.decision", _fallback_sig)
    if _should_emit_fallback:
        _ic_preview_log(
            "fallback decision: source_changed=%s last_good=%s key=%s rekeyed=%s is_content_swap=%s atomic=%s more_pending=%s current_entries=%d last_good_has_marker=%s content_swap_flag=%s decision_atomic=%s level_hold=%s hires_hold=%s",
            source_changed,
            last_good_key,
            key,
            dict(rekeyed) if rekeyed else None,
            decision_is_content_swap,
            decision_atomic,
            main_more_pending,
            len(current_array_plan),
            decision_last_good_has_marker,
            decision_content_swap_flag,
            decision_atomic,
            _atomic_level_hold,
            _hires_flip_hold,
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
    renderer._fallback_atomic_snapshot = decision_atomic
    renderer._fallback_more_pending_snapshot = main_more_pending
    fallback_diag: dict[str, int] = {}
    if last_good_key is None and main_more_pending and current_array_plan:
        try:
            _hold_sig = (str(key), len(current_array_plan), bool(main_more_pending))
            if _throttle_emit("fallback.first_paint_hold", _hold_sig):
                _ic_preview_log(
                    "first_paint_hold _resolve: last_good None more_pending True hold placeholder current=%d key=%s",
                    len(current_array_plan),
                    key,
                )
        except Exception:
            pass
        fallback_diag["held_first_paint"] = 1
        return None, []
    # Cascade-quiescence gate (tile-seam fix 2026-09-20): freshly uploaded
    # tiles sample stale coarse mips at their edges for 1-2 frames, so a
    # tier must not promote the same frame its uploads land. Previous
    # frames' leftovers live in renderer._pending_dirty_layers; this
    # frame's uploads in the realizer's stashed count (main path only —
    # magnifier captures are excluded at the stash site). None-safe:
    # missing attrs read as quiescent (fail-open, old behavior).
    #
    # NOTE (task-fix-export-lod-parity-2026-09-20): no narrow-bbox
    # promotion gate here anymore. Sliver filtering is engine-owned —
    # build_compare_pair_plan drops intersections below SLIVER_MIN=0.002
    # before the bbox expand (which only grows), so no plan item can carry
    # a bbox side below 0.001; the old 0.001/0.3 gate could never fire, and
    # a geometry-proxy gate must never pin the stale tier ahead of the
    # residency-signal guards above. Sliver invariant owner:
    # test_gap_mixed_size_no_sliver.py.
    _cascade_leftover = bool(getattr(renderer, "_pending_dirty_layers", None))
    try:
        _cascade_uploaded = int(
            getattr(renderer.resources.residency, "last_uploaded_count", 0)
            or 0
        )
    except Exception:
        _cascade_uploaded = 0
    _cascade_pending = _cascade_leftover or _cascade_uploaded > 0
    if (
        not main_more_pending
        and not _cascade_pending
        and current_array_plan
    ):
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
                frame_context=frame_context,
            )
            fallback_diag["raw"] = len(items)
            fallback_diag["kept"] = len(items)
            return items

        def _drop_covered(fallback_items, current_items):
            # Phase F flag-day: tab adapter deleted, engine owns the
            # filter -- adapt item rects + letterboxes at the call site.
            if not current_items:
                dropped = fallback_items
            else:
                kept = drop_covered_fallback_items(
                    [(item.rect1, item.rect2) for item in fallback_items],
                    [(item.rect1, item.rect2) for item in current_items],
                    tuple(base_image.letterbox1),
                    tuple(base_image.letterbox2),
                )
                dropped = [fallback_items[index] for index in kept]
            fallback_diag["kept"] = len(dropped)
            return dropped

        new_last_good_key, array_draw_plan = resolve_fallback_lod(
            key=key,
            current_items=current_array_plan,
            more_pending=main_more_pending,
            last_good_key=last_good_key,
            build_fallback_items=_build_fallback_items,
            drop_covered=_drop_covered,
            atomic=decision_atomic,
            cascade_pending=_cascade_pending,
        )
    if new_last_good_key == key:
        if decision_content_swap_flag:
            _ic_preview_log(
                "fallback content_swap_active: CLEARED on promotion (new_last_good==key %s) decision_atomic_was=%s",
                key,
                decision_is_content_swap,
            )
        renderer._content_swap_active = False
        if _should_emit_fallback:
            _ic_preview_log(
                "fallback promotion: promoted=True key=%s more_pending_at_decision=%s coverage_will_be_checked_in_render",
                key,
                renderer._fallback_more_pending_snapshot,
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
    if _should_emit_fallback:
        _ic_preview_log(
            "fallback result: atomic=%s fallback_raw=%s fallback_kept=%s resolved=%d current=%d more_pending=%s last_good=%s new_last_good=%s promoted=%s decision_atomic=%s",
            decision_atomic,
            fallback_diag.get("raw"),
            fallback_diag.get("kept"),
            len(array_draw_plan),
            len(current_array_plan),
            renderer._fallback_more_pending_snapshot,
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
    elif last_good_key is None and _should_emit_fallback:
        _ic_preview_log(
            "fallback NO_BASELINE: last_good is None (first paint or after eviction) — no placeholder possible for key=%s",
            key,
        )
    if fallback_diag:
        rhi_render_debug(
            "render FALLBACK_ACTIVE old_keys=%s new_keys=%s fallback_raw=%d fallback_entries=%d current_entries=%d main_more_pending=%s",
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
            old_texture_keys=[str(k) for k in old_texture_keys] if old_texture_keys is not None else None,
            new_texture_keys=[str(k) for k in texture_keys],
            diff_source_key=str(diff_source_key) if diff_source_key is not None else None,
            fallback_raw=fallback_diag.get("raw"),
            fallback_kept=fallback_diag.get("kept"),
            current_entries=len(current_array_plan),
            resolved_entries=len(array_draw_plan),
            main_more_pending=renderer._fallback_more_pending_snapshot,
            fallback_active=bool(fallback_diag),
            rekeyed_same_slot_swap={str(k): str(v) for k, v in rekeyed.items()} if rekeyed else None,
            content_swap_active=decision_is_content_swap,
            decision_atomic=decision_atomic,
            decision_flag=decision_content_swap_flag,
        )
    # P1A frame-context pilot: record the final decision IN ADDITION to the
    # logs above (never instead of them). Unthrottled — the context keeps
    # every frame's verdict even when the sig-throttled logs stay quiet.
    # Phase-2 frame bus: ids follow the schema-v1 layout (frame tag first).
    if frame_context is not None:
        _promoted = new_last_good_key == key
        frame_context.record(
            "fallback",
            "ran" if fallback_diag else "skipped",
            f"fallback atomic={decision_atomic}"
            f" more_pending={main_more_pending} promoted={_promoted}"
            f" cascade_pending={_cascade_pending}"
            f" uploaded={_cascade_uploaded}"
            f" hires_hold={_hires_flip_hold}"
            f" current={len(current_array_plan)}"
            f" kept={fallback_diag.get('kept')} raw={fallback_diag.get('raw')}",
            ids=make_ids(
                frame_context.frame_id, texture_keys, diff_source_key
            ),
        )
    return new_last_good_key, array_draw_plan
