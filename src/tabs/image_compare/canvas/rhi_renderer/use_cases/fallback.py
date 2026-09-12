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

from shared.rendering.fallback_lod import resolve_fallback_lod
from shared.rendering.lod import LevelKey
from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled

from ..draw_plan import (
    build_array_draw_plan,
    drop_covered_fallback_items,
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

logger = logging.getLogger("ImproveImgSLI")

# Throttle globals moved from renderer.py — owned here, shared via module.
_last_renderer_fallback_sig: tuple | None = None
_last_renderer_rekeyed_sig: tuple | None = None
_last_first_paint_hold_sig: tuple | None = None


def _is_rekeyed_content_key(key: object) -> bool:
    if isinstance(key, LevelKey):
        key = key.base
    return isinstance(key, tuple) and len(key) > 0 and key[0] in ("_prev_content", "_content_stash")


def _is_rekeyed_content_baseline(last_good_key) -> bool:
    if last_good_key is None:
        return False
    texture_keys, diff_key = last_good_key
    return any(_is_rekeyed_content_key(k) for k in texture_keys) or _is_rekeyed_content_key(diff_key)


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
            global _last_renderer_rekeyed_sig
            _rk_sig = (tuple(str(k) for k in texture_keys), tuple(sorted((str(k), str(v)) for k, v in rekeyed.items())), str(last_good_key))
            if _rk_sig != _last_renderer_rekeyed_sig:
                _last_renderer_rekeyed_sig = _rk_sig
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
    global _last_renderer_fallback_sig
    _fallback_sig = (str(key), str(last_good_key), decision_is_content_swap, main_more_pending, len(current_array_plan), str(dict(rekeyed) if rekeyed else None))
    _should_emit_fallback = _fallback_sig != _last_renderer_fallback_sig
    if _should_emit_fallback:
        _last_renderer_fallback_sig = _fallback_sig
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
    renderer._fallback_atomic_snapshot = decision_is_content_swap
    renderer._fallback_more_pending_snapshot = main_more_pending
    fallback_diag: dict[str, int] = {}
    if last_good_key is None and main_more_pending and current_array_plan:
        try:
            global _last_first_paint_hold_sig
            _hold_sig = (str(key), len(current_array_plan), bool(main_more_pending))
            if _hold_sig != _last_first_paint_hold_sig:
                _last_first_paint_hold_sig = _hold_sig
                _ic_preview_log(
                    "first_paint_hold _resolve: last_good None more_pending True hold placeholder current=%d key=%s",
                    len(current_array_plan),
                    key,
                )
        except Exception:
            pass
        fallback_diag["held_first_paint"] = 1
        return None, []
    _narrow_blocked = False
    if not main_more_pending and current_array_plan:
        try:
            _narrow_cnt = sum(1 for _it in current_array_plan if _it.bbox[2] < 0.001 or _it.bbox[3] < 0.001)
            if _narrow_cnt / len(current_array_plan) > 0.3:
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
            fallback_diag["kept"] = len(items)
            return items

        def _drop_covered(fallback_items, current_items):
            dropped = drop_covered_fallback_items(fallback_items, current_items, base_image)
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
            decision_is_content_swap,
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
            decision_atomic=decision_is_content_swap,
            decision_flag=decision_content_swap_flag,
        )
    return new_last_good_key, array_draw_plan
