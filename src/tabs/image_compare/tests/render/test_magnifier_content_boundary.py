"""Magnifier content boundary, pinned by PIXELS (not by source substrings).

The magnifier's content path samples the shared tile texture array
(``ArrayResources.tile_arrays[0]``) through per-tile draw records: each record
carries the tile's array ``layer``, its ``content_scale`` and the
tile-local uv_rect the shader mixes against TexCoord. The question
this file answers is the one the feature is named after: *at a given lens
pixel, which tile's pixel is sampled?* — the tile under the cursor, the
neighbour across a seam (a bleed), padding (garbage), or nothing at all.

Until 2026-10-20 this file asserted shader/pass *source substrings*
(``"newTextureArray" in pass_source`` …), i.e. it restated the implementation
and could not fail on a wrong pixel. It now drives the real per-record
geometry (``_source_slices`` + ``build_tile_records``) over a fixture texture
array whose every tile carries a distinctive colour (plus a small within-tile
ramp) and whose unused layer padding is poison magenta, and reads the sampled
texel out of that fixture.

Two deliberate modelling choices, because a real GPU is unavailable in this
environment (``QT_QPA_PLATFORM=offscreen``; a Gles2/QRhi context segfaults, see
``LIVE-PROOF WANTED`` in DONE.md / docs/dev/SCREENSHOTS.md):

1. ``magInterpMode == 0`` (nearest): the only mode with an exact per-pixel
   answer — every filtering mode is a weighted kernel over several texels, so
   its "boundary pixel" is legitimately a blend, not one tile's colour. The
   sampling *geometry* (uv mix, content scale, content clamp) is identical
   across modes; only the kernel differs.
2. The sampler kernel (mix(uvRect.xy, uvRect.zw, tc) -> * scale -> clamp to
   round(layerPx * scale) -> texelFetch) is transcribed from ``mag.frag``.
   That transcription cannot itself be proven offscreen, which is why
   ``test_shader_clamps_sampling_taps_to_tile_content`` stays: it is the one
   source check the pixels cannot replace. Everything the model is
   *fed* (layer / uv_rect / content_scale / clip rects) comes from product
   code, so a geometry regression shows up as a wrong colour, not a wrong
   string.
"""

from __future__ import annotations

import math
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

from engine.cache.tile_texture_service import TileTextureService

from tabs.image_compare.canvas.features.magnifier.geometry.core import (
    clamp_capture_position,
)
from tabs.image_compare.canvas.features.magnifier.render.tile_capture import (
    build_tile_records,
)
from tabs.image_compare.canvas.features.magnifier.render.tile_residency_gate import (
    _source_slices,
)
from tabs.image_compare.canvas.rhi_renderer import (
    _apron_rect,
    _ARRAY_LAYER_PX,
    _TILE_APRON_PX,
)

SOURCE_A = "img1"
SOURCE_B = "img2"

_MAG_FRAG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "canvas"
    / "features"
    / "magnifier"
    / "shaders"
    / "qrhi"
    / "mag.frag"
)

# 2x2 tiles over 1024x1024, so any capture window can be made to straddle a
# tile seam without needing an unrealistic (huge) image.
TILE_PX = 512
IMAGE_SIZE = (1024, 1024)

#: Square lens used to turn a continuous ``tc`` into discrete "pixels"
#: (``tc = (px + 0.5) / LENS_PX``, the same centre-of-pixel convention
#: ``mag.vert``'s quad interpolation produces). 400 px keeps the seam
#: transition several pixels wide, so "inside tile A" vs "inside tile B" is
#: unambiguous rather than a one-pixel coin flip.
LENS_PX = 400

#: Per-tile fixture colours. Every tile of every source is a distinct RGB, so
#: any wrong layer / wrong record lands on an identifiable colour instead of a
#: plausible one. Sources A and B differ so a source-side switch is visible in
#: the sampled pixel. On top of the flat base each tile carries a small
#: position-dependent ramp (see ``_image_pixel_colour``) so that a *sub-tile*
#: uv regression — same tile, wrong pixels — is also visible as a wrong colour
#: rather than being hidden by a uniform tile.
TILE_COLOURS = {
    (SOURCE_A, (0, 0)): (205, 40, 40),
    (SOURCE_A, (0, 1)): (40, 205, 40),
    (SOURCE_A, (1, 0)): (40, 40, 205),
    (SOURCE_A, (1, 1)): (205, 205, 40),
    (SOURCE_B, (0, 0)): (120, 0, 60),
    (SOURCE_B, (0, 1)): (0, 120, 60),
    (SOURCE_B, (1, 0)): (60, 0, 120),
    (SOURCE_B, (1, 1)): (0, 60, 120),
}

