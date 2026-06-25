"""Pure operations on the multi-compare layout tree.

These mirror the helpers in :mod:`tabs.multi_compare.models` but never mutate
their inputs — every operation returns a fresh tree (or sub-tree) so the result
can be stored in an immutable ``MultiCompareState`` and diffed against the
previous value by identity.

The traversal/rounding semantics match ``models.py`` exactly so behavior parity
is preserved during the migration.
"""

from __future__ import annotations

from tabs.multi_compare.models import (
    LayoutNode,
    LeafNode,
    SplitNode,
    find_path,
)


def _clone_split(node: SplitNode, *, children=None, weights=None) -> SplitNode:
    return SplitNode(
        direction=node.direction,
        children=list(children) if children is not None else list(node.children),
        weights=list(weights) if weights is not None else list(node.weights),
    )


def remove_leaf(node: LayoutNode | None, slot_id: int) -> LayoutNode | None:
    """Return a new tree with the leaf removed; collapses single-child splits."""
    if node is None:
        return None
    if isinstance(node, LeafNode):
        return None if node.slot_id == slot_id else node
    new_children: list[LayoutNode] = []
    new_weights: list[float] = []
    for child, weight in zip(node.children, node.weights):
        pruned = remove_leaf(child, slot_id)
        if pruned is not None:
            new_children.append(pruned)
            new_weights.append(weight)
    if not new_children:
        return None
    if len(new_children) == 1:
        return new_children[0]
    return _clone_split(node, children=new_children, weights=new_weights)


def swap_slot_ids(
    node: LayoutNode | None, sid_a: int, sid_b: int
) -> LayoutNode | None:
    if node is None or sid_a == sid_b:
        return node
    if isinstance(node, LeafNode):
        if node.slot_id == sid_a:
            return LeafNode(sid_b)
        if node.slot_id == sid_b:
            return LeafNode(sid_a)
        return node
    return _clone_split(
        node,
        children=[swap_slot_ids(c, sid_a, sid_b) for c in node.children],
    )


def _wrap_node(node: LayoutNode, side: str, new_slot_id: int) -> SplitNode:
    direction = "h" if side in ("left", "right") else "v"
    new_leaf = LeafNode(new_slot_id)
    children = [new_leaf, node] if side in ("left", "top") else [node, new_leaf]
    return SplitNode(direction=direction, children=children, weights=[1.0, 1.0])


def insert_beside_path(
    root: LayoutNode | None,
    path: tuple[int, ...],
    side: str,
    new_slot_id: int,
) -> LayoutNode | None:
    """Insert ``new_slot_id`` beside the node at ``path``; returns new root.

    Same flattening rule as the legacy helper: when the target's parent split
    runs in the requested direction, the new leaf is added as a sibling rather
    than nesting a new split.
    """
    if root is None:
        return LeafNode(new_slot_id)
    if not path:
        return _wrap_node(root, side, new_slot_id)
    new_root = _rebuild_with_insert(root, path, side, new_slot_id)
    return new_root if new_root is not None else root


def _rebuild_with_insert(
    node: LayoutNode,
    path: tuple[int, ...],
    side: str,
    new_slot_id: int,
) -> LayoutNode | None:
    if len(path) == 1:
        assert isinstance(node, SplitNode)
        idx = path[0]
        target = node.children[idx]
        wanted_dir = "h" if side in ("left", "right") else "v"
        if wanted_dir == node.direction:
            avg_w = sum(node.weights) / len(node.weights) if node.weights else 1.0
            ins_at = idx if side in ("left", "top") else idx + 1
            new_children = list(node.children)
            new_weights = list(node.weights)
            new_children.insert(ins_at, LeafNode(new_slot_id))
            new_weights.insert(ins_at, avg_w)
            return _clone_split(node, children=new_children, weights=new_weights)
        new_children = list(node.children)
        new_children[idx] = _wrap_node(target, side, new_slot_id)
        return _clone_split(node, children=new_children)

    assert isinstance(node, SplitNode)
    idx = path[0]
    rebuilt_child = _rebuild_with_insert(
        node.children[idx], path[1:], side, new_slot_id
    )
    if rebuilt_child is None:
        return None
    new_children = list(node.children)
    new_children[idx] = rebuilt_child
    return _clone_split(node, children=new_children)


def insert_beside(
    node: LayoutNode | None,
    target_slot_id: int,
    side: str,
    new_slot_id: int,
) -> LayoutNode | None:
    """Pure variant of ``models.insert_beside`` keyed by slot id."""
    if node is None:
        return LeafNode(new_slot_id)
    path = find_path(node, target_slot_id)
    if path is None:
        return node
    return insert_beside_path(node, tuple(path), side, new_slot_id)


def set_split_weights(
    root: LayoutNode | None,
    path: tuple[int, ...],
    weights: tuple[float, ...] | list[float],
) -> LayoutNode | None:
    """Return a new tree with the SplitNode at ``path`` getting ``weights``.

    ``path`` is the chain of child indices from root to that split (the same
    convention as ``find_path`` / ``node_at_path``). Children themselves are
    not replaced. If the node at ``path`` is not a SplitNode the tree is
    returned unchanged.
    """
    if root is None:
        return None
    if not path:
        if isinstance(root, SplitNode):
            return _clone_split(root, weights=list(weights))
        return root
    if not isinstance(root, SplitNode):
        return root
    idx = path[0]
    if idx < 0 or idx >= len(root.children):
        return root
    new_child = set_split_weights(root.children[idx], path[1:], weights)
    new_children = list(root.children)
    new_children[idx] = new_child
    return _clone_split(root, children=new_children)


def move_leaf(
    root: LayoutNode | None,
    source_slot_id: int,
    target_slot_id: int,
    side: str,
) -> LayoutNode | None:
    if root is None or source_slot_id == target_slot_id:
        return root
    pruned = remove_leaf(root, source_slot_id)
    if pruned is None:
        return LeafNode(source_slot_id)
    return insert_beside(pruned, target_slot_id, side, source_slot_id)
