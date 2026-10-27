"""The fallback basline may only ever show THIS pair's content.

Owner report (2026-10-27 14:34:41, `IMGSLI_IC_PREVIEW_DEBUG=1`): after a pair
swap the atomic fallback baseline still presented the OLD pair for one or two
frames (~23 ms) although the new content was already applied to the GPU::

    41.412  pick->GPU applied … picked_uids=11/12 stored_uids=11/12 match=True
    41.429  fallback content_swap_active: SET
    41.429  fallback result: atomic=True fallback_raw=9 fallback_kept=9
    41.442  present #171                        <-- flash of the previous pair
    41.452  content_swap_active CLEARED on promotion
    41.468  present #173                        <-- correct again

The mechanism is the cascade-quiescence gate, not a missing upload: the new
pair's tiles were uploaded THIS frame (``last_uploaded_count > 0``), so
``resolve_frame_fallback`` refused to promote and the atomic content-swap hold
drew the *previous* pair's stashed content instead. The gate exists to hide a
one-frame stale-mip edge seam on the SAME content (level hold / hires flip) --
on a genuine content replacement it is exactly backwards: it trades a subtle
seam of the right picture for a whole frame of the WRONG picture.

Identity beats smoothness (owner requirement): a baseline whose content does
not belong to the current pair is never drawn. When the new pair is applied,
present it now (cascade gate or not); when it is not ready yet, show its own
partial tiles (or nothing for the changed side) -- never the previous pair.

Same-content tier transitions keep their old baseline: a preview QImage being
replaced by the tiled store of the SAME image (hires flip, ``stored_*`` <->
``source_*``) is one picture at two resolutions, so the smaller/older tier is
still this pair's content.
"""

from types import SimpleNamespace

from engine.cache.lod import LevelKey
from engine.cache.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.rhi_renderer import residency as residency_mod
from tabs.image_compare.canvas.rhi_renderer.draw_plan import build_array_draw_plan
from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer


def _base_image():
    return SimpleNamespace(
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
    )


def _register_full(tile_service, key, size):
    grid = tile_service.register_source(key, size)
    for row in range(grid.rows):
        for column in range(grid.columns):
            tile_service.mark_resident(
                key, (row, column), byte_size=1024, content_size=(512, 512)
            )


def _mark_budgeted(tile_service, key, indices):
    for index in indices:
        tile_service.mark_resident(
            key, index, byte_size=1024, content_size=(512, 512)
        )


def _layers(tile_service, key):
    return {
        tile_service.slot_for(key, index)[1]
        for index in tile_service.resident_tiles(key)
    }


def _binds_any_layer(tile_service, plan, keys):
    bound = set()
    for key in keys:
        bound |= _layers(tile_service, key)
    return any(
        item.layer1 in bound or item.layer2 in bound for item in plan
    ), bound


def _resolve(renderer, tile_service, texture_keys, base_image, *, current_plan,
             more_pending, source_changed, rekeyed, content_replaced=()):
    """Drive one frame the way ``render()`` does, including the realizer's
    per-frame content-identity verdict (``last_content_replaced_keys``)."""
    renderer.resources.residency.last_content_replaced_keys = set(content_replaced)
    new_last_good, plan = renderer._resolve_fallback_plan(
        tile_service=tile_service,
        texture_keys=texture_keys,
        diff_source_key=None,
        base_image=base_image,
        sampler_name="linear",
        viewport_zoom=None,
        viewport_offset=None,
        main_more_pending=more_pending,
        current_array_plan=current_plan,
        source_changed=source_changed,
        rekeyed=rekeyed,
        current_sources_is_same=False,
    )
    if new_last_good is not None:
        renderer._last_good_texture_keys, renderer._last_good_diff_key = (
            new_last_good
        )
    return new_last_good, plan


