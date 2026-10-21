"""Tab-agnostic texture-array instanced-draw core.

Owns the per-instance vertex layout, the packing/unpacking of one
``ArrayInstance`` into that layout, and the record sequence that binds the
array pipeline/SRB and issues one instanced ``draw(4, N)``. The GPU
resource owner (texture arrays, pipeline, SRB cache, instance/uniform
buffers) lives next door in ``engine.gpu.array_resources``; this module only
turns a sequence of logical instances into the vertex bytes and records the
draw against a caller-supplied command buffer and resources object.

The layout and packing here are the shared ones a texture-array compare tab
moves into the engine: byte-for-byte the format the image path used before
(rect1/rect2/content-scale/content-scale-diff/layers/bbox/rect-diff). No
shader is compiled here, no uniform block is packed here -- uniform layout
stays with its owning tab -- and no tab module is imported.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtGui import (
    QRhiDepthStencilClearValue,
    QRhiVertexInputAttribute,
    QRhiViewport,
    QShader,
)

from engine.cache.uniform_layout import assert_uniform_size

Rect = tuple[float, float, float, float]

# Per-instance vertex layout (base_array.vert):
# iRect1(vec4,16) + iRect2(vec4,16) + iContentScale(vec4,16) +
# iContentScaleDiff(vec2,8) + iLayers(ivec3,12) + iBBox(vec4,16) +
# iRectDiff(vec4,16) = 100 bytes. Plain vertex attribute packing -- no
# std140 alignment rules apply (that's a uniform-buffer-only constraint),
# just consistency between this stride, ARRAY_INSTANCE_FMT below, and the
# attribute offsets in ARRAY_INSTANCE_ATTRIBUTES.
ARRAY_INSTANCE_STRIDE: int = 100
ARRAY_INSTANCE_FMT: str = "<4f4f4f2f3i4f4f"
assert_uniform_size(
    ARRAY_INSTANCE_FMT, ARRAY_INSTANCE_STRIDE, label="_pack_array_instance"
)

ARRAY_INSTANCE_ATTRIBUTES: tuple[QRhiVertexInputAttribute, ...] = (
    QRhiVertexInputAttribute(1, 2, QRhiVertexInputAttribute.Format.Float4, 0),
    QRhiVertexInputAttribute(1, 3, QRhiVertexInputAttribute.Format.Float4, 16),
    QRhiVertexInputAttribute(1, 4, QRhiVertexInputAttribute.Format.Float4, 32),
    QRhiVertexInputAttribute(1, 5, QRhiVertexInputAttribute.Format.Float2, 48),
    QRhiVertexInputAttribute(1, 6, QRhiVertexInputAttribute.Format.SInt3, 56),
    QRhiVertexInputAttribute(1, 7, QRhiVertexInputAttribute.Format.Float4, 68),
    QRhiVertexInputAttribute(1, 8, QRhiVertexInputAttribute.Format.Float4, 84),
)

# Byte offset of the layer2 int inside one packed instance: everything
# before the 3i group (rects/scales), plus one int for layer1. Derived from
# the fmt instead of a magic number.
_LAYER2_OFFSET = struct.calcsize("<4f4f4f2f") + 4


def array_layer_px(live_tile_extent: int, apron_px: int) -> int:
    """Pixel size of one texture-array layer: tile content (at most
    ``live_tile_extent + 2*apron_px``) is uploaded 1:1 into the top-left
    corner of a layer this size, so every layer can share one size."""
    return live_tile_extent + 2 * apron_px


@dataclass(frozen=True)
class ArrayInstance:
    """One instance of the texture-array instanced draw, in the logical
    fields ``pack_array_instance`` turns into per-instance vertex bytes."""

    rect1: Rect
    rect2: Rect
    content_scale: tuple[float, float, float, float]
    content_scale_diff: tuple[float, float]
    layer1: int
    layer2: int
    layer_diff: int
    bbox: Rect
    rect_diff: Rect = (0.0, 0.0, 1.0, 1.0)
    sampler_name: str = "linear"


def pack_array_instance(
    inst: ArrayInstance | None = None, **fields
) -> bytes:
    """One instance's worth of ``base_array.vert``'s per-instance vertex
    attributes -- byte-for-byte matching ``ARRAY_INSTANCE_STRIDE`` and the
    pipeline's ``QRhiVertexInputAttribute`` offsets.

    The documented call style is ``pack_array_instance(ArrayInstance(...))``.
    The legacy keyword-field style (``rect1=...``/``rect2=...``/...) is kept
    as a thin compatibility path: it builds an ``ArrayInstance`` and packs
    it through the same single implementation.
    """
    if inst is None:
        inst = ArrayInstance(**fields)
    return struct.pack(
        ARRAY_INSTANCE_FMT,
        *inst.rect1,
        *inst.rect2,
        *inst.content_scale,
        *inst.content_scale_diff,
        inst.layer1,
        inst.layer2,
        inst.layer_diff,
        *inst.bbox,
        *inst.rect_diff,
    )


def unpack_instance_layer2(instance_bytes: bytes, index: int) -> int:
    """Read back the layer2 field of instance ``index`` from packed
    ``instance_bytes`` — the submit-vs-plan discriminator. Read-only
    inspection, no behavior change."""
    (layer2,) = struct.unpack_from(
        "<i", instance_bytes, index * ARRAY_INSTANCE_STRIDE + _LAYER2_OFFSET
    )
    return int(layer2)


# ---------------------------------------------------------------------------
# Slot instance layout (single-source / multi-slot array pass)
# ---------------------------------------------------------------------------
#
# The slot pass (``slot_array.vert``/``.frag``, formerly Multi Compare's
# ``multi_compare_array.*``) carries its whole transform PER INSTANCE --
# ``iPanFit``/``iZoom``/``iTileRect``/``iSlotRect`` -- so one instanced draw
# covers N independent slots (Multi Compare) or one full-canvas slot
# (Quick Look). This is the proven single/multi-slot array layout; the pair
# layout above (``ARRAY_INSTANCE_*``) stays for Image Compare's diff pass.
#
# iPanFit(vec4,16) + iZoom(float,4) + iTileRect(vec4,16) + iSlotRect(vec4,16)
# + iContentScale(vec2,8) + iLayer(int,4) + iBBox(vec4,16) = 80 bytes.
SLOT_INSTANCE_STRIDE: int = 80
SLOT_INSTANCE_FMT: str = "<4f f 4f 4f 2f i 4f"
assert_uniform_size(
    SLOT_INSTANCE_FMT, SLOT_INSTANCE_STRIDE, label="pack_slot_instance"
)

SLOT_INSTANCE_ATTRIBUTES: tuple[QRhiVertexInputAttribute, ...] = (
    QRhiVertexInputAttribute(1, 2, QRhiVertexInputAttribute.Format.Float4, 0),
    QRhiVertexInputAttribute(1, 3, QRhiVertexInputAttribute.Format.Float, 16),
    QRhiVertexInputAttribute(1, 4, QRhiVertexInputAttribute.Format.Float4, 20),
    QRhiVertexInputAttribute(1, 5, QRhiVertexInputAttribute.Format.Float4, 36),
    QRhiVertexInputAttribute(1, 6, QRhiVertexInputAttribute.Format.Float2, 52),
    QRhiVertexInputAttribute(1, 7, QRhiVertexInputAttribute.Format.SInt, 60),
    QRhiVertexInputAttribute(1, 8, QRhiVertexInputAttribute.Format.Float4, 64),
)

# std140 UBuf (slot_array.vert/frag): mat4 mvp(64) + vec4 letterbox(16) = 80.
SLOT_UNIFORM_FMT: str = "<16f4f"
SLOT_UNIFORM_BLOCK_SIZE: int = 80
assert_uniform_size(
    SLOT_UNIFORM_FMT, SLOT_UNIFORM_BLOCK_SIZE, label="pack_slot_array_uniforms"
)

_SLOT_SHADER_DIR = Path(__file__).resolve().parent / "shaders"


@dataclass
class SlotInstance:
    """One instance of the slot array draw (see ``SLOT_INSTANCE_*``)."""

    pan_fit: tuple[float, float, float, float]
    zoom: float
    tile_rect: Rect
    slot_rect: Rect
    content_scale: tuple[float, float]
    layer: int
    bbox: Rect


def pack_slot_instance(inst: SlotInstance) -> bytes:
    """One slot instance's per-instance vertex bytes (``SLOT_INSTANCE_FMT``)."""
    return struct.pack(
        SLOT_INSTANCE_FMT,
        *inst.pan_fit,
        inst.zoom,
        *inst.tile_rect,
        *inst.slot_rect,
        *inst.content_scale,
        inst.layer,
        *inst.bbox,
    )


