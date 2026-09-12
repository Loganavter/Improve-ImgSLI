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

from shared.rendering.image_identity import image_uid
from shared.rendering.tile_constants import LOD_FETCH_SETTLE_MS
from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled

from ..draw_plan import resolve_lod_texture_keys

try:
    from tabs.image_compare.debug import ic_preview_debug as _ic_preview_log  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug_enabled as _ic_preview_enabled  # type: ignore
except Exception:  # pragma: no cover

    def _ic_preview_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _ic_preview_enabled() -> bool:  # type: ignore
        return False


# Throttle per-frame committed-sources log — moved from renderer.py.
_last_renderer_sources_committed_sig: tuple | None = None


def commit_lod_keys(renderer, texture_keys, sources, base_image, canvas_size_px) -> tuple:
    """Thin-owner wrapper: identical to ``RhiCanvasRenderer`` LOD commit
    block in ``renderer.py:862`` — see its inline comments for contract.

    Resolves ``texture_keys``/``sources``/``base_image``/``canvas_size_px``
    via ``resolve_lod_texture_keys``, then applies the pending/since
    debounce and ``image_uid``-based ``source_changed`` detection with
    ``LOD_FETCH_SETTLE_MS`` settling. Mutates ``renderer._lod_pending_*``
    / ``renderer._lod_committed_*`` exactly as before and returns
    ``(committed_keys, source_changed)``.
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
    if (
        renderer._lod_committed_keys is None
        or source_changed
        or (now - renderer._lod_pending_since) * 1000.0 >= LOD_FETCH_SETTLE_MS
    ):
        renderer._lod_committed_keys = raw_texture_keys
        renderer._lod_committed_source_ids = source_ids
    texture_keys = renderer._lod_committed_keys
    # sources vs draw_plan stale fix: log after LOD commit so is_same and tex_keys reflect committed draw.
    if _ic_preview_enabled():
        # throttle committed sources — 60Hz spam
        try:
            global _last_renderer_sources_committed_sig  # type: ignore[used-before-def]
            _is_same_committed = len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]
            _comm_sig = (base_image.use_hires, tuple(str(k) for k in raw_texture_keys), tuple(str(k) for k in texture_keys), _is_same_committed, tuple(image_uid(s) if s is not None else None for s in sources))  # type: ignore[has-type]
            if _comm_sig != _last_renderer_sources_committed_sig:  # type: ignore[has-type]
                _last_renderer_sources_committed_sig = _comm_sig  # type: ignore[has-type]
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
    return texture_keys, source_changed
