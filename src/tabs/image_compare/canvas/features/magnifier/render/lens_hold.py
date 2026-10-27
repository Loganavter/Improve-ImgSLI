"""Last-good lens sample for the frames a pair replacement leaves sourceless.

Owner report (2026-10-27): "лупа почему-то пропадает на пару кадров во время
смены изображений" -- the loupe's content vanished for 1-2 frames whenever the
pair's images were swapped/replaced.

Probe on the real residents (``ContentStash`` + ``TileTextureService``, no GPU
needed) shows why the residency hold cannot cover it: right after a
replacement every key the lens is allowed to look at is blank.

* before the swap the lens samples ``source_0``/``source_1`` (resident);
* the replacement re-registers both roles -- ``stored_*`` too -- so
  ``_lens_residency_hold`` holds (its "hold_stored_until_resident" reason) and
  the lens falls back to the stored role, whose grid was just reset:
  ``slot_for`` misses every tile, ``_source_slices`` returns ``[]``,
  ``prepare`` has zero records for the quad, and the lens content is simply
  not drawn (``magnifier_pass.prepare``'s ``if not records: continue``).
* the PREVIOUS content is still there: the realizer rekeys a replaced slot's
  resident tiles onto ``("_content_stash", key, uid)`` and reports that key in
  ``last_rekeyed_keys`` (the same map the canvas's own old-content baseline
  reads). Nothing about it belongs to the other slot -- it is this slot key's
  own previous picture, at the same grid.

So the lens can keep drawing ITS OWN previous frame instead of disappearing:
``replay_held_records`` re-points the records this pass last DREW at those
stashed tiles. Identity is enforced structurally, not by trust:

* a record role is only re-pointed through ``stash_by_key[<the record's own
  source key>]`` -- a left lens can therefore only ever reach
  ``("_content_stash", "source_0", ...)``, never the neighbour slot's key;
* the stash tile must still hold a GPU slot (``slot_for``) on a registered
  grid -- a freed/recycled layer, or content the realizer never stashed,
  fails closed and the quad keeps the pre-fix behaviour (nothing drawn);
* the check is all-or-nothing per quad: a partially proven quad would draw a
  patch of the lens, which is worse than the frozen frame it replaces.

Frozen means frozen: the replay keeps the previous records' uv/tc mapping
(the capture window it was drawn from) while the quad's screen geometry
(centre, radius, zoom) still follows this frame, so the lens stays attached
to the cursor. The caller must not cache the replay result as a new
last-good sample -- anchoring on the live draw is what makes the identity
argument hold on later frames.
"""

from __future__ import annotations

from tabs.image_compare.canvas.rhi_renderer import _ARRAY_LAYER_PX

#: The three texture roles ``build_tile_records`` fills (see
#: ``tile_capture.build_tile_records``): one shared texture array addressed
#: per record by layer, so each role is itself a (key, tile) reference.
TEX_ROLES = ("tex1", "tex2", "texd")


def cache_quad_records(records, refs_by_tile_key) -> list:
    """This quad's drawn records + where each sampled tile came from.

    ``refs_by_tile_key`` is filled by the caller while it resolves slices
    (``{tile_key: (source_key, tile_index)}``), so the reference is the
    service's own answer instead of a guess parsed back out of a key.
    A role whose tile_key has no reference (the raster/placeholder path)
    keeps ``None`` and makes the whole quad non-replayable, which is the
    correct fail-closed answer: an unidentifiable sample cannot be proven
    to still be this side's content.
    """
    entries = []
    for record in records:
        refs = {}
        for role in TEX_ROLES:
            tex = record.get(role)
            # ``key is None`` is ``build_tile_records``' explicit "this record
            # does not sample this role" (the shader picks a role per
            # source_mode/combined branch), not an unidentifiable tile.
            if not tex or tex.get("key") is None:
                continue
            refs[role] = refs_by_tile_key.get(tex.get("key"))
        entries.append({"record": record, "refs": refs})
    return entries


def replay_held_records(tile_service, entries, stash_by_key) -> list:
    """Re-point a quad's last-good records at the stashed previous content.

    Returns the records to draw this frame, or ``[]`` when anything cannot
    be proven (no entries -- the lens never drew, requirement "no sample, no
    lens" -- an unidentified role, no stash for that key, a stash grid that
    is gone, or a tile whose GPU slot was released). An empty result is the
    pre-fix behaviour, never a wrong picture.
    """
    if not entries or not stash_by_key or tile_service is None:
        return []
    # Same engine entry the live slice path uses for content scale (see
    # tile_residency_gate._source_slices): function-local keeps the tab ->
    # engine edge at the call site.
    from engine.cache.draw_plans import content_scale_for as _engine_content_scale

    replayed = []
    for entry in entries:
        record = entry["record"]
        new_record = dict(record)
        proven = 0
        for role in TEX_ROLES:
            tex = record.get(role)
            if not tex or tex.get("key") is None:
                continue
            ref = entry["refs"].get(role)
            if ref is None:
                return []
            source_key, tile_index = ref
            tile_index = tuple(tile_index)
            stash_key = stash_by_key.get(source_key)
            # A stash entry equal to the live key would mean "the previous
            # content is the current content" -- not a replacement, so this
            # quad must not be frozen over it.
            if stash_key is None or stash_key == source_key:
                return []
            if tile_service.grid_for(stash_key) is None:
                return []
            slot = tile_service.slot_for(stash_key, tile_index)
            if slot is None:
                return []
            new_record[role] = {
                "key": tile_service.tile_key(stash_key, tile_index[0], tile_index[1]),
                "layer": slot[1],
                "scale": _engine_content_scale(
                    tile_service.content_size_for(stash_key, tile_index),
                    _ARRAY_LAYER_PX,
                ),
            }
            proven += 1
        # A record that samples nothing identifiable (the raster/placeholder
        # path) proves nothing about identity: never draw it from a guess.
        if not proven:
            return []
        replayed.append(new_record)
    return replayed
