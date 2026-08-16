"""Shared per-array-layer mip-downsample cascade (docs/dev/rendering/
tile-array-atlas-plan.md Phase 9): regenerates the mip chain for a set of
dirtied ``(array_index, layer)`` pairs in a texture array via a manual cascade
of single-layer downsample passes, instead of a whole-array
``QRhiResourceUpdateBatch.generateMips`` call.

Extracted out of two tabs' array-path renderers, which independently carried
a ~350-line byte-identical copy of this logic (each tab derives its own
``_ARRAY_LAYER_PX`` and owns its own shader directory, so everything
tab-specific is threaded through as a constructor/call argument instead of
assumed).
"""

from __future__ import annotations

import struct
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QColor,
    QImage,
    QRhi,
    QRhiBuffer,
    QRhiColorAttachment,
    QRhiDepthStencilClearValue,
    QRhiGraphicsPipeline,
    QRhiReadbackDescription,
    QRhiReadbackResult,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiTexture,
    QRhiTextureCopyDescription,
    QRhiRenderPassDescriptor,
    QRhiTextureRenderTarget,
    QRhiTextureRenderTargetDescription,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
    QShader,
)

from shared.rendering.tile_debug import dump_tile_image, log_tile_event, tile_dump_enabled
from shared.rendering.tile_mip import mip_level_count, mip_level_pixel_size

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"


def _load_mip_downsample_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


