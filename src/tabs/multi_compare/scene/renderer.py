"""QRhi renderer orchestration for the multi-compare scene.

The widget owns interaction and state.  The renderer owns QRhi resources,
texture uploads, per-frame projection, and command recording.  This mirrors the
main image-compare split where ``RhiCanvasRenderer`` is separate from the
canvas widget and feature passes.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiDepthStencilClearValue,
    QRhiSampler,
    QRhiTexture,
)

from tabs.multi_compare.canvas.registry import registry
from tabs.multi_compare.scene.passes import BaseImagesPass
from tabs.multi_compare.scene.projection import build_render_context
from ui.widgets.canvas.render_executor import iter_active_render_passes
from ui.widgets.canvas.rhi_backend import log_initialized_rhi_widget

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareRhiRenderer:
    """Persistent QRhi renderer for ``MultiCompareCanvasWidget``.

    ``image_pass`` (base image tiles) is core-owned and always wired
    directly, first — mirrors how image_compare's own base-image draw is
    hardcoded ahead of its feature passes (see
    MULTI_COMPARE_QRHI_REFACTOR.md A6). ``feature_passes`` are discovered
    through the shared canvas feature registry, same as image_compare
    (``rhi_renderer/__init__.py``'s ``initialize()``).
    """

    def __init__(self, host) -> None:
        self.host = host
        self.rhi = None
        self.target = None
        self.sampler = None
        self.placeholder = None
        self.image_pass = BaseImagesPass()
        self.feature_passes: list = []
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
            logger.warning(
                "[mc-renderer] initialize() aborted: rhi or renderTarget is None "
                "(widget not properly realized yet)"
            )
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
        command_buffer.resourceUpdate(upload)

        self.feature_passes = [
            type(render_pass)() for render_pass in registry().get_render_passes()
        ]
        for render_pass in self.feature_passes:
            render_pass.initialize(self.rhi, target)

        self.initialized = True
        self.host._sync_textures()

    def release(self) -> None:
        self.image_pass.release()
        for render_pass in self.feature_passes:
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
            if not getattr(self, "_logged_not_initialized", False):
                self._logged_not_initialized = True
                logger.warning(
                    "[mc-renderer] render() called before initialize() completed "
                    "(initialized=%s rhi=%s)",
                    self.initialized,
                    self.rhi is not None,
                )
            return False
        target = self.host.renderTarget()
        if target is None:
            if not getattr(self, "_logged_no_target", False):
                self._logged_no_target = True
                logger.warning("[mc-renderer] render() aborted: renderTarget() is None")
            return False
        target_size = target.pixelSize()
        fb_w = float(target_size.width())
        fb_h = float(target_size.height())

        updates = self.rhi.nextResourceUpdateBatch()
        self.host._sync_textures()
        self.image_pass.apply_pending_texture_ops(self, updates)

        composition = self.host._active_composition
        clear_color = self.host._theme_or_palette_bg()
        ctx = build_render_context(
            composition=composition,
            framebuffer_size=(fb_w, fb_h),
            clip_matrix=tuple(float(v) for v in self.rhi.clipSpaceCorrMatrix().data()),
            available_slot_ids=set(self.image_pass.slot_texture_ids()),
            widget=self.host,
        )
        self.image_pass.prepare(self, ctx, updates)

        active_feature_passes = iter_active_render_passes(ctx, self.feature_passes)
        for render_pass in active_feature_passes:
            render_pass.prepare(self.host, ctx, updates)

        command_buffer.beginPass(
            target,
            self.host._theme_or_palette_bg(),
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )
        self.image_pass.record(self, ctx, command_buffer)
        for render_pass in active_feature_passes:
            render_pass.record(command_buffer, self.host, ctx)
        command_buffer.endPass()
        return True
