"""MultiCompareState → CompositionPlan conversion.

B1: slots are path-only — pixel sources arrive via ``sources={slot_id:
image}`` (resolved from the session cache in production). Imageless leaves
(no entry) are skipped per the A4 policy pin below.
"""

from __future__ import annotations

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareDividerSettings,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.services.composition_builder import build_composition_plan
from tabs.multi_compare.tests.pixel_fixtures import slot_image
from ui.canvas_presentation.composition import (
    LayerNode,
    SplitNode as CompSplitNode,
    resolve_composition,
)


def _slot(slot_id: int, label: str = "") -> CompareSlot:
    return CompareSlot(id=slot_id, label=label or f"slot{slot_id}")


def _plan(state, *specs, **kw):
    """Build with explicit sources; each spec is ``(slot_id, w, h)``."""
    sources = {sid: slot_image(w, h) for sid, w, h in specs}
    return build_composition_plan(state, sources=sources, **kw)


def test_empty_tree_returns_none():
    state = MultiCompareState()
    assert _plan(state) is None


def test_single_leaf_maps_to_single_layer():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1)],
    )
    plan = _plan(state, (1, 800, 600))
    assert plan is not None
    assert isinstance(plan.root, LayerNode)
    assert plan.canvas_w == 800 and plan.canvas_h == 600


def test_split_with_two_leaves_maps_to_split_node():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1), _slot(2)],
    )
    plan = _plan(state, (1, 200, 200), (2, 200, 200))
    assert plan is not None
    assert isinstance(plan.root, CompSplitNode)
    assert plan.root.direction == "h"
    assert len(plan.root.children) == 2
    # canvas should be 400 wide so each 1/2 cell fits 200px image
    assert plan.canvas_w == 400
    assert plan.canvas_h == 200


def test_split_gap_defaults_to_divider_thickness():
    """docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up's divider
    side-quest: the divider-width toolbar control used to only resize
    GridDividersPass's own (underlay, and thus mostly-hidden) quad, while
    the actual layout gap reserved between sibling images stayed pinned to
    the hardcoded DEFAULT_SPLIT_GAP_PX regardless -- so widening/narrowing
    the divider setting had no visible effect at all. ``split_gap_px`` must
    default to ``state.divider_settings.thickness`` so the reserved layout
    space actually tracks the user's setting."""
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1), _slot(2)],
        divider_settings=MultiCompareDividerSettings(thickness=20),
    )
    plan = _plan(state, (1, 200, 200), (2, 200, 200))
    assert plan is not None
    assert isinstance(plan.root, CompSplitNode)
    assert plan.root.gap_px == 20


def test_split_gap_collapses_to_zero_when_divider_hidden():
    """Turning the divider-width toolbar control down to 0 flips
    ``visible`` off but keeps the last nonzero ``thickness`` (so
    re-enabling remembers it) -- the reserved layout gap must still
    collapse to 0 in that case, or images stay pulled apart by the old
    thickness with nothing drawn in the gap to explain the empty space."""
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1), _slot(2)],
        divider_settings=MultiCompareDividerSettings(visible=False, thickness=6),
    )
    plan = _plan(state, (1, 200, 200), (2, 200, 200))
    assert plan is not None
    assert plan.root.gap_px == 0


def test_split_gap_explicit_override_wins_over_divider_thickness():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1), _slot(2)],
        divider_settings=MultiCompareDividerSettings(thickness=20),
    )
    plan = _plan(state, (1, 200, 200), (2, 200, 200), split_gap_px=7)
    assert plan is not None
    assert plan.root.gap_px == 7


def test_missing_slot_image_is_skipped():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1), CompareSlot(id=2)],
    )
    plan = _plan(state, (1, 200, 200))
    # Split collapses to its single loaded child
    assert plan is not None
    assert isinstance(plan.root, LayerNode)
    assert plan.root.layer_id == 1


def test_all_imageless_leaves_return_none():
    """A4 imageless-leaf policy pin: imageless leaves are *skipped*, never
    placeholder layers -- so an all-imageless tree yields plan None (the
    chrome placeholder owns the empty surface; session-restore ordering is
    B1/P6, not papered over here). Do not drift toward invented geometry."""
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[CompareSlot(id=1), CompareSlot(id=2)],
    )
    assert _plan(state) is None


def test_focused_slot_isolates_single_leaf():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1), _slot(2)],
        focused_slot_id=2,
    )
    plan = _plan(state, (1, 200, 200), (2, 400, 400))
    assert plan is not None
    assert isinstance(plan.root, LayerNode)
    assert plan.root.layer_id == 2
    assert plan.canvas_w == 400 and plan.canvas_h == 400


def test_zoom_pan_propagate_to_layers():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1)],
        zoom=2.5,
        pan_x=0.1,
        pan_y=-0.2,
    )
    plan = _plan(state, (1, 100, 100))
    resolved = resolve_composition(plan)
    assert resolved.layers[0].zoom == 2.5
    assert resolved.layers[0].pan_x == 0.1
    assert resolved.layers[0].pan_y == -0.2


def test_labels_included_by_default():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1, label="image-A")],
    )
    plan = _plan(state, (1, 100, 100))
    assert plan.root.label is not None
    assert plan.root.label.text == "image-A"


def test_labels_disabled_when_include_labels_false():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1, label="image-A")],
    )
    plan = _plan(state, (1, 100, 100), include_labels=False)
    assert plan.root.label is None


def test_explicit_canvas_size_overrides_native():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1)],
    )
    plan = _plan(state, (1, 800, 600), canvas_w=1920, canvas_h=1080)
    assert plan.canvas_w == 1920
    assert plan.canvas_h == 1080
