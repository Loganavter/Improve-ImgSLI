"""QRhi render pass for the drag_drop_overlay feature."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from tabs.multi_compare.canvas.rhi_overlay_pass_base import FullscreenOverlayTexturePass
from tabs.multi_compare.debug import mc_dnd_debug, mc_dnd_debug_enabled
from tabs.multi_compare.scene.passes.drag_overlay import DragDropOverlaySource
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole


class DragDropOverlayPass(FullscreenOverlayTexturePass):
    """Rasterizes live drag/drop affordances into their own overlay texture.

    Live-only, interaction-driven — uses ``TRANSIENT_PREVIEW`` stacking (see
    MULTI_COMPARE_QRHI_REFACTOR.md B1). Does *not* set
    ``visibility = SceneVisibility.INTERACTIVE``: ``MultiCompareRenderContext``
    carries no render-mode signal (no ``render_metrics``/``render_intent``),
    so ``iter_active_render_passes``' visibility resolver always defaults to
    ``PREVIEW`` here — an ``INTERACTIVE``-only flag would silently disable
    this pass permanently, including during real drags. `should_paint`'s own
    `state.drag_active` check already gates this correctly (only true during
    an actual interactive drag), so the default `SceneVisibility.ALL` is
    correct and sufficient.
    """

    stack_role = CanvasStackRole.TRANSIENT_PREVIEW

    def __init__(self) -> None:
        super().__init__()
        self._source = DragDropOverlaySource()
        self._dbg_was_active = False
        self._dbg_recorded = False

    def should_paint(self, ctx) -> bool:
        if ctx.widget is None:
            return False
        return self._source.should_paint(ctx.composition, ctx.widget.state)

    def _raster(self, widget, ctx) -> QImage | None:
        state = widget.state
        if not self._source.should_paint(ctx.composition, state):
            if self._dbg_was_active:
                self._dbg_was_active = False
                self._source.reset_debug_state()
                if mc_dnd_debug_enabled():
                    mc_dnd_debug(
                        "overlay HIDDEN (drag_active=%s presents=%s)",
                        state.drag_active,
                        getattr(widget, "_rhi_presents_completed", "?"),
                    )
            return None
        self._dbg_was_active = True
        fb_w, fb_h = ctx.framebuffer_size
        img = QImage(
            max(1, int(fb_w)),
            max(1, int(fb_h)),
            QImage.Format.Format_RGBA8888_Premultiplied,
        )
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        dpr = max(1.0, float(widget.devicePixelRatioF()))
        painter.save()
        painter.scale(dpr, dpr)
        self._source.paint(painter, host=widget)
        painter.restore()
        painter.end()
        return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)

    def record(self, command_buffer, widget, ctx) -> None:
        super().record(command_buffer, widget, ctx)
        # COMMIT = the quad was actually written into this frame's command
        # buffer (raster + texture upload in prepare, then draw here).
        # RASTER without COMMIT means the pass produced an image that never
        # reached the framebuffer (culled pass / missing pipeline).
        if not mc_dnd_debug_enabled():
            self._dbg_recorded = bool(self.active and self.pipeline is not None)
            return
        recorded = bool(self.active and self.pipeline is not None)
        if recorded == self._dbg_recorded:
            return
        self._dbg_recorded = recorded
        state = widget.state if widget is not None else None
        if recorded:
            mc_dnd_debug(
                "overlay COMMIT path=%s side=%s presents=%s (quad recorded, awaiting present)",
                getattr(state, "drag_target_path", None),
                getattr(state, "drag_target_side", None),
                getattr(widget, "_rhi_presents_completed", "?"),
            )
        else:
            mc_dnd_debug(
                "overlay quad NOT recorded (active=%s pipeline=%s) — "
                "rasterized but not drawn",
                self.active,
                self.pipeline is not None,
            )


RENDER_PASSES: list[FullscreenOverlayTexturePass] = [DragDropOverlayPass()]
RENDER_PASSES = RENDER_PASSES
