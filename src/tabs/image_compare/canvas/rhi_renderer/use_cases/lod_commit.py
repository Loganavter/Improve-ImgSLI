# Audit-Meta: pattern=thin-owner-target size=exempt reason="LOD commit extracted from RhiCanvasRenderer — see renderer.py Audit-Meta state-machine"
"""LOD commit extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer.render`` contained ~90 LOC of LOD-level commit
logic around ``resolve_lod_texture_keys`` plus pending/since debounce,
``image_uid``-based source identity, and ``LOD_FETCH_SETTLE_MS``
settling. This module holds the same body as a plain function taking the
owning renderer as first arg — the owner keeps construction/wiring +
instance state (``_lod_pending_keys/_lod_pending_since/_lod_committed_keys/
_lod_committed_source_ids``) per CODE_PATTERNS.md:25.
"""

from __future__ import annotations

import time

from engine.cache.image_identity import image_uid
from engine.cache.lod import LevelKey
from engine.cache.tile_constants import LOD_FETCH_SETTLE_MS
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from engine.store.pyramid_registry import pyramid_for

from ..draw_plan import resolve_lod_texture_keys

from engine.frame.context import BudgetStats, FrameContext, make_ids
from tabs.image_compare.canvas.loupe_trace import throttle_emit as _throttle_emit

try:
    from tabs.image_compare.debug import ic_preview_debug as _ic_preview_log  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug_enabled as _ic_preview_enabled  # type: ignore
except Exception:  # pragma: no cover

    def _ic_preview_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _ic_preview_enabled() -> bool:  # type: ignore
        return False


# Throttle per-frame committed-sources log — state lives in loupe_trace's
# centralized throttle store (stream "lod_commit.sources_committed").


def committed_lod_baseline_stale(committed_keys, texture_keys, sources) -> bool:
    """True when a previously committed ``LevelKey`` no longer names live content.

    Compares each committed level key's generation against the live pyramid
    for its base source (``texture_keys``/``sources`` run parallel, so the
    base maps positionally) and re-checks ``is_level_built``: a reunified
    base (fresh generation), a swept pyramid, or a level closed between
    pick and sample all verdict stale. Stale baselines must never be drawn
    or promoted -- the caller re-commits the freshly resolved keys
    immediately instead of waiting out the settle window. Fails open
    (False) on any lookup surprise: the sample-time guard
    (``_pil_image_for_texture_key`` -> gap) still covers what this misses.
    """
    if not committed_keys:
        return False
    try:
        base_by_key = dict(zip(texture_keys, sources))
    except Exception:
        return False
    for key in committed_keys:
        if not isinstance(key, LevelKey):
            continue
        try:
            pyramid = pyramid_for(base_by_key.get(key.base))
        except Exception:
            continue
        if pyramid is None:
            continue
        try:
            if key.generation != pyramid.generation:
                return True
            if not pyramid.is_level_built(key.level):
                return True
        except Exception:
            continue
    return False


