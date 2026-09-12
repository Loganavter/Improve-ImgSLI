# Audit-Meta: pattern=thin-owner-target size=exempt reason="coverage+first_paint_hold extracted from RhiCanvasRenderer — see renderer.py Audit-Meta state-machine"
"""Coverage + first-paint hold extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer.render`` contained ~150 LOC of gap-coverage diagnostics
(``covered_fraction``/``_to_common_space``/``_visible_side_image_rect``) and
first-paint hold. This module holds the same bodies as plain functions taking
the owning renderer as first arg — the owner keeps construction/wiring + instance
state (``_last_good_*``, ``_content_swap_active``) per CODE_PATTERNS.md:25.
"""

from __future__ import annotations

from types import SimpleNamespace

from shared.rendering.tile_coverage import (
    covered_fraction as _covered_fraction,
    intersection_rect as _intersection_rect,
    rects_overlap as _rects_overlap,
    to_common_space as _to_common_space,
)

from .._debug import rhi_render_debug, rhi_render_debug_enabled
from ...texture_parts.tile_geometry import _visible_side_image_rect

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

# Throttle globals moved from renderer.py — owned here.
_last_renderer_coverage_sig: tuple | None = None
_last_first_paint_hold_sig: tuple | None = None


def evaluate_coverage(
    renderer,
    tile_service,
    texture_keys: tuple[object, object],
    base_image,
    viewport_zoom: tuple[float, float] | None,
    viewport_offset: tuple[float, float] | None,
    array_draw_plan: list,
    main_more_pending: bool,
) -> tuple[float, float, float]:
    """Gap-coverage diagnostics extracted from ``RhiCanvasRenderer.render``.

    Computes ``covered1``/``covered2``/``bbox_cov`` against the currently
    visible rect (zoom/pan-cropped) and emits ``GAP_DETECTED`` /
    ``coverage_healthy`` / ``gap bbox_dist`` logs with throttling, exactly
    as the inlined block in ``renderer.py`` did. Returns
    ``(covered1, covered2, bbox_cov)`` for ``apply_first_paint_hold`` to use
    without recomputing. When debug/preview is off no logs are emitted and
    coverage still computed (cheap 9x9 sampling) so the caller always has
    valid numbers.
    """
    global _last_renderer_coverage_sig

    # Fast path: when no debug requested we still need coverage numbers for
    # first_paint_hold, so compute them cheaply without the extra bbox-dist
    # / tracer work. Preserve original gating for logs but always return
    # numbers.
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
            _bbox_med = _bws_sorted[len(_bws_sorted) // 2] if _bws_sorted else 0.0
            _bbox_narrow = sum(1 for w in _bws if w < 0.01)
            if _rects_overlap(visible1_common, visible2_common):
                _overlap = _intersection_rect(visible1_common, visible2_common)
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
                            _Tracer2.instance().record(
                                "ic.gap.narrow_bbox",
                                f"narrow bbox min {_bbox_min:.5f} narrow {_bbox_narrow}/{len(array_draw_plan)}",
                                {"min_w": _bbox_min, "narrow": _bbox_narrow, "bbox_cov": _bbox_cov},
                                caller_skip=1,
                            )
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        # Still need bbox_cov for gap detection even when _gap_enabled() is
        # false but rhi debug / preview is on. Original computed it inside the
        # _gap_enabled block only, leaving _bbox_cov=1.0; gap detection then
        # used _bbox_cov_for_gap = locals().get("_bbox_cov", 1.0) which is 1.0.
        # For parity when only preview debug is on, compute bbox_cov cheaply
        # if we have overlap and plan, but keep gap Log gated.
        if array_draw_plan:
            try:
                if _rects_overlap(visible1_common, visible2_common):
                    _overlap = _intersection_rect(visible1_common, visible2_common)
                    _bbox_cov = _covered_fraction(_overlap, [it.bbox for it in array_draw_plan])
                else:
                    _bbox_cov = 0.0
            except Exception:
                _bbox_cov = 1.0

    # Only emit gap healthy/detected when at least one of the debug flags is
    # on, exactly as the original `if rhi_render_debug_enabled() or
    # _ic_preview_enabled():` gate.
    if not (rhi_render_debug_enabled() or _ic_preview_enabled()):
        return covered1, covered2, _bbox_cov

    _gap_atomic = getattr(renderer, "_fallback_atomic_snapshot", getattr(renderer, "_content_swap_active", False))
    _gap_more = getattr(renderer, "_fallback_more_pending_snapshot", False)
    if _gap_more is None:
        try:
            _gap_more = main_more_pending  # type: ignore[has-type]
        except NameError:
            _gap_more = False
    _bbox_cov_for_gap = _bbox_cov
    _bbox_min_for_gap = _bbox_min
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
            getattr(renderer, "_content_swap_active", False),
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
                        _Tracer3.instance().record(
                            "ic.gap.detected",
                            f"GAP covered {covered1:.3f}/{covered2:.3f} bbox {_bbox_cov_for_gap:.3f}",
                            {
                                "covered1": covered1,
                                "covered2": covered2,
                                "bbox_cov": _bbox_cov_for_gap,
                                "entries": len(array_draw_plan),
                                "more_pending": _gap_more,
                                "atomic": _gap_atomic,
                                "letterbox1": str(letterbox1),
                                "letterbox2": str(letterbox2),
                            },
                            caller_skip=1,
                        )
                except Exception:
                    pass
            except Exception:
                pass
    elif _ic_preview_enabled():
        try:
            _cov_sig = (
                round(covered1, 3),
                round(covered2, 3),
                round(_bbox_cov_for_gap, 3),
                len(array_draw_plan),
                bool(_gap_more),
                bool(_gap_atomic),
            )
            if _cov_sig != _last_renderer_coverage_sig:
                _last_renderer_coverage_sig = _cov_sig
                _ic_preview_log(
                    "coverage_healthy covered1=%.4f covered2=%.4f bbox=%.4f entries=%d more_pending=%s atomic=%s decision_atomic=%s",
                    covered1,
                    covered2,
                    _bbox_cov_for_gap,
                    len(array_draw_plan),
                    _gap_more,
                    getattr(renderer, "_content_swap_active", False),
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
                getattr(renderer, "_content_swap_active", False),
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
    return covered1, covered2, _bbox_cov


def apply_first_paint_hold(
    renderer,
    array_draw_plan: list,
    current_array_plan: list,
    main_more_pending: bool,
    prev_last_good,
    base_image=None,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
    covered_ok: bool | tuple[float, float, float] | None = None,
    *,
    covered1: float | None = None,
    covered2: float | None = None,
    bbox_cov: float | None = None,
) -> list:
    """First-paint atomic hold extracted from ``RhiCanvasRenderer.render``.

    When ``prev_last_good is None`` (no baseline yet) do not emit a partial
    plan even if ``_resolve`` returned it. Keep placeholder cleared until
    ``more_pending`` is False and coverage is 1.0. Throttled log. Mutates
    ``renderer._last_good_*`` on hold and returns the (possibly cleared)
    ``array_draw_plan``.

    ``covered_ok`` may be a bool or a ``(covered1, covered2, bbox_cov)``
    tuple from ``evaluate_coverage``; explicit ``covered1``/``covered2``/
    ``bbox_cov`` kwargs are also accepted for backwards compat with the
    thin delegator's call shape. If no coverage is supplied and
    ``base_image`` is available, coverage is recomputed cheaply (matching
    the original ``if "covered1" not in locals():`` fallback).
    """
    global _last_first_paint_hold_sig
    # Normalize covered_ok into per-side values
    _hold_cov1: float | None = covered1
    _hold_cov2: float | None = covered2
    _hold_bbox: float | None = bbox_cov
    _hold_covered_ok: bool | None = None
    if isinstance(covered_ok, tuple) and len(covered_ok) == 3:
        _hold_cov1, _hold_cov2, _hold_bbox = covered_ok  # type: ignore[assignment]
        _hold_covered_ok = (_hold_cov1 >= 0.999 and _hold_cov2 >= 0.999 and _hold_bbox >= 0.999)  # type: ignore[operator]
    elif isinstance(covered_ok, bool):
        _hold_covered_ok = covered_ok
        # keep covs if also passed via kwargs
    # If still missing, try to derive from kwargs or compute
    if _hold_cov1 is None or _hold_cov2 is None or _hold_bbox is None:
        # If caller passed nothing, attempt cheap recompute when base_image known
        if _hold_cov1 is None and base_image is not None and array_draw_plan:
            try:
                _lb1 = tuple(base_image.letterbox1)
                _lb2 = tuple(base_image.letterbox2)
                _ug = SimpleNamespace(total_width=1.0, total_height=1.0)
                _v1 = _visible_side_image_rect(base_image, _lb1, _ug, viewport_zoom=viewport_zoom, viewport_offset=viewport_offset)
                _v2 = _visible_side_image_rect(base_image, _lb2, _ug, viewport_zoom=viewport_zoom, viewport_offset=viewport_offset)
                _v1c = _to_common_space((_v1[0], _v1[1], _v1[2] - _v1[0], _v1[3] - _v1[1]), _lb1)
                _v2c = _to_common_space((_v2[0], _v2[1], _v2[2] - _v2[0], _v2[3] - _v2[1]), _lb2)
                _hold_cov1 = _covered_fraction(_v1c, [_to_common_space(it.rect1, _lb1) for it in array_draw_plan])
                _hold_cov2 = _covered_fraction(_v2c, [_to_common_space(it.rect2, _lb2) for it in array_draw_plan])
                if _hold_bbox is None:
                    # bbox cov not recomputed in original cheap fallback; keep 1.0 or derive
                    _hold_bbox = 1.0
                    try:
                        if _rects_overlap(_v1c, _v2c):
                            _overlap = _intersection_rect(_v1c, _v2c)
                            _hold_bbox = _covered_fraction(_overlap, [it.bbox for it in array_draw_plan])
                        else:
                            _hold_bbox = 0.0
                    except Exception:
                        _hold_bbox = 1.0
            except Exception:
                _hold_covered_ok = False
                _hold_cov1 = _hold_cov2 = 0.0
                _hold_bbox = 0.0
        else:
            if _hold_cov1 is None:
                _hold_cov1 = 1.0
            if _hold_cov2 is None:
                _hold_cov2 = 1.0
            if _hold_bbox is None:
                _hold_bbox = 1.0
    if _hold_covered_ok is None:
        _hold_covered_ok = _hold_cov1 >= 0.999 and _hold_cov2 >= 0.999 and _hold_bbox >= 0.999  # type: ignore[operator]

    try:
        _prev_hold_is_first = prev_last_good is None  # type: ignore[has-type]
    except NameError:
        _prev_hold_is_first = False

    if _prev_hold_is_first and array_draw_plan:
        if main_more_pending or not _hold_covered_ok:
            try:
                _hold_sig2 = (bool(main_more_pending), round(float(_hold_cov1), 3), round(float(_hold_cov2), 3), len(array_draw_plan))  # type: ignore[arg-type]
                if _hold_sig2 != _last_first_paint_hold_sig:
                    _last_first_paint_hold_sig = _hold_sig2
                    _ic_preview_log(
                        "first_paint_hold render: prev_last_good None more_pending=%s covered=%.3f/%.3f bbox=%.3f hold placeholder (was %d entries)",
                        main_more_pending,
                        _hold_cov1,
                        _hold_cov2,
                        _hold_bbox,
                        len(array_draw_plan),
                    )
                    rhi_render_debug(
                        "render FIRST_PAINT_HOLD more_pending=%s covered=%.3f/%.3f bbox=%.3f entries=%d -> hold 0",
                        main_more_pending,
                        _hold_cov1,
                        _hold_cov2,
                        _hold_bbox,
                        len(array_draw_plan),
                    )
            except Exception:
                pass
            # Hold placeholder: clear partial draw, revert promotion
            try:
                renderer._last_good_texture_keys, renderer._last_good_diff_key = (None, None)
            except Exception:
                pass
            return []
        # covered and not more_pending -> allow through, keep plan as-is
        return array_draw_plan
    elif _prev_hold_is_first and not array_draw_plan and current_array_plan and main_more_pending:
        try:
            _hold_sig3 = (bool(main_more_pending), len(current_array_plan))
            if _hold_sig3 != _last_first_paint_hold_sig:
                _last_first_paint_hold_sig = _hold_sig3
                _ic_preview_log(
                    "first_paint_hold render: still held placeholder current=%d more_pending=%s",
                    len(current_array_plan),
                    main_more_pending,
                )
        except Exception:
            pass
        return array_draw_plan
    return array_draw_plan
