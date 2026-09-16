"""Shared fullscreen textured overlay shell (overlay-shell R3a).

Owns the retained GPU objects for one raster-upload overlay pass: one
dynamic vertex buffer (shared quad), one 64-byte uniform buffer (clip
matrix), one linear sampler, one RGBA8 texture (grown on demand), one
shader-resource binding set, and one graphics pipeline (premultiplied
alpha blend, TriangleStrip, no scissor).

Lifted verbatim in behavior from the tab-side fullscreen-texture
resource shape: same vertex bytes (reused from ``shell.py``), same
premultiplied blend factors (One / OneMinusSrcAlpha), same sampler
(Linear / Linear / None, ClampToEdge), same lazy 1x1 RGBA8 placeholder,
same resize path (destroy texture, new RGBA8 texture, rebuild bindings,
force-rebuild the pipeline), same full-framebuffer viewport draw with
no scissor. Only the entry point names differ from the retired shape
(``initialize`` / ``prepare`` / ``record`` / ``release``); the retired
tab-side class keeps those names until R3b removes it, so this shell
keeps its renamed entry points the way the uniform shell does.

Minimal public API (R3b mounts onto this verbatim; names are stable):

- ``TexturedOverlayShell``: owns the retained GPU objects for one
  raster-upload overlay pass. Entry points: ``mount`` /
  ``stage_quad`` / ``stage_clip`` / ``upload_frame`` / ``draw`` /
  ``teardown``. The ``active`` flag reports whether the last
  ``upload_frame`` staged drawable content.
- ``TexturedOverlayResolver`` + ``TexturedOverlayBinding``: the
  tab-side seam. ``TexturedOverlayResolver`` is ctx-first --
  ``resolve(ctx)`` takes the opaque per-frame pass context first and
  returns a framebuffer raster as ``(width, height, pixels) | None``,
  where ``pixels`` is a ``bytes`` snapshot of premultiplied RGBA8888
  rows (``width * 4`` bytes per row). Bytes intake -- never host
  images -- keeps host image types tab-side: the tab rasterizes its
  own image and converts it to bytes, and the shell wraps the bytes in
  a host image only for the synchronous upload call. The engine never
  interprets ``ctx`` and never names tab geometry; the tab binds its
  own frame sources behind the closure.
- ``TexturedOverlayBinding`` declares *what* to mount for one pass
  (shader location + stem). Rasters flow per frame through the
  resolver, so the bundle itself holds no per-frame state.

Ownership rule: tab passes declare bindings only (shader location,
ctx-first resolvers). All GPU allocation and all draw-recorder calls
live here. See ``tests/contracts/test_overlay_shell.py`` (textured
ownership + mount pins).

The shell is strict by construction: every per-frame value arrives
precomputed (clip matrix tuple, framebuffer width/height, raster
bytes, render target for pipeline rebuilds). Tab-side fallbacks for
contexts that lack ``clip_matrix`` / ``framebuffer_size`` stay in the
tab pass, never here -- the retired base owned them, the shell does
not.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiTexture,
    QRhiViewport,
    QShader,
)

from .shell import FULLSCREEN_VERTICES

TEXTURED_UNIFORM_SIZE = 64

__all__ = [
    "TEXTURED_UNIFORM_SIZE",
    "TexturedOverlayBinding",
    "TexturedOverlayResolver",
    "TexturedOverlayShell",
]


@runtime_checkable
class TexturedOverlayResolver(Protocol):
    """Tab-side raster resolver: ctx in, framebuffer bytes out."""

    def __call__(self, ctx: Any) -> tuple[int, int, bytes] | None:
        """Resolve this frame's raster from the opaque context.

        Returns ``(width, height, pixels)`` with ``pixels`` a ``bytes``
        snapshot of premultiplied RGBA8888 rows, or ``None`` when the
        pass has nothing to draw this frame.
        """
        ...


@dataclass(frozen=True, slots=True)
class TexturedOverlayBinding:
    """Mount declaration for one textured overlay pass (no GPU)."""

    shader_dir: Path
    shader_stem: str


def _load_qshader(shader_dir: Path, shader_stem: str, name: str) -> QShader:
    shader = QShader.fromSerialized((shader_dir / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid {shader_stem} overlay shader: {name}")
    return shader


def _vertex_input_layout() -> Any:
    from PySide6.QtGui import (
        QRhiVertexInputAttribute,
        QRhiVertexInputBinding,
        QRhiVertexInputLayout,
    )

    layout = QRhiVertexInputLayout()
    layout.setBindings([QRhiVertexInputBinding(16)])
    layout.setAttributes(
        [
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
        ]
    )
    return layout


class TexturedOverlayShell:
    """Retained GPU shell for one raster-upload overlay pass."""

    def __init__(self) -> None:
        self.uniform_size = TEXTURED_UNIFORM_SIZE
        self.rhi: Any | None = None
        self.vertex_buffer: Any | None = None
        self.uniform_buffer: Any | None = None
        self.sampler: Any | None = None
        self.texture: Any | None = None
        self.texture_size: Any | None = None
        self.srb: QRhiShaderResourceBindings | None = None
        self.pipeline: Any | None = None
        self._render_pass_descriptor: Any | None = None
        self._pipeline_sample_count: int | None = None
        self._shader_dir: Path | None = None
        self._shader_stem: str = ""
        self.active = False

    def mount(self, rhi: Any, target: Any, shader_dir: Path, shader_stem: str) -> None:
        """Create the vertex/uniform/sampler/texture/SRB/pipeline set."""
        self.teardown()
        self.rhi = rhi
        self._shader_dir = shader_dir
        self._shader_stem = shader_stem
        self.vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.vertex_buffer.create():
            raise RuntimeError(f"Failed to create {shader_stem} vertex buffer")
        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            TEXTURED_UNIFORM_SIZE,
        )
        if not self.uniform_buffer.create():
            raise RuntimeError(f"Failed to create {shader_stem} uniform buffer")
        self.sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler.create():
            raise RuntimeError(f"Failed to create {shader_stem} sampler")
        self.texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        if not self.texture.create():
            raise RuntimeError(f"Failed to create {shader_stem} placeholder texture")
        self.texture_size = QSize(1, 1)
        self.srb = self._build_srb()
        self._ensure_pipeline(target)

    def _build_srb(self) -> Any:
        assert self.rhi is not None
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, self.texture, self.sampler
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError(f"Failed to create {self._shader_stem} SRB")
        return srb

    def _ensure_pipeline(self, target: Any, *, force: bool = False) -> bool:
        if self.rhi is None or target is None or self.srb is None:
            return False
        assert self._shader_dir is not None
        descriptor = target.renderPassDescriptor()
        sample_count = int(target.sampleCount())
        if (
            not force
            and self.pipeline is not None
            and descriptor is self._render_pass_descriptor
            and sample_count == self._pipeline_sample_count
        ):
            return False
        if self.pipeline is not None:
            try:
                self.pipeline.destroy()
            except RuntimeError:
                pass
            self.pipeline = None
        pipeline = self.rhi.newGraphicsPipeline()
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    _load_qshader(
                        self._shader_dir, self._shader_stem, f"{self._shader_stem}.vert.qsb"
                    ),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    _load_qshader(
                        self._shader_dir, self._shader_stem, f"{self._shader_stem}.frag.qsb"
                    ),
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(sample_count)
        pipeline.setRenderPassDescriptor(descriptor)
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        pipeline.setTargetBlends([blend])
        pipeline.setShaderResourceBindings(self.srb)
        pipeline.setVertexInputLayout(_vertex_input_layout())
        if not pipeline.create():
            raise RuntimeError(f"Failed to create {self._shader_stem} QRhi pipeline")
        self.pipeline = pipeline
        self._render_pass_descriptor = descriptor
        self._pipeline_sample_count = sample_count
        return True

    def stage_quad(self, resource_updates: Any) -> None:
        """Stage the shared fullscreen-quad vertex buffer."""
        resource_updates.updateDynamicBuffer(
            self.vertex_buffer, 0, FULLSCREEN_VERTICES
        )

    def stage_clip(self, resource_updates: Any, clip_matrix: tuple[float, ...]) -> None:
        """Stage the 16-float clip-space correction matrix."""
        resource_updates.updateDynamicBuffer(
            self.uniform_buffer, 0, struct.pack("<16f", *clip_matrix)
        )

    def upload_frame(
        self,
        resource_updates: Any,
        render_target: Any,
        frame: tuple[int, int, bytes] | None,
    ) -> bool:
        """Grow the texture to ``frame`` if needed, upload, set ``active``.

        ``frame`` is ``(width, height, pixels)`` with premultiplied
        RGBA8888 bytes, or ``None`` when the pass has nothing to draw.
        ``render_target`` rebuilds the pipeline after a resize (may be
        ``None`` when the caller has no target -- the upload still
        lands, the rebuild waits for the next target).
        """
        if frame is None:
            self.active = False
            return False
        width, height, pixels = frame
        if width <= 0 or height <= 0 or not pixels:
            self.active = False
            return False
        size = QSize(int(width), int(height))
        if self.texture_size != size:
            try:
                if self.texture is not None:
                    self.texture.destroy()
            except RuntimeError:
                pass
            assert self.rhi is not None
            self.texture = self.rhi.newTexture(QRhiTexture.Format.RGBA8, size)
            if not self.texture.create():
                raise RuntimeError(f"Failed to resize {self._shader_stem} texture")
            self.texture_size = size
            try:
                if self.srb is not None:
                    self.srb.destroy()
            except RuntimeError:
                pass
            self.srb = self._build_srb()
            # The pipeline was created against the previous bindings;
            # rebuild so the layout binding stays valid after texture
            # resize (Vulkan).
            if render_target is not None:
                self._ensure_pipeline(render_target, force=True)
        image = QImage(pixels, int(width), int(height), int(width) * 4, QImage.Format.Format_RGBA8888_Premultiplied)
        if image.isNull():
            self.active = False
            return False
        resource_updates.uploadTexture(self.texture, image)
        self.active = True
        return True

    def draw(self, command_buffer: Any, *, width: float, height: float) -> None:
        """Draw the uploaded raster as one fullscreen quad (no scissor)."""
        if not self.active or self.pipeline is None:
            return
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, float(width), float(height)))
        command_buffer.setShaderResources(self.srb)
        command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
        command_buffer.draw(4)

    def teardown(self) -> None:
        """Destroy all retained GPU objects."""
        for resource in (
            self.pipeline,
            self.srb,
            self.texture,
            self.uniform_buffer,
            self.vertex_buffer,
            self.sampler,
        ):
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self.rhi = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.sampler = None
        self.texture = None
        self.texture_size = None
        self.srb = None
        self.pipeline = None
        self._render_pass_descriptor = None
        self._pipeline_sample_count = None
        self._shader_dir = None
        self._shader_stem = ""
        self.active = False
