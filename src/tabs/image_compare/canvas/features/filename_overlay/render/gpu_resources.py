"""QRhi resources for the IC filename_overlay pass (F5 BOUNDARY, re-opened C1).

F5 filename-verdict (variant C1, re-opened 2026-10-06) -- documented permanent
boundary, not a migration candidate. Variant A's per-slot two-texture +
4x-supersample + Lanczos-downsample cluster is GONE: text is now per-glyph
quads sampling one shared signed-distance-field atlas
(``render/glyph_atlas.py``), and the rounded-rect background is a mode-0 quad
through the same pipeline. Three-part proof (full statement on
``FilenameOverlayPass``; mechanical pins in
``src/tabs/image_compare/tests/render/test_filename_boundary.py``):

(1) WHAT STAYS: one shared SDF atlas texture + linear/nearest samplers, one
pipeline with a four-attribute vertex layout (pos / uv / color / mode+weight),
per-slot growable vertex buffers holding the background quad plus N glyph
quads, per-slot uniform buffers, and per-slot screen draws of N quads (never
one fullscreen quad).

(2) WHY: N independently-positioned glyph quads sampling a shared atlas, plus
a procedural rounded-box background composited through per-slot uniforms, has
no image in the single-fullscreen-upload ``TexturedOverlayShell`` (one
texture, upload-then-draw in the same main pass, shared
``FULLSCREEN_VERTICES``, one ``srb``, one 64B uniform). MC ``layer_labels``
rides the shell ONLY because it is one fullscreen raster with a pre-composited
background.

(3) INVALIDATION: re-open the verdict if the shell gains a shared glyph atlas
plus per-glyph quads, or if these labels drop the atlas + per-slot N-quad
shape for a single fullscreen raster like MC. Either resource-shape change
breaks the markers pinned in ``test_filename_boundary.py``.

Contract note: this is one of the pinned tab texture owners
(``test_no_direct_texture_alloc.py`` / ``test_no_private_grid.py``) -- the
atlas texture is created HERE, never in ``render/glyph_atlas.py`` (which only
builds the CPU image + slot metadata).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QFont,
    QImage,
    QRhi,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiTexture,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
)

from tabs.image_compare.canvas.rhi_feature_common import load_qshader
from tabs.image_compare.canvas.features.filename_overlay.render.glyph_atlas import (
    GlyphAtlas,
)

_SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders"
# std140 block shared by filename_overlay.vert / .frag:
#   mat4 mvp (64B) + vec4 bgColor (16B) + vec2 quadSizePx (8B) +
#   vec2 pad0 (8B) + float cornerRadiusPx + float bgEnabled +
#   float sdfRangePx + float pixelSize + float edgePx + float pad1 +
#   vec2 pad2 (8B) = 128 bytes (32 floats).
_UNIFORM_SIZE = 128
# location 0 vec2 pos + 1 vec2 uv + 2 vec4 color + 3 vec2 aux(mode,weight).
_VERTEX_STRIDE = 40
_ATLAS_PLACEHOLDER = QSize(1, 1)
_INITIAL_VERTEX_CAPACITY = _VERTEX_STRIDE * 6 * 64


class LabelSlot:
    def __init__(self) -> None:
        # Growable screen-quad vertex buffer: the rounded-rect background quad
        # plus one quad per glyph, all in the pass's pixel space.
        self.vertex_buffer: QRhiBuffer | None = None
        self.vertex_capacity: int = 0
        self.vertex_count: int = 0
        # Per-slot 128-byte uniform block: pixel->clip matrix, premultiplied
        # bg color, quad size / corner radius / bg flag, and the SDF decode
        # params (range, pixel size, AA edge). Per slot rather than one shared
        # buffer so prepare() can write each active slot's own values.
        self.uniform_buffer: QRhiBuffer | None = None
        # One SRB per sampler flavour; both bind the shared atlas texture and
        # this slot's uniform buffer.
        self.srb_nearest: QRhiShaderResourceBindings | None = None
        self.srb_linear: QRhiShaderResourceBindings | None = None
        self.active: bool = False
        self.smooth: bool = False
        self.vertices: bytes | None = None

    def release(self) -> None:
        for res in (
            self.srb_nearest,
            self.srb_linear,
            self.vertex_buffer,
            self.uniform_buffer,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.srb_nearest = None
        self.srb_linear = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.vertex_capacity = 0
        self.vertex_count = 0
        self.active = False
        self.smooth = False
        self.vertices = None


class FilenameOverlayGpuResources:
    """Owns the QRhi pipeline/buffers/samplers/atlas for the filename_overlay pass.

    Split out of ``FilenameOverlayPass`` so the pass class itself only holds
    the should_paint/prepare/record orchestration; resource lifecycle
    (create in ``initialize()``, rebuild the atlas on demand, destroy in
    ``release()``) lives here instead.

    F5 BOUNDARY: the shared SDF atlas + per-slot N-quad vertex buffers is what
    stays -- it has no image in ``TexturedOverlayShell``'s single-texture,
    single-SRB, fullscreen-quad shape. See the module docstring for the full
    verdict and its invalidation condition.
    """

    def __init__(self) -> None:
        self.rhi: QRhi | None = None
        self.sampler_nearest: QRhiSampler | None = None
        self.sampler_linear: QRhiSampler | None = None
        self.pipeline: QRhiGraphicsPipeline | None = None
        self.atlas: GlyphAtlas | None = None
        self.atlas_texture: QRhiTexture | None = None
        self.atlas_image: QImage | None = None
        self.slots: list[LabelSlot] = [LabelSlot(), LabelSlot()]

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi

        self.sampler_nearest = rhi.newSampler(
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler_nearest.create():
            raise RuntimeError("Failed to create filename_overlay nearest sampler")

        self.sampler_linear = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler_linear.create():
            raise RuntimeError("Failed to create filename_overlay linear sampler")

        self.atlas = GlyphAtlas(rhi)
        self.atlas_texture = rhi.newTexture(QRhiTexture.Format.RGBA8, _ATLAS_PLACEHOLDER)
        if not self.atlas_texture.create():
            raise RuntimeError("Failed to create filename_overlay atlas texture")

        for slot in self.slots:
            slot.vertex_buffer = rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.VertexBuffer,
                _INITIAL_VERTEX_CAPACITY,
            )
            if not slot.vertex_buffer.create():
                raise RuntimeError("Failed to create filename_overlay vertex buffer")
            slot.vertex_capacity = _INITIAL_VERTEX_CAPACITY
            slot.uniform_buffer = rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                _UNIFORM_SIZE,
            )
            if not slot.uniform_buffer.create():
                raise RuntimeError(
                    "Failed to create filename_overlay slot uniform buffer"
                )
            self._rebuild_slot_srbs(slot)

        self.pipeline = rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    load_qshader(_SHADER_DIR / "filename_overlay.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    load_qshader(_SHADER_DIR / "filename_overlay.frag.qsb"),
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
        self.pipeline.setSampleCount(target.sampleCount())
        srb_linear = self.slots[0].srb_linear
        assert srb_linear is not None
        self.pipeline.setShaderResourceBindings(srb_linear)
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())

        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]  # PySide6 stub types BlendFactor fields as int
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        self.pipeline.setTargetBlends([blend])

        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(_VERTEX_STRIDE)])
        layout.setAttributes(
            [
                QRhiVertexInputAttribute(
                    0, 0, QRhiVertexInputAttribute.Format.Float2, 0
                ),
                QRhiVertexInputAttribute(
                    0, 1, QRhiVertexInputAttribute.Format.Float2, 8
                ),
                QRhiVertexInputAttribute(
                    0, 2, QRhiVertexInputAttribute.Format.Float4, 16
                ),
                QRhiVertexInputAttribute(
                    0, 3, QRhiVertexInputAttribute.Format.Float2, 32
                ),
            ]
        )
        self.pipeline.setVertexInputLayout(layout)
        if not self.pipeline.create():
            raise RuntimeError("Failed to create filename_overlay QRhi pipeline")

    def _build_srb(self, sampler, uniform_buffer):
        assert self.atlas_texture is not None
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, self.atlas_texture, sampler
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create filename_overlay SRB")
        return srb

    def _rebuild_slot_srbs(self, slot: LabelSlot) -> None:
        for srb_attr, sampler in (
            ("srb_nearest", self.sampler_nearest),
            ("srb_linear", self.sampler_linear),
        ):
            srb = getattr(slot, srb_attr)
            if srb is not None:
                try:
                    srb.destroy()
                except RuntimeError:
                    pass
            setattr(slot, srb_attr, self._build_srb(sampler, slot.uniform_buffer))

    def ensure_atlas(self, font: QFont, pixel_size: int, dpr: float, weight: int = 0) -> bool:
        """Build/refresh the shared SDF atlas; returns True when it changed.

        On a rebuild the atlas texture is recreated at the new size and every
        slot's SRBs are rebound to it. The caller uploads ``atlas_image`` via
        its own resource-update batch.
        """
        assert self.atlas is not None
        changed = self.atlas.ensure(font, pixel_size, dpr, weight)
        if not changed:
            return False
        self.atlas_image = self.atlas.image
        if self.atlas_image is None:
            return False
        # BOUNDARY (F5): one shared SDF atlas texture for every glyph quad.
        if self.atlas_texture is not None:
            try:
                self.atlas_texture.destroy()
            except RuntimeError:
                pass
        self.atlas_texture = self.rhi.newTexture(
            QRhiTexture.Format.RGBA8,
            QSize(int(self.atlas_image.width()), int(self.atlas_image.height())),
        )
        if not self.atlas_texture.create():
            raise RuntimeError("Failed to create filename_overlay atlas texture")
        for slot in self.slots:
            self._rebuild_slot_srbs(slot)
        # Keep the pipeline's default SRB pointing at a live object (record()
        # rebinds per draw, but never leave a destroyed SRB as the default).
        if self.pipeline is not None:
            self.pipeline.setShaderResourceBindings(self.slots[0].srb_linear)
        return True

    def ensure_vertex_capacity(self, slot: LabelSlot, needed_bytes: int) -> None:
        """Grow ``slot``'s vertex buffer so it can hold ``needed_bytes``."""
        if slot.vertex_buffer is not None and slot.vertex_capacity >= needed_bytes:
            return
        capacity = max(needed_bytes, slot.vertex_capacity * 2, _INITIAL_VERTEX_CAPACITY)
        if slot.vertex_buffer is not None:
            try:
                slot.vertex_buffer.destroy()
            except RuntimeError:
                pass
        slot.vertex_buffer = self.rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            capacity,
        )
        if not slot.vertex_buffer.create():
            raise RuntimeError("Failed to grow filename_overlay vertex buffer")
        slot.vertex_capacity = capacity

    def release(self) -> None:
        for slot in self.slots:
            slot.release()
        for res in (
            self.pipeline,
            self.atlas_texture,
            self.sampler_linear,
            self.sampler_nearest,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.pipeline = None
        self.atlas_texture = None
        self.atlas_image = None
        self.atlas = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.rhi = None