def _swapped_pair(tile_service, *, new_sizes, upload_this_frame=0,
                  fully_resident=True, uids=(9, 8)):
    """Model the swap frame exactly as residency leaves it.

    The outgoing pair is rekeyed to ``_content_stash`` markers (its content
    survives as the fallback baseline), the live slot keys are re-registered
    for the incoming pair, and the incoming tiles are (partially) uploaded.
    Returns ``(stash_keys, rekeyed_map)``.
    """
    stash_keys = (
        ("_content_stash", "stored_0", uids[0]),
        ("_content_stash", "stored_1", uids[1]),
    )
    tile_service.rekey_source("stored_0", stash_keys[0])
    tile_service.rekey_source("stored_1", stash_keys[1])
    for slot, size in zip(("stored_0", "stored_1"), new_sizes):
        grid = tile_service.register_source(slot, size)
        indices = [
            (row, column)
            for row in range(grid.rows)
            for column in range(grid.columns)
        ]
        if fully_resident:
            _mark_budgeted(tile_service, slot, indices)
        else:
            _mark_budgeted(tile_service, slot, indices[: upload_this_frame or 1])
    return stash_keys, {"stored_0": stash_keys[0], "stored_1": stash_keys[1]}


def test_swap_presents_the_new_pair_even_while_the_cascade_is_dirty():
    """Frame 41.429 of the live log: the new pair is fully applied, but this
    frame's uploads make ``cascade_pending`` true. The previous pair must not
    be drawn -- not for one frame either."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()

    # The pair before the swap, fully resident under the bare slot keys.
    _register_full(tile_service, "stored_0", (1200, 800))
    _register_full(tile_service, "stored_1", (900, 700))
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = None

    stash_keys, rekeyed = _swapped_pair(
        tile_service, new_sizes=((2000, 1000), (1600, 900))
    )
    # This frame uploaded the incoming pair's remaining tiles -> the cascade
    # gate refuses promotion (``test_cascade_quiescence_holds_fast_path_
    # promotion`` pins that for the SAME content).
    renderer.resources.residency.last_uploaded_count = 4

    texture_keys = ("stored_0", "stored_1")
    current_plan = build_array_draw_plan(
        tile_service, texture_keys, base_image, diff_key=None, sampler_name="linear"
    )
    assert current_plan, "the incoming pair is fully resident this frame"

    new_last_good, plan = _resolve(
        renderer,
        tile_service,
        texture_keys,
        base_image,
        current_plan=current_plan,
        more_pending=False,
        source_changed=True,
        rekeyed=rekeyed,
        content_replaced=("stored_0", "stored_1"),
    )

    binds_old, old_layers = _binds_any_layer(tile_service, plan, stash_keys)
    assert not binds_old, (
        "the draw plan still binds the previous pair's stashed content "
        f"(layers {sorted(old_layers)}) on the frame the new pair was applied"
    )
    assert new_last_good == (texture_keys, None), (
        "an applied pair must promote immediately, cascade gate or not; "
        f"got {new_last_good}"
    )
    assert plan == current_plan


def test_swap_never_logs_a_kept_previous_pair_baseline():
    """The [ic-preview] trail must not report ``fallback_kept=<n>`` (n > 0)
    for a pair whose content already changed -- that number IS the old-pair
    placeholder a present would draw."""
    from tabs.image_compare.canvas.rhi_renderer.use_cases import fallback as fb

    lines: list[str] = []
    original = fb._ic_preview_log

    def _capture(msg, *args, **kwargs):
        try:
            lines.append(msg % args if args else msg)
        except Exception:
            lines.append(msg)
        return original(msg, *args, **kwargs)

    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()
    _register_full(tile_service, "stored_0", (1200, 800))
    _register_full(tile_service, "stored_1", (900, 700))
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = None
    _stash_keys, rekeyed = _swapped_pair(
        tile_service, new_sizes=((2000, 1000), (1600, 900)), uids=(19, 18)
    )
    renderer.resources.residency.last_uploaded_count = 4

    texture_keys = ("stored_0", "stored_1")
    current_plan = build_array_draw_plan(
        tile_service, texture_keys, base_image, diff_key=None, sampler_name="linear"
    )
    fb._ic_preview_log = _capture
    try:
        _resolve(
            renderer,
            tile_service,
            texture_keys,
            base_image,
            current_plan=current_plan,
            more_pending=False,
            source_changed=True,
            rekeyed=rekeyed,
            content_replaced=("stored_0", "stored_1"),
        )
    finally:
        fb._ic_preview_log = original

    assert any("fallback decision:" in line for line in lines), (
        "the frame under test never reached the fallback decision log -- "
        f"nothing was observed: {lines}"
    )
    kept = [
        line
        for line in lines
        if "fallback_kept=" in line and _kept_count(line) not in (None, 0)
    ]
    assert not kept, f"old-pair baseline reported as kept for the new key: {kept}"


def _kept_count(line: str):
    try:
        raw = line.split("fallback_kept=", 1)[1].split()[0]
        return int(raw)
    except Exception:
        return None


def test_swap_partial_new_pair_shows_its_own_tiles_never_the_previous_picture():
    """The new pair is still streaming in (``more_pending``): the changed
    side may be partial or blank, but a previous/adjacent picture is not an
    option -- and both sides come from the new pair, never one new + one old."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()
    _register_full(tile_service, "stored_0", (1200, 800))
    _register_full(tile_service, "stored_1", (900, 700))
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = None

    stash_keys, rekeyed = _swapped_pair(
        tile_service, new_sizes=((2000, 1000), (1600, 900)),
        upload_this_frame=2, fully_resident=False,
    )
    texture_keys = ("stored_0", "stored_1")
    current_plan = build_array_draw_plan(
        tile_service, texture_keys, base_image, diff_key=None, sampler_name="linear"
    )

    _new_last_good, plan = _resolve(
        renderer,
        tile_service,
        texture_keys,
        base_image,
        current_plan=current_plan,
        more_pending=True,
        source_changed=True,
        rekeyed=rekeyed,
        content_replaced=("stored_0", "stored_1"),
    )

    binds_old, _old_layers = _binds_any_layer(tile_service, plan, stash_keys)
    assert not binds_old, (
        "mid-swap frame drew the previous pair's content instead of the "
        "incoming pair's own (partial) tiles"
    )


