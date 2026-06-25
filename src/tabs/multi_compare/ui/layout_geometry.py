"""Pure layout geometry helpers for the multi-compare grid."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect

from tabs.multi_compare.models import LeafNode, SplitNode


def walk_paths(
    node,
    rect: QRect,
    path: tuple[int, ...] = (),
    *,
    only_path: tuple[int, ...] | None = None,
    gap: int = 4,
) -> tuple[
    list[tuple[LeafNode, QRect, tuple[int, ...]]],
    list[tuple[SplitNode, QRect, tuple[int, ...]]],
]:
    leaves: list[tuple[LeafNode, QRect, tuple[int, ...]]] = []
    splits: list[tuple[SplitNode, QRect, tuple[int, ...]]] = []
    _walk_paths(node, rect, path, leaves, splits, only_path, gap)
    return leaves, splits


def _walk_paths(
    node,
    rect: QRect,
    path: tuple[int, ...],
    leaves: list[tuple[LeafNode, QRect, tuple[int, ...]]],
    splits: list[tuple[SplitNode, QRect, tuple[int, ...]]],
    only_path: tuple[int, ...] | None,
    gap: int,
) -> None:
    on_path = only_path is None or only_path[: len(path)] == path
    if not on_path:
        return
    if isinstance(node, LeafNode):
        if only_path is None or only_path == path:
            leaves.append((node, rect, path))
        return

    assert isinstance(node, SplitNode)
    splits.append((node, rect, path))
    weights = node.normalized_weights()
    count = len(node.children)
    depth = len(path)
    if node.direction == "h":
        inner = max(rect.width() - gap * (count - 1), 1)
        sizes = _weighted_sizes(inner, weights)
        x = rect.x()
        for index, (child, size) in enumerate(zip(node.children, sizes)):
            child_rect = QRect(x, rect.y(), size, rect.height())
            if only_path is None or (
                depth < len(only_path) and only_path[depth] == index
            ):
                _walk_paths(
                    child,
                    child_rect,
                    path + (index,),
                    leaves,
                    splits,
                    only_path,
                    gap,
                )
            x += size + gap
        return

    inner = max(rect.height() - gap * (count - 1), 1)
    sizes = _weighted_sizes(inner, weights)
    y = rect.y()
    for index, (child, size) in enumerate(zip(node.children, sizes)):
        child_rect = QRect(rect.x(), y, rect.width(), size)
        if only_path is None or (
            depth < len(only_path) and only_path[depth] == index
        ):
            _walk_paths(
                child,
                child_rect,
                path + (index,),
                leaves,
                splits,
                only_path,
                gap,
            )
        y += size + gap


def drop_gaps(node, rect: QRect, *, gap: int = 4) -> list[tuple[SplitNode, tuple[int, ...], int, QRect]]:
    gaps: list[tuple[SplitNode, tuple[int, ...], int, QRect]] = []
    _walk_drop_gaps(node, rect, (), gaps, gap)
    return gaps


def _walk_drop_gaps(
    node,
    rect: QRect,
    path: tuple[int, ...],
    gaps: list[tuple[SplitNode, tuple[int, ...], int, QRect]],
    gap: int,
) -> None:
    if isinstance(node, LeafNode):
        return
    assert isinstance(node, SplitNode)
    weights = node.normalized_weights()
    child_count = len(node.children)

    if node.direction == "h":
        inner = max(rect.width() - gap * (child_count - 1), 1)
        sizes = _weighted_sizes(inner, weights)
        x = rect.x()
        for index, (child, size) in enumerate(zip(node.children, sizes)):
            child_rect = QRect(x, rect.y(), size, rect.height())
            _walk_drop_gaps(child, child_rect, path + (index,), gaps, gap)
            if index < child_count - 1:
                gaps.append((node, path, index, QRect(x + size, rect.y(), gap, rect.height())))
            x += size + (gap if index < child_count - 1 else 0)
        return

    inner = max(rect.height() - gap * (child_count - 1), 1)
    sizes = _weighted_sizes(inner, weights)
    y = rect.y()
    for index, (child, size) in enumerate(zip(node.children, sizes)):
        child_rect = QRect(rect.x(), y, rect.width(), size)
        _walk_drop_gaps(child, child_rect, path + (index,), gaps, gap)
        if index < child_count - 1:
            gaps.append((node, path, index, QRect(rect.x(), y + size, rect.width(), gap)))
        y += size + (gap if index < child_count - 1 else 0)


def side_subrect(rect: QRect, side: str | None) -> QRect | None:
    if side is None:
        return None
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if side == "left":
        return QRect(x, y, w // 2, h)
    if side == "right":
        return QRect(x + w // 2, y, w - w // 2, h)
    if side == "top":
        return QRect(x, y, w, h // 2)
    if side == "bottom":
        return QRect(x, y + h // 2, w, h - h // 2)
    if side == "center":
        return QRect(x, y, w, h)
    return None


def nearest_rect_distance_sq(pos: QPoint, rect: QRect) -> int:
    dx = max(rect.x() - pos.x(), 0, pos.x() - (rect.x() + rect.width() - 1))
    dy = max(rect.y() - pos.y(), 0, pos.y() - (rect.y() + rect.height() - 1))
    return dx * dx + dy * dy


def _weighted_sizes(inner: int, weights: list[float] | tuple[float, ...]) -> list[int]:
    sizes = [int(inner * weight) for weight in weights]
    if sizes:
        sizes[-1] = inner - sum(sizes[:-1])
    return sizes
