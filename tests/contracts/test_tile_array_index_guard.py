"""Tile-array guard: a pair-plan instance is never emitted out of texture
array >= 1, and a diff role with no resident slot in the pair's own array
never falls back to sampling layer 0 as a "blank" diff.

Why (docs/dev/rendering/tile-rendering-system.md, tile-array-atlas-plan.md):
``array_resources.ensure_array_srb`` binds only ``tile_arrays[0]`` while
``TileTextureService.slot_for`` can return ``(array_index >= 1, layer)`` once
the array-0 layer budget (867 layers in Image Compare, sized so one bound
array holds the worst-case visible set) is exceeded. The fragment shader addresses a layer inside the *bound*
array, so an item carrying ``array_index >= 1`` is uploaded into
``tile_arrays[1]`` but drawn from ``tile_arrays[0]`` at the same layer index --
another tile's content. Multi Compare drops such items itself
(``multi_compare/scene/passes/base_images.py`` ``array_index != 0`` guard); the
engine pair builder shared by both tabs must enforce the same rule.

Second half (plan P1.3): ``diffMode == 4`` (the SSIM clamp-sampling path)
samples ``vLayers.z`` whenever ``diffSourceReady`` is set. Emitting a pair with
``layer_diff = 0`` / ``content_scale_diff = (1, 1)`` therefore does NOT mean
"no diff" -- layer 0 of the bound array is another tile, not blank. Such a
pair must not be emitted for that frame: fail CLOSED (a one-frame gap is
allowed; a neighbour's content is not).

Observability: one ``log_tile_event`` line per plan build under
``IMGSLI_TILE_DUMP`` carrying the dropped counts by reason and the maximum
array index seen.
"""

from __future__ import annotations

from types import SimpleNamespace

from engine.cache import draw_plans as plans
from engine.cache.draw_plans import PlanTile, build_compare_pair_plan

_IDENTITY = (0.0, 0.0, 1.0, 1.0)
_FULL_TILE = PlanTile(rect=_IDENTITY, index=(0, 0))


class _Grid:
    """Minimal ``UniformTileGrid`` stand-in: the shape fields the plan builder
    branches on plus ``iter_regions`` for ``best_overlap_tile_index``."""

    def __init__(self, rows: int, columns: int, total: float = 1024.0) -> None:
        self.rows = rows
        self.columns = columns
        self.total_width = total
        self.total_height = total

    def iter_regions(self):
        width = self.total_width / self.columns
        height = self.total_height / self.rows
        for row in range(self.rows):
            for col in range(self.columns):
                yield (
                    row,
                    col,
                    SimpleNamespace(
                        left=col * width,
                        top=row * height,
                        right=(col + 1) * width,
                        bottom=(row + 1) * height,
                    ),
                )


class _TileService:
    """Stub ``TileTextureService`` with explicit slot/grid/content maps.

    ``slots`` maps ``(key, (row, col))`` to ``(array_index, layer)`` or is
    absent for "not resident yet" -- the same shape the real service returns.
    """

    def __init__(self, slots=None, grids=None, content_sizes=None) -> None:
        self.slots = dict(slots or {})
        self.grids = dict(grids or {})
        self.content_sizes = dict(content_sizes or {})

    def slot_for(self, key, index):
        return self.slots.get((key, tuple(index)))

    def grid_for(self, key):
        return self.grids.get(key)

    def content_size_for(self, key, index):
        return self.content_sizes.get((key, tuple(index)), (1024, 1024))


def _build(
    service: _TileService,
    *,
    side1=None,
    side2=None,
    diff_key: str | None = None,
    diff_tiles=(),
):
    return build_compare_pair_plan(
        service,
        "img1",
        "img2",
        _IDENTITY,
        _IDENTITY,
        side1=side1 if side1 is not None else [_FULL_TILE],
        side2=side2 if side2 is not None else [_FULL_TILE],
        diff_key=diff_key,
        diff_tiles=diff_tiles,
        layer_px=1024.0,
    )


def test_pair_in_array_one_is_never_emitted():
    """Both sides legitimately overlap, but their slots live in array 1 --
    the SRB only binds tile_arrays[0], so this pair would sample a different
    tile. Nothing may be emitted (mirrors MC's per-item array_index guard)."""
    service = _TileService(
        slots={("img1", (0, 0)): (1, 5), ("img2", (0, 0)): (1, 6)}
    )
    assert _build(service) == []


