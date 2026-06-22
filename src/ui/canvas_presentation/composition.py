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
    """

    root: CompositionNode
    canvas_w: int
    canvas_h: int
    fill_rgba: tuple[int, int, int, int] | None = None


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
class ResolvedComposition:
    """Composition plan flattened to a sequence of pixel-rect layers.

    GL passes consume this directly: one ``ResolvedLayer`` per textured quad to
    draw. Layer order follows tree traversal (front-to-back = top-to-bottom).
    """

    canvas_w: int
    canvas_h: int
    fill_rgba: tuple[int, int, int, int] | None
    layers: tuple[ResolvedLayer, ...] = field(default_factory=tuple)


def resolve_composition(plan: CompositionPlan) -> ResolvedComposition:
    """Walk the tree once and produce a flat sequence of pixel-rect layers.

    Rect rounding uses ``int()`` truncation with the last child absorbing the
    rounding error so the children always cover the parent rect exactly — same
    behavior as ``GLGridWidget._walk_paths`` to keep visual parity.
    """
    layers: list[ResolvedLayer] = []
    _walk(plan.root, (0, 0, plan.canvas_w, plan.canvas_h), layers)
    return ResolvedComposition(
        canvas_w=plan.canvas_w,
        canvas_h=plan.canvas_h,
        fill_rgba=plan.fill_rgba,
        layers=tuple(layers),
    )


def _walk(
    node: CompositionNode,
    rect: tuple[int, int, int, int],
    out: list[ResolvedLayer],
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
            _walk(child, rect, out)
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
            for child, size in zip(node.children, sizes):
                _walk(child, (cursor, y, size, h), out)
                cursor += size + gap
            return
        total_gap = gap * (n - 1)
        inner = max(h - total_gap, 1)
        sizes = [int(inner * wt) for wt in weights]
        sizes[-1] = inner - sum(sizes[:-1])
        cursor = y
        for child, size in zip(node.children, sizes):
            _walk(child, (x, cursor, w, size), out)
            cursor += size + gap
        return
    raise TypeError(f"Unknown composition node: {type(node).__name__}")


def compute_native_canvas_size(
    plan_root: CompositionNode,
    *,
    max_edge: int = 16384,
) -> tuple[int, int]:
    """Return the smallest canvas where every leaf renders at native resolution.

    The rect of each leaf is a fixed fraction of the canvas size determined by
    the tree weights. For each leaf we need ``rect_w >= img_w`` and
    ``rect_h >= img_h`` to avoid downscaling. ``W = max(img_w / fw)``,
    ``H = max(img_h / fh)`` across leaves. Gaps are ignored as a small constant
    cost. Result is clamped to ``max_edge`` on the longest side.
    """
    fractions: list[tuple[float, float, int, int]] = []
    _collect_fractions(plan_root, 1.0, 1.0, fractions)
    if not fractions:
        return 1, 1
    w_scale = max(iw / fw for fw, _fh, iw, _ih in fractions if fw > 0)
    h_scale = max(ih / fh for _fw, fh, _iw, ih in fractions if fh > 0)
    width = max(1, int(round(w_scale)))
    height = max(1, int(round(h_scale)))
    longest = max(width, height)
    if longest > max_edge:
        scale = max_edge / longest
        width = max(1, int(round(width * scale)))
        height = max(1, int(round(height * scale)))
    return width, height


def _collect_fractions(
    node: CompositionNode,
    fw: float,
    fh: float,
    out: list[tuple[float, float, int, int]],
) -> None:
    if isinstance(node, LayerNode):
        image = node.image
        if image is None:
            return
        if hasattr(image, "shape"):
            h, w = image.shape[:2]
        else:
            w, h = image.width, image.height
        if w <= 0 or h <= 0:
            return
        out.append((fw, fh, int(w), int(h)))
        return
    if isinstance(node, GroupNode):
        for child in node.children:
            _collect_fractions(child, fw, fh, out)
        return
    if isinstance(node, SplitNode):
        weights = node.normalized_weights()
        if node.direction == "h":
            for child, wt in zip(node.children, weights):
                _collect_fractions(child, fw * wt, fh, out)
            return
        for child, wt in zip(node.children, weights):
            _collect_fractions(child, fw, fh * wt, out)
        return