def pack_slot_array_uniforms(
    clip_matrix: Sequence[float],
    letterbox: Rect,
) -> bytes:
    """Bytes for the slot pass's ``UBuf`` (std140: ``mat4 + vec4``)."""
    matrix = tuple(float(v) for v in clip_matrix)
    if len(matrix) != 16:
        raise ValueError(f"clip_matrix must have 16 floats, got {len(matrix)}")
    lb = tuple(float(v) for v in letterbox)
    if len(lb) != 4:
        raise ValueError(f"letterbox must have 4 floats, got {len(lb)}")
    return struct.pack(SLOT_UNIFORM_FMT, *matrix, *lb)


def load_slot_array_shader(name: str) -> QShader:
    """Load one of the engine's baked ``slot_array.*.qsb`` shaders."""
    shader = QShader.fromSerialized((_SLOT_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


def _apply_bbox(
    index: int,
    inst: ArrayInstance,
    bbox_resolver: Callable[[int, ArrayInstance], Rect] | None,
) -> ArrayInstance:
    if bbox_resolver is None:
        return inst
    return replace(inst, bbox=bbox_resolver(index, inst))


def draw_array_instances(
    command_buffer,
    *,
    resources,
    vertex_buffer,
    instance_count: int,
    sampler_name: str | None = None,
    viewport_size: tuple[int, int],
) -> None:
    """Records the array instanced-draw command sequence into an already-open
    pass: bind the array pipeline, set the viewport to ``viewport_size``
    (``(width, height)`` in pixels), bind the slot vertex buffer plus the
    shared per-instance buffer, bind the array SRB for ``sampler_name``, and
    issue one ``draw(4, instance_count)``.

    No pass begin/end and no buffer uploads -- the caller owns the pass and
    has already ensured the pipeline, grown the instance buffer, and written
    the uniform/instance bytes before opening it. ``sampler_name=None`` uses
    the resources' own default sampler; ``ensure_array_srb`` is cached, so
    once the pipeline has been ensured this frame the call is a look-up.
    """
    width, height = viewport_size
    command_buffer.setGraphicsPipeline(resources.array_pipeline)
    command_buffer.setViewport(
        QRhiViewport(0.0, 0.0, float(width), float(height))
    )
    command_buffer.setVertexInput(
        0,
        [
            (vertex_buffer, 0),
            (resources.array_instance_buffer, 0),
        ],
    )
    command_buffer.setShaderResources(resources.ensure_array_srb(sampler_name))
    command_buffer.draw(4, instance_count)


def record_array_draw(
    command_buffer,
    *,
    resources,
    vertex_buffer,
    instances: Sequence[ArrayInstance],
    uniform_bytes: bytes | None,
    target,
    clear_color,
    updates,
    bbox_resolver: Callable[[int, ArrayInstance], Rect] | None = None,
    pre_begin: Callable[[], None] | None = None,
    in_pass: Callable[[], None] | None = None,
    pack_instance: Callable[[object], bytes] = pack_array_instance,
) -> None:
    """Records one array-pass frame: optional pre-pass work, resource
    ensure/upload, one ``beginPass``/instanced draw/``endPass`` with optional
    in-pass work. Empty ``instances`` still runs ``pre_begin`` and the
    begin/end pass pair, but records no draw.

    Order is fixed (and relied on): ``pre_begin`` first (callers run their
    feature-pass ``prepare``/``record_pre_pass`` there, before any pass is
    open), then pipeline/capacity/uniform/instance/SRB setup (resource
    creation is illegal inside an open pass, and the dynamic buffers must be
    written before the same-pass read), then one pass with the instanced
    draw, then ``in_pass`` (feature-pass ``record``), then ``endPass``.

    ``endPass`` runs in a ``finally``: a raise from the draw path or from
    ``in_pass`` must not leave the pass open on ``command_buffer`` (the next
    frame would record into a never-closed pass — stuck black frame). The
    exception still propagates; nothing is swallowed.
    """
    if pre_begin is not None:
        pre_begin()

    if instances:
        resources.ensure_array_pipeline(target)
        resources.ensure_array_instance_capacity(len(instances))
        if uniform_bytes is not None and updates is not None:
            updates.updateDynamicBuffer(
                resources.array_uniform_buffer, 0, uniform_bytes
            )
        instance_bytes = b"".join(
            pack_instance(_apply_bbox(index, inst, bbox_resolver))
            for index, inst in enumerate(instances)
        )
        if updates is not None:
            updates.updateDynamicBuffer(
                resources.array_instance_buffer, 0, instance_bytes
            )
        # Ensure the instance's sampler SRB before the pass opens (resource
        # creation is illegal inside an open pass). ``draw_array_instances``
        # re-ensures the same name inside the pass, which is a cache hit.
        # Pair instances carry ``sampler_name``; slot instances use the
        # resources' own default sampler (``None`` -> default).
        resources.ensure_array_srb(getattr(instances[0], "sampler_name", None))

    command_buffer.beginPass(
        target,
        clear_color,
        QRhiDepthStencilClearValue(1.0, 0),
        updates,
    )
    try:
        if instances:
            size = target.pixelSize()
            draw_array_instances(
                command_buffer,
                resources=resources,
                vertex_buffer=vertex_buffer,
                instance_count=len(instances),
                sampler_name=getattr(instances[0], "sampler_name", None),
                viewport_size=(size.width(), size.height()),
            )
        if in_pass is not None:
            in_pass()
    finally:
        command_buffer.endPass()
