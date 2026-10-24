"""Shared fullscreen-quad uniform overlay shell (overlay-shell S1).

Owns the retained GPU objects for one fullscreen-quad overlay pass:
one dynamic vertex buffer (shared quad), one graphics pipeline (alpha
blend, scissor-enabled, 2xFloat2 layout), and one uniform buffer +
shader-resource binding per drawn item, grown on demand.

Lifted verbatim in behavior from the tab-side fullscreen-uniform
resource shape: same vertex bytes, same blend factors, same vertex
layout, same lazy pipeline creation (the pipeline binds the first
binding and is created once the first slot exists). Only the entry
point names differ (see package docstring for why).

The shell never interprets the frame context and never touches host
frame sources: per-frame blocks arrive as opaque packed bytes from a
tab-side ``OverlayResolver`` (ctx-first), and the scissor/viewport
arrive precomputed. ``shader_dir`` / ``shader_stem`` locate the
tab-owned compiled shaders (``<stem>.vert.qsb`` / ``<stem>.frag.qsb``);
shader bytes stay tab-owned, pipeline ownership lives here.

The v2 semantic intake (``semantic.py``) packs scale-free items into the
same opaque blocks; ``stage_packed`` below is its staging entry point
(ensure slots + stage quad + stage each block, returning the count).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from PySide6.QtGui import (
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
    QShader,
)

from engine.gpu.rt_y_orientation import composited_clip_correction

FULLSCREEN_VERTICES = struct.pack(
    "<16f",
    -1.0,
    1.0,
    0.0,
    0.0,
    -1.0,
    -1.0,
    0.0,
    1.0,
    1.0,
    1.0,
    1.0,
    0.0,
    1.0,
    -1.0,
    1.0,
    1.0,
)

__all__ = ["FULLSCREEN_VERTICES", "OverlayShell"]


def _load_qshader(shader_dir: Path, shader_stem: str, name: str) -> QShader:
    shader = QShader.fromSerialized((shader_dir / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid {shader_stem} overlay shader: {name}")
    return shader


class OverlayShell:
    """Retained GPU shell for one fullscreen-quad uniform overlay pass."""

    def __init__(self, uniform_size: int) -> None:
        self.uniform_size = uniform_size
        self.rhi: Any | None = None
        self.vertex_buffer: Any | None = None
        self.pipeline: Any | None = None
        self.slot_uniforms: list = []
        self.slot_bindings: list = []
        self.pipeline_ready = False

    def mount(self, rhi: Any, target: Any, shader_dir: Path, shader_stem: str) -> None:
        """Create the vertex buffer and pipeline against ``target``."""
        self.teardown()
        self.rhi = rhi
        self.vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.vertex_buffer.create():
            raise RuntimeError(f"Failed to create {shader_stem} vertex buffer")
        self.pipeline = self._build_pipeline(rhi, target, shader_dir, shader_stem)

    def _build_pipeline(
        self, rhi: Any, target: Any, shader_dir: Path, shader_stem: str
    ) -> Any:
        pipeline = rhi.newGraphicsPipeline()
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    _load_qshader(shader_dir, shader_stem, f"{shader_stem}.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    _load_qshader(shader_dir, shader_stem, f"{shader_stem}.frag.qsb"),
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(target.sampleCount())
        pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        pipeline.setFlags(QRhiGraphicsPipeline.Flag.UsesScissor)
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha  # type: ignore[assignment]
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        pipeline.setTargetBlends([blend])
        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(16)])
        layout.setAttributes(
            [
                QRhiVertexInputAttribute(
                    0, 0, QRhiVertexInputAttribute.Format.Float2, 0
                ),
                QRhiVertexInputAttribute(
                    0, 1, QRhiVertexInputAttribute.Format.Float2, 8
                ),
            ]
        )
        pipeline.setVertexInputLayout(layout)
        return pipeline

    def ensure_slots(self, count: int) -> None:
        """Grow uniform buffers + bindings to ``count`` slots."""
        assert self.rhi is not None
        stage = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        while len(self.slot_uniforms) < count:
            buffer = self.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                self.uniform_size,
            )
            if not buffer.create():
                raise RuntimeError("Failed to create overlay uniform buffer")
            bindings = self.rhi.newShaderResourceBindings()
            bindings.setBindings(
                [QRhiShaderResourceBinding.uniformBuffer(0, stage, buffer)]
            )
            if not bindings.create():
                raise RuntimeError("Failed to create overlay binding")
            self.slot_uniforms.append(buffer)
            self.slot_bindings.append(bindings)
        if not self.pipeline_ready and self.slot_bindings:
            assert self.pipeline is not None
            self.pipeline.setShaderResourceBindings(self.slot_bindings[0])
            if not self.pipeline.create():
                raise RuntimeError("Failed to create overlay pipeline")
            self.pipeline_ready = True

    def clip_matrix(self) -> tuple[float, ...]:
        """Current clip-space correction matrix as 16 floats."""
        assert self.rhi is not None
        # COMPOSITED case: see engine/gpu/rt_y_orientation.
        return composited_clip_correction(self.rhi)

    def stage_quad(self, resource_updates: Any) -> None:
        """Stage the shared fullscreen-quad vertex buffer."""
        resource_updates.updateDynamicBuffer(
            self.vertex_buffer, 0, FULLSCREEN_VERTICES
        )

    def stage_slot(self, resource_updates: Any, index: int, block: bytes) -> None:
        """Stage one packed uniform block into slot ``index``."""
        resource_updates.updateDynamicBuffer(
            self.slot_uniforms[index], 0, block
        )

    def stage_packed(
        self,
        resource_updates: Any,
        blocks: tuple[bytes, ...] | list[bytes],
        *,
        start: int = 0,
    ) -> int:
        """Stage v2 semantic-packed blocks (ensure slots + quad + slots).

        Takes the opaque blocks a ``semantic.py`` pack function produced
        for this frame; grows the slot set, stages the shared quad, then
        stages each block from ``start``. Returns the staged count (0 and
        no GPU traffic when ``blocks`` is empty).
        """
        blocks = tuple(blocks)
        if not blocks:
            return 0
        self.ensure_slots(start + len(blocks))
        self.stage_quad(resource_updates)
        for offset, block in enumerate(blocks):
            self.stage_slot(resource_updates, start + offset, block)
        return len(blocks)

    def draw(
        self,
        command_buffer: Any,
        *,
        width: float,
        height: float,
        scissor: Any,
        count: int,
    ) -> None:
        """Draw ``count`` fullscreen-quad items with the given scissor."""
        if count <= 0 or self.pipeline is None:
            return
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, float(width), float(height)))
        command_buffer.setScissor(scissor)
        command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
        for index in range(count):
            command_buffer.setShaderResources(self.slot_bindings[index])
            command_buffer.draw(4)

    def teardown(self) -> None:
        """Destroy all retained GPU objects."""
        for resource in (
            self.pipeline,
            *self.slot_bindings,
            *self.slot_uniforms,
            self.vertex_buffer,
        ):
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self.rhi = None
        self.vertex_buffer = None
        self.pipeline = None
        self.slot_uniforms = []
        self.slot_bindings = []
        self.pipeline_ready = False
