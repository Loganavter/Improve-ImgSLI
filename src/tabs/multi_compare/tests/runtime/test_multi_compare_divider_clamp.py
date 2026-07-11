"""Multi-compare dividers preserve content-scale sanity."""

import numpy as np

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.scene import actions, reduce
from tabs.multi_compare.scene.layout_constraints import (
    is_symmetric_layout,
    natural_pair_weight_ratio,
)


def _slot(slot_id: int, width: int, height: int) -> CompareSlot:
    return CompareSlot(
        id=slot_id,
        image=np.zeros((height, width, 3), dtype=np.uint8),
    )


def test_symmetric_two_image_layout_locks_to_natural_weight_at_reset_zoom():
    """Symmetric reset-zoom layouts should not expose letterbox via dividers."""
    root = SplitNode(
        direction="h",
        children=[LeafNode(1), LeafNode(2)],
        weights=[1.0, 1.0],
    )
    state = MultiCompareState(
        root=root,
        slots=[_slot(1, 1920, 1080), _slot(2, 1920, 1080)],
    )

    next_state = reduce(state, actions.set_split_weights((), [0.9, 0.1]))

    assert isinstance(next_state.root, SplitNode)
    weights = next_state.root.normalized_weights()
    assert weights == [0.5, 0.5]


def test_symmetric_layout_can_move_divider_after_zooming_in():
    root = SplitNode(
        direction="h",
        children=[LeafNode(1), LeafNode(2)],
        weights=[1.0, 1.0],
    )
    state = MultiCompareState(
        root=root,
        slots=[_slot(1, 1920, 1080), _slot(2, 1920, 1080)],
        zoom=2.0,
    )

    next_state = reduce(state, actions.set_split_weights((), [0.8, 0.2]))

    assert isinstance(next_state.root, SplitNode)
    weights = next_state.root.normalized_weights()
    assert weights == [0.8, 0.2]


def test_asymmetric_layout_keeps_drag_weights_at_reset_zoom():
    bottom = SplitNode(
        direction="h",
        children=[LeafNode(2), LeafNode(3)],
        weights=[1.0, 1.0],
    )
    root = SplitNode(
        direction="v",
        children=[LeafNode(1), bottom],
        weights=[1.0, 1.0],
    )
    state = MultiCompareState(
        root=root,
        slots=[
            _slot(1, 1600, 900),
            _slot(2, 1600, 900),
            _slot(3, 1600, 900),
        ],
    )

    next_state = reduce(state, actions.set_split_weights((), [0.8, 0.2]))

    assert not is_symmetric_layout(state.root, state.slots)
    assert isinstance(next_state.root, SplitNode)
    weights = next_state.root.normalized_weights()
    assert weights == [0.8, 0.2]


def test_horizontal_split_uses_child_aspects_as_natural_ratio():
    root = SplitNode(
        direction="h",
        children=[LeafNode(1), LeafNode(2)],
        weights=[1.0, 1.0],
    )
    slots = [_slot(1, 3200, 1000), _slot(2, 1000, 1000)]
    state = MultiCompareState(
        root=root,
        slots=slots,
    )

    ratio = natural_pair_weight_ratio(state.root, (), 0, "h", state.slots)

    assert ratio == 3.2


def test_nested_vertical_split_uses_inverse_child_aspects():
    bottom = SplitNode(
        direction="h",
        children=[LeafNode(2), LeafNode(3)],
        weights=[1.0, 1.0],
    )
    root = SplitNode(
        direction="v",
        children=[LeafNode(1), bottom],
        weights=[1.0, 1.0],
    )
    state = MultiCompareState(
        root=root,
        slots=[
            _slot(1, 1600, 900),
            _slot(2, 1600, 900),
            _slot(3, 1600, 900),
        ],
    )

    ratio = natural_pair_weight_ratio(state.root, (), 0, "v", state.slots)

    assert ratio == 2.0
