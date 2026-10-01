"""D1 parity tests: shared ``demand_level`` / ``dest_scale_fit``.

The engine owns the four LOD call sites' policy now (QL ``_ql_needed_level``,
IC ``needed_level_for_view`` + ``resolve_lod_texture_keys``, MC
``lod_key_and_source``). These tests pin both the trivial wrapper identity
and the fit formula against an independent re-statement of the old math, so a
sign flip (min vs max) or a log2 change fails loudly.
"""

import math

from engine.cache.lod import demand_level, dest_scale_fit, select_level

# (fb_size, source_size), covering wide/tall limiting axes.
_FIT_CASES = [
    ((800, 600), (100, 50)),
    ((800, 600), (5000, 3000)),
    ((1920, 1080), (100, 50)),
    ((1920, 1080), (5000, 3000)),
    ((600, 800), (3000, 5000)),
]

_ZOOMS = [1.0, 0.5, 0.25, 4.0]

_LEVEL_COUNTS = [1, 2, 3, 5]


def _old_select_level(dest_scale: float, level_count: int) -> int:
    """Independent restatement of the pre-D1 ``select_level`` body."""
    if level_count <= 1:
        return 0
    if dest_scale >= 1.0:
        return 0
    if dest_scale <= 0.0 or not math.isfinite(dest_scale):
        return level_count - 1
    level = int(math.floor(math.log2(1.0 / dest_scale)))
    return max(0, min(level, level_count - 1))


def _old_fit(fb_size, source_size, zoom) -> float:
    """Independent restatement of the old QL/IC min() fit formula."""
    fb_w, fb_h = fb_size
    src_w, src_h = source_size
    return min(fb_w / src_w, fb_h / src_h) * zoom


def _max_fit(fb_size, source_size, zoom) -> float:
    """The wrong-axis twin: equal to _old_fit only when min == max."""
    fb_w, fb_h = fb_size
    src_w, src_h = source_size
    return max(fb_w / src_w, fb_h / src_h) * zoom


def test_demand_level_is_select_level_parity_table():
    for fb, src in _FIT_CASES:
        for zoom in _ZOOMS:
            scale = _old_fit(fb, src, zoom)
            for n in _LEVEL_COUNTS:
                assert demand_level(scale, n) == _old_select_level(scale, n)
                assert demand_level(scale, n) == select_level(scale, n)


def test_dest_scale_fit_matches_old_formula_table():
    for fb, src in _FIT_CASES:
        for zoom in _ZOOMS:
            assert dest_scale_fit(fb, src, zoom) == _old_fit(fb, src, zoom)


def test_dest_scale_fit_is_limiting_min_axis_not_max():
    flipped = 0
    for fb, src in _FIT_CASES:
        for zoom in _ZOOMS:
            assert dest_scale_fit(fb, src, zoom) == _old_fit(fb, src, zoom)
            if _old_fit(fb, src, zoom) != _max_fit(fb, src, zoom):
                # A min->max sign flip MUST disagree here.
                assert dest_scale_fit(fb, src, zoom) != _max_fit(fb, src, zoom)
                flipped += 1
    # The table must actually contain anisotropic cases or the test is blind.
    assert flipped > 0


def test_dest_scale_fit_nonpositive_source_returns_zero():
    assert dest_scale_fit((800, 600), (0, 50), 1.0) == 0.0
    assert dest_scale_fit((800, 600), (100, 0), 1.0) == 0.0
    assert dest_scale_fit((800, 600), (-4, 50), 1.0) == 0.0
    # Non-positive framebuffer matches the old 0.0 result (0/positive*zoom).
    assert dest_scale_fit((0, 600), (100, 50), 4.0) == 0.0


def test_dest_scale_fit_never_raises_on_garbage():
    # Non-finite zoom propagates exactly like the old inline `min(...) * zoom`;
    # `select_level` (via demand_level) owns the inf/nan decision, so clamping
    # here would silently change the picked level.
    assert math.isnan(dest_scale_fit((800, 600), (100, 50), float("nan")))
    assert math.isinf(dest_scale_fit((800, 600), (100, 50), float("inf")))
    # Old parity: inf scale still resolves to level 0 through demand_level.
    assert demand_level(
        dest_scale_fit((800, 600), (100, 50), float("inf")), 5
    ) == 0
    assert dest_scale_fit(None, (100, 50), 1.0) == 0.0
    assert dest_scale_fit((800, 600), None, 1.0) == 0.0
    assert dest_scale_fit((800, 600), (100, 50), "nope") == 0.0
