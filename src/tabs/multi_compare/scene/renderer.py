"""QRhi renderer orchestration for the multi-compare scene.

The widget owns interaction and state.  The renderer owns QRhi resources,
texture uploads, per-frame projection, and command recording.  This mirrors the
main image-compare split where ``RhiCanvasRenderer`` is separate from the
canvas widget and feature passes.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiDepthStencilClearValue,
    QRhiSampler,
    QRhiTexture,
)

from tabs.multi_compare.scene.overlay_painter import MultiCompareOverlayPainter
from tabs.multi_compare.scene.passes import BaseImagesPass, OverlayTexturePass
from tabs.multi_compare.scene.projection import build_render_context
from ui.widgets.gl_canvas.rhi_backend import log_initialized_rhi_widget


class MultiCompareRhiRenderer:
    """Persistent QRhi renderer for ``MultiCompareCanvasWidget``."""

    def __init__(self, host) -> None:
        self.host = host
        self.rhi = None
        self.target = None
        self.sampler = None
        self.placeholder = None
        self.overlay_painter = MultiCompareOverlayPainter(host)
        self.image_pass = BaseImagesPass()
        self.overlay_pass = OverlayTexturePass()
        self.passes = (self.image_pass, self.overlay_pass)
        self.initialized = False

    def has_slot_texture(self, slot_id: int) -> bool:
        return self.image_pass.has_slot_texture(slot_id)

    def slot_texture_ids(self) -> list[int]:
        return self.image_pass.slot_texture_ids()

    def queue_upload(self, slot_id: int, image: QImage) -> None:
        self.image_pass.queue_upload(slot_id, image)

    def queue_remove(self, slot_id: int) -> None:
        self.image_pass.queue_remove(slot_id)

    def initialize(self, command_buffer) -> None:
        log_initialized_rhi_widget(self.host)
        rhi = self.host.rhi()
        target = self.host.renderTarget()
        if rhi is None or target is None:
            return
        self.rhi = rhi
        self.target = target

        self.sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        self.sampler.create()

        self.placeholder = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        self.placeholder.create()

        upload = rhi.nextResourceUpdateBatch()
        ph = QImage(1, 1, QImage.Format.Format_RGBA8888)
        ph.fill(0)
        upload.uploadTexture(self.placeholder, ph)
        self.image_pass.initialize(self, target)
        self.overlay_pass.initialize(self, target, upload)
        command_buffer.resourceUpdate(upload)

        self.initialized = True
        self.host._sync_textures()

    def release(self) -> None:
        for render_pass in self.passes:
            render_pass.release()
        for res in (
            self.sampler,
            self.placeholder,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        host = self.host
        self.__init__(host)

    def render(self, command_buffer) -> bool:
        if not self.initialized or self.rhi is None:
            return False
        target = self.host.renderTarget()
        if target is None:
            return False
        target_size = target.pixelSize()
        fb_w = float(target_size.width())
        fb_h = float(target_size.height())

        updates = self.rhi.nextResourceUpdateBatch()
        self.host._sync_textures()
        self.image_pass.apply_pending_texture_ops(self, updates)

        composition = self.host._active_composition
        ctx = build_render_context(
            composition=composition,
            framebuffer_size=(fb_w, fb_h),
            clip_matrix=tuple(float(v) for v in self.rhi.clipSpaceCorrMatrix().data()),
            available_slot_ids=set(self.image_pass.slot_texture_ids()),
        )
        for render_pass in self.passes:
            render_pass.prepare(self, ctx, updates)

        command_buffer.beginPass(
            target,
            self.host._theme_or_palette_bg(),
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )
        for render_pass in self.passes:
            render_pass.record(self, ctx, command_buffer)
        command_buffer.endPass()
        return True