def test_hires_flip_still_holds_the_same_contents_previous_tier():
    """Same content, bigger resolution (``stored_* -> source_*``): the old
    tier is still THIS pair's picture, so holding it whole while the new tier
    streams in stays correct and must not be swept up by the rule above."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()

    _register_full(tile_service, "stored_0", (1200, 800))
    _register_full(tile_service, "stored_1", (900, 700))
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = None

    hires_keys = ("source_0", "source_1")
    for key in hires_keys:
        tile_service.register_source(key, (2400, 1600))
    _mark_budgeted(tile_service, hires_keys[0], [(0, 0)])
    _mark_budgeted(tile_service, hires_keys[1], [(0, 0)])
    current_plan = build_array_draw_plan(
        tile_service, hires_keys, base_image, diff_key=None, sampler_name="linear"
    )

    new_last_good, plan = _resolve(
        renderer,
        tile_service,
        hires_keys,
        base_image,
        current_plan=current_plan,
        more_pending=True,
        source_changed=False,
        rekeyed={},
        content_replaced=(),
    )

    binds_old, _old_layers = _binds_any_layer(
        tile_service, plan, ("stored_0", "stored_1")
    )
    assert binds_old, (
        "hires flip lost its same-content baseline hold -- the old (smaller) "
        "tier of the same picture is legitimate"
    )
    assert new_last_good == (("stored_0", "stored_1"), (None))


def test_foreign_verdict_clears_once_the_new_pair_promotes():
    """The verdict lasts for the transition, not forever: after promotion the
    very next level hold on the NEW content must work again."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()
    _register_full(tile_service, "stored_0", (1200, 800))
    _register_full(tile_service, "stored_1", (900, 700))
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = None
    _swapped_pair(tile_service, new_sizes=((2000, 1000), (1600, 900)))
    texture_keys = ("stored_0", "stored_1")
    current_plan = build_array_draw_plan(
        tile_service, texture_keys, base_image, diff_key=None, sampler_name="linear"
    )
    _resolve(
        renderer, tile_service, texture_keys, base_image,
        current_plan=current_plan, more_pending=False, source_changed=True,
        rekeyed={"stored_0": ("_content_stash", "stored_0", 9),
                 "stored_1": ("_content_stash", "stored_1", 8)},
        content_replaced=("stored_0", "stored_1"),
    )
    assert renderer._fallback_baseline_foreign is False, (
        "the foreign-baseline verdict survived promotion"
    )

    # Same content, coarser level: the level hold must still hold the
    # (now legitimate) baseline tier.
    coarse = (LevelKey("stored_0", 2), LevelKey("stored_1", 2))
    fine = (LevelKey("stored_0", 1), LevelKey("stored_1", 1))
    for key in coarse:
        _register_full(tile_service, key, (1000, 500))
    for key in fine:
        tile_service.register_source(key, (2000, 1000))
    _mark_budgeted(tile_service, fine[0], [(0, 0)])
    _mark_budgeted(tile_service, fine[1], [(0, 0)])
    renderer._last_good_texture_keys = coarse
    fine_plan = build_array_draw_plan(
        tile_service, fine, base_image, diff_key=None, sampler_name="linear"
    )
    _new_last_good, level_plan = _resolve(
        renderer, tile_service, fine, base_image,
        current_plan=fine_plan, more_pending=True, source_changed=False,
        rekeyed={}, content_replaced=(),
    )
    binds_coarse, _layers_coarse = _binds_any_layer(tile_service, level_plan, coarse)
    assert binds_coarse, "a level hold on the new content stopped holding its tier"


