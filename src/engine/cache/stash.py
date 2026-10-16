"""Per-key content-stash contract for tile residency realizers.

Extracted from the fixed-pair render tab's ``TileResidencyRealizer``
(``tabs/image_compare/canvas/rhi_renderer/residency.py`` -- its stash/hold
state machine, now ``ContentStash.note_source`` / ``rekey_or_restore`` /
``release_and_protect_preview_holds`` / ``preview_extra_protect_keys``),
with identical semantics; only the storage home and the call boundary
changed. Engine
types only -- no tab imports (see ``tests/contracts/
test_platform_isolation.py``).

A texture key (``"stored_0"``/``"source_1"``/...) is a stable slot label,
not per-image identity: loading new content into an already-loaded slot
reuses the same key, and ``register_source`` on that key resets residency
bookkeeping -- silently dropping every already-uploaded tile before a
single tile of the new content has landed. The stash keeps the swapped-out
content alive under a stable per-``(key, content_uid)`` marker key so a
later swap back restores it with zero GPU work, and so the caller's
fallback-LOD baseline has something real to draw underneath the
still-uploading new content.

The hold state machine (moved verbatim):

- **Preview baseline kept, not promoted**: the first QImage preview stashed
  for a slot is a *joint* hold ("until BOTH halves have complete tile
  replacement"). Intermediate low-res stores must not overwrite it as the
  fallback baseline, so while the hold is alive the tab keeps reporting the
  preview stash key (not the intermediate stash key) as this call's rekeyed
  old content.
- **Restore-on-rekey**: a role toggling between a small fixed set of
  distinct contents under the same slot key swaps a still-resident stashed
  entry straight back onto the key instead of registering a blank grid.
- **Release-and-protect**: dead holds (stash key lost all residency) are
  dropped; this call's pair holds release once both halves' new content is
  fully resident; surviving holds contribute their role keys to the
  host-cache protected set so a foreign-pair call (the magnifier's
  ``source_*`` residency call shares the realizer and the host cache with
  the main ``stored_*`` call) cannot evict the held baseline's host image
  while its GPU hold is still active.

``tile_service`` is duck-typed (``rekey_source``/``register_source``/
``grid_for``/``resident_tiles``/``is_resident``) -- the same shape
``engine.cache.residency.TileResidencyRealizerBase.realize_specs`` already
assumes. Content uids are opaque (``image_uid`` ints, or ``(uid, box)``
tuples once a crop box joins the content identity); the stash only ever
compares and hashes them, never interprets them.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Callable, Mapping

from engine.cache.tile_debug import log_tile_event, tile_dump_enabled


def make_stash_key(key: object, content_uid: object) -> tuple:
    """Stable marker key a slot's swapped-out content is stowed under.

    Stable per ``(key, content_uid)`` (not a disposable one-shot key) so a
    later swap back to the same content is recognized and restored. The
    ``"_content_stash"`` head is load-bearing: the tab's fallback-LOD
    content-swap detector matches it alongside ``"_prev_content"``.
    """
    return ("_content_stash", key, content_uid)


def is_stash_key(key: object) -> bool:
    """True iff ``key`` is a stowed-content marker made by
    ``make_stash_key``."""
    return isinstance(key, tuple) and len(key) > 0 and key[0] == "_content_stash"


def _noop_log(msg: str, *args, **kwargs) -> None:
    return None


class ContentStash:
    """Owns stowed tile-content keys + preview-hold state for one realizer.

    One instance per resources owner (mirrors the per-``RhiResources``/
    per-``BaseImagesPass`` construction pattern). Holds cross-frame
    stash/hold state only -- fixed config stays with the caller. The
    per-frame rekeyed-old-content map (``last_rekeyed_keys``) stays owned
    by the tab realizer (the renderer reads and resets it every frame);
    the methods below take it as an explicit ``rekeyed`` argument and
    record into it.
    """

    def __init__(self, *, log: Callable[..., None] | None = None) -> None:
        self._log = log or _noop_log
        # Per-key memo of {content_uid: stash_key} for content this key has
        # already shown before. A role that keeps toggling between a small
        # fixed set of distinct contents under the *same* slot key would
        # otherwise re-register (register_source resets residency) and
        # fully re-crop+re-upload every tile on every single toggle, even
        # though the content it's toggling back to was fully resident a
        # moment ago. Entries live only as long as `tile_service` still
        # has them resident (budget eviction can still reclaim a stashed
        # entry between toggles -- then it's just a normal cache miss, not
        # a correctness issue).
        self._contents: dict[object, dict[object, object]] = {}
        # Preview baseline that must survive until BOTH halves have complete
        # tile replacement (UX: preview never deleted until both sides'
        # final hires tiles fully resident). The first QImage preview
        # stashed for a slot is kept here and always added to
        # extra_protect_keys, so intermediate low-res stores (1024/1440
        # unified) never evict it before the final hires (5760) is fully
        # resident and promoted.
        self._preview_holds: dict[object, object] = {}
        # Last-seen content uid of the live source per key, so a same-size
        # content swap (grid dimensions unchanged) is still detected.
        self._source_uid_by_key: dict[object, object] = {}
        # Whether previous source for key was a QImage preview (not a
        # tiled pixel store).
        self._prev_is_preview_by_key: dict[object, bool] = {}

    def note_source(
        self, key: object, content_uid: object, *, is_preview: bool
    ) -> tuple[object | None, bool, bool]:
        """Records this call's live ``content_uid`` for ``key``.

        Called unconditionally for every key with a live source (even on
        first registration, so the next call has a baseline). Returns
        ``(prev_uid, prev_is_preview, content_changed)`` for the caller's
        re-register decision -- a same-size image swap leaves grid
        dimensions unchanged, so the size check alone never re-fires and
        only this identity comparison catches it.
        """
        prev_uid = self._source_uid_by_key.get(key)
        content_changed = prev_uid is not None and prev_uid != content_uid
        prev_is_preview = bool(self._prev_is_preview_by_key.get(key, False))
        self._source_uid_by_key[key] = content_uid
        self._prev_is_preview_by_key[key] = bool(is_preview)
        return prev_uid, prev_is_preview, content_changed

    def rekey_or_restore(
        self,
        tile_service,
        key: object,
        content_uid: object,
        size: tuple[int, int],
        *,
        prev_uid: object | None,
        prev_is_preview: bool = False,
        rekeyed: dict,
    ):
        """Same-slot content swap for ``key`` (``prev_uid``'s content ->
        ``content_uid``'s). If ``content_uid`` was stowed here from an
        earlier swap *and* is still resident, restores it onto ``key`` via
        ``rekey_source`` with zero GPU work instead of registering a blank
        grid and re-cropping+re-uploading every tile -- the toggle-between-
        a-few-known-contents case (see ``self._contents``' docstring in
        ``__init__``). Otherwise behaves like the old unconditional
        ``rekey_stale_content`` + ``register_source``, except the outgoing
        content is stowed under a key stable per ``(key, prev_uid)``
        (``make_stash_key``) rather than a disposable one-shot key, so a
        later swap back to it can be recognized. Records this call's
        rekeyed-old-content mapping into ``rekeyed`` (the tab's
        ``last_rekeyed_keys``). Returns the freshly resolved grid.
        """
        src_w, src_h = size
        if prev_uid is not None and prev_uid == content_uid:
            # Same object, different size -- a mutated/resized source, not
            # a swap between two known contents. Nothing to stash or
            # restore; drop straight through to a fresh register below.
            return tile_service.register_source(key, (src_w, src_h))

        stowed = self._contents.setdefault(key, {})
        if prev_uid is not None and tile_service.resident_tiles(key):
            stash_key = make_stash_key(key, prev_uid)
            tile_service.rekey_source(key, stash_key)
            stowed[prev_uid] = stash_key
            if prev_is_preview:
                # Keep QImage preview baseline until BOTH halves have complete
                # tile replacement (joint hold). Intermediate low-res stores
                # must not overwrite it as fallback baseline.
                self._preview_holds[key] = stash_key
                rekeyed[key] = stash_key
                self._log(
                    "rekey _content_stash preview hold: key=%s prev_uid=%s -> stash_key=%s resident=%d (preview baseline kept)",
                    key,
                    prev_uid,
                    stash_key,
                    len(tile_service.resident_tiles(stash_key) or ()),
                )
            else:
                # If preview baseline still resident, keep it as fallback
                # instead of overwriting with intermediate low-res store.
                _preview_key = self._preview_holds.get(key)
                if _preview_key is not None and tile_service.resident_tiles(_preview_key):
                    self._log(
                        "rekey _content_stash: key=%s prev_uid=%s -> stash_key=%s resident=%d (preview baseline kept, not promoted)",
                        key,
                        prev_uid,
                        stash_key,
                        len(tile_service.resident_tiles(stash_key) or ()),
                    )
                    # keep last_rekeyed pointing to preview, not intermediate
                    rekeyed[key] = _preview_key
                else:
                    # no preview hold, promote intermediate as usual; clear stale preview hold
                    if _preview_key is not None:
                        self._preview_holds.pop(key, None)
                    rekeyed[key] = stash_key
                    self._log(
                        "rekey _content_stash: key=%s prev_uid=%s -> stash_key=%s resident=%d",
                        key,
                        prev_uid,
                        stash_key,
                        len(tile_service.resident_tiles(stash_key) or ()),
                    )
            if tile_dump_enabled():
                log_tile_event(
                    "rekey_stale_content",
                    key=str(key),
                    prev_key=str(stash_key),
                    resident_tile_count=len(tile_service.resident_tiles(stash_key)),
                )

        restore_key = stowed.get(content_uid)
        if restore_key is not None and tile_service.resident_tiles(restore_key):
            self._log(
                "restore_stashed_content: key=%s src_uid=%s <- restore_key=%s resident=%d",
                key,
                content_uid,
                restore_key,
                len(tile_service.resident_tiles(restore_key) or ()),
            )
            tile_service.rekey_source(restore_key, key)
            del stowed[content_uid]
            if tile_dump_enabled():
                log_tile_event(
                    "restore_stashed_content",
                    key=str(key),
                    restore_key=str(restore_key),
                    resident_tile_count=len(tile_service.resident_tiles(key)),
                )
            return tile_service.grid_for(key)
        elif restore_key is not None:
            self._log(
                "restore_stashed_content: SKIP key=%s src_uid=%s restore_key=%s — evicted, cache miss",
                key,
                content_uid,
                restore_key,
            )

        return tile_service.register_source(key, (src_w, src_h))

    def preview_extra_protect_keys(self, tile_service) -> tuple:
        """Stash keys the caller's eviction pass must protect this call.

        The joint preview hold keeps the QImage preview stash alive until
        BOTH halves have complete tile replacement -- without this,
        intermediate 1024/1440 stores would evict the preview baseline
        before the final hires (5760) is fully resident. Returns the
        still-resident hold keys (empty when no hold is active); the caller
        appends them to its own ``extra_protect_keys``.
        """
        if self._preview_holds:
            _preview_protect = tuple(
                k for k in self._preview_holds.values() if tile_service.resident_tiles(k)
            )
            if _preview_protect:
                self._log(
                    "preview protect hold: keys=%s resident=%s",
                    list(self._preview_holds.keys()),
                    [len(tile_service.resident_tiles(k) or ()) for k in _preview_protect],
                )
                return _preview_protect
        return ()

    def release_and_protect_preview_holds(
        self, tile_service, pairs, texture_keys, result
    ) -> set:
        """Joint preview-hold maintenance + host-cache protected set.

        The preview baseline stowed in ``_preview_holds`` is a *joint* hold
        ("until BOTH halves have complete tile replacement"): its GPU tiles
        are protected via ``extra_protect_keys`` inside ``realize_specs``,
        but the host-side QImage behind the fallback is evicted by a
        separate ``evict_texture_upload_cache_over_budget`` pass whose
        protected set used to be only this call's own pairs. A call made
        for a different role pair (the magnifier's ``source_*`` residency
        call shares the realizer and the host cache with the main
        ``stored_*`` call) could therefore drop the held baseline while its
        GPU hold was still active -- and neither progressive re-crop nor
        post-context-loss ``restore_texture_uploads`` (which re-queues from
        the host cache) could bring it back.

        So: drop holds whose stash key lost all residency (dead fallback --
        protecting nothing), release this call's pair holds once both
        halves' new content is fully resident (per
        ``result.key_incomplete_by_key``), and return this call's pairs plus
        the role keys backing the surviving holds as the host protected set.
        Stash/tuple keys never live in the host cache (whole-image QImages
        keyed by texture role), so only the role key is added per hold.
        """
        for held_role in list(self._preview_holds):
            try:
                alive = bool(
                    tile_service.resident_tiles(self._preview_holds[held_role])
                )
            except Exception:
                alive = False
            if not alive:
                self._preview_holds.pop(held_role, None)
        try:
            pair_complete = bool(texture_keys) and all(
                result.key_incomplete_by_key.get(key) is False
                for key in texture_keys
            )
        except Exception:
            pair_complete = False
        if pair_complete:
            for key in texture_keys:
                self._preview_holds.pop(key, None)
        host_protected = {key for key, _ in pairs}
        for held_role, stash_key in self._preview_holds.items():
            try:
                if tile_service.resident_tiles(stash_key):
                    host_protected.add(held_role)
            except Exception:
                pass
        return host_protected

    def preview_holds_view(self) -> Mapping:
        """Live read view of the active joint preview holds.

        ``{role key: stash key}``; reflects subsequent stow/release calls.
        Exists for the tab's frozen preview-hold tripwire assertions --
        producers must go through ``rekey_or_restore`` /
        ``release_and_protect_preview_holds``, never mutate this view.
        """
        return MappingProxyType(self._preview_holds)
