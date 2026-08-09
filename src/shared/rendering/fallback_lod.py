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

_T = TypeVar("_T")


def resolve_fallback_lod(
    *,
    key: object,
    current_items: list[_T],
    more_pending: bool,
    last_good_key: object | None,
    build_fallback_items: Callable[[object], list[_T]],
    drop_covered: Callable[[list[_T], list[_T]], list[_T]],
    atomic: bool = False,
) -> tuple[object | None, list[_T]]:
    """Decides this frame's draw plan and whether to promote ``key`` as the
    new fallback baseline.

    Returns ``(new_last_good_key, draw_plan)``: ``new_last_good_key`` is
    ``key`` itself once promotion happens, or ``last_good_key`` unchanged
    otherwise (including the "no fallback baseline yet" ``None`` case) --
    the caller stores it back into its own dict/attribute.

    Promotion happens once ``key``'s own tile set is fully uploaded
    (``not more_pending``) and non-empty; at that point the new level needs
    no fallback of its own, so ``current_items`` alone is the draw plan and
    ``build_fallback_items``/``drop_covered`` are not called at all. If not
    promoted this frame and a different key is tracked as the last good
    baseline, that old key's still-resident footprint (``build_fallback_items``)
    is drawn underneath wherever ``current_items`` doesn't already cover it
    (``drop_covered``) -- these two callbacks only run in this branch, since
    building and filtering a whole extra tile set is wasted work otherwise.

    ``atomic=True`` (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up,
    seventh fix) changes that not-yet-promoted branch: instead of layering
    ``current_items`` over the dropped-and-covered fallback (which reveals
    the new content tile-by-tile as each one uploads, visible as a
    "streaming in" effect the caller wants to avoid for a genuine content
    swap), it draws *only* ``fallback_items`` -- ``current_items`` stays
    completely hidden until promotion, at which point the whole draw plan
    flips over in one frame. ``build_fallback_items`` still runs so there is
    something to draw; ``drop_covered`` is skipped since nothing needs to be
    subtracted from a plan that never includes ``current_items``. Intended
    for a caller that only sets ``atomic=True`` while ``last_good_key`` is
    itself a rekeyed same-slot-swap marker (see callers) -- a plain
    LOD/pyramid-level transition keeps ``atomic=False`` and the original
    progressive reveal, which is the right behavior there (finer detail
    filling in over an already-visible coarser image, not a content
    change)."""
    if not more_pending and current_items:
        return key, current_items
    if last_good_key is not None and last_good_key != key:
        fallback_items = build_fallback_items(last_good_key)
        if atomic:
            return last_good_key, fallback_items
        fallback_items = drop_covered(fallback_items, current_items)
        return last_good_key, fallback_items + current_items
    return last_good_key, current_items
