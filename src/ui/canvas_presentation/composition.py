"""Composition tree primitives for the canvas render plan.

A composition describes *what* is drawn and *where*, decoupled from the GPU
backend. A single ``LayerNode`` is a textured quad with a per-layer transform;
a ``SplitNode`` lays its children out in a row/column; a ``GroupNode`` simply
nests children inside the parent rect (no layout effect by itself).

The applicator walks the tree once per frame, computes integer pixel rects for
every leaf, and dispatches draw calls. The same tree is consumed by the live
canvas and by the offscreen exporter — only the target framebuffer changes.

Coordinates inside the tree are *canvas-px* relative to the parent rect. The
applicator anchors the root rect at ``(0, 0, canvas_w, canvas_h)``. Per-layer
``zoom`` / ``pan`` use the same shader-side semantics as the multi_compare
pipeline:

    img_uv = (cell_uv - 0.5) / (fit * zoom) + 0.5 - pan

where ``fit`` is the aspect-fit scale of the image inside its cell rect. The
visible image rect in cell-uv space is centered at ``0.5 + pan * fit * zoom``
with size ``fit * zoom``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Union

from PIL import Image


@dataclass(frozen=True)
class LayerLabel:
    """Per-layer text label drawn at the bottom of the layer rect."""

    text: str
    font_pt: int = 10
    padding: int = 6
    bg_alpha: int = 170


@dataclass(frozen=True)
class LayerNode:
    """A single textured quad — one image slot."""

    layer_id: int
    image: object  # PIL.Image.Image | numpy.ndarray
    source_image: object | None = None
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    fit_mode: Literal["contain", "stretch"] = "contain"
    label: LayerLabel | None = None
    fill_rgba: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class SplitNode:
    """Row (``h``) or column (``v``) split of children with normalized weights."""

    direction: Literal["h", "v"]
    children: tuple["CompositionNode", ...]
    weights: tuple[float, ...]
    gap_px: int = 0

    def normalized_weights(self) -> tuple[float, ...]:
        total = sum(self.weights) or 1.0
        return tuple(w / total for w in self.weights)


@dataclass(frozen=True)
class GroupNode:
    """Transparent container — children are stacked in the parent rect."""

    children: tuple["CompositionNode", ...]


CompositionNode = Union[LayerNode, SplitNode, GroupNode]


@dataclass(frozen=True)
class CompositionPlan:
    """Composition tree + global frame parameters.

    ``canvas_w`` / ``canvas_h`` are the target framebuffer size in pixels. The
    root rect ``(0, 0, canvas_w, canvas_h)`` is divided down by the tree.
    ``fill_rgba`` is the clear color; ``None`` means transparent.

    ``divider_settings`` / ``label_settings`` are opaque, feature-owned style
    objects (e.g. multi_compare's ``MultiCompareDividerSettings`` /
    ``LabelSettings``) baked in at plan-build time so overlay render passes
    read styling from this immutable plan instead of a mutable widget/state
    object — the live canvas and the offscreen exporter build their own
    ``CompositionPlan`` from the same source state, so both see identical
    styling without the exporter needing to replicate ``set_state``.
    """

    root: CompositionNode
    canvas_w: int
    canvas_h: int
    fill_rgba: tuple[int, int, int, int] | None = None
    divider_settings: object | None = None
    label_settings: object | None = None


@dataclass(frozen=True)
class ResolvedLayer:
    """A composition leaf resolved to an integer pixel rect."""

    layer_id: int
    image: object
    source_image: object | None
    rect: tuple[int, int, int, int]  # x, y, w, h in canvas-px
    zoom: float
    pan_x: float
    pan_y: float
    fit_mode: Literal["contain", "stretch"]
    label: LayerLabel | None
    fill_rgba: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class ResolvedGap:
    """A split-gap band resolved to an integer pixel rect.

    ``direction`` is the owning ``SplitNode.direction`` — ``"h"`` gaps are
    thin vertical strips between side-by-side children, ``"v"`` gaps are thin
    horizontal strips between stacked children.
    """

    direction: Literal["h", "v"]
    rect: tuple[int, int, int, int]  # x, y, w, h in canvas-px


@dataclass(frozen=True)
class ResolvedComposition:
    """Composition plan flattened to a sequence of pixel-rect layers.

    GL passes consume this directly: one ``ResolvedLayer`` per textured quad to
    draw. Layer order follows tree traversal (front-to-back = top-to-bottom).
    ``gaps`` carries every ``SplitNode`` divider band so overlay passes (grid
    dividers) can draw from this immutable snapshot instead of re-deriving
    geometry from a separately-tracked, possibly-unset widget state.
    """

    canvas_w: int
    canvas_h: int
    fill_rgba: tuple[int, int, int, int] | None
    layers: tuple[ResolvedLayer, ...] = field(default_factory=tuple)
    gaps: tuple[ResolvedGap, ...] = field(default_factory=tuple)
    divider_settings: object | None = None
    label_settings: object | None = None


def resolve_composition(plan: CompositionPlan) -> ResolvedComposition:
    """Walk the tree once and produce a flat sequence of pixel-rect layers.

    Rect rounding uses ``int()`` truncation with the last child absorbing the
    rounding error so the children always cover the parent rect exactly — same
    behavior as ``MultiCompareCanvasWidget._walk_paths`` to keep visual parity.
    """
    layers: list[ResolvedLayer] = []
    gaps: list[ResolvedGap] = []
    _walk(plan.root, (0, 0, plan.canvas_w, plan.canvas_h), layers, gaps)
    return ResolvedComposition(
        canvas_w=plan.canvas_w,
        canvas_h=plan.canvas_h,
        fill_rgba=plan.fill_rgba,
        layers=tuple(layers),
        gaps=tuple(gaps),
        divider_settings=plan.divider_settings,
        label_settings=plan.label_settings,
    )


def _walk(
    node: CompositionNode,
    rect: tuple[int, int, int, int],
    out: list[ResolvedLayer],
    out_gaps: list[ResolvedGap],
) -> None:
    if isinstance(node, LayerNode):
        out.append(
            ResolvedLayer(
                layer_id=node.layer_id,
                image=node.image,
                source_image=node.source_image,
                rect=rect,
                zoom=float(node.zoom),
                pan_x=float(node.pan_x),
                pan_y=float(node.pan_y),
                fit_mode=node.fit_mode,
                label=node.label,
                fill_rgba=node.fill_rgba,
            )
        )
        return
    if isinstance(node, GroupNode):
        for child in node.children:
            _walk(child, rect, out, out_gaps)
        return
    if isinstance(node, SplitNode):
        x, y, w, h = rect
        n = len(node.children)
        if n == 0:
            return
        weights = node.normalized_weights()
        gap = max(0, int(node.gap_px))
        if node.direction == "h":
            total_gap = gap * (n - 1)
            inner = max(w - total_gap, 1)
            sizes = [int(inner * wt) for wt in weights]
            sizes[-1] = inner - sum(sizes[:-1])
            cursor = x
            for index, (child, size) in enumerate(zip(node.children, sizes)):
                _walk(child, (cursor, y, size, h), out, out_gaps)
                cursor += size
                if gap > 0 and index < n - 1:
                    out_gaps.append(
                        ResolvedGap(direction="h", rect=(cursor, y, gap, h))
                    )
                cursor += gap
            return
        total_gap = gap * (n - 1)
        inner = max(h - total_gap, 1)
        sizes = [int(inner * wt) for wt in weights]
        sizes[-1] = inner - sum(sizes[:-1])
        cursor = y
        for index, (child, size) in enumerate(zip(node.children, sizes)):
            _walk(child, (x, cursor, w, size), out, out_gaps)
            cursor += size
            if gap > 0 and index < n - 1:
                out_gaps.append(ResolvedGap(direction="v", rect=(x, cursor, w, gap)))
            cursor += gap
        return
    raise TypeError(f"Unknown composition node: {type(node).__name__}")


def compute_native_canvas_size(
    plan_root: CompositionNode,
    *,
    max_edge: int | None = None,
) -> tuple[int, int]:
    """Return the smallest canvas where every leaf renders at native resolution.

    The rect of each leaf is a fixed fraction of its parent rect (``_walk``),
    and every split subtracts ``gap_px * (n - 1)`` from its inner extent before
    the fractions apply. So the requirement is recursive: a leaf needs its own
    pixel size, an ``h`` split needs ``max(cell_need / weight)`` plus its gaps,
    a ``v`` split likewise on height, and a group passes the max of its
    children through.

    Including the gaps is not cosmetic. A canvas derived from the leaf
    fractions alone leaves every cell ``gap``-pixels short of the image
    aspect, so the aspect-fit image is letterboxed by a few px along the
    canvas edge — invisible on the live canvas, but on export it is a
    transparent (white once the background is filled or alpha is flattened)
    rim around the picture. Measured 2026-10-23: a 2×1280×800 split with a
    4 px divider exported 2560×800 with a 1 px rim on all sides.

    ``_walk`` truncates child sizes with ``int()`` (last child absorbs the
    remainder), so the per-split inner extent steps to the smallest integer
    whose product with the weight still reaches the requirement.

    When ``max_edge`` is set, the longest side is clamped to that value.
    """
    required = _required_rect(plan_root)
    if required is None:
        return 1, 1
    width = max(1, int(required[0]))
    height = max(1, int(required[1]))
    longest = max(width, height)
    if max_edge is not None and longest > int(max_edge):
        scale = int(max_edge) / longest
        width = max(1, int(round(width * scale)))
        height = max(1, int(round(height * scale)))
    return width, height


def _required_rect(node: CompositionNode) -> tuple[int, int] | None:
    """Smallest integer rect in which ``node`` renders every leaf at native size."""
    if isinstance(node, LayerNode):
        return _image_pixel_size(node.image)
    if isinstance(node, GroupNode):
        needs = [n for n in (_required_rect(c) for c in node.children) if n]
        if not needs:
            return None
        return (
            max(w for w, _h in needs),
            max(h for _w, h in needs),
        )
    if isinstance(node, SplitNode):
        weights = node.normalized_weights()
        needs: list[tuple[tuple[int, int], float]] = []
        for child, weight in zip(node.children, weights):
            need = _required_rect(child)
            if need is not None:
                needs.append((need, float(weight)))
        if not needs:
            return None
        gap = max(0, int(node.gap_px))
        total_gap = gap * max(0, len(node.children) - 1)
        if node.direction == "h":
            inner_w = max(_min_inner_for(need[0], wt) for need, wt in needs)
            inner_h = max(need[1] for need, _wt in needs)
            return (inner_w + total_gap, inner_h)
        inner_w = max(need[0] for need, _wt in needs)
        inner_h = max(_min_inner_for(need[1], wt) for need, wt in needs)
        return (inner_w, inner_h + total_gap)
    raise TypeError(f"Unknown composition node: {type(node).__name__}")


def _min_inner_for(required: int, weight: float) -> int:
    """Smallest integer ``inner`` with ``int(inner * weight) >= required``.

    Mirrors ``_walk``'s truncation exactly: a value that only reaches the
    requirement through float rounding is one pixel short in practice, and
    that pixel comes back as the letterbox rim this function exists to avoid.
    """
    if weight <= 0.0:
        return max(1, int(required))
    value = max(1, int(math.ceil(required / weight)))
    while int(value * weight) < required:
        value += 1
    while value > 1 and int((value - 1) * weight) >= required:
        value -= 1
    return value


def _image_pixel_size(image: object) -> tuple[int, int] | None:
    """``(w, h)`` of a duck-typed pixel source, or ``None`` when imageless."""
    if image is None:
        return None
    if hasattr(image, "shape"):
        h, w = image.shape[:2]
    elif hasattr(image, "width") and callable(image.width):
        # QImage (e.g. a progressive-load preview) — width/height are
        # methods, not attributes, unlike PIL.Image/TiledPixelStore.
        w, h = image.width(), image.height()  # type: ignore[attr-defined]  # duck-typed pixel source
    else:
        w, h = image.width, image.height  # type: ignore[attr-defined]  # duck-typed pixel source
    if w <= 0 or h <= 0:
        return None
    return int(w), int(h)
