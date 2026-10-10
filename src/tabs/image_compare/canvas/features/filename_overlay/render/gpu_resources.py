# File-Size-Exempt: one QRhi resource-lifecycle owner for the filename_overlay device-resolve (per-slot raw/final textures, downsample targets, shared pipeline); splitting scatters a single create/upload/resize/release lifecycle across files.
"""QRhi resources for the IC filename_overlay pass (F5 BOUNDARY, stays).

F5 filename-verdict -- documented permanent boundary, not a migration
candidate. Three-part proof (full statement on ``FilenameOverlayPass``;
mechanical pins in
``src/tabs/image_compare/tests/render/test_filename_boundary.py``):

(1) WHAT STAYS: per-slot raw + final textures (``ensure_slot_textures``
below), per-slot ``RenderTarget`` downsample targets with their own
rpdesc, the ``_LABEL_SUPERSAMPLE = 4`` supersampled upload -> Lanczos
pre-pass (``label_downsample.frag`` ``SCALE = 4`` / ``RADIUS = 8``) ->
device-resolve in ``record_pre_pass``, per-slot screen quads via
``build_quad_vertices`` (never fullscreen), per-slot vertex buffers
with ``srb_linear`` / ``srb_nearest`` selection.

(2) WHY: two independently-sized label textures plus a supersample
stage plus a device-resolve plus per-slot screen quads has no image in
the single-fullscreen-upload ``TexturedOverlayShell`` (one texture,
upload-then-draw in the same main pass, shared ``FULLSCREEN_VERTICES``,
one ``srb``). MC ``layer_labels`` rides the shell ONLY because it is
one fullscreen raster with no supersample stage.

(3) INVALIDATION: re-open the verdict if the shell gains slot-targets
plus a GPU-supersample stage, or if these labels drop supersampling
for a single fullscreen raster like MC.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhi,
    QRhiBuffer,
    QRhiColorAttachment,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiRenderPassDescriptor,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiTexture,
    QRhiTextureRenderTarget,
    QRhiTextureRenderTargetDescription,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
)

from tabs.image_compare.canvas.rhi_feature_common import load_qshader

_SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders"
_UNIFORM_SIZE = 64
_VERTEX_STRIDE = 16
_VERTEX_BUFFER_SIZE = _VERTEX_STRIDE * 4


class LabelSlot:
    def __init__(self) -> None:
        self.vertex_buffer: QRhiBuffer | None = None
        # Final, device-resolution texture -- what filename_overlay.frag
        # actually samples for the on-screen quad. Filled by the downsample
        # pass below, not uploaded directly (see raw_texture).
        self.texture: QRhiTexture | None = None
        self.texture_size: QSize | None = None
        self.srb_nearest: QRhiShaderResourceBindings | None = None
        self.srb_linear: QRhiShaderResourceBindings | None = None
        # CPU-uploaded source: the label rasterized supersampled (see
        # render/label_raster.py's _LABEL_SUPERSAMPLE), undownscaled.
        self.raw_texture: QRhiTexture | None = None
        self.raw_texture_size: QSize | None = None
        # Set by prepare() when the label was just re-rasterized, consumed
        # (uploaded, then cleared) by record_pre_pass() -- NOT queued into
        # prepare()'s own shared resource-update batch, which only actually
        # gets submitted alongside the *main* pass's own beginPass call
        # (see rhi_renderer.render()), i.e. *after* record_pre_pass()'s own
        # downsample pass would already have tried to read it. Needs its
        # own resourceUpdate(), submitted right before that read, same
        # ordering shared.rendering.glass_panel.render_backdrops() already
        # uses for its own upload-then-downsample-same-call sequence.
        self.pending_upload_image: QImage | None = None
        # Lanczos-2 downsample stage: raw_texture -> texture, one dedicated
        # pipeline/target per slot (not shared across slots -- mirrors
        # shared.rendering.glass_panel._PanelGpu's own "every panel gets its
        # own pipeline+rpdesc" precedent, after a confirmed cross-target
        # leak/ghosting bug from sharing one there).
        self.downsample_target: QRhiTextureRenderTarget | None = None
        self.downsample_rpdesc: QRhiRenderPassDescriptor | None = None
        self.downsample_pipeline: QRhiGraphicsPipeline | None = None
        self.srb_downsample: QRhiShaderResourceBindings | None = None
        # True from the frame a new raw_texture upload is pending until
        # record_pre_pass() has actually uploaded it and run the downsample
        # pass once for it.
        self.needs_downsample: bool = False
        # Interactive (drag) path: the label was rasterized at 1x, so
        # ``pending_upload_image`` is device-resolution and is uploaded
        # straight into ``texture`` (the sampled target), skipping the
        # Lanczos downsample (whose SCALE=4 expects a 4x raw). Mutually
        # exclusive with ``needs_downsample``.
        self.direct_upload: bool = False
        self.content_key: object | None = None
        self.active: bool = False
        self.smooth: bool = False
        self.vertices: bytes | None = None

    def release(self) -> None:
        for res in (
            self.srb_nearest,
            self.srb_linear,
            self.srb_downsample,
            self.downsample_pipeline,
            self.downsample_rpdesc,
            self.downsample_target,
            self.texture,
            self.raw_texture,
            self.vertex_buffer,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.vertex_buffer = None
        self.texture = None
        self.texture_size = None
        self.srb_nearest = None
        self.srb_linear = None
        self.raw_texture = None
        self.raw_texture_size = None
        self.downsample_target = None
        self.downsample_rpdesc = None
        self.downsample_pipeline = None
        self.srb_downsample = None
        self.needs_downsample = False
        self.direct_upload = False
        self.pending_upload_image = None
        self.content_key = None
        self.active = False
        self.vertices = None


class FilenameOverlayGpuResources:
    """Owns the QRhi pipeline/buffers/samplers for the filename_overlay pass.

    Split out of ``FilenameOverlayPass`` so the pass class itself only holds
    the should_paint/prepare/record orchestration; resource lifecycle
    (create in ``initialize()``, resize on demand, destroy in ``release()``)
    lives here instead.

    F5 BOUNDARY: this two-slot shape (raw + final texture, per-slot
    downsample target/rpdesc/pipeline/SRB, per-slot vertex buffer and
    ``srb_nearest`` / ``srb_linear``) is what stays -- it has no image
    in ``TexturedOverlayShell``'s single-texture, single-SRB,
    fullscreen-quad shape. See the module docstring for the full
    verdict and its invalidation condition.
    """

    def __init__(self) -> None:
        self.rhi: QRhi | None = None
        self.uniform_buffer: QRhiBuffer | None = None
        self.sampler_nearest: QRhiSampler | None = None
        self.sampler_linear: QRhiSampler | None = None
        self.pipeline: QRhiGraphicsPipeline | None = None
        self.slots: list[LabelSlot] = [LabelSlot(), LabelSlot()]

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi

        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_SIZE,
        )
        if not self.uniform_buffer.create():
            raise RuntimeError("Failed to create filename_overlay uniform buffer")

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

        for slot in self.slots:
            slot.vertex_buffer = rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.VertexBuffer,
                _VERTEX_BUFFER_SIZE,
            )
            if not slot.vertex_buffer.create():
                raise RuntimeError("Failed to create filename_overlay vertex buffer")
            self.ensure_slot_textures(slot, QSize(1, 1), QSize(1, 1))

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
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
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
            ]
        )
        self.pipeline.setVertexInputLayout(layout)
        if not self.pipeline.create():
            raise RuntimeError("Failed to create filename_overlay QRhi pipeline")

    def _build_srb(self, texture, sampler):
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(1, fragment, texture, sampler),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create filename_overlay SRB")
        return srb

    def ensure_slot_textures(
        self, slot: LabelSlot, raw_size: QSize, final_size: QSize
    ) -> None:
        assert self.rhi is not None
        """(Re)builds ``slot``'s raw (CPU-uploaded, supersampled) and final
        (device-res, GPU-downsampled-into) textures, plus everything that
        depends on either -- the main pass's srb_nearest/srb_linear, the
        downsample SRB and render target. The downsample render-pass
        descriptor and graphics pipeline are created ONCE (they depend on
        attachment format + SRB layout, not texture size) and reused across
        size changes. ``raw_size`` and ``final_size`` always change together
        in practice (raw is a fixed multiple of final, see
        render/label_raster.py's ``_LABEL_SUPERSAMPLE``), but each is checked
        independently since neither depends on the other having actually
        changed."""
        # BOUNDARY (F5): per-slot raw + final textures -- the two-texture
        # shape (supersampled CPU-upload source + RenderTarget-flagged
        # device-res resolve target) the single-texture shell cannot host.
        raw_changed = slot.raw_texture is None or slot.raw_texture_size != raw_size
        if raw_changed:
            if slot.raw_texture is not None:
                try:
                    slot.raw_texture.destroy()
                except RuntimeError:
                    pass
            slot.raw_texture = self.rhi.newTexture(QRhiTexture.Format.RGBA8, raw_size)
            if not slot.raw_texture.create():
                raise RuntimeError("Failed to create filename_overlay raw texture")
            slot.raw_texture_size = raw_size

        final_changed = slot.texture is None or slot.texture_size != final_size
        if final_changed:
            if slot.texture is not None:
                try:
                    slot.texture.destroy()
                except RuntimeError:
                    pass
            slot.texture = self.rhi.newTexture(
                QRhiTexture.Format.RGBA8, final_size, 1, QRhiTexture.Flag.RenderTarget
            )
            if not slot.texture.create():
                raise RuntimeError("Failed to resize filename_overlay texture")
            slot.texture_size = final_size
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
                setattr(slot, srb_attr, self._build_srb(slot.texture, sampler))

        if not (raw_changed or final_changed):
            return

        # BOUNDARY (F5): per-slot downsample target + own rpdesc -- one
        # dedicated RenderTarget/pipeline/SRB per slot (never shared
        # across slots), the device-resolve stage with no shell image.
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        # The downsample SRB samples raw_texture, so it must be rebuilt only
        # when that texture object changes (or on first creation) -- not on
        # every final-size change.
        if slot.srb_downsample is None or raw_changed:
            if slot.srb_downsample is not None:
                try:
                    slot.srb_downsample.destroy()
                except RuntimeError:
                    pass
            slot.srb_downsample = self.rhi.newShaderResourceBindings()
            slot.srb_downsample.setBindings(
                [
                    QRhiShaderResourceBinding.sampledTexture(
                        0, fragment, slot.raw_texture, self.sampler_linear  # type: ignore[arg-type]  # set right above; typed Optional for lifecycle
                    ),
                ]
            )
            if not slot.srb_downsample.create():
                raise RuntimeError("Failed to create filename_overlay downsample SRB")

        # The render target wraps the final texture, so it is recreated when
        # that texture object changes -- but the render-pass descriptor is
        # REUSED: QRhi rpdesc compatibility is format-based (see
        # engine/gpu/mip_cascade.py's probe-target pattern), so the pipeline
        # baked against it stays valid across label-size changes.
        if slot.downsample_target is None or final_changed:
            if slot.downsample_target is not None:
                try:
                    slot.downsample_target.destroy()
                except RuntimeError:
                    pass
            assert slot.texture is not None
            slot.downsample_target = self.rhi.newTextureRenderTarget(
                QRhiTextureRenderTargetDescription(QRhiColorAttachment(slot.texture))
            )
            if slot.downsample_rpdesc is None:
                slot.downsample_rpdesc = (
                    slot.downsample_target.newCompatibleRenderPassDescriptor()
                )
            slot.downsample_target.setRenderPassDescriptor(slot.downsample_rpdesc)
            if not slot.downsample_target.create():
                raise RuntimeError(
                    "Failed to create filename_overlay downsample target"
                )

        # The downsample pipeline is created ONCE. It depends only on the
        # shaders, vertex layout, topology and the (format-based) rpdesc --
        # never on texture size. Recreating it on every label-size change was
        # the divider-drag stall: a graphics pipeline create per mouse-move
        # frame. The SRB changes with the source texture, but a rebuilt SRB
        # with the same binding layout is compatible with the existing
        # pipeline, which is re-bound at draw time (record_pre_pass) -- same
        # shape mip_cascade uses for its per-(layer, level) targets.
        if slot.downsample_pipeline is None:
            assert slot.downsample_rpdesc is not None
            slot.downsample_pipeline = self.rhi.newGraphicsPipeline()
            slot.downsample_pipeline.setShaderStages(
                [
                    QRhiShaderStage(
                        QRhiShaderStage.Type.Vertex,
                        load_qshader(_SHADER_DIR / "label_downsample.vert.qsb"),
                    ),
                    QRhiShaderStage(
                        QRhiShaderStage.Type.Fragment,
                        load_qshader(_SHADER_DIR / "label_downsample.frag.qsb"),
                    ),
                ]
            )
            slot.downsample_pipeline.setTopology(
                QRhiGraphicsPipeline.Topology.Triangles
            )
            slot.downsample_pipeline.setRenderPassDescriptor(slot.downsample_rpdesc)
            slot.downsample_pipeline.setShaderResourceBindings(slot.srb_downsample)
            if not slot.downsample_pipeline.create():
                raise RuntimeError(
                    "Failed to create filename_overlay downsample pipeline"
                )

    def release(self) -> None:
        for slot in self.slots:
            slot.release()
        for res in (
            self.pipeline,
            self.sampler_linear,
            self.sampler_nearest,
            self.uniform_buffer,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.pipeline = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.uniform_buffer = None
        self.rhi = None
