"""The loupe must not disappear while a pair swap/replacement lands.

Owner report (2026-10-27): "вот только сама лупа почему-то пропадает на пару
кадров во время смены изображений" -- the loupe's content vanished for 1-2
frames whenever the pair's images were swapped.

Mechanism (probed on the real residents, no GPU needed): the lens draws from
``source_*`` while those are resident; the replacement re-registers BOTH roles
(``stored_*`` included), so ``_lens_residency_hold`` holds (its
"hold_stored_until_resident" reason), the lens falls back to the stored role
whose grid was just reset, ``_source_slices`` resolves zero tiles,
``prepare`` has no records for the quad -- and the lens content is simply not
drawn.

The previous picture is not gone, though: the realizer rekeys a replaced
slot's resident tiles onto ``("_content_stash", <key>, <uid>)`` and reports it
in ``last_rekeyed_keys`` (the same map the canvas baseline reads). These tests
pin that the lens keeps drawing ITS OWN previous frame from exactly those
tiles -- frozen, never blank and never the neighbour slot's content:

* red-before: on the swap frame ``MagnifierPass.prepare`` produced zero mag
  items (the first test fails with "the loupe vanished on the swap frame" on
  the pre-fix pass, which had no last-good sample at all);
* identity: every tile the replayed frame samples is the stashed copy of THIS
  lens's own source key -- a left-side lens cannot reach ``source_1``'s content
  even when a stash for it exists, and a stash that lost its GPU slots fails
  closed to the pre-fix (undrawn) frame;
* no new sample: a lens that never drew stays undrawn (no invented content),
  and the frame that finally draws live again drops the stash map.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

from engine.cache.stash import ContentStash
from engine.cache.tile_texture_service import TileTextureService
from engine.frame.context import FrameContext
from tabs.image_compare.canvas.features.magnifier.render import magnifier_pass as mag_mod
from tabs.image_compare.canvas.features.magnifier.render import lens_hold

LEFT, RIGHT = "source_0", "source_1"
STORED_LEFT, STORED_RIGHT = "stored_0", "stored_1"
SOURCES = (LEFT, RIGHT)
STOREDS = (STORED_LEFT, STORED_RIGHT)

#: The lens capture window as a fraction of the full source image: exactly the
#: top-left tile of a 2x2 grid, so one quad draws one tile slice.
CAPTURE_UV = (0.0, 0.0, 0.5, 0.5)

OLD_UID = 11
NEW_UID = 21


@pytest.fixture(autouse=True)
def _loupe_debug_on(monkeypatch):
    """Hold-replay verdicts are FrameContext records, gated like every loupe."""
    from tabs.image_compare.canvas.loupe_trace import reset_loupe_trace_state

    monkeypatch.setenv("IMGSLI_IC_LOUPE_DEBUG", "1")
    reset_loupe_trace_state()
    yield
    reset_loupe_trace_state()


# ---------------------------------------------------------------------------
# Harness: the real decision chain, QRhi faked only where a live GPU object
# would be required (SRB construction, uniform buffer allocation).
# ---------------------------------------------------------------------------


class _Matrix:
    def data(self):
        return [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]


class _Rhi:
    def clipSpaceCorrMatrix(self):
        return _Matrix()

    def ubufAligned(self, size):
        return int(size) + (-int(size) % 256)


class _ResourceUpdates:
    def __init__(self):
        self.writes = []

    def updateDynamicBuffer(self, buffer, offset, data):  # noqa: ANN001 - QRhi shape
        self.writes.append((buffer, offset, data))


class _RecordingService:
    """Delegating tile service that remembers which tiles actually resolved.

    The identity contract is about *what the frame samples*, so the assertion
    reads the service's own answers instead of decoding packed uniform blocks.
    """

    def __init__(self, inner):
        self.inner = inner
        self.hits: list[tuple] = []

    def slot_for(self, source_id, index):
        slot = self.inner.slot_for(source_id, index)
        if slot is not None:
            self.hits.append((source_id, tuple(index)))
        return slot

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _resident_grid(service, key, size, content_size=(1024, 1024)):
    grid = service.register_source(key, size)
    for row in range(grid.rows):
        for column in range(grid.columns):
            service.mark_resident(
                key, (row, column), byte_size=100, content_size=content_size
            )
    return grid


def _pair_residents():
    """The pair fully resident: sources (hires) + stored tiers, both sides."""
    service = TileTextureService(max_tile_extent=1024)
    for key in SOURCES:
        _resident_grid(service, key, (2048, 2048))
    for key in STOREDS:
        _resident_grid(service, key, (512, 512), content_size=(512, 512))
    return service


def _apply_pair_swap(service, stash, *, old_uid=OLD_UID, new_uid=NEW_UID):
    """The realizer's own replacement path: note the new identity, rekey the
    previous content onto its stash key, register the new (blank) grid.

    Returns this transition's ``key -> stash key`` map, i.e. exactly what
    ``last_rekeyed_keys`` holds on the frame the replacement lands.
    """
    rekeyed: dict = {}
    for key, size in (
        (LEFT, (2048, 2048)),
        (RIGHT, (2048, 2048)),
        (STORED_LEFT, (512, 512)),
        (STORED_RIGHT, (512, 512)),
    ):
        stash.note_source(key, old_uid, is_preview=False)
        prev_uid, prev_is_preview, changed = stash.note_source(
            key, new_uid, is_preview=False
        )
        assert changed, f"{key}: identity change not detected"
        stash.rekey_or_restore(
            service,
            key,
            new_uid,
            size,
            prev_uid=prev_uid,
            prev_is_preview=prev_is_preview,
            rekeyed=rekeyed,
        )
    return rekeyed


def _overlay(*, source=0):
    return SimpleNamespace(
        gpu_active=True,
        gpu_diff_mode=0,
        gpu_interp_mode=1,
        gpu_channel_mode=0,
        gpu_diff_threshold=20.0 / 255.0,
        border_width=0.0,
        quads=[(0.0, 0.0, 100.0, 100.0, 50.0, 50.0, 40.0)],
        gpu_slots=[
            {"uv_rect": CAPTURE_UV, "uv_rect2": CAPTURE_UV, "source": source}
        ],
    )


def _ctx(overlay, *, sources_ready=True):
    return SimpleNamespace(
        width=800.0,
        height=600.0,
        zoom_level=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        feature_overlay=overlay,
        shader_letterbox_mode=sources_ready,
        source_images_ready=sources_ready,
        source_texture_ids=[LEFT, RIGHT],
        texture_ids=[STORED_LEFT, STORED_RIGHT],
        diff_source_ready=False,
        diff_source_texture_id=None,
    )


def _build_pass(tile_service):
    """A pass whose ``prepare`` runs for real; only the two steps that need a
    live QRhi object are replaced (SRB creation, uniform-buffer growth)."""
    pass_ = mag_mod.MagnifierPass()
    pass_.rhi = _Rhi()
    pass_.mag_uniform_buffer = object()  # capacity guard: never regrow
    pass_.mag_uniform_capacity = 1024
    pass_.placeholder_texture_array = object()
    pass_.border.rhi = pass_.rhi  # ensure_items(0) only asserts it exists
    pass_._build_mag_srb = lambda bg_array: None
    renderer = SimpleNamespace(
        tile_service=tile_service,
        resources=SimpleNamespace(
            array_resources=None,
            residency=SimpleNamespace(last_rekeyed_keys={}),
        ),
        frame_context=FrameContext(),
    )
    widget = SimpleNamespace(
        _rhi_renderer=renderer,
        runtime_state=SimpleNamespace(),
        width=lambda: 800,
        height=lambda: 600,
    )
    return pass_, widget, renderer


def _prepare(pass_, widget, renderer, overlay, *, sources_ready=True):
    frame_context = FrameContext()
    renderer.frame_context = frame_context
    updates = _ResourceUpdates()
    pass_.prepare(widget, _ctx(overlay, sources_ready=sources_ready), updates)
    return frame_context, updates


def _decisions(frame_context, pass_name):
    return [d for d in frame_context if d.pass_name == pass_name]


# ---------------------------------------------------------------------------
# (1) red-before: the swap frame still draws the lens, from its own stash
# ---------------------------------------------------------------------------


def test_the_loupe_keeps_its_own_last_sample_on_the_swap_frame():
    service = _RecordingService(_pair_residents())
    pass_, widget, renderer = _build_pass(service)
    overlay = _overlay()

    # Frame 1: the lens draws live from this side's own source tiles.
    _prepare(pass_, widget, renderer, overlay)
    assert pass_._mag_items, "precondition: the lens drew before the swap"
    assert {key for key, _ in service.hits} == {LEFT}

    # The replacement lands: every key the lens may look at is re-registered,
    # the previous content moves onto content-addressed stash keys.
    rekeyed = _apply_pair_swap(service.inner, ContentStash())
    renderer.resources.residency.last_rekeyed_keys = dict(rekeyed)
    service.hits.clear()

    # Frame 2 (the owner's 1-2 frames): no live tile is resident, yet the lens
    # must still be there -- frozen on ITS OWN previous sample.
    frame_context, _updates = _prepare(pass_, widget, renderer, overlay)
    assert pass_._mag_items, "the loupe vanished on the swap frame"

    replay = _decisions(frame_context, "loupe.mag_hold_replay")
    assert [d.verdict for d in replay] == ["ran"]

    # Identity: every tile that resolved belongs to this side's stashed copy.
    drawn_keys = {key for key, _ in service.hits}
    assert drawn_keys == {rekeyed[LEFT]}, (
        f"the frozen lens sampled something else: {drawn_keys!r}"
    )
    assert isinstance(rekeyed[LEFT], tuple) and rekeyed[LEFT][0] == "_content_stash"
    assert rekeyed[LEFT][1] == LEFT, "a left-side lens must never borrow the right slot"


def test_the_live_frame_after_the_swap_goes_back_to_live_tiles():
    service = _RecordingService(_pair_residents())
    pass_, widget, renderer = _build_pass(service)
    overlay = _overlay()
    _prepare(pass_, widget, renderer, overlay)
    rekeyed = _apply_pair_swap(service.inner, ContentStash())
    renderer.resources.residency.last_rekeyed_keys = dict(rekeyed)
    _prepare(pass_, widget, renderer, overlay)  # held frame (replay)

    # New content finishes uploading: the lens draws live again and forgets
    # the stash map, so a later unrelated gap cannot replay an old picture.
    for key in SOURCES:
        for row in range(2):
            for column in range(2):
                service.inner.mark_resident(
                    key, (row, column), byte_size=100, content_size=(1024, 1024)
                )
    for key in STOREDS:
        service.inner.mark_resident(
            key, (0, 0), byte_size=100, content_size=(512, 512)
        )
    renderer.resources.residency.last_rekeyed_keys = {}
    service.hits.clear()
    frame_context, _updates = _prepare(pass_, widget, renderer, overlay)

    assert pass_._mag_items, "the lens stopped drawing after the swap settled"
    assert _decisions(frame_context, "loupe.mag_hold_replay") == []
    assert {key for key, _ in service.hits} == {LEFT}
    assert pass_._lens_stash_keys == {}


# ---------------------------------------------------------------------------
# (2) identity at the helper seam: own stash only, reject anything unproven
# ---------------------------------------------------------------------------


def _entries_for_left_lens():
    tessellated = {"key": (LEFT, 0, 0), "layer": 3, "scale": (2.0, 2.0)}
    record = {
        "tc_x": (0.0, 1.0),
        "tc_y": (0.0, 1.0),
        "core_tc_x": (0.0, 1.0),
        "core_tc_y": (0.0, 1.0),
        "uv_rect1": CAPTURE_UV,
        "uv_rect2": CAPTURE_UV,
        "tex1": tessellated,
        "tex2": {"key": None, "layer": 0, "scale": (1.0, 1.0)},
        "texd": None,
    }
    refs = {tessellated["key"]: (LEFT, (0, 0))}
    return lens_hold.cache_quad_records([record], refs)


def _stash_of(service, key, uid):
    from engine.cache.stash import make_stash_key

    stash_key = make_stash_key(key, uid)
    assert service.grid_for(stash_key) is not None, "fixture: stash grid missing"
    return stash_key


def test_replay_never_reaches_the_neighbour_slot_even_when_it_has_a_stash():
    service = _pair_residents()
    stash = ContentStash()
    rekeyed = _apply_pair_swap(service, stash)
    entries = _entries_for_left_lens()

    replayed = lens_hold.replay_held_records(service, entries, rekeyed)

    assert len(replayed) == 1
    stash_key = rekeyed[LEFT]
    assert stash_key[0] == "_content_stash" and stash_key[1] == LEFT
    # Re-pointed at THIS side's stashed tile, layer and content scale taken
    # from the live service (never the frozen record's stale layer).
    assert replayed[0]["tex1"]["key"] == service.tile_key(stash_key, 0, 0)
    assert replayed[0]["tex1"]["layer"] == service.slot_for(stash_key, (0, 0))[1]
    # The right slot's copy exists and is resident -- and is still not used.
    assert service.slot_for(rekeyed[RIGHT], (0, 0)) is not None
    assert LEFT != RIGHT


def test_replay_fails_closed_without_a_stash_for_this_key():
    service = _pair_residents()
    stash = ContentStash()
    rekeyed = _apply_pair_swap(service, stash)
    entries = _entries_for_left_lens()

    # Only the OTHER side has a stash: borrowing it would be foreign content.
    assert lens_hold.replay_held_records(
        service, entries, {RIGHT: rekeyed[RIGHT]}
    ) == []
    # No replacement at all: the live key is not a frozen-sample source.
    assert lens_hold.replay_held_records(service, entries, {LEFT: LEFT}) == []
    assert lens_hold.replay_held_records(service, entries, {}) == []


def test_replay_fails_closed_when_the_stashed_tiles_were_evicted():
    service = _pair_residents()
    stash = ContentStash()
    rekeyed = _apply_pair_swap(service, stash)
    entries = _entries_for_left_lens()

    service.invalidate_source(_stash_of(service, LEFT, OLD_UID))

    assert lens_hold.replay_held_records(service, entries, rekeyed) == []


def test_a_record_sampling_an_unidentifiable_tile_is_never_replayed():
    """A placeholder/raster role (``key is None``) has no (key, tile) anchor,
    so its identity cannot be proven -- the quad keeps the old behaviour."""
    service = _pair_residents()
    rekeyed = _apply_pair_swap(service, ContentStash())
    record = {
        "tc_x": (0.0, 1.0),
        "tc_y": (0.0, 1.0),
        "core_tc_x": (0.0, 1.0),
        "core_tc_y": (0.0, 1.0),
        "uv_rect1": CAPTURE_UV,
        "uv_rect2": CAPTURE_UV,
        "tex1": {"key": None, "layer": 0, "scale": (1.0, 1.0)},
        "tex2": None,
        "texd": None,
    }
    entries = lens_hold.cache_quad_records([record], {})

    assert lens_hold.replay_held_records(service, entries, rekeyed) == []


# ---------------------------------------------------------------------------
# (3) no sample -> no lens (requirement 3), and no crash on a dead frame
# ---------------------------------------------------------------------------


def test_a_lens_that_never_drew_stays_undrawn_instead_of_inventing_content():
    service = TileTextureService(max_tile_extent=1024)
    for key in SOURCES:
        service.register_source(key, (2048, 2048))  # registered, nothing resident
    for key in STOREDS:
        service.register_source(key, (512, 512))
    pass_, widget, renderer = _build_pass(service)
    overlay = _overlay()

    frame_context, _updates = _prepare(pass_, widget, renderer, overlay)

    assert pass_._mag_items == []
    replay = _decisions(frame_context, "loupe.mag_hold_replay")
    assert [d.verdict for d in replay] == ["skipped"]
    assert "no provable last good sample" in replay[0].reason


def test_an_undrawn_quad_does_not_prune_the_other_quads_sample():
    """Two lenses (left + right side): a frame where only one of them can
    sample live must not throw the other one's sample away."""
    service = _pair_residents()
    pass_, widget, renderer = _build_pass(service)
    left = _overlay(source=0)
    both = SimpleNamespace(
        **{
            **vars(left),
            "quads": left.quads * 2,
            "gpu_slots": [
                {"uv_rect": CAPTURE_UV, "uv_rect2": CAPTURE_UV, "source": 0},
                {"uv_rect": CAPTURE_UV, "uv_rect2": CAPTURE_UV, "source": 1},
            ],
        }
    )
    _prepare(pass_, widget, renderer, both)
    assert len(pass_._lens_last_good) == 2

    # Only the second slot loses its residents (one side still draws live).
    service.invalidate_source(RIGHT)
    service.register_source(RIGHT, (2048, 2048))
    frame_context, _updates = _prepare(pass_, widget, renderer, both)

    assert set(pass_._lens_last_good) == {0, 1}, "a quad's sample was dropped"
    assert pass_._lens_stash_keys == {}
    assert pass_._mag_items, "the still-resident lens stopped drawing"
    # Both quads still resolve their sample: the second side's stored tier is
    # resident, so the held frame samples it live instead of freezing.
    assert [d.verdict for d in _decisions(frame_context, "loupe.mag_hold_replay")] == []
