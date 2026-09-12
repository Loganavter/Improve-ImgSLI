from shared.rendering.lod import select_level


def test_zoomed_in_uses_base_level():
    assert select_level(1.0, 5) == 0
    assert select_level(2.5, 5) == 0


def test_halving_thresholds():
    # dest_scale 0.5 => level-1 texel spans exactly 1 screen px.
    assert select_level(0.5, 5) == 1
    assert select_level(0.51, 5) == 0
    assert select_level(0.25, 5) == 2
    assert select_level(0.26, 5) == 1
    assert select_level(0.124, 5) == 3


def test_clamped_to_available_levels():
    assert select_level(0.001, 3) == 2
    assert select_level(0.001, 1) == 0


def test_degenerate_scale_falls_to_coarsest():
    assert select_level(0.0, 4) == 3
    assert select_level(-1.0, 4) == 3
    assert select_level(float("inf"), 4) == 0
    assert select_level(float("nan"), 4) == 3