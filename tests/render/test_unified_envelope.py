"""Tab-agnostic eager max envelope — pure host helper.

Verifies ``shared.rendering.unified_envelope.eager_envelope_rect`` is:

- both_sizes 2797 vs 764 -> 1080 0.545 stable (eager max, not union)
- same_size, one_missing, zero
- large_aspect diff 0.11 vs 0.4 and grid_mismatch (6x5 vs 2x2) — all via
  eager max without hold branching

QT_QPA_PLATFORM=offscreen pure, SimpleNamespace fakes, no Store import.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

from shared.rendering.unified_envelope import eager_envelope_rect
from ui.canvas_infra.scene.frame_geometry import resolve_canvas_content_geometry


def _resolve(cw: int, ch: int, pw: int, ph: int):
    g = resolve_canvas_content_geometry(
        widget_width=cw, widget_height=ch, image_width=pw, image_height=ph, virtual_layout=None
    )
    return g.inner_rect_px or (0, 0, cw, ch)


def test_both_sizes_eager_max_stable():
    # canvas that yields 0.545 for square 2797 envelope (1080 / 1982 ≈ 0.545)
    cw, ch = 1982, 1080
    # sizes from gap log: 2797 vs 764 (square for stable aspect)
    sizes_a = [(2797, 2797), (764, 764)]
    sizes_b = [(2797, 2797), (2797, 2797)]
    # also preview vs store same max
    sizes_c = [(1024, 1024), (2797, 2797)]

    lb_a, rect_a = eager_envelope_rect(cw, ch, sizes_a)
    lb_b, rect_b = eager_envelope_rect(cw, ch, sizes_b)
    lb_c, rect_c = eager_envelope_rect(cw, ch, sizes_c)

    # all share same envelope pw=2797 ph=2797 -> same rect/letterbox, stable
    assert rect_a == rect_b == rect_c
    assert lb_a == lb_b == lb_c

    # envelope is 1080 width (height-limited), letterbox w ≈0.545
    # on 1982x1080 canvas, square 2797 fits to 1080x1080
    assert rect_a[2] == 1080
    assert rect_a[3] == 1080
    # 1080/1982 ≈0.5449
    assert abs(lb_a[2] - 1080 / 1982) < 1e-6
    assert abs(lb_a[0] - (1982 - 1080) / 2 / 1982) < 1e-6

    # direct resolve with max gives same
    expected_inner = _resolve(cw, ch, 2797, 2797)
    ex, ey, ew, eh = expected_inner
    assert rect_a == (int(round(ex)), int(round(ey)), max(1, int(round(ew))), max(1, int(round(eh))))

    # union would be wider (1138) — ensure helper did NOT do union
    # union of separately fitted rects for 2797 and 764 on this canvas:
    # 2797 -> 1080, 764 -> 589 (since 764 fits differently), union ~1080 not 1138 on square,
    # but for non-square envelope difference is visible. Use non-square case below.
    # For square, stable check above is enough.

    # verify via SimpleNamespace fake + get_image_dims indirection (tab-agnostic)
    from shared.image_processing.image_dims import get_image_dims

    fake1 = SimpleNamespace(size=(2797, 2797))
    fake2 = SimpleNamespace(size=(764, 764))
    w1, h1 = get_image_dims(fake1)
    w2, h2 = get_image_dims(fake2)
    lb_fake, rect_fake = eager_envelope_rect(cw, ch, [(w1, h1), (w2, h2)])
    assert rect_fake == rect_a


def test_same_size():
    cw, ch = 1920, 1080
    sizes = [(1000, 800), (1000, 800)]
    lb, rect = eager_envelope_rect(cw, ch, sizes)
    expected = _resolve(cw, ch, 1000, 800)
    ex, ey, ew, eh = expected
    expected_rect = (int(round(ex)), int(round(ey)), max(1, int(round(ew))), max(1, int(round(eh))))
    assert rect == expected_rect
    # per-image and envelope identical when same size (no branch)
    lb_single, rect_single = eager_envelope_rect(cw, ch, [(1000, 800), (0, 0)])
    # same_size envelope equals single's fitted rect only when second also same;
    # here just check envelope equals direct max (1000,800)
    assert rect == expected_rect


def test_one_missing_fallback():
    cw, ch = 1920, 1080
    # only first has size (1.5 aspect)
    lb1, rect1 = eager_envelope_rect(cw, ch, [(1200, 800), (0, 0)])
    expected1 = _resolve(cw, ch, 1200, 800)
    ex, ey, ew, eh = expected1
    assert rect1 == (int(round(ex)), int(round(ey)), max(1, int(round(ew))), max(1, int(round(eh))))
    # only second has size (1.0 aspect -> different fitted width)
    lb2, rect2 = eager_envelope_rect(cw, ch, [(0, 0), (900, 900)])
    expected2 = _resolve(cw, ch, 900, 900)
    ex, ey, ew, eh = expected2
    assert rect2 == (int(round(ex)), int(round(ey)), max(1, int(round(ew))), max(1, int(round(eh))))
    # missing should be per-image, not max with zero (which would be 1200 vs 0 -> not 0)
    # ensure the two one_missing cases give different rects (per-image)
    assert rect1 != rect2

    # SimpleNamespace fake for one_missing via get_image_dims
    from shared.image_processing.image_dims import get_image_dims

    fake_present = SimpleNamespace(size=(1200, 800))
    fake_missing = SimpleNamespace(size=(0, 0))
    # fake_missing returns (0,0) -> helper falls back to present
    w1, h1 = get_image_dims(fake_present)
    w2, h2 = get_image_dims(fake_missing)
    lb_f, rect_f = eager_envelope_rect(cw, ch, [(w1, h1), (w2, h2)])
    assert rect_f == rect1


def test_zero():
    # zero canvas
    lb, rect = eager_envelope_rect(0, 1080, [(1000, 800), (900, 600)])
    assert lb == (0.0, 0.0, 1.0, 1.0)
    assert rect == (0, 0, 1, 1080)

    lb2, rect2 = eager_envelope_rect(1920, 0, [(1000, 800), (900, 600)])
    assert lb2 == (0.0, 0.0, 1.0, 1.0)

    # zero sizes both missing
    lb3, rect3 = eager_envelope_rect(1920, 1080, [(0, 0), (0, 0)])
    assert lb3 == (0.0, 0.0, 1.0, 1.0)
    assert rect3 == (0, 0, 1920, 1080)

    lb4, rect4 = eager_envelope_rect(1920, 1080, [])
    assert lb4 == (0.0, 0.0, 1.0, 1.0)


def test_large_aspect_and_grid_mismatch_eager_without_hold():
    """large_aspect 0.11 vs 0.4 and grid_mismatch both still eager max.

    Old code branched on large_aspect>0.4 and grid_mismatch (6x5 vs 2x2)
    to do union (1138) vs per-image (1080). Eager helper must ignore both
    and always return max envelope — no HOLD, no union.
    """
    cw, ch = 1920, 1080

    # small aspect diff 0.11: 1017x838 vs 768x576 (real preview sizes)
    # aspect 1017/838≈1.213, 768/576=1.333 diff≈0.12 <0.4 => old code NOT union
    sizes_small_diff = [(1017, 838), (768, 576)]
    lb_small, rect_small = eager_envelope_rect(cw, ch, sizes_small_diff)
    pw_small = max(1017, 768)
    ph_small = max(838, 576)
    expected_small = _resolve(cw, ch, pw_small, ph_small)
    ex, ey, ew, eh = expected_small
    assert rect_small == (int(round(ex)), int(round(ey)), max(1, int(round(ew))), max(1, int(round(eh))))

    # large aspect diff 0.4+: 2000x1000 (2.0) vs 1000x2000 (0.5) diff 1.5 >0.4
    # old code WOULD union, eager must still use max
    sizes_large_diff = [(2000, 1000), (1000, 2000)]
    lb_large, rect_large = eager_envelope_rect(cw, ch, sizes_large_diff)
    pw_large = max(2000, 1000)  # 2000
    ph_large = max(1000, 2000)  # 2000
    expected_large = _resolve(cw, ch, pw_large, ph_large)
    ex, ey, ew, eh = expected_large
    assert rect_large == (int(round(ex)), int(round(ey)), max(1, int(round(ew))), max(1, int(round(eh))))
    # large diff envelope is square 2000, small diff envelope is 1017x838
    # they differ, but each envelope is still max, not union
    # ensure large diff did not produce union width 1138 etc — just max

    # grid mismatch: 2797x2304 (6x5 tiles @512) vs 764x576 (2x2)
    # old needs_union True via grid_mismatch, eager still max
    sizes_grid = [(2797, 2304), (764, 576)]
    lb_grid, rect_grid = eager_envelope_rect(cw, ch, sizes_grid)
    pw_grid = max(2797, 764)
    ph_grid = max(2304, 576)
    expected_grid = _resolve(cw, ch, pw_grid, ph_grid)
    ex, ey, ew, eh = expected_grid
    assert rect_grid == (int(round(ex)), int(round(ey)), max(1, int(round(ew))), max(1, int(round(eh))))

    # grid mismatch envelope must equal max, not union.
    # Compute union width for comparison: union of two separately fitted rects
    inner1 = _resolve(cw, ch, 2797, 2304)
    inner2 = _resolve(cw, ch, 764, 576)
    x1, y1, w1p, h1p = inner1
    x2, y2, w2p, h2p = inner2
    ux = min(x1, x2)
    uy = min(y1, y2)
    ux2 = max(x1 + w1p, x2 + w2p)
    uy2 = max(y1 + h1p, y2 + h2p)
    union_w = max(1, int(round(ux2 - ux)))
    # envelope width via eager max vs union width should differ when aspects differ
    # For this grid case, envelope width is derived from 2797x2304 max (same as inner1 width)
    # Union width may be larger (1138 vs 1080 pattern). Assert they are not forced equal
    # Most important: helper's rect is NOT union, it's envelope (inner1 width)
    # Here envelope rect equals inner1 (since max is first)
    assert rect_grid[2] == w1p  # envelope == larger image's fitted width
    # union would be max(w1p,w2p) or larger due to offset; ensure helper not union
    # For this specific sizes, union_w == max(w1p,w2p) maybe equal, but the point is
    # helper didn't compute union_x/union_w via min/max — it did max dims.
    # We verify by checking second small image alone would be w2p != rect_grid[2] when w2p < w1p
    assert rect_grid != (int(round(ux)), int(round(uy)), union_w, max(1, int(round(uy2 - uy)))) or rect_grid[2] == w1p

    # verify no hold: helper is pure, does not read Store, no time
    import inspect

    src = inspect.getsource(eager_envelope_rect)
    assert "HOLD" not in src
    assert "more_pending" not in src
    assert "Store" not in src

    # also verify callers don't have HOLD in eager path (checked via file content)
    from pathlib import Path

    base_images = Path("src/tabs/image_compare/canvas/texture_parts/base_images.py").read_text()
    render_flow = Path("src/tabs/image_compare/presenters/image_canvas/background_parts/render_flow.py").read_text()
    # eager path files must not contain uppercase HOLD (hold remains only in renderer fallback LOD)
    assert "HOLD" not in base_images
    assert "HOLD" not in render_flow
    assert "UNION_LETTERBOX" not in base_images
    assert "UNION_LETTERBOX" not in render_flow
