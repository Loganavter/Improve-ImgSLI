"""Shared fallback-LOD promotion/coverage-drop control flow.

Both render tabs implement the same mechanism: remember the last key whose
tile set was fully drawable, draw its still-resident tiles underneath the
current key's (possibly partial) tiles until the current key catches up,
and drop the old tiles once the current key's own tiles cover them (see
docs/dev/rendering/tile-rendering-system.md "Fallback-LOD"). This module
holds no state itself -- callers own their own last-good-key value(s),
mirroring ``residency.py``'s caller-owns-the-dicts shape.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from engine.cache.tile_policy import TilePolicy

_T = TypeVar("_T")


def resolve_frame_fallback(
    policy: TilePolicy,
    *,
    key: object,
    current_items: list[_T],
    more_pending: bool,
    last_good_key: object | None,
    build_fallback_items: Callable[[object], list[_T]],
    drop_covered: Callable[[list[_T], list[_T]], list[_T]],
    cascade_pending: bool = False,
    is_content_swap: bool = False,
    is_hires_flip: bool = False,
    is_level_hold: bool = False,
) -> tuple[object | None, list[_T]]:
    """Per-frame fallback entry: apply ``policy`` to ``resolve_fallback_lod``.

    The surfaces used to reach ``resolve_fallback_lod`` directly and pass their
    own ``atomic=`` expression, which made the policy invisible outside each
    renderer. Here the caller still owns the per-frame *detection* (which kind
    of transition this frame is) and the policy owns which kinds it holds
    whole, so a surface with a flag off keeps the progressive reveal it always
    had. ``atomic`` is exactly::

        policy.atomic_on_content_swap and is_content_swap
        or policy.atomic_on_hires_flip and is_hires_flip
        or policy.atomic_on_level_change and is_level_hold

    Everything else (promotion gates, fail-open on an empty fallback plan,
    callback invocation order) is ``resolve_fallback_lod``'s, unchanged --
    this function holds no state and adds no branch of its own.
    """
    return resolve_fallback_lod(
        key=key,
        current_items=current_items,
        more_pending=more_pending,
        last_good_key=last_good_key,
        build_fallback_items=build_fallback_items,
        drop_covered=drop_covered,
        atomic=policy.atomic_for(
            is_content_swap=is_content_swap,
            is_hires_flip=is_hires_flip,
            is_level_hold=is_level_hold,
        ),
        cascade_pending=cascade_pending,
    )


def resolve_fallback_lod(
    *,
    key: object,
    current_items: list[_T],
    more_pending: bool,
    last_good_key: object | None,
    build_fallback_items: Callable[[object], list[_T]],
    drop_covered: Callable[[list[_T], list[_T]], list[_T]],
    atomic: bool = False,
    cascade_pending: bool = False,
) -> tuple[object | None, list[_T]]:
    """Decides this frame's draw plan and whether to promote ``key`` as the
    new fallback baseline.

    Returns ``(new_last_good_key, draw_plan)``: ``new_last_good_key`` is
    ``key`` itself once promotion happens, or ``last_good_key`` unchanged
    otherwise (including the "no fallback baseline yet" ``None`` case) --
    the caller stores it back into its own dict/attribute.

    Promotion happens once ``key``'s own tile set is fully uploaded
    (``not more_pending``), its mip cascade has drained (``not
    cascade_pending`` — freshly uploaded tiles sample stale coarse mips
    at their edges for 1-2 frames, visible as a tile seam; live trace
    2026-09-20: 51 dirty layers draining over exactly frames 85-86 while
    the plan drew a full 40 entries), and the set is non-empty; at that
    point the new level needs no fallback of its own, so ``current_items``
    alone is the draw plan and ``build_fallback_items``/``drop_covered``
    are not called at all. If not
    promoted this frame and a different key is tracked as the last good
    baseline, that old key's still-resident footprint (``build_fallback_items``)
    is drawn underneath wherever ``current_items`` doesn't already cover it
    (``drop_covered``) -- these two callbacks only run in this branch, since
    building and filtering a whole extra tile set is wasted work otherwise.

    ``atomic=True`` (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up,
    seventh fix; extended by plan-atomic-lod-transitions to LOD level
    changes) changes that not-yet-promoted branch: instead of layering
    ``current_items`` over the dropped-and-covered fallback (which reveals
    the new content tile-by-tile as each one uploads, visible as a
    "streaming in" effect the caller wants to avoid for a genuine content
    swap), it draws *only* ``fallback_items`` -- ``current_items`` stays
    completely hidden until promotion, at which point the whole draw plan
    flips over in one frame. ``build_fallback_items`` still runs so there is
    something to draw; ``drop_covered`` is skipped since nothing needs to be
    subtracted from a plan that never includes ``current_items``. If the
    fallback plan comes back empty (the old content was fully evicted or
    never resident), atomicity is moot -- nothing old is left to hold the
    screen -- so the partial ``current_items`` are drawn rather than a blank
    frame. Callers opt in explicitly, and not uniformly -- the opt-in now
    lives in each surface's ``TilePolicy`` (``engine.cache.tile_policy``) and
    reaches this function through ``resolve_frame_fallback`` above.
    image_compare opts into all three kinds (content swap, LOD level
    transition with a complete baseline, and hires flip; one tier per frame,
    no mixed grids -- live trace 2026-09-20 showed progressive reveal
    flashing resolution-step seams at every old/new boundary during sustained
    zoom). multi_compare opts into the level hold only: atomic on a same-slot
    LOD tier change with a tracked baseline (``base_images._is_level_hold``),
    with no content-swap branch of its own, so its other cases keep the
    progressive reveal. ``engine.gpu.tiled_image_view`` opts into none
    (default ``False``)."""
    if not more_pending and not cascade_pending and current_items:
        return key, current_items
    if last_good_key is not None and last_good_key != key:
        fallback_items = build_fallback_items(last_good_key)
        if atomic:
            if fallback_items:
                return last_good_key, fallback_items
            return last_good_key, current_items
        fallback_items = drop_covered(fallback_items, current_items)
        return last_good_key, fallback_items + current_items
    return last_good_key, current_items
