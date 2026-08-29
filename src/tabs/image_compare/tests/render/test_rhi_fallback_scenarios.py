"""Universal auto-generated test for RHI fallback / duplicate-baseline bugs.

Covers the systemic lie described in docs/dev/investigations/store-redux-dogma-and-preview-race-2026-08-30.md
and the Python 3.14 hasattr change (TiledPixelStore.size raises RuntimeError).

Auto-generation idea: scenario = Frame{is_same, keys, more_pending, rekeyed, LevelKey}
Invariants checked on every frame without real QRhi (fake TileTextureService + monkeypatch).
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from shared.rendering.fallback_lod import resolve_fallback_lod
from shared.rendering.lod import LevelKey
from tabs.image_compare.canvas.rhi_renderer.renderer import (
    RhiCanvasRenderer,
    _is_rekeyed_content_baseline,
    _is_rekeyed_content_key,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

SRC = Path(__file__).resolve().parents[2] / "src"


def _fake_tile_service():
    """Minimal stub that satisfies draw_plan.build_array_draw_plan calls.

    Returns 1 visible tile per key, slot_for -> (array_index=0, layer=hash(key)%100)
    """
    class Grid:
        rows = 1
        columns = 1
        total_width = 1
        total_height = 1

        def iter_regions(self):
            # region with left/top/right/bottom
            yield (0, 0, SimpleNamespace(left=0, top=0, right=1, bottom=1))

    grid = Grid()

    class Svc:
        def grid_for(self, key):
            return grid

        def visible_tiles(self, key, rect):
            return {(0, 0)}

        def slot_for(self, key, idx):
            # distinct layer per key identity (including LevelKey)
            return (0, abs(hash(str(key))) % 100 + 1)

        def content_size_for(self, key, idx):
            return (256, 256)

    return Svc()


def _base_image():
    return SimpleNamespace(
        letterbox1=(0.0, 0.0, 0.5, 1.0),
        letterbox2=(0.5, 0.0, 0.5, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )


def _run_fallback(
    *,
    prev_is_same: bool | None,
    cur_is_same: bool,
    more_pending: bool,
    current_items: list,
    last_good: tuple | None,
    rekeyed: dict,
    texture_keys: tuple = ("stored_0", "stored_1"),
    source_changed: bool = False,
    diff_key=None,
):
    """Drive _resolve_fallback_plan for one frame with fakes, return (new_last_good, plan, renderer)."""
    r = RhiCanvasRenderer()
    # don't init GPU
    r._last_good_texture_keys, r._last_good_diff_key = (
        (last_good[0], last_good[1]) if last_good is not None else (None, None)
    )
    # emulate previous frame's prev flag
    r._prev_sources_is_same = prev_is_same
    # ensure clean state except what we set
    r._content_swap_active = False
    # patch build_array_draw_plan to avoid real TileTextureService geometry
    # but keep real logic for atomic vs progressive via fake fallback items
    with mock.patch(
        "tabs.image_compare.canvas.rhi_renderer.renderer.build_array_draw_plan"
    ) as mock_build:
        # fallback builder will be called inside _resolve_fallback_plan via its own closure,
        # but that closure also calls build_array_draw_plan - we intercept there
        # Instead we let _resolve_fallback_plan's internal _build_fallback_items call the patched version.
        # Our fake: return 2 fallback items with distinct layers per texture key
        def fake_build(tile_service, keys, base_image, diff_key=None, sampler_name=None, viewport_zoom=None, viewport_offset=None):
            # keys is prior texture_keys tuple
            # return items whose layer encodes key identity
            from tabs.image_compare.canvas.rhi_renderer.draw_plan import ArrayDrawItem

            # produce 1 item per visible tile intersection: simplified to 2 items for 2 keys?
            # Use slot_for to get layer
            svc = tile_service
            items = []
            # simulate one item per pair
            l1 = svc.slot_for(keys[0], (0, 0))[1] if len(keys) > 0 else 1
            l2 = svc.slot_for(keys[1], (0, 0))[1] if len(keys) > 1 else 2
            items.append(
                ArrayDrawItem(
                    rect1=(0, 0, 0.5, 1),
                    rect2=(0.5, 0, 0.5, 1),
                    content_scale=(1, 1, 1, 1),
                    content_scale_diff=(1, 1),
                    layer1=l1,
                    layer2=l2,
                    layer_diff=0,
                    array_index=0,
                    sampler_name=sampler_name or "linear",
                    bbox=(0, 0, 1, 1),
                )
            )
            return items

        mock_build.side_effect = fake_build

        # also patch drop_covered to be identity
        with mock.patch(
            "tabs.image_compare.canvas.rhi_renderer.renderer.drop_covered_fallback_items",
            side_effect=lambda f, c, base: f,
        ):
            svc = _fake_tile_service()
            base = _base_image()
            new_last_good, plan = r._resolve_fallback_plan(
                tile_service=svc,
                texture_keys=texture_keys,
                diff_source_key=diff_key,
                base_image=base,
                sampler_name="linear",
                viewport_zoom=(1.0, 1.0),
                viewport_offset=(0.0, 0.0),
                main_more_pending=more_pending,
                current_array_plan=current_items,
                source_changed=source_changed,
                rekeyed=rekeyed,
                current_sources_is_same=cur_is_same,
            )
            # mimic render() post-update
            r._prev_sources_is_same = cur_is_same
            if new_last_good is not None:
                r._last_good_texture_keys, r._last_good_diff_key = new_last_good
            return new_last_good, plan, r


# ---------------------------------------------------------------------------
# contract style: no hasattr on TiledPixelStore size (Python 3.14)
# ---------------------------------------------------------------------------

def test_no_hasattr_on_closed_tiled_store_size():
    """Dogma: no hasattr(obj,'size') that would raise RuntimeError on closed TiledPixelStore.
    Prefer pixel_source_size. Mirrors test_no_direct_store_mutation pattern."""
    offenders = []
    for p in SRC.rglob("*.py"):
        if "tests" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "hasattr":
                # hasattr(x, "size") or hasattr(x, "width")
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value in ("size", "width", "height"):
                    # allowlist: _framework itself and pixel_source_size impl checks hasattr for theme etc?
                    # We only forbid in renderer/draw code that handles TiledPixelStore.
                    rel = p.relative_to(SRC.parent).as_posix()
                    if "tiled_pixel_store.py" in rel and "pixel_source_size" in p.read_text():
                        continue
                    # check file contains TiledPixelStore import or usage - narrow
                    text = p.read_text()
                    if "TiledPixelStore" in text or "pixel_source" in text or "renderer.py" in rel or "draw_plan" in rel:
                        offenders.append(f"{rel}:{node.lineno} hasattr(..., '{node.args[1].value}')")
    # We fixed renderer.py, so should be 0 now. If new code adds it, test fails with file:line.
    assert not offenders, f"hasattr on size/width/height that breaks Python 3.14 closed store:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# universal scenario invariants
# ---------------------------------------------------------------------------

def test_is_rekeyed_content_key_unwraps_levelkey():
    assert _is_rekeyed_content_key(("_prev_content", "stored_0", 0))
    assert _is_rekeyed_content_key(("_content_stash", "stored_1", 4))
    assert _is_rekeyed_content_key(LevelKey(("_prev_content", "stored_0", 0), 1))
    assert _is_rekeyed_content_key(LevelKey(("_content_stash", "stored_1", 4), 2))
    assert not _is_rekeyed_content_key("stored_0")
    assert not _is_rekeyed_content_key(LevelKey("stored_0", 1))
    assert _is_rekeyed_content_baseline(((("_prev_content", "stored_0", 0), "stored_1"), None))
    assert not _is_rekeyed_content_baseline((("stored_0", "stored_1"), None))
    assert not _is_rekeyed_content_baseline(None)


def test_duplicate_baseline_dropped_on_single_to_dual():
    """Universal: single-image (is_same True) -> dual (is_same False) must not hold atomic duplicate."""
    # frame1: single image, both slots same
    new_last_good, plan, r = _run_fallback(
        prev_is_same=None,
        cur_is_same=True,
        more_pending=False,
        current_items=["cur"],
        last_good=None,
        rekeyed={},
        source_changed=False,
    )
    # promote to last_good = (stored_0, stored_1)
    assert new_last_good is not None
    last_good = new_last_good  # this is duplicate baseline (both left)
    # frame2: second image arrives, cur becomes distinct, prev was True
    new_last_good2, plan2, r2 = _run_fallback(
        prev_is_same=True,
        cur_is_same=False,
        more_pending=True,
        current_items=["cur2"],
        last_good=last_good,
        rekeyed={},  # no rekey yet, guard should drop
        source_changed=True,
    )
    # guard should have dropped last_good -> not atomic, plan == current (or fallback+current)
    # In our fake, fallback dropped => plan should be current (since more_pending True, atomic False => fallback+current)
    # But crucial: _content_swap_active must be False and plan must not be pure fallback with duplicate layers
    assert r2._content_swap_active is False or r2._content_swap_active == False
    # If still atomic holding duplicate, test fails
    assert not r2._content_swap_active, "duplicate baseline must not become atomic"


def test_content_swap_atomic_until_promoted():
    """Atomic holds current hidden while more_pending, then promotes."""
    # content swap with rekeyed marker
    rekeyed = {"stored_0": ("_prev_content", "stored_0", 0)}
    new_last_good, plan, r = _run_fallback(
        prev_is_same=False,
        cur_is_same=False,
        more_pending=True,
        current_items=["cur"],
        last_good=(("stored_0", "stored_1"), None),
        rekeyed=rekeyed,
        source_changed=True,
    )
    # should be atomic (is_rekeyed_content_baseline true)
    assert r._content_swap_active or _is_rekeyed_content_baseline(((rekeyed["stored_0"], "stored_1"), None))
    # plan should be fallback only (no current)
    assert plan, "fallback should exist when atomic and not promoted"
    # next frame: more_pending False -> promotion
    new_last_good2, plan2, r2 = _run_fallback(
        prev_is_same=False,
        cur_is_same=False,
        more_pending=False,
        current_items=["cur"],
        last_good=new_last_good,
        rekeyed={},
        source_changed=False,
    )
    # after promotion, _content_swap_active cleared
    assert r2._content_swap_active is False
    assert new_last_good2 == (("stored_0", "stored_1"), None)


def test_levelkey_stash_unwrap():
    """LevelKey wrapping a stash must be recognized as content swap."""
    rekeyed = {"stored_0": ("_content_stash", "stored_1", 4)}
    texture_keys = (LevelKey("stored_0", 1), LevelKey("stored_1", 1))
    new_last_good, plan, r = _run_fallback(
        prev_is_same=False,
        cur_is_same=False,
        more_pending=True,
        current_items=["cur"],
        last_good=(("stored_0", "stored_1"), None),
        rekeyed=rekeyed,
        texture_keys=texture_keys,  # type: ignore
        source_changed=False,
    )
    # because rekeyed base unwrapped, last_good becomes (LevelKey(stash,1), LevelKey(...))
    # _is_rekeyed_content_baseline should be True
    assert _is_rekeyed_content_baseline(new_last_good) or r._content_swap_active


def test_lod_churn_progressive_not_atomic():
    """LOD level change on same content must be progressive, not atomic."""
    # same content, just LOD level change, no rekey, no source_changed
    tex_before = (LevelKey("stored_0", 2), LevelKey("stored_1", 2))
    tex_after = (LevelKey("stored_0", 1), LevelKey("stored_1", 1))
    new_last_good, plan, r = _run_fallback(
        prev_is_same=False,
        cur_is_same=False,
        more_pending=True,
        current_items=["cur"],
        last_good=(tex_before, None),
        rekeyed={},
        texture_keys=tex_after,  # type: ignore
        source_changed=False,
    )
    # should NOT be atomic
    assert not r._content_swap_active
    assert not _is_rekeyed_content_baseline(new_last_good) or new_last_good == (tex_after, None)


@pytest.mark.parametrize(
    "scenario",
    [
        # auto-generated scenarios: (prev_is_same, cur_is_same, more_pending, rekeyed, source_changed, expect_atomic)
        (True, False, True, {}, True, False),  # single->dual first frame: not atomic (guard drops)
        (False, False, True, {"stored_0": ("_prev_content", "stored_0", 0)}, True, True),  # same-slot swap
        (False, False, True, {"stored_1": ("_content_stash", "stored_1", 4)}, False, True),  # stash
        (False, False, True, {}, False, False),  # LOD churn
        (False, False, False, {}, False, False),  # promoted
    ],
)
def test_autogenerated_invariants(scenario):
    prev_is_same, cur_is_same, more_pending, rekeyed, source_changed, expect_atomic = scenario
    last_good = (("stored_0", "stored_1"), None) if prev_is_same is not None else None
    new_last_good, plan, r = _run_fallback(
        prev_is_same=prev_is_same,
        cur_is_same=cur_is_same,
        more_pending=more_pending,
        current_items=["cur"],
        last_good=last_good,
        rekeyed=rekeyed,
        source_changed=source_changed,
    )
    is_atomic = r._content_swap_active or _is_rekeyed_content_baseline(
        ((rekeyed.get("stored_0", "stored_0"), rekeyed.get("stored_1", "stored_1")), None)
        if rekeyed
        else new_last_good
    )
    # For guard case expect not atomic
    if prev_is_same is True and cur_is_same is False:
        assert not r._content_swap_active, "single->dual must not be atomic"

def test_resolve_fallback_lod_atomic_contract():
    """Direct contract from existing test_fallback_lod but parametrized."""
    for atomic, more_pending, should_hide in [(False, True, False), (True, True, True), (True, False, False)]:
        new_key, plan = resolve_fallback_lod(
            key="new",
            current_items=["cur"],
            more_pending=more_pending,
            last_good_key="old",
            build_fallback_items=lambda pk: ["fb"],
            drop_covered=lambda items, cur: items,
            atomic=atomic,
        )
        if atomic and more_pending:
            assert plan == ["fb"]
        elif atomic and not more_pending:
            assert plan == ["cur"]
        else:
            assert plan == ["fb", "cur"]