def commit_lod_keys(
    renderer,
    texture_keys,
    sources,
    base_image,
    canvas_size_px,
    frame_context: FrameContext | None = None,
) -> tuple:
    """Thin-owner wrapper: identical to ``RhiCanvasRenderer`` LOD commit
    block in ``renderer.py:862`` — see its inline comments for contract.

    Resolves ``texture_keys``/``sources``/``base_image``/``canvas_size_px``
    via ``resolve_lod_texture_keys``, then applies the pending/since
    debounce and ``image_uid``-based ``source_changed`` detection with
    ``LOD_FETCH_SETTLE_MS`` settling. Mutates ``renderer._lod_pending_*``
    / ``renderer._lod_committed_*`` exactly as before and returns
    ``(committed_keys, source_changed)``.

    ``frame_context`` is the Phase-2 frame-bus hook: when provided, the
    commit decision records its LOD keys + settle time IN ADDITION to
    existing behavior (``None`` keeps every existing call site
    behavior-identical).
    """
    # Copy-pasted body from renderer.py:491-597 — keep log throttling identical.
    raw_texture_keys = resolve_lod_texture_keys(
        texture_keys,
        sources,
        base_image,
        canvas_size_px,
    )
    now = time.monotonic()
    if raw_texture_keys != renderer._lod_pending_keys:
        # Flap diagnostic (plan-atomic-lod-transitions Wave B): pyramid
        # readiness races make raw keys oscillate A->B->A with quiet gaps
        # that defeat the settle window (seen: 4.6s pending then forced
        # commit). Count oscillations; a hot counter justifies future
        # hysteresis, a cold one closes the case. Behavior unchanged.
        try:
            _prev_pending = renderer._lod_pending_keys
            _flaps = getattr(renderer, "_lod_flap_count", 0)
            _last_flap = getattr(renderer, "_lod_flap_since", 0.0)
            if (
                _prev_pending is not None
                and raw_texture_keys == getattr(renderer, "_lod_flap_alt", None)
                and (now - _last_flap) * 1000.0 < 4 * LOD_FETCH_SETTLE_MS
            ):
                renderer._lod_flap_count = _flaps + 1  # type: ignore[attr-defined]
                renderer._lod_flap_since = now  # type: ignore[attr-defined]
                _ic_preview_log(
                    "lod_commit flap raw oscillating (count=%d)",
                    _flaps + 1,
                )
            else:
                renderer._lod_flap_alt = _prev_pending  # type: ignore[attr-defined]
                renderer._lod_flap_since = now  # type: ignore[attr-defined]
        except Exception:
            pass
        renderer._lod_pending_keys = raw_texture_keys
        renderer._lod_pending_since = now
    # image_uid, not id(): id() is a memory address that CPython can
    # (and does) reuse once the old source object is garbage
    # collected -- exactly what tends to happen right after a swap
    # discards the old source -- so a *second* swap could coincide
    # with the freed old address being handed to the new source
    # object, making source_changed below false-negative and commit
    # skip the immediate re-fetch it exists for, showing the stale
    # image under a doubly-stale key until the settle window and
    # residency catch up. image_uid tags each object with a
    # monotonic counter value once (via .info/an attribute) that
    # persists for that object's lifetime and is never reused.
    source_ids = (image_uid(sources[0]), image_uid(sources[1]))
    # An actual image replacement (not just a LOD level change on the
    # still-loaded image) must commit immediately rather than wait
    # out the settle delay: the settle delay's premise is that the
    # *previously committed* key's tiles are still valid, real
    # content worth protecting from a premature re-fetch churn (see
    # LOD_FETCH_SETTLE_MS's docstring) -- that premise is false the
    # instant the underlying source object changes, since the old
    # committed key (e.g. a bare, pre-pyramid key from the prior
    # image) then points at stale content. Holding it anyway made
    # realize_tile_plan re-register and tile the *new* image at full
    # source resolution under that stale bare key for the whole
    # settle window, instead of the small pyramid level
    # resolve_lod_texture_keys had already picked (docs/dev/
    # rendering/tile-array-atlas-plan.md Phase 9 "image swap tiles
    # full source under stale committed key" finding).
    source_changed = source_ids != renderer._lod_committed_source_ids
    # A stale committed baseline (reunified base / swept pyramid / level
    # closed since it committed) commits the fresh resolve immediately,
    # like a source change: holding it through the settle window would pin
    # a key the sample-time guard can only render as a gap.
    stale_baseline = committed_lod_baseline_stale(
        renderer._lod_committed_keys, texture_keys, sources
    )
    if (
        renderer._lod_committed_keys is None
        or source_changed
        or stale_baseline
        or (now - renderer._lod_pending_since) * 1000.0 >= LOD_FETCH_SETTLE_MS
    ):
        renderer._lod_committed_keys = raw_texture_keys
        renderer._lod_committed_source_ids = source_ids
    texture_keys = renderer._lod_committed_keys
    # sources vs draw_plan stale fix: log after LOD commit so is_same and tex_keys reflect committed draw.
    if _ic_preview_enabled():
        # throttle committed sources — 60Hz spam
        try:
            _is_same_committed = len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]
            _comm_sig = (base_image.use_hires, tuple(str(k) for k in raw_texture_keys), tuple(str(k) for k in texture_keys), _is_same_committed, tuple(image_uid(s) if s is not None else None for s in sources))  # type: ignore[has-type]
            if _throttle_emit("lod_commit.sources_committed", _comm_sig):  # type: ignore[has-type]
                _ic_preview_log(
                    "sources committed use_hires=%s tex_keys_raw=%s tex_keys_committed=%s is_same_object_committed=%s src_uids=%s committed_uids_src=%s",
                    base_image.use_hires,
                    [str(k) for k in raw_texture_keys],
                    [str(k) for k in texture_keys],
                    _is_same_committed,
                    [image_uid(s) if s is not None else None for s in sources],
                    list(source_ids),
                )
                _ic_preview_log(
                    "draw_sources committed tex_keys=%s is_same=%s committed_src_ids=%s raw_src_ids=%s",
                    [str(k) for k in texture_keys],
                    _is_same_committed,
                    list(source_ids),
                    [str(k) for k in raw_texture_keys],
                )
        except Exception:
            _is_same_committed = len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]
            _ic_preview_log(
                "sources committed use_hires=%s tex_keys_raw=%s tex_keys_committed=%s is_same_object_committed=%s src_uids=%s committed_uids_src=%s",
                base_image.use_hires,
                [str(k) for k in raw_texture_keys],
                [str(k) for k in texture_keys],
                _is_same_committed,
                [image_uid(s) if s is not None else None for s in sources],
                list(source_ids),
            )
            _ic_preview_log(
                "draw_sources committed tex_keys=%s is_same=%s committed_src_ids=%s raw_src_ids=%s",
                [str(k) for k in texture_keys],
                _is_same_committed,
                list(source_ids),
                [str(k) for k in raw_texture_keys],
            )
    if source_changed:
        _ic_preview_log(
            "lod_commit source_changed=True src_ids=%s raw=%s committed=%s pending_ms=%.1f",
            list(source_ids),
            [str(k) for k in raw_texture_keys],
            [str(k) for k in texture_keys],
            (now - renderer._lod_pending_since) * 1000.0,
        )
    if tile_dump_enabled():
        log_tile_event(
            "lod_commit",
            source_ids=list(source_ids),
            source_changed=source_changed,
            raw_texture_keys=[str(k) for k in raw_texture_keys],
            committed_texture_keys=[str(k) for k in texture_keys],
            pending_since_ms=(now - renderer._lod_pending_since) * 1000.0,
        )
    # Phase-2 frame bus: LOD keys + settle time (record only, never instead).
    if frame_context is not None:
        _pending_ms = (now - renderer._lod_pending_since) * 1000.0
        _held = bool(raw_texture_keys != texture_keys)
        _stats = BudgetStats(
            time_ms=_pending_ms,
            budget_ms=float(LOD_FETCH_SETTLE_MS),
            more_pending=_held,
        )
        frame_context.record(
            "lod_commit",
            "skipped" if _held else "ran",
            f"lod_commit source_changed={source_changed}"
            f" raw={[str(k) for k in raw_texture_keys]}"
            f" committed={[str(k) for k in texture_keys]}"
            f" {_stats.describe()}",
            ids=make_ids(
                frame_context.frame_id,
                tuple(str(k) for k in raw_texture_keys),
                tuple(str(k) for k in texture_keys),
                _stats.as_tuple(),
            ),
        )
    return texture_keys, source_changed
