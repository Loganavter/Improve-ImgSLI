"""Shared budgeted-upload-loop primitives for tile residency realizers
(docs/dev/rendering/renderer-unification-plan.md Phase 3) -- factors out the
per-call time-budget bookkeeping and per-key upload-batch selection that
each render tab's own ``TileResidencyRealizer``/``residency.realize``
duplicated almost line-for-line. Each tab's own crop/upload-one-tile logic
stays in the caller's own loop body -- it's genuinely different per tab
(single-textured-array upload vs a branching array/plain-path plus
host-tile caching/debug dump), only the deadline/batch bookkeeping around
it was duplicated risk.
"""

from __future__ import annotations

import time

from shared.rendering.tile_constants import TILE_UPLOAD_TIME_BUDGET_MS


class UploadDeadline:
    """One call's shared time budget across every key/slot it processes.

    Never skips a key's *first* tile for it, unless the budget was already
    blown before this call even started (a already-pathological frame then
    doesn't get made worse) -- a preceding key's crop+upload can alone
    exceed the whole budget on a large source (e.g. a 100MB+ tile just
    after a pyramid-level/grid-size transition), and both tabs' array paths
    show nothing at all for a screen region until every side/slot sharing
    that draw call has at least one co-resident tile. Without this bypass,
    one key could perpetually starve every other key's upload time within
    the same call, call after call, never making progress."""

    __slots__ = ("_deadline", "_deadline_already_exhausted")

    def __init__(self, *, budget_ms: float = TILE_UPLOAD_TIME_BUDGET_MS) -> None:
        # Two separate time.monotonic() reads, not one reused value: a
        # second read that's already past the first read's deadline is the
        # "prior frame overran badly" case this guards -- in real use the
        # two reads are microseconds apart so this is always False, but
        # tests simulate the pathological case by mocking the clock to jump
        # between them (see test_time_budget_stops_upload_before_count_budget).
        start = time.monotonic()
        self._deadline = start + budget_ms / 1000.0
        self._deadline_already_exhausted = time.monotonic() >= self._deadline

    def stop_before(self, batch_offset: int) -> bool:
        """Returns True if the caller should stop uploading *before*
        processing ``batch``'s entry at ``batch_offset`` (0-based) this
        call -- whatever's left in ``batch`` stays un-uploaded and gets
        reconsidered on the next call via the caller's own "protected"
        tracking of the full (not just this call's batch) target set."""
        guaranteed_first_tile = batch_offset == 0 and not self._deadline_already_exhausted
        return not guaranteed_first_tile and time.monotonic() >= self._deadline


def plan_key_upload(
    tile_service,
    key: object,
    target: set[tuple[int, int]],
    visible_rect,
    budget_per_call: int,
) -> tuple[list[tuple[int, int]], int]:
    """Given this key's resolved ``target`` tile-index set, touches whatever
    is already resident and returns ``(batch, missing_count)``: the
    (possibly budget-capped) subset of missing indices to upload this call,
    and how many indices were actually missing before the per-call cap --
    ``len(batch) < missing_count`` means the cap left some of this key's
    tiles deferred, which the caller should fold into its own "more tiles
    pending" tracking (and typically its own debug logging, which differs
    enough per tab -- format strings, extra fields -- to stay out of this
    shared helper)."""
    missing: set[tuple[int, int]] = set()
    for index in target:
        if tile_service.is_resident(key, index):
            tile_service.touch(key, index)
        else:
            missing.add(index)
    batch = tile_service.select_upload_batch(key, missing, visible_rect, budget_per_call)
    return batch, len(missing)
