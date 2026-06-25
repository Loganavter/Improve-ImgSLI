"""Semantic constraints for multi-compare layout weights."""

from __future__ import annotations

from tabs.multi_compare.models import CompareSlot, LayoutNode, LeafNode, SplitNode, node_at_path

MIN_SPLIT_WEIGHT_FRACTION = 0.15


def constrain_split_weights(
    root: LayoutNode | None,
    path: tuple[int, ...],
    proposed_weights: tuple[float, ...] | list[float],
    slots: list[CompareSlot],
    zoom: float = 1.0,
) -> list[float]:
    """Clamp proposed SplitNode weights only when the whole layout is symmetric."""
    split = node_at_path(root, path)
    if not isinstance(split, SplitNode):
        return list(proposed_weights)
    weights = _sanitize_weights(proposed_weights, len(split.children), split.weights)
    if len(weights) < 2:
        return weights

    weights = _apply_min_share(weights)
    if zoom > 1.0 or not is_symmetric_layout(root, slots):
        return weights

    natural = natural_split_weights(split, slots)
    if natural is None:
        return weights
    total = sum(weights) or 1.0
    natural_total = sum(natural) or 1.0
    return [total * weight / natural_total for weight in natural]


def is_symmetric_layout(root: LayoutNode | None, slots: list[CompareSlot]) -> bool:
    """Return True when every split repeats the same child shape/content aspect."""
    if root is None:
        return False
    slots_by_id = {slot.id: slot for slot in slots}
    signature = _symmetry_signature(root, slots_by_id)
    return signature is not None


def natural_split_weights(
    split: SplitNode,
    slots: list[CompareSlot],
) -> list[float] | None:
    """Weights that make each direct child keep its natural aspect at zoom 1."""
    slots_by_id = {slot.id: slot for slot in slots}
    aspects = [natural_aspect_for_node(child, slots_by_id) for child in split.children]
    if any(aspect is None or aspect <= 0 for aspect in aspects):
        return None
    if split.direction == "h":
        return [float(aspect) for aspect in aspects]
    return [1.0 / float(aspect) for aspect in aspects]


def natural_pair_weight_ratio(
    root: LayoutNode | None,
    split_path: tuple[int, ...],
    divider_idx: int,
    direction: str,
    slots: list[CompareSlot],
) -> float | None:
    """Return the natural left/right or top/bottom weight ratio for a divider."""
    split = node_at_path(root, split_path)
    if not isinstance(split, SplitNode):
        return None
    if divider_idx < 0 or divider_idx + 1 >= len(split.children):
        return None
    slots_by_id = {slot.id: slot for slot in slots}
    first_aspect = natural_aspect_for_node(split.children[divider_idx], slots_by_id)
    second_aspect = natural_aspect_for_node(split.children[divider_idx + 1], slots_by_id)
    if first_aspect is None or second_aspect is None:
        return None
    if direction == "h":
        return first_aspect / second_aspect
    return second_aspect / first_aspect


def natural_aspect_for_node(
    node: LayoutNode,
    slots_by_id: dict[int, CompareSlot],
) -> float | None:
    """Natural aspect ratio for a leaf/subtree, ignoring divider gaps."""
    if isinstance(node, LeafNode):
        slot = slots_by_id.get(node.slot_id)
        image = slot.image if slot is not None else None
        if image is None:
            return None
        if hasattr(image, "shape"):
            height, width = image.shape[:2]
        else:
            width, height = image.width, image.height
        if width <= 0 or height <= 0:
            return None
        return float(width) / float(height)
    if not isinstance(node, SplitNode):
        return None
    child_aspects = [
        aspect
        for child in node.children
        if (aspect := natural_aspect_for_node(child, slots_by_id)) is not None
        and aspect > 0
    ]
    if not child_aspects:
        return None
    if len(child_aspects) == 1:
        return child_aspects[0]
    if node.direction == "h":
        return sum(child_aspects)
    inverse_sum = sum(1.0 / aspect for aspect in child_aspects)
    if inverse_sum <= 0:
        return None
    return 1.0 / inverse_sum


def _symmetry_signature(
    node: LayoutNode,
    slots_by_id: dict[int, CompareSlot],
):
    if isinstance(node, LeafNode):
        aspect = natural_aspect_for_node(node, slots_by_id)
        if aspect is None:
            return None
        return ("leaf", round(aspect, 6))
    if not isinstance(node, SplitNode) or not node.children:
        return None
    child_signatures = [
        _symmetry_signature(child, slots_by_id)
        for child in node.children
    ]
    if any(signature is None for signature in child_signatures):
        return None
    first = child_signatures[0]
    if any(signature != first for signature in child_signatures[1:]):
        return None
    return (node.direction, first, len(child_signatures))


def _sanitize_weights(
    proposed_weights: tuple[float, ...] | list[float],
    child_count: int,
    fallback_weights: list[float],
) -> list[float]:
    weights = [float(weight) for weight in proposed_weights[:child_count]]
    if len(weights) < child_count:
        weights.extend(float(weight) for weight in fallback_weights[len(weights):child_count])
    if len(weights) != child_count or any(weight <= 0 for weight in weights):
        return [1.0] * child_count
    return weights


def _apply_min_share(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        return weights
    max_floor = total / (len(weights) * 2.0)
    floor = min(total * MIN_SPLIT_WEIGHT_FRACTION, max_floor)
    clamped = [max(floor, weight) for weight in weights]
    extra = sum(clamped) - total
    if extra <= 0:
        return clamped
    reducible = sum(max(0.0, weight - floor) for weight in clamped)
    if reducible <= 0:
        return [total / len(weights)] * len(weights)
    return [
        weight - extra * max(0.0, weight - floor) / reducible
        for weight in clamped
    ]