def test_multi_tile_diff_with_no_resident_tile_drops_the_pair():
    """Multi-tile diff grid, but the covering diff tile has no slot yet: the
    old code emitted the pair with layer_diff=0 (array layer 0 = another
    tile). The pair must be absent instead."""
    service = _TileService(
        slots={("img1", (0, 0)): (0, 1), ("img2", (0, 0)): (0, 2)},
        grids={"diff": _Grid(2, 2)},
    )
    items = _build(
        service,
        diff_key="diff",
        diff_tiles=[PlanTile(rect=(0.0, 0.0, 0.5, 0.5), index=(0, 0))],
    )
    assert items == []


def test_single_tile_diff_without_a_slot_drops_the_pair():
    """Single-tile path: ``slot_for`` answers None for the diff role (not
    resident yet), so there is no layer to sample -- the pair must be absent,
    not emitted with the layer-0 fallback."""
    service = _TileService(
        slots={("img1", (0, 0)): (0, 1), ("img2", (0, 0)): (0, 2)}
    )
    assert _build(service, diff_key="diff") == []


def test_dump_line_reports_reasons_and_max_array_index(monkeypatch):
    """One dump event per plan build, with the dropped-item counts split by
    reason and the maximum array index seen."""
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(plans, "tile_dump_enabled", lambda: True)
    monkeypatch.setattr(
        plans,
        "log_tile_event",
        lambda kind, **fields: events.append((kind, fields)),
    )
    service = _TileService(
        slots={
            ("img1", (0, 0)): (1, 7),  # dropped: array >= 1
            ("img1", (1, 0)): (0, 3),  # array 0, but diff role is missing
            ("img2", (0, 0)): (0, 4),
        }
    )
    side1 = [
        PlanTile(rect=_IDENTITY, index=(0, 0)),
        PlanTile(rect=_IDENTITY, index=(1, 0)),
    ]
    assert _build(service, side1=side1, diff_key="diff") == []
    assert len(events) == 1, f"expected exactly one dump line, got {events}"
    _kind, fields = events[0]
    assert fields["dropped_array_index"] == 1
    assert fields["dropped_diff_missing"] == 1
    assert fields["max_array_index"] == 1


def test_no_dump_line_when_tile_dump_is_off(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(plans, "tile_dump_enabled", lambda: False)
    monkeypatch.setattr(
        plans, "log_tile_event", lambda kind, **fields: events.append(kind)
    )
    service = _TileService(
        slots={("img1", (0, 0)): (1, 0), ("img2", (0, 0)): (1, 1)}
    )
    assert _build(service) == []
    assert events == []


def test_resident_pair_with_resident_diff_is_unchanged():
    """No behaviour change in the normal case: array 0 everywhere, every diff
    role resident -- identical single item with the resolved fields."""
    service = _TileService(
        slots={
            ("img1", (0, 0)): (0, 3),
            ("img2", (0, 0)): (0, 4),
            ("diff", (0, 0)): (0, 5),
        }
    )
    items = _build(service, diff_key="diff")
    assert len(items) == 1
    item = items[0]
    assert item.array_index == 0
    assert (item.layer1, item.layer2, item.layer_diff) == (3, 4, 5)
    assert item.content_scale_diff == (1.0, 1.0)
    assert item.bbox == (0.0, 0.0, 1.0, 1.0)


def test_resident_multi_tile_diff_is_unchanged():
    """Normal multi-tile case: the resident diff tile still splits the pair
    into one instance carrying that tile's own rect/layer."""
    service = _TileService(
        slots={
            ("img1", (0, 0)): (0, 3),
            ("img2", (0, 0)): (0, 4),
            ("diff", (0, 0)): (0, 5),
        },
        grids={"diff": _Grid(2, 2)},
    )
    diff_tile = PlanTile(rect=(0.0, 0.0, 0.5, 0.5), index=(0, 0))
    items = _build(service, diff_key="diff", diff_tiles=[diff_tile])
    assert len(items) == 1
    item = items[0]
    assert item.array_index == 0
    assert item.layer_diff == 5
    assert item.rect_diff == diff_tile.rect
    # Micro-gap expand (BBOX_EPS = 0.003) grows the 0.5-clipped bbox.
    assert item.bbox == (0.0, 0.0, 0.506, 0.506)
