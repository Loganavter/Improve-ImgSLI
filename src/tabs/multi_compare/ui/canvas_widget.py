"""Canvas host widget for the multi-compare scene.

Input chrome lives in ``canvas/interaction.py``; drop/hit projection in
``ui/drop_targets.py`` and ``ui/hit_projection.py``. Feature gestures stay
under ``canvas/features/*/input/``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QMouseEvent, QPalette, QWheelEvent
from PySide6.QtWidgets import QRhiWidget, QWidget

from ui.widgets.canvas.rhi_backend import configure_rhi_widget

from tabs.multi_compare.canvas import interaction as canvas_interaction
from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
)
from tabs.multi_compare.scene import MultiCompareAction
from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer
from tabs.multi_compare.ui import drop_targets, hit_projection
from tabs.multi_compare.ui.canvas_helpers import (
    INTERNAL_SLOT_MIME,
    _dividers_locked,
    _layout_is_symmetric,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ImproveImgSLI")

# Re-exports for feature modules / tests that import from this module.
__all__ = [
    "INTERNAL_SLOT_MIME",
    "MultiCompareCanvasWidget",
    "_dividers_locked",
    "_layout_is_symmetric",
]


class MultiCompareCanvasWidget(QRhiWidget):
    """QRhi canvas host for multi-compare rendering and input dispatch."""

    ZOOM_MIN = 1.0
    ZOOM_MAX = 50.0
    ZOOM_STEP = 1.1

    firstFrameRendered = Signal()

    dropTargetChanged = None

    def __init__(self, parent: QWidget | None = None, *, translate=None):
        super().__init__(parent)
        configure_rhi_widget(self)
        # Match image_compare's CanvasWidget: never enable QWidget autofill on a
        # QRhiWidget. Autofill + palette clear can fight RHI texture compositing
        # (stale zoom after reset while render() already drew z=1). Clear color
        # stays in the RHI pass via ``_theme_or_palette_bg()``.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._allow_transparent_clear = False
        self.apply_theme_background()
        self._translate = translate or (lambda _key, default=None: default or _key)

        self.state = MultiCompareState()

        self._dispatch: callable | None = None

        self._active_composition = None
        self._export_canvas_viewport: tuple[int, int, int, int] | None = None

        self._renderer = MultiCompareRhiRenderer(self)
        self._first_frame_emitted = False

        self._panning = False
        self._pan_start_pos = QPointF()
        self._pan_start_state = (0.0, 0.0)
        self._pan_ref_rect = QRect()
        self._pan_ref_fit = (1.0, 1.0)

        self._divider_drag: tuple[tuple[int, ...], int, str, list[float]] | None = None
        self._divider_start_cursor = QPointF()

        self._lmb_press_pos: QPointF | None = None
        self._lmb_press_slot_id: int | None = None
        self._view_update_pending = False
        self._color_buffer_frozen = False

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_state(self, state: MultiCompareState) -> None:
        self.state = state
        self._sync_textures()
        self._rebuild_composition()
        self.request_view_update()

    def request_view_update(self) -> None:
        """Ensure the QRhi backing store re-composites after view changes.

        Immediate ``update()`` plus a next-tick pass so overlay hide/show in
        the same stack frame (zoom-reset chip) cannot leave a stale frame.
        """
        self.update()
        if self._view_update_pending:
            return
        self._view_update_pending = True
        QTimer.singleShot(0, self._flush_view_update)

    def _flush_view_update(self) -> None:
        self._view_update_pending = False
        if not self.isVisible():
            return
        self.update()

    def is_color_buffer_frozen(self) -> bool:
        fixed = self.fixedColorBufferSize()
        return bool(fixed.isValid() and fixed.width() > 0 and fixed.height() > 0)

    def freeze_color_buffer(self) -> bool:
        """Pin the GPU color buffer (same idea as main-window CSD resize freeze).

        Popup / CSD micro-geometry must not recreate the swapchain or
        re-letterbox ``ox/oy/sr`` while a zoomed frame is on screen — that
        looks like a zoom nudge even when ``zoom``/``pan`` are unchanged.
        """
        try:
            if self.is_color_buffer_frozen():
                self._color_buffer_frozen = True
                return True
            size = self.size()
            if size.width() <= 0 or size.height() <= 0:
                return False
            self.setFixedColorBufferSize(size)
            self._color_buffer_frozen = True
            return True
        except Exception:
            logger.exception("freeze_color_buffer failed")
            return False

    def unfreeze_color_buffer(self) -> None:
        """Clear a fixed color buffer pin and request one present."""
        try:
            self.setFixedColorBufferSize(QSize())
        except Exception:
            logger.exception("unfreeze_color_buffer failed")
        self._color_buffer_frozen = False
        if self.isVisible():
            self.update()

    def render(self, command_buffer) -> None:
        painted = self._renderer.render(command_buffer)
        if painted and not self._first_frame_emitted:
            self._first_frame_emitted = True
            self.firstFrameRendered.emit()

    def setAutoFillBackground(self, enabled) -> None:  # noqa: N802 — Qt API
        # Intentionally ignore — see __init__ comment. Image compare does the same.
        return

    def resizeEvent(self, event) -> None:  # noqa: D401 — Qt signature
        super().resizeEvent(event)
        # Skip no-op geometry churn and any resize while the color buffer is
        # pinned for a popup/CSD interaction (context menu, window drag).
        if event.size() == event.oldSize():
            return
        if self._color_buffer_frozen or self.is_color_buffer_frozen():
            return
        self.request_view_update()

    def set_dispatch(self, dispatch) -> None:
        """Install the redux dispatch callable used for interaction-driven changes."""
        self._dispatch = dispatch

    def _do_dispatch(self, action: MultiCompareAction) -> None:
        if self._dispatch is not None:
            self._dispatch(action)

    def _rebuild_composition(self) -> None:
        """Build the CompositionPlan from state and apply it to ``self``.

        ``_active_composition`` ends up holding a ``ResolvedComposition`` —
        the flat list of textured-quad layers in canvas-px that ``render()``
        consumes. Canvas size = native canvas (computed from image extents)
        so live and export share the same canon; ``sr = min(fb/canvas)`` is
        applied once in ``render()`` to project canvas-px into framebuffer-px.
        """
        from tabs.multi_compare.services.composition_builder import (
            build_composition_plan,
        )
        from ui.canvas_presentation.composition import resolve_composition

        plan = build_composition_plan(self.state)
        if plan is None:
            self._active_composition = None
            return
        self._active_composition = resolve_composition(plan)

    # --- drop / hit projection (thin wrappers for features + tests) ---

    def compute_drop_target(
        self, pos: QPoint, *, include_center: bool = False
    ) -> tuple[tuple[int, ...] | None, str | None, bool, int | None]:
        return drop_targets.compute_drop_target(
            self, pos, include_center=include_center
        )

    def _drop_target_for_gap(
        self, pos: QPoint
    ) -> tuple[tuple[int, ...], str, bool, None] | None:
        return drop_targets.drop_target_for_gap(self, pos)

    def _canvas_layout(self) -> tuple[int, int, float, float, float] | None:
        return hit_projection.canvas_layout(self)

    def _project_canvas_rect(
        self, rect_canvas: QRect, sr: float, ox: float, oy: float
    ) -> QRect:
        return hit_projection.project_canvas_rect(rect_canvas, sr, ox, oy)

    @staticmethod
    def _composition_gap_canvas_px() -> int:
        return hit_projection.composition_gap_canvas_px()

    def _drop_gaps(self):
        return hit_projection.drop_gaps(self)

    def _leaf_paths_and_rects(self):
        return hit_projection.leaf_paths_and_rects(self)

    def _node_rect_at_path(self, path: tuple[int, ...]) -> QRect | None:
        return hit_projection.node_rect_at_path(self, path)

    def _leaf_rects(self) -> list[tuple[LeafNode, QRect]]:
        return hit_projection.leaf_rects(self)

    # --- textures / RHI ---

    def upload_image(self, slot: CompareSlot) -> None:
        if slot.image is None:
            return
        self.upload_pixel_source(slot.id, slot.image)

    def upload_pixel_source(self, slot_id: int, source) -> None:
        self._renderer.queue_upload(slot_id, source)
        self.update()

    def remove_texture(self, slot_id: int) -> None:
        self._renderer.queue_remove(slot_id)
        self.update()

    def _sync_textures(self) -> None:
        """Reconcile GPU textures with all available image sources.

        Union of ``state.slots`` (live data ownership — includes hidden slots
        during focused mode) and ``_active_composition.layers`` (export path
        when ``state`` is empty). Texture eviction tracks the union so toggling
        focus never evicts a still-loaded slot.
        """
        sources: dict[int, object] = {}
        for slot in self.state.slots:
            if slot.image is not None:
                sources.setdefault(int(slot.id), slot.image)
        if self._active_composition is not None:
            for layer in self._active_composition.layers:
                if layer.image is not None:
                    sources.setdefault(int(layer.layer_id), layer.image)

        for sid, source in sources.items():
            if not self._renderer.has_slot_texture(sid):
                self.upload_pixel_source(sid, source)
        stale = [sid for sid in self._renderer.slot_texture_ids() if sid not in sources]
        for sid in stale:
            self.remove_texture(sid)

    def initialize(self, command_buffer) -> None:
        self._renderer.initialize(command_buffer)

    def releaseResources(self) -> None:
        self._renderer.release()

    def apply_theme_background(self, color: QColor | None = None) -> None:
        bg = QColor(color) if isinstance(color, QColor) and color.isValid() else None
        if bg is None:
            bg = self.palette().color(QPalette.ColorRole.Window)
            if not bg.isValid():
                bg = self.palette().color(QPalette.ColorRole.Base)
            if not bg.isValid():
                bg = QColor(30, 30, 30)
        if not getattr(self, "_allow_transparent_clear", False):
            bg.setAlpha(255)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), bg)
        palette.setColor(QPalette.ColorRole.Window, bg)
        palette.setColor(QPalette.ColorRole.Base, bg)
        self.setPalette(palette)
        self._theme_background_color = QColor(bg)

    def _theme_or_palette_bg(self) -> QColor:
        bg = getattr(self, "_theme_background_color", None)
        if not isinstance(bg, QColor) or not bg.isValid():
            bg = self.palette().color(QPalette.ColorRole.Window)
        if not bg.isValid():
            bg = QColor(30, 30, 30)
        if not getattr(self, "_allow_transparent_clear", False):
            bg.setAlpha(255)
        return bg

    # --- chrome input (stubs → canvas/interaction.py) ---

    @staticmethod
    def _clamp_pan_values(
        pan_x: float, pan_y: float, zoom: float
    ) -> tuple[float, float]:
        return canvas_interaction.clamp_pan_values(pan_x, pan_y, zoom)

    @staticmethod
    def _fit_scale_for(slot: CompareSlot, rect: QRect) -> tuple[float, float]:
        return canvas_interaction.fit_scale_for(slot, rect)

    def wheelEvent(self, event: QWheelEvent) -> None:
        canvas_interaction.handle_wheel_event(self, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        canvas_interaction.handle_mouse_press_event(self, event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        canvas_interaction.handle_context_menu_event(self, event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        canvas_interaction.handle_mouse_move_event(self, event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        canvas_interaction.handle_mouse_release_event(self, event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        canvas_interaction.handle_mouse_double_click_event(self, event)

    def keyPressEvent(self, event) -> None:
        canvas_interaction.handle_key_press_event(self, event)

    def _start_internal_drag(self, slot_id: int) -> None:
        canvas_interaction.start_internal_drag(self, slot_id)

    def _leaf_at(self, pos: QPoint, leaf_rects) -> tuple[LeafNode, QRect] | None:
        return canvas_interaction.leaf_at(pos, leaf_rects)