def test_preview_to_store_tier_upgrade_is_not_a_foreign_replacement():
    """The preview QImage -> tiled store flip is ONE picture at two
    resolutions (the same document side), so its preview baseline stays
    legitimate; a store -> store swap, or any preview -> preview swap, is a
    different picture and must be reported as a replacement. A crop-box
    change re-registers the same picture and is not a replacement either."""
    _upgrade = dict(prev_is_preview=True, is_tiled_store=True)
    _store_swap = dict(prev_is_preview=False, is_tiled_store=True)
    _preview_swap = dict(prev_is_preview=True, is_tiled_store=False)
    _lazy_swap = dict(prev_is_preview=False, is_tiled_store=False)

    assert not residency_mod.is_foreign_content_replacement(
        prev_uid=7, content_uid=11, **_upgrade
    ), "preview -> store of the same document side lost its baseline"
    assert residency_mod.is_foreign_content_replacement(
        prev_uid=9, content_uid=11, **_store_swap
    ), "a store -> store pair swap was not reported as a replacement"
    assert residency_mod.is_foreign_content_replacement(
        prev_uid=9, content_uid=11, **_preview_swap
    )
    assert residency_mod.is_foreign_content_replacement(
        prev_uid=9, content_uid=11, **_lazy_swap
    )
    # Crop box joining the identity: same picture, new rect.
    assert not residency_mod.is_foreign_content_replacement(
        prev_uid=9,
        content_uid=(9, (0, 0, 40, 30)),
        **_store_swap,
    )
    assert not residency_mod.is_foreign_content_replacement(
        prev_uid=(9, (0, 0, 40, 30)),
        content_uid=(9, (0, 0, 20, 20)),
        **_store_swap,
    )
    # Same object, resized in place (mutated source) / first registration.
    assert not residency_mod.is_foreign_content_replacement(
        prev_uid=9, content_uid=9, **_store_swap
    )
    assert not residency_mod.is_foreign_content_replacement(
        prev_uid=None, content_uid=11, **_store_swap
    )
