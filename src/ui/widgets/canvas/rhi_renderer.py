from __future__ import annotations

import logging
import os
import struct
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
    QShader,
)

from .render_common import should_render_blank_white
from .render_context import build_render_runtime_context
from .render_executor import iter_active_render_passes
from .texture_parts.upload_queue import queue_texture_upload

logger = logging.getLogger("ImproveImgSLI")

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_BLOCK_SIZE = 144
_VERTICES = struct.pack(
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


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def _rhi_render_debug_enabled() -> bool:
    return _env_flag("IMGSLI_RESIZE_DEBUG")


def _rhi_render_debug(message: str, *args) -> None:
    if _rhi_render_debug_enabled():
        logger.debug("[rhi-render-debug] " + message, *args)


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {name}")
    return shader


def pack_base_uniforms(rhi, base_image, *, diff_source_ready: bool) -> bytes:
    matrix = tuple(float(value) for value in rhi.clipSpaceCorrMatrix().data())
    return struct.pack(
        "<28f4if3f",
        *matrix,
        float(base_image.pan_offset_x),
        float(base_image.pan_offset_y),
        float(base_image.zoom),
        float(base_image.split_position),
        *base_image.letterbox1,
        *base_image.letterbox2,
        int(bool(base_image.is_horizontal)),
        int(base_image.channel_mode_int),
        int(base_image.diff_mode_int),
        int(bool(diff_source_ready)),
        20.0 / 255.0,
        0.0,
        0.0,
        0.0,
    )


class RhiCanvasRenderer:
    def __init__(self) -> None:
        self.rhi = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.samplers: dict[str, object] = {}
        self.textures: dict[object, object] = {}
        self.texture_sizes: dict[object, QSize] = {}
        self.srb = None
        self.pipeline = None
        self._srb_signature = None
        self._render_pass_descriptor = None
        self.feature_passes: list[object] = []

    def initialize(self, widget, command_buffer: QRhiCommandBuffer) -> None:
        self.release()
        self.rhi = widget.rhi()
        if self.rhi is None:
            raise RuntimeError("QRhiWidget.initialize called without QRhi")

        self.vertex_buffer = self.rhi.newBuffer(
            QRhiBuffer.Type.Immutable,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(_VERTICES),
        )
        self.vertex_buffer.setName(b"canvas-quad")
        if not self.vertex_buffer.create():
            raise RuntimeError("Failed to create canvas vertex buffer")

        self.uniform_buffer = self.rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_BLOCK_SIZE,
        )
        self.uniform_buffer.setName(b"canvas-uniforms")
        if not self.uniform_buffer.create():
            raise RuntimeError("Failed to create canvas uniform buffer")

        for name, filter_mode in (
            ("nearest", QRhiSampler.Filter.Nearest),
            ("linear", QRhiSampler.Filter.Linear),
        ):
            sampler = self.rhi.newSampler(
                filter_mode,
                filter_mode,
                QRhiSampler.Filter.None_,
                QRhiSampler.AddressMode.ClampToEdge,
                QRhiSampler.AddressMode.ClampToEdge,
            )
            sampler.setName(f"canvas-{name}-sampler".encode())
            if not sampler.create():
                raise RuntimeError(f"Failed to create {name} sampler")
            self.samplers[name] = sampler

        placeholder = QImage(1, 1, QImage.Format.Format_RGBA8888)
        placeholder.fill(0)
        updates = self.rhi.nextResourceUpdateBatch()
        updates.uploadStaticBuffer(self.vertex_buffer, _VERTICES)
        self._replace_texture("placeholder", placeholder, updates)
        command_buffer.resourceUpdate(updates)
        self._ensure_pipeline(widget)
        from ui.canvas_infra.scene.pass_registry import get_canvas_render_passes

        self.feature_passes = [
            type(render_pass)() for render_pass in get_canvas_render_passes()
        ]
        target = widget.renderTarget()
        _rhi_render_debug(
            "initialize widget=%s size=%dx%d target_px=%s api=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target.pixelSize() if target is not None else None,
            getattr(widget.api(), "name", "unknown"),
        )
        for render_pass in self.feature_passes:
            render_pass.initialize(self.rhi, target)
        self._restore_texture_uploads(widget)

    def release(self) -> None:
        resources = [
            self.pipeline,
            self.srb,
            *self.textures.values(),
            *self.samplers.values(),
            self.uniform_buffer,
            self.vertex_buffer,
        ]
        for resource in resources:
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        for render_pass in self.feature_passes:
            render_pass.release()
        self.__init__()

    def _replace_texture(self, key, image: QImage, updates) -> None:
        if self.srb is not None:
            self.srb.destroy()
            self.srb = None
            self._srb_signature = None
        old_texture = self.textures.pop(key, None)
        if old_texture is not None:
            old_texture.destroy()

        texture = self.rhi.newTexture(
            QRhiTexture.Format.RGBA8,
            image.size(),
        )
        texture.setName(f"canvas-{key}".encode())
        if not texture.create():
            raise RuntimeError(f"Failed to create texture {key} at {image.size()}")
        self.textures[key] = texture
        self.texture_sizes[key] = image.size()
        updates.uploadTexture(texture, image)

    def _apply_pending_uploads(self, widget, updates) -> None:
        pending = widget.runtime_state._pending_texture_uploads
        while pending:
            key, image, _slot = pending.pop(0)
            if not isinstance(image, QImage) or image.isNull():
                continue
            size_changed = self.texture_sizes.get(key) != image.size()
            if key not in self.textures or size_changed:
                self._replace_texture(key, image, updates)
            else:
                updates.uploadTexture(self.textures[key], image)

    @staticmethod
    def _restore_texture_uploads(widget) -> None:
        state = widget.runtime_state
        if state._pending_texture_uploads:
            return
        cache = getattr(state, "_texture_upload_cache", {}) or {}
        restored_from_cache = 0
        for slot, texture_key in enumerate(widget.texture_ids):
            cached = cache.get(texture_key)
            if cached is not None:
                state._pending_texture_uploads.append((texture_key, cached, slot))
                state._images_uploaded[slot] = True
                restored_from_cache += 1
            else:
                image = state._stored_pil_images[slot]
                queue_texture_upload(widget, image, texture_key, slot)
        for slot, texture_key in enumerate(widget._source_texture_ids):
            cached = cache.get(texture_key)
            if cached is not None:
                state._pending_texture_uploads.append((texture_key, cached, None))
                restored_from_cache += 1
            else:
                image = state._source_pil_images[slot]
                queue_texture_upload(widget, image, texture_key)
        diff_key = widget._diff_source_texture_id
        cached_diff = cache.get(diff_key)
        if cached_diff is not None:
            state._pending_texture_uploads.append((diff_key, cached_diff, None))
            restored_from_cache += 1
        elif state._diff_source_pil_image is not None:
            queue_texture_upload(widget, state._diff_source_pil_image, diff_key)
        _rhi_render_debug(
            "restore texture uploads widget=%s pending=%d cache_hits=%d",
            f"{type(widget).__name__}@{id(widget):x}",
            len(state._pending_texture_uploads),
            restored_from_cache,
        )

    def _ensure_srb(
        self, texture_keys: tuple[object, object, object], sampler_name: str
    ) -> None:
        signature = (*texture_keys, sampler_name)
        if self.srb is not None and signature == self._srb_signature:
            return

        if self.srb is not None:
            self.srb.destroy()
        sampler = self.samplers[sampler_name]
        placeholder = self.textures["placeholder"]
        textures = [self.textures.get(key, placeholder) for key in texture_keys]
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        self.srb = self.rhi.newShaderResourceBindings()
        self.srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, textures[0], sampler
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    2, fragment, textures[1], sampler
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    3, fragment, textures[2], sampler
                ),
            ]
        )
        if not self.srb.create():
            raise RuntimeError("Failed to create canvas shader resource bindings")
        self._srb_signature = signature

    def _ensure_pipeline(self, widget) -> None:
        target = widget.renderTarget()
        if target is None:
            return
        descriptor = target.renderPassDescriptor()
        if self.pipeline is not None and descriptor is self._render_pass_descriptor:
            return
        if self.pipeline is not None:
            self.pipeline.destroy()

        self._ensure_srb(("placeholder", "placeholder", "placeholder"), "linear")
        pipeline = self.rhi.newGraphicsPipeline()
        pipeline.setName(b"canvas-base-pipeline")
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("base.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, _load_shader("base.frag.qsb")
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(target.sampleCount())
        pipeline.setShaderResourceBindings(self.srb)
        pipeline.setRenderPassDescriptor(descriptor)

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

        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        pipeline.setTargetBlends([blend])

        if not pipeline.create():
            raise RuntimeError("Failed to create canvas graphics pipeline")
        self.pipeline = pipeline
        self._render_pass_descriptor = descriptor

    def render(self, widget, command_buffer, clear_color) -> None:
        target = widget.renderTarget()
        if target is None or self.rhi is None:
            _rhi_render_debug(
                "render skip widget=%s target=%r rhi=%r",
                f"{type(widget).__name__}@{id(widget):x}",
                target,
                self.rhi,
            )
            return
        self._ensure_pipeline(widget)

        updates = self.rhi.nextResourceUpdateBatch()
        self._apply_pending_uploads(widget, updates)
        ctx = build_render_runtime_context(widget)
        base_image = getattr(ctx.render_list, "base_image", None)
        should_draw = (
            base_image is not None
            and any(ctx.images_uploaded)
            and not should_render_blank_white(ctx.scene_frame)
        )
        target_size = target.pixelSize()
        _rhi_render_debug(
            "render begin widget=%s widget=%dx%d target_px=%dx%d clear=rgba(%d,%d,%d,%d) "
            "images=%s should_draw=%s passes=%d fixed=%dx%d",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target_size.width(),
            target_size.height(),
            clear_color.red(),
            clear_color.green(),
            clear_color.blue(),
            clear_color.alpha(),
            list(ctx.images_uploaded),
            should_draw,
            len(self.feature_passes),
            widget.fixedColorBufferSize().width(),
            widget.fixedColorBufferSize().height(),
        )

        if should_draw:
            texture_keys = (
                tuple(ctx.source_texture_ids)
                if base_image.use_hires
                else tuple(ctx.texture_ids)
            )
            diff_key = (
                ctx.diff_source_texture_id if ctx.diff_source_ready else "placeholder"
            )
            sampler_name = (
                "nearest"
                if str(ctx.scene_frame.zoom_interpolation_method).upper() == "NEAREST"
                else "linear"
            )
            self._ensure_srb((texture_keys[0], texture_keys[1], diff_key), sampler_name)
            updates.updateDynamicBuffer(
                self.uniform_buffer,
                0,
                pack_base_uniforms(
                    self.rhi,
                    base_image,
                    diff_source_ready=ctx.diff_source_ready,
                ),
            )
        active_feature_passes = iter_active_render_passes(ctx, self.feature_passes)
        for render_pass in active_feature_passes:
            render_pass.prepare(widget, ctx, updates)

        from PySide6.QtGui import QRhiDepthStencilClearValue

        command_buffer.beginPass(
            target,
            clear_color,
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )
        if should_draw:
            size = target.pixelSize()
            command_buffer.setGraphicsPipeline(self.pipeline)
            command_buffer.setViewport(
                QRhiViewport(0.0, 0.0, float(size.width()), float(size.height()))
            )
            command_buffer.setShaderResources(self.srb)
            command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
            command_buffer.draw(4)
        for render_pass in active_feature_passes:
            render_pass.record(command_buffer, widget, ctx)
        command_buffer.endPass()
        _rhi_render_debug(
            "render end widget=%s target_px=%dx%d should_draw=%s",
            f"{type(widget).__name__}@{id(widget):x}",
            target_size.width(),
            target_size.height(),
            should_draw,
        )