#: Amplitude of the per-pixel ramp (+-6 per channel, 12 px period along x).
RAMP_AMPLITUDE = 6


#: Filler for a layer's unused padding (the upload writes tile content 1:1
#: into the top-left corner, see ``Engine TileArrayResourcesBase
#: .upload_tile_to_array``). Deliberately not a tile colour: if a sample ever
#: lands there, the shader's content clamp is gone or the content scale is
#: wrong, and the pixel test says so.
PADDING_POISON = (255, 0, 255)

#: What a lens pixel shows when no record covers it (nothing was drawn, so the
#: canvas background/placeholder shows through).
BACKGROUND = None


def _image_pixel_colour(grid, key, x: int, y: int):
    """The fixture image's colour at image pixel ``(x, y)``.

    Tile base colour plus a ramp local to the tile that owns the pixel, so the
    fixture behaves like a real image: neighbouring pixels differ slightly and
    a tile's apron band carries its *neighbour's* pixels.
    """
    row = min(grid.rows - 1, max(0, y // grid.tile_height))
    col = min(grid.columns - 1, max(0, x // grid.tile_width))
    region = grid.region_for(row, col)
    base = TILE_COLOURS[(key, (row, col))]
    ramp = (
        (x - region.left) * 7 + (y - region.top) * 13
    ) % (2 * RAMP_AMPLITUDE + 1) - RAMP_AMPLITUDE
    return tuple(min(255, max(0, channel + ramp)) for channel in base)


class _TileArrayFixture:
    """Per-texel RGBA8 stand-in for one texture array's layers.

    Real memory, real indexing: ``texel()`` is a byte read, so the assertions
    are about pixels and not about a colour lookup table keyed by tile id.
    """

    def __init__(self, layer_px: int) -> None:
        self.layer_px = layer_px
        self._layers: dict[int, bytearray] = {}

    def upload(self, layer: int, content_size: tuple[int, int], pixel_fn) -> None:
        buf = bytearray(bytes(PADDING_POISON) * (self.layer_px * self.layer_px))
        for y in range(content_size[1]):
            offset = y * self.layer_px * 3
            row = bytearray()
            for x in range(content_size[0]):
                row += bytes(pixel_fn(x, y))
            buf[offset : offset + len(row)] = row
        self._layers[layer] = buf

    def texel(self, layer: int, x: int, y: int):
        buf = self._layers[layer]
        offset = (y * self.layer_px + x) * 3
        return (buf[offset], buf[offset + 1], buf[offset + 2])


_FIXTURE_CACHE: dict = {}


def _build_service_and_fixture():
    """Resident 2x2 grids for both sources, uploaded into the fixture array.

    Built once per session and shared read-only: filling every layer texel
    through the image function costs ~4 s, and the tests only read it.

    Mirrors the upload path's own bookkeeping: each tile's *content* is its
    apron-inclusive crop (``_apron_rect``), which is what
    ``Engine TileArrayResourcesBase.upload_tile_to_array`` records as
    ``content_size`` and what the shader rescales by ``content_scale``.
    """
    if _FIXTURE_CACHE:
        return _FIXTURE_CACHE["built"]
    service = TileTextureService(max_tile_extent=TILE_PX)
    fixture = _TileArrayFixture(_ARRAY_LAYER_PX)
    grids = {}
    for key in (SOURCE_A, SOURCE_B):
        grid = service.register_source(key, IMAGE_SIZE)
        grids[key] = grid
        for row, col, region in grid.iter_regions():
            apron = _apron_rect(
                grid.total_width, grid.total_height, region, _TILE_APRON_PX
            )
            content_size = (apron[2] - apron[0], apron[3] - apron[1])
            service.mark_resident(key, (row, col), 0, content_size=content_size)
            array_index, layer = service.slot_for(key, (row, col))
            assert array_index == 0  # 8 fixture tiles fit in one array
            # The upload is the apron crop of the image, written 1:1 into the
            # layer's top-left corner (see upload_tile_to_array), so layer
            # texel (lx, ly) is image pixel (apron.left + lx, apron.top + ly).
            fixture.upload(
                layer,
                content_size,
                lambda lx, ly, key=key, apron=apron, grid=grid: (
                    _image_pixel_colour(grid, key, apron[0] + lx, apron[1] + ly)
                ),
            )
    _FIXTURE_CACHE["built"] = (service, fixture, grids)
    return service, fixture, grids


def _records(service, *, uv_rect, source_mode: int = 0):
    """Real per-record draw geometry for one lens, as the pass builds it."""
    renderer = SimpleNamespace(tile_service=service)
    return build_tile_records(
        source_slices_fn=lambda key, rect: _source_slices(renderer, key, rect),
        combined=False,
        source_mode=source_mode,
        diff_mode=0,
        uv_rect1=uv_rect,
        uv_rect2=uv_rect,
        tex_key_1=SOURCE_A,
        tex_key_2=SOURCE_B,
        diff_key="diff",
        internal_split=0.5,
        comb_horizontal=False,
    )


def _sample_pixel(records, fixture: _TileArrayFixture, tc, *, source_mode: int = 0):
    """The colour ``mag.frag`` (nearest mode) would put at lens point ``tc``."""
    hit = None
    for record in records:
        # The pass uploads the record's core_tc_* as the shader's clipRect:
        # the discard test is the apron-free core, so exactly one record owns
        # a seam pixel (later draws win if two tiny ranges touch, same as GL
        # raster order).
        if (
            record["core_tc_x"][0] <= tc[0] <= record["core_tc_x"][1]
            and record["core_tc_y"][0] <= tc[1] <= record["core_tc_y"][1]
        ):
            hit = record
    if hit is None:
        return BACKGROUND

    tex, uv_rect = (
        (hit["tex2"], hit["uv_rect2"])
        if source_mode == 1
        else (hit["tex1"], hit["uv_rect1"])
    )
    scale = tex["scale"]
    u = min(1.0, max(0.0, uv_rect[0] + (uv_rect[2] - uv_rect[0]) * tc[0])) * scale[0]
    v = min(1.0, max(0.0, uv_rect[1] + (uv_rect[3] - uv_rect[1]) * tc[1])) * scale[1]
    # ``ivec2(round(vec2(arraySize) * scale))`` -- the tile's real content
    # extent inside the padded layer (mag.frag's anti-bleed clamp bound).
    content_w = max(1, round(_ARRAY_LAYER_PX * scale[0]))
    content_h = max(1, round(_ARRAY_LAYER_PX * scale[1]))
    # Nearest = texelFetch at round(uv * arraySize - 0.5); GLSL round() is
    # half-away-from-zero and uv is >= 0 here, so that is floor(uv * size).
    x = math.floor(u * _ARRAY_LAYER_PX)
    y = math.floor(v * _ARRAY_LAYER_PX)
    x = min(content_w - 1, max(0, x))
    y = min(content_h - 1, max(0, y))
    return fixture.texel(tex["layer"], x, y)


def _cursor_px(grid, uv_rect, tc) -> tuple[float, float]:
    """Image pixel a lens point shows: ``uv_rect`` is a fraction of the image."""
    return (
        (uv_rect[0] + (uv_rect[2] - uv_rect[0]) * tc[0]) * grid.total_width,
        (uv_rect[1] + (uv_rect[3] - uv_rect[1]) * tc[1]) * grid.total_height,
    )


def _image_colour_at(grid, key, x: float, y: float):
    """The fixture image's own colour under image pixel ``(x, y)``."""
    xi = math.floor(x)
    yi = math.floor(y)
    if 0 <= xi < grid.total_width and 0 <= yi < grid.total_height:
        return _image_pixel_colour(grid, key, xi, yi)
    return BACKGROUND


def _colour_distance(a, b) -> int:
    """Largest per-channel difference (distinct fixtures: well above the ramp)."""
    return max(abs(x - y) for x, y in zip(a, b))


def _distance_to_inner_seams(grid, x: float, y: float) -> float:
    """How far ``(x, y)`` is from the nearest *interior* tile seam, in px."""
    best = float("inf")
    for row, col, region in grid.iter_regions():
        for seam in (region.left, region.right):
            if 0 < seam < grid.total_width:
                best = min(best, abs(x - seam))
        for seam in (region.top, region.bottom):
            if 0 < seam < grid.total_height:
                best = min(best, abs(y - seam))
    return best


def _assert_every_lens_pixel_samples_the_image_beneath_it(
    records, fixture, grid, uv_rect, *, key=SOURCE_A, source_mode=0, step=4
):
    """Full-lens sweep: each pixel shows the image pixel under it.

    A sample within 1 image px of a seam may legitimately show the
    neighbour: tiles are uploaded with a 1-px apron of real neighbour pixels
    (``_TILE_APRON_PX``) precisely so filtering at a seam has true data. Every
    sample further than that from a seam must be the exactly-expected colour —
    which is what makes a bleed (a pixel showing the tile next door) fail.
    """
    checked = 0
    for py in range(step // 2, LENS_PX, step):
        for px in range(step // 2, LENS_PX, step):
            tc = ((px + 0.5) / LENS_PX, (py + 0.5) / LENS_PX)
            got = _sample_pixel(records, fixture, tc, source_mode=source_mode)
            assert got is not BACKGROUND, f"lens pixel ({px},{py}) drew nothing"
            assert got != PADDING_POISON, (
                f"lens pixel ({px},{py}) sampled layer padding — content clamp "
                "or content scale regression"
            )
            x, y = _cursor_px(grid, uv_rect, tc)
            if _distance_to_inner_seams(grid, x, y) <= _TILE_APRON_PX:
                continue  # 1-px apron: either side is correct
            expected = _image_colour_at(grid, key, x, y)
            assert got == expected, (
                f"lens pixel ({px},{py}) tc={tc} shows {got}, image under it is "
                f"{expected} at ({x:.1f},{y:.1f}) — tile bleed / wrong record"
            )
            checked += 1
    assert checked > 0


# ---------------------------------------------------------------------------
# The pins
# ---------------------------------------------------------------------------


def test_centre_pixel_is_the_colour_under_the_cursor():
    """Lens centre == the image pixel the cursor points at (single tile)."""
    service, fixture, grids = _build_service_and_fixture()
    grid = grids[SOURCE_A]
    # Capture window entirely inside tile (1, 1): 0.62..0.72 of a 2x2 grid.
    uv_rect = (0.62, 0.62, 0.72, 0.72)
    records = _records(service, uv_rect=uv_rect)

    centre = (0.5, 0.5)
    cursor_x, cursor_y = _cursor_px(grid, uv_rect, centre)
    expected = _image_colour_at(grid, SOURCE_A, cursor_x, cursor_y)
    # Still the tile's own distinctive colour, within the ramp's amplitude.
    base = TILE_COLOURS[(SOURCE_A, (1, 1))]
    assert _colour_distance(expected, base) <= RAMP_AMPLITUDE
    assert expected != TILE_COLOURS[(SOURCE_A, (0, 0))]

    got = _sample_pixel(records, fixture, centre)
    assert got == expected

    _assert_every_lens_pixel_samples_the_image_beneath_it(
        records, fixture, grid, uv_rect
    )


def test_tile_boundary_pixel_does_not_take_the_neighbour_tile_colour():
    """A pixel just inside each side of a tile seam shows its own tile.

    The capture window straddles the vertical seam at x = 0.5 (row 0), so the
    lens is fed one draw record per tile. Two pixels 40 lens px either side of
    the seam are ~5 image px inside their own tile — well outside the 1-px
    apron — so each must be its own tile's colour, never the neighbour's.
    """
    service, fixture, grids = _build_service_and_fixture()
    grid = grids[SOURCE_A]
    uv_rect = (0.45, 0.20, 0.55, 0.30)  # straddles x=0.5, wholly inside row 0
    records = _records(service, uv_rect=uv_rect)
    assert {record["tex1"]["key"][1:] for record in records} == {(0, 0), (0, 1)}

    seam_tc = (0.5 - uv_rect[0]) / (uv_rect[2] - uv_rect[0])
    inside = 40.0 / LENS_PX
    left_tc = (seam_tc - inside, 0.5)
    right_tc = (seam_tc + inside, 0.5)
    left = _sample_pixel(records, fixture, left_tc)
    right = _sample_pixel(records, fixture, right_tc)

    left_expected = _image_colour_at(grid, SOURCE_A, *_cursor_px(grid, uv_rect, left_tc))
    right_expected = _image_colour_at(
        grid, SOURCE_A, *_cursor_px(grid, uv_rect, right_tc)
    )
    # Each side samples its own tile's pixels exactly...
    assert left == left_expected
    assert right == right_expected
    # ...which are still the tiles' distinctive colours...
    left_base = TILE_COLOURS[(SOURCE_A, (0, 0))]
    right_base = TILE_COLOURS[(SOURCE_A, (0, 1))]
    assert _colour_distance(left, left_base) <= RAMP_AMPLITUDE
    assert _colour_distance(right, right_base) <= RAMP_AMPLITUDE
    # ...and never the neighbour's (a bleed), in either direction.
    assert _colour_distance(left, right_base) > 2 * RAMP_AMPLITUDE
    assert _colour_distance(right, left_base) > 2 * RAMP_AMPLITUDE

    _assert_every_lens_pixel_samples_the_image_beneath_it(
        records, fixture, grid, uv_rect
    )


def test_capture_window_outside_the_image_samples_background_not_a_tile():
    """Out-of-domain capture draws nothing — never a clamped/wrapped tile.

    A capture window entirely past the right edge (cursor off the image) has
    no tiles to slice against, so ``_source_slices`` yields nothing and the
    pass skips the lens quad: the lens area keeps the background/placeholder
    rather than smearing the nearest tile's pixels across it.
    """
    service, fixture, grids = _build_service_and_fixture()
    grid = grids[SOURCE_A]
    uv_rect = (1.20, 0.50, 1.30, 0.60)

    renderer = SimpleNamespace(tile_service=service)
    assert _source_slices(renderer, SOURCE_A, uv_rect) == []
    records = _records(service, uv_rect=uv_rect)
    assert records == []

    sampled = [
        _sample_pixel(records, fixture, tc)
        for tc in ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0))
    ]
    assert sampled == [BACKGROUND, BACKGROUND, BACKGROUND]
    assert not (set(sampled) & set(TILE_COLOURS.values()))


def test_live_capture_clamp_keeps_a_cursor_outside_the_canvas_in_domain():
    """The shipped path cannot reach that background case by accident.

    ``build_magnifier_layout`` clamps the capture position so the whole window
    stays inside the image, so dragging past the canvas edge keeps sampling
    real (edge) image pixels. This is the complement of the test above: the
    background result needs an out-of-domain window, which only a stale
    capture can produce.
    """
    service, _, grids = _build_service_and_fixture()
    grid = grids[SOURCE_A]
    capture_size_relative = 0.2  # window is 0.1 of the image per axis

    # Cursor far outside the canvas (1.8, -0.4) — the live path clamps it.
    cap_x, cap_y = clamp_capture_position(
        1.8, -0.4, IMAGE_SIZE[0], IMAGE_SIZE[1], capture_size_relative
    )
    half = capture_size_relative / 2.0  # radius as a fraction of each axis
    uv_rect = (cap_x - half, cap_y - half, cap_x + half, cap_y + half)

    assert 0.0 <= uv_rect[0] and uv_rect[2] <= 1.0
    assert 0.0 <= uv_rect[1] and uv_rect[3] <= 1.0
    renderer = SimpleNamespace(tile_service=service)
    assert _source_slices(renderer, SOURCE_A, uv_rect)
    assert _image_colour_at(grid, SOURCE_A, *_cursor_px(grid, uv_rect, (0.5, 0.5)))


def test_source_side_switch_changes_the_sampled_colour():
    """Choosing the other side of the comparison samples the other image."""
    service, fixture, grids = _build_service_and_fixture()
    grid = grids[SOURCE_A]
    uv_rect = (0.62, 0.62, 0.72, 0.72)

    left_side = _sample_pixel(
        _records(service, uv_rect=uv_rect, source_mode=0), fixture, (0.5, 0.5)
    )
    right_side = _sample_pixel(
        _records(service, uv_rect=uv_rect, source_mode=1),
        fixture,
        (0.5, 0.5),
        source_mode=1,
    )

    cursor = _cursor_px(grids[SOURCE_A], uv_rect, (0.5, 0.5))
    assert left_side == _image_colour_at(grids[SOURCE_A], SOURCE_A, *cursor)
    assert right_side == _image_colour_at(grids[SOURCE_B], SOURCE_B, *cursor)
    assert left_side != right_side
    _assert_every_lens_pixel_samples_the_image_beneath_it(
        _records(service, uv_rect=uv_rect, source_mode=1),
        fixture,
        grid,
        uv_rect,
        key=SOURCE_B,
        source_mode=1,
    )


def test_shader_clamps_sampling_taps_to_tile_content():
    """The one source pin the pixels cannot replace: the content clamp.

    Every sampler in ``mag.frag`` clamps its kernel taps to the tile's own
    content extent (``contentSize - 1``), not to the padded array layer. The
    1-px band past ``content_scale`` is *not* this tile's data (it is the
    upload's apron/padding, or leftover from a previous tile), and the default
    "linear" mode samples several neighbours per texel — without this clamp a
    seam pixel reads whatever lives there. Offscreen Qt has no GPU (a Gles2
    context segfaults under the offscreen QPA), so no pixel test can observe a
    missing clamp; the fixture above pins everything else.
    """
    shader = _MAG_FRAG_PATH.read_text()
    clamp_bound = re.findall(r"clamp\([^;]*contentSize[^;]*- ivec2\(1\)", shader)
    assert len(clamp_bound) >= 5, (
        "mag.frag samplers must clamp every tap to contentSize - 1 "
        f"(found {len(clamp_bound)} clamps)"
    )
    assert "texSize - ivec2(1)" not in shader  # never clamp to the padded layer
