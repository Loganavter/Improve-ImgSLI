"""MultiCompare drop zones are local to an image cell, not its parent split."""

from types import SimpleNamespace

from PyQt6.QtCore import QPoint, QRect

from tabs.multi_compare.models import LeafNode, MultiCompareState, SplitNode
from tabs.multi_compare.ui.gl_grid import GLGridWidget


def _grid_with_two_columns():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(1), LeafNode(2)],
            weights=[1.0, 1.0],
        ),
    )
    return SimpleNamespace(
        state=state,
        _drop_target_for_gap=lambda pos: None,
        _leaf_paths_and_rects=lambda: [
            (LeafNode(1), QRect(0, 0, 498, 600), (0,)),
            (LeafNode(2), QRect(502, 0, 498, 600), (1,)),
        ],
    )


def _target(grid, pos, *, include_center=False):
    return GLGridWidget.compute_drop_target(
        grid, pos, include_center=include_center
    )


def test_internal_center_is_relative_to_target_leaf():
    grid = _grid_with_two_columns()

    target = _target(grid, QPoint(370, 300), include_center=True)

    assert target == ((0,), "center", False, 1)


def test_internal_drop_near_divider_targets_adjacent_leaf_edge():
    grid = _grid_with_two_columns()

    target = _target(grid, QPoint(500, 300), include_center=True)

    assert target == ((1,), "left", False, None)


def test_external_drop_near_divider_inserts_at_adjacent_leaf_edge():
    grid = _grid_with_two_columns()

    target = _target(grid, QPoint(500, 300))

    assert target == ((1,), "left", False, None)


def test_drop_zone_does_not_promote_to_whole_grid_split():
    grid = _grid_with_two_columns()

    target = _target(grid, QPoint(750, 100))

    assert target == ((1,), "top", False, None)


def _gap_target(y):
    split = SplitNode(
        direction="h",
        children=[LeafNode(1), LeafNode(2)],
        weights=[1.0, 1.0],
    )
    grid = SimpleNamespace(
        _drop_gaps=lambda: [(split, (), 0, QRect(498, 0, 4, 600))]
    )
    return GLGridWidget._drop_target_for_gap(grid, QPoint(500, y))


def test_vertical_gap_top_quarter_inserts_above_both_images():
    assert _gap_target(50) == ((), "top", False, None)


def test_vertical_gap_middle_half_inserts_between_images():
    assert _gap_target(300) == ((1,), "left", False, None)


def test_vertical_gap_bottom_quarter_inserts_below_both_images():
    assert _gap_target(550) == ((), "bottom", False, None)