class MipCascadeGenerator:
    """Owns the downsample pipeline/uniform-buffer/SRB-cache/scratch-textures
    needed to regenerate mips for a tab's tile-array texture(s). Callers own
    the ``tile_arrays`` list itself (and whatever grows it) -- this class only
    ever reads from it, indexed by ``array_index``.
    """

    def __init__(
        self,
        *,
        rhi_getter: Callable[[], QRhi | None],
        tile_arrays: list,
        ensure_tile_array: Callable[[int], None],
        sampler_getter: Callable[[], QRhiSampler | None],
        layer_px: int,
        name_prefix: str = "canvas",
    ) -> None:
        self._rhi_getter = rhi_getter
        self._tile_arrays = tile_arrays
        self._ensure_tile_array = ensure_tile_array
        self._sampler_getter = sampler_getter
        self._layer_px = layer_px
        self._name_prefix = name_prefix

        self._downsample_pipeline: QRhiGraphicsPipeline | None = None
        self._downsample_render_pass_descriptor: QRhiRenderPassDescriptor | None = None
        self._downsample_uniform_buffer: QRhiBuffer | None = None
        self._downsample_slot_stride = 16
        self._downsample_slot_capacity = 0
        self._downsample_srb_cache: dict[int, QRhiShaderResourceBindings] = {}
        # Frame-invariant (depends only on the QRhi backend, not on any
        # per-draw state): written once, on first use, then never rewritten.
        self._downsample_corr_buffer = None
        self._downsample_corr_written = False
        # Keyed by (width, height): a scratch (non-array) render target the
        # cascade renders each level into, then copies from -- see
        # generate_all_dirty_mips for why this can't render straight into
        # tile_arrays.
        self._downsample_scratch_textures: dict[tuple[int, int], QRhiTexture] = {}
        self._downsample_scratch_targets: dict[tuple[int, int], QRhiTextureRenderTarget] = {}
        # IMGSLI_TILE_DUMP-only (see _flush_debug_readbacks): QRhi's Python
        # bindings don't expose QRhiReadbackResult.completed, so instead of a
        # completion callback this polls result.data() on the next call --
        # by then the GPU has virtually always finished the prior frame.
        self._debug_pending_readbacks: list[tuple[QRhiReadbackResult, int, int, int, int]] = []

    @property
    def _rhi(self) -> QRhi:
        rhi = self._rhi_getter()
        assert rhi is not None
        return rhi

    def release(self) -> None:
        resources = [
            self._downsample_pipeline,
            self._downsample_render_pass_descriptor,
            *self._downsample_srb_cache.values(),
            self._downsample_uniform_buffer,
            self._downsample_corr_buffer,
            *self._downsample_scratch_targets.values(),
            *self._downsample_scratch_textures.values(),
        ]
        for resource in resources:
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self._downsample_pipeline = None
        self._downsample_render_pass_descriptor = None
        self._downsample_uniform_buffer = None
        self._downsample_slot_capacity = 0
        self._downsample_srb_cache = {}
        self._downsample_corr_buffer = None
        self._downsample_corr_written = False
        self._downsample_scratch_textures = {}
        self._downsample_scratch_targets = {}
        self._debug_pending_readbacks = []

    def _mip_level_count(self) -> int:
        return mip_level_count(self._layer_px)

    def _mip_level_pixel_size(self, level: int) -> QSize:
        return QSize(*mip_level_pixel_size(self._layer_px, level))

    def _ensure_downsample_pipeline(self) -> None:
        if self._downsample_pipeline is not None:
            return
        rhi = self._rhi
        self._ensure_tile_array(0)
        probe_attachment = QRhiColorAttachment(self._tile_arrays[0])
        probe_attachment.setLayer(0)
        probe_attachment.setLevel(1)
        probe_target = rhi.newTextureRenderTarget(
            QRhiTextureRenderTargetDescription(probe_attachment)
        )
        probe_rpdesc = probe_target.newCompatibleRenderPassDescriptor()
        probe_target.setRenderPassDescriptor(probe_rpdesc)
        if not probe_target.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} probe mip render target"
            )

        pipeline = rhi.newGraphicsPipeline()
        pipeline.setName(f"{self._name_prefix}-mip-downsample-pipeline".encode())
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    _load_mip_downsample_shader("mip_downsample.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    _load_mip_downsample_shader("mip_downsample.frag.qsb"),
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(probe_target.sampleCount())
        pipeline.setRenderPassDescriptor(probe_rpdesc)

        input_layout = QRhiVertexInputLayout()
        input_layout.setBindings([QRhiVertexInputBinding(16)])
        input_layout.setAttributes(
            [
                QRhiVertexInputAttribute(
                    0, 0, QRhiVertexInputAttribute.Format.Float2, 0
                ),
                QRhiVertexInputAttribute(
                    0, 1, QRhiVertexInputAttribute.Format.Float2, 8
                ),
            ]
        )
        pipeline.setVertexInputLayout(input_layout)

        self._ensure_downsample_uniform_buffer()
        pipeline.setShaderResourceBindings(self._ensure_downsample_srb(0))
        if not pipeline.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} mip-downsample pipeline"
            )

        self._downsample_pipeline = pipeline
        self._downsample_render_pass_descriptor = probe_rpdesc
        # Only needed to obtain probe_rpdesc; the actual per-(layer, level)
        # targets used at draw time are separate objects (see
        # _ensure_downsample_scratch) so this one is disposable.
        probe_target.destroy()

    def _ensure_downsample_uniform_buffer(self, slot_count: int = 1) -> None:
        """Growable, multi-slot ``UBuf`` buffer for ``generate_all_dirty_mips`` --
        one slot per (layer, level) draw needed in a frame, strided via
        ``rhi.ubufAligned`` so each draw can select its own slot with
        ``setShaderResources(srb, 1, (0, slot_index * stride))``.

        A shared ``Dynamic`` uniform buffer rewritten between passes in the
        same frame is not guaranteed visible only to the pass it was meant
        for on every QRhi backend -- this codebase hit that exact bug twice
        (see docs/dev/rendering/investigations/multitile-uniform-desync.md),
        producing permanent GPU-resident mip corruption. The fix: grow to fit
        the whole frame's draws, write every slot in one pre-pass batch, bind
        with a dynamic offset, and never touch the buffer between passes."""
        rhi = self._rhi
        slot_count = max(1, slot_count)
        stride = rhi.ubufAligned(16)
        self._downsample_slot_stride = stride
        if (
            self._downsample_uniform_buffer is not None
            and slot_count <= self._downsample_slot_capacity
        ):
            return
        new_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            stride * slot_count,
        )
        new_buffer.setName(f"{self._name_prefix}-mip-downsample-ubuf".encode())
        if not new_buffer.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} mip-downsample uniform buffer"
            )
        old_buffer = self._downsample_uniform_buffer
        self._downsample_uniform_buffer = new_buffer
        self._downsample_slot_capacity = slot_count
        for srb in self._downsample_srb_cache.values():
            try:
                srb.destroy()
            except RuntimeError:
                pass
        self._downsample_srb_cache.clear()
        if old_buffer is not None:
            try:
                old_buffer.destroy()
            except RuntimeError:
                pass

    def _ensure_downsample_corr_buffer(self):
        """Vertex-stage-only ``mat4`` applying an unconditional Y-flip -- NOT
        ``rhi.clipSpaceCorrMatrix()`` (tried first, empirically confirmed a
        no-op: identity on this project's OpenGL backend). The scratch
        render targets this cascade draws into are never composited to
        screen (no visible ``QRhiWidget`` backing-store blit to absorb a
        convention mismatch), the same situation as the offscreen
        ``grabFramebuffer()``-only export canvas in
        docs/dev/rendering/qrhi-gotchas.md's "Offscreen scissor Y-flip" case
        -- there, the fix was to flip unconditionally rather than gate on
        ``isYUpInFramebuffer()``, since that gating only holds for a target
        whose *later* on-screen compositing step cancels one flip out.
        Without a matching unconditional flip here, each generated mip level
        samples the previous level (itself already flipped once by this same
        pass) and re-flips on write, so levels alternate orientation by
        parity -- exactly the flipped/shrunk-tile symptom, and why it showed
        up one mip transition apart rather than uniformly. Depends only on
        this invariant, not on any per-draw state, so it's created once and
        never rewritten."""
        if self._downsample_corr_buffer is not None:
            return self._downsample_corr_buffer
        buffer = self._rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            64,
        )
        buffer.setName(f"{self._name_prefix}-mip-downsample-corr".encode())
        if not buffer.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} mip-downsample corr-matrix buffer"
            )
        self._downsample_corr_buffer = buffer
        self._downsample_corr_written = False
        return buffer

    def _ensure_downsample_srb(self, array_index: int):
        cached = self._downsample_srb_cache.get(array_index)
        if cached is not None:
            return cached
        self._ensure_downsample_uniform_buffer()
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        vertex = QRhiShaderResourceBinding.StageFlag.VertexStage
        srb = self._rhi.newShaderResourceBindings()
        sampler = self._sampler_getter()
        assert sampler is not None
        assert self._downsample_uniform_buffer is not None
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBufferWithDynamicOffset(
                    0, fragment, self._downsample_uniform_buffer, 16
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    1,
                    fragment,
                    self._tile_arrays[array_index],
                    sampler,
                ),
                QRhiShaderResourceBinding.uniformBuffer(
                    2, vertex, self._ensure_downsample_corr_buffer()
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} mip-downsample "
                "shader resource bindings"
            )
        self._downsample_srb_cache[array_index] = srb
        return srb

    def _ensure_downsample_scratch(self, size: QSize):
        """A plain (non-array) render target sized for one mip level, reused
        across every ``(array_index, layer)`` at that level.

        The cascade renders into this instead of straight into
        ``tile_arrays[array_index]`` -- rendering directly into the array
        texture while also sampling that same array texture's previous level
        via the downsample SRB in the same pass trips QRhi's "used with
        different accesses within the same pass" validation. Writing here (a
        different QRhiTexture object) and copying into the array afterwards,
        outside any pass, avoids that."""
        rhi = self._rhi
        key = (size.width(), size.height())
        cached_target = self._downsample_scratch_targets.get(key)
        if cached_target is not None:
            return self._downsample_scratch_textures[key], cached_target
        texture = rhi.newTexture(
            QRhiTexture.Format.RGBA8,
            size,
            1,
            QRhiTexture.Flag.RenderTarget | QRhiTexture.Flag.UsedAsTransferSource,
        )
        texture.setName(
            f"{self._name_prefix}-mip-downsample-scratch-"
            f"{size.width()}x{size.height()}".encode()
        )
        if not texture.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} mip-downsample scratch texture"
            )
        attachment = QRhiColorAttachment(texture)
        target = rhi.newTextureRenderTarget(
            QRhiTextureRenderTargetDescription(attachment)
        )
        assert self._downsample_render_pass_descriptor is not None
        target.setRenderPassDescriptor(self._downsample_render_pass_descriptor)
        if not target.create():
            texture.destroy()
            raise RuntimeError(
                f"Failed to create {self._name_prefix} mip-downsample "
                "scratch render target"
            )
        self._downsample_scratch_textures[key] = texture
        self._downsample_scratch_targets[key] = target
        return texture, target

    def _flush_debug_readbacks(self) -> None:
        """IMGSLI_TILE_DUMP-only: drains readbacks issued by a prior call to
        ``generate_all_dirty_mips``, dumping each completed one as a PNG
        alongside a ``mip.cascade.readback`` JSONL event -- lets a suspect
        ``(array_index, layer, level)`` from ``mip.cascade.draw`` be visually
        inspected instead of only reasoned about from bookkeeping."""
        if not self._debug_pending_readbacks:
            return
        still_pending = []
        for result, array_index, layer, level, slot_index in self._debug_pending_readbacks:
            data = result.data
            if not data:
                still_pending.append((result, array_index, layer, level, slot_index))
                continue
            size = result.pixelSize
            image = QImage(
                bytes(data),  # type: ignore[call-overload]  # QByteArray supports buffer protocol
                size.width(),
                size.height(),
                QImage.Format.Format_RGBA8888,
            ).copy()
            name = (
                f"mip_readback_{self._name_prefix}_a{array_index}_l{layer}"
                f"_lvl{level}_slot{slot_index}"
            )
            path = dump_tile_image(image, name)
            log_tile_event(
                "mip.cascade.readback",
                name_prefix=self._name_prefix,
                array_index=array_index,
                layer=layer,
                level=level,
                slot_index=slot_index,
                image_path=path,
            )
        self._debug_pending_readbacks = still_pending

    def generate_all_dirty_mips(
        self,
        command_buffer,
        vertex_buffer,
        dirty_layers: dict[int, set[int]],
        time_budget_ms: float | None = None,
    ) -> dict[int, set[int]]:
        """Regenerates the mip chains for every ``(array_index, layer)`` pair
        in ``dirty_layers`` -- the Phase 9 replacement for
        ``updates.generateMips(tile_arrays[array_index])``, which touches
        every layer of the array (profiled at up to ~130ms per call, the true
        dominant cost behind visible tile erase-then-redraw flicker during LOD
        transitions, dwarfing the per-tile crop/upload cost this same array
        design already optimizes).

        Cascades level 1 up from level 0 (the just-uploaded content) for each
        dirty layer, each level rendered from the previous one via a single
        textureLod sample (mip_downsample.frag) into a size-matched *scratch*
        render target, then copied into its real ``(layer, level)`` slot of
        ``tile_arrays[array_index]`` via a ``copyTexture`` resource update.

        Must be called only after the tile upload(s) for these layers have
        already been submitted to the GPU (i.e. after
        ``command_buffer.resourceUpdate(updates)``, not merely enqueued into
        an unsubmitted batch) -- this reads back the texture it's sampling
        from, which a same-batch write does not guarantee visibility for.

        When ``time_budget_ms`` is given, the wall-clock check happens before
        every single pass (not just between whole layers -- a per-layer-only
        check let one costly trailing layer's first-time render-target/SRB
        creation blow the budget in one uninterruptible lump). A layer left
        with only some of its mip levels refreshed this call is reported back
        to the caller wholesale (not the specific levels done) -- the next
        call simply redoes its full cascade from level 0, which is idempotent
        and cheap relative to the render-target creation cost that dominates
        a first touch. Returns any deferred ``(array_index, layer)`` pairs so
        the caller can fold them back into next frame's ``dirty_layers``."""
        if tile_dump_enabled():
            self._flush_debug_readbacks()
        if not dirty_layers:
            return {}
        self._ensure_downsample_pipeline()
        level_count = self._mip_level_count()

        groups: list[tuple[int, int]] = [
            (array_index, layer)
            for array_index, layers in dirty_layers.items()
            for layer in layers
        ]
        if not groups:
            return {}

        draws: list[tuple[int, int, int]] = [
            (array_index, layer, level)
            for array_index, layer in groups
            for level in range(1, level_count)
        ]

        rhi = self._rhi
        self._ensure_downsample_uniform_buffer(len(draws))
        stride = self._downsample_slot_stride
        slot_updates = rhi.nextResourceUpdateBatch()
        if not self._downsample_corr_written:
            # Unconditional Y-flip (see _ensure_downsample_corr_buffer) --
            # diagonal, so row-major vs. column-major storage of the mat4
            # doesn't matter here.
            flip_data = (
                1.0, 0.0, 0.0, 0.0,
                0.0, -1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            )
            assert self._downsample_corr_buffer is not None
            slot_updates.updateDynamicBuffer(
                self._downsample_corr_buffer,
                0,
                struct.pack("<16f", *flip_data),
            )
            self._downsample_corr_written = True
        for slot_index, (array_index, layer, level) in enumerate(draws):
            src_level = level - 1
            assert self._downsample_uniform_buffer is not None
            slot_updates.updateDynamicBuffer(
                self._downsample_uniform_buffer,
                slot_index * stride,
                struct.pack("<iiii", layer, src_level, 0, 0),
            )
        command_buffer.resourceUpdate(slot_updates)

        start = time.monotonic()
        slot_index = 0
        processed_groups = 0
        group_incomplete = False
        for _group_array_index, _group_layer in groups:
            for _ in range(1, level_count):
                if (
                    time_budget_ms is not None
                    and slot_index > 0
                    and (time.monotonic() - start) * 1000.0 >= time_budget_ms
                ):
                    group_incomplete = True
                    break
                array_index, layer, level = draws[slot_index]
                target_size = self._mip_level_pixel_size(level)
                scratch_texture, target = self._ensure_downsample_scratch(
                    target_size
                )
                srb = self._ensure_downsample_srb(array_index)
                if tile_dump_enabled():
                    log_tile_event(
                        "mip.cascade.draw",
                        name_prefix=self._name_prefix,
                        slot_index=slot_index,
                        array_index=array_index,
                        layer=layer,
                        level=level,
                        src_level=level - 1,
                        target_w=target_size.width(),
                        target_h=target_size.height(),
                        scratch_id=id(scratch_texture),
                        srb_id=id(srb),
                    )
                command_buffer.beginPass(
                    target,
                    QColor(0, 0, 0, 0),
                    QRhiDepthStencilClearValue(1.0, 0),
                    None,
                )
                command_buffer.setGraphicsPipeline(self._downsample_pipeline)
                command_buffer.setViewport(
                    QRhiViewport(
                        0.0,
                        0.0,
                        float(target_size.width()),
                        float(target_size.height()),
                    )
                )
                command_buffer.setVertexInput(0, [(vertex_buffer, 0)])
                command_buffer.setShaderResources(srb, 1, (0, slot_index * stride))
                command_buffer.draw(4)
                command_buffer.endPass()

                # Copy the freshly-downsampled scratch content into its real
                # slot in the array, outside any pass -- the next level's SRB
                # samples this array texture's now-updated level as its
                # source, and the level after that needs this one visible.
                copy_updates = rhi.nextResourceUpdateBatch()
                copy_desc = QRhiTextureCopyDescription()
                copy_desc.setDestinationLayer(layer)
                copy_desc.setDestinationLevel(level)
                copy_desc.setPixelSize(target_size)
                copy_updates.copyTexture(
                    self._tile_arrays[array_index], scratch_texture, copy_desc
                )
                if tile_dump_enabled():
                    rb_desc = QRhiReadbackDescription(self._tile_arrays[array_index])
                    rb_desc.setLayer(layer)
                    rb_desc.setLevel(level)
                    rb_result = QRhiReadbackResult()
                    copy_updates.readBackTexture(rb_desc, rb_result)
                    self._debug_pending_readbacks.append(
                        (rb_result, array_index, layer, level, slot_index)
                    )
                command_buffer.resourceUpdate(copy_updates)

                slot_index += 1
            if group_incomplete:
                break
            processed_groups += 1

        deferred: dict[int, set[int]] = {}
        for array_index, layer in groups[processed_groups:]:
            deferred.setdefault(array_index, set()).add(layer)
        return deferred
