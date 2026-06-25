"""Canvas host widget for the multi-compare scene."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QImage,
    QMouseEvent,
    QPalette,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtWidgets import QRhiWidget
from ui.widgets.gl_canvas.rhi_backend import configure_rhi_widget

INTERNAL_SLOT_MIME = "application/x-imgsli-multi-slot"

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.scene import MultiCompareAction, actions
from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer
from tabs.multi_compare.ui import layout_geometry
from ui.context_menu.manager import open_context_menu
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareCanvasWidget(QRhiWidget):
    """QRhi canvas host for multi-compare rendering and input dispatch."""

    CELL_GAP = 4
    DIVIDER_GRAB_PX = 8

    ZOOM_MIN = 1.0
    ZOOM_MAX = 50.0
    ZOOM_STEP = 1.1

    firstFrameRendered = Signal()

    # exposed for widget DnD
    dropTargetChanged = None  # set up by widget if needed

    def __init__(self, parent: QWidget | None = None, *, translate=None):
        super().__init__(parent)
        configure_rhi_widget(self)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self._allow_transparent_clear = False
        self.apply_theme_background()
        self._translate = translate or (lambda _key, default=None: default or _key)

        self.state = MultiCompareState()
        # Set by the parent widget to redux-dispatch interaction-driven state
        # changes (zoom/pan/focus/divider drag). When unset (standalone tests),
        # state mutations are silently dropped.
        self._dispatch: callable | None = None
        # ResolvedComposition driving the render. Populated by
        # ``_rebuild_composition`` (live) or by ``apply_canvas_render_plan``
        # (export) — both ultimately set this attribute and ``render()`` walks
        # it. ``None`` means "nothing to draw".
        self._active_composition = None

        self._renderer = MultiCompareRhiRenderer(self)
        self._first_frame_emitted = False

        # pan
        self._panning = False
        self._pan_start_pos = QPointF()
        self._pan_start_state = (0.0, 0.0)
        self._pan_ref_rect = QRect()
        self._pan_ref_fit = (1.0, 1.0)

        # divider drag (path-keyed so it survives store-driven tree rebuilds)
        # tuple: (split_path, divider_idx, direction, start_weights)
        self._divider_drag: tuple[tuple[int, ...], int, str, list[float]] | None = None
        self._divider_start_cursor = QPointF()

        # internal slot-drag (swap / move)
        self._lmb_press_pos: QPointF | None = None
        self._lmb_press_slot_id: int | None = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ---- public state ----

    def set_state(self, state: MultiCompareState) -> None:
        self.state = state
        self._sync_textures()
        self._rebuild_composition()
        self.update()

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

    def resizeEvent(self, event) -> None:  # noqa: D401 — Qt signature
        super().resizeEvent(event)
        self.update()

    def compute_drop_target(
        self, pos: QPoint, *, include_center: bool = False
    ) -> tuple[tuple[int, ...] | None, str | None, bool, int | None]:
        """Return (target_path, side, target_root, swap_slot_id).

        target_root=True when tree is empty (whole widget is the drop zone).
        When include_center=True, the central half of a leaf maps to side="center";
        in that case swap_slot_id holds the leaf's slot id (for internal drag swap).
        All zones are relative to the target leaf, never to the whole grid or an
        enclosing split.
        """
        if self.state.root is None:
            return None, None, True, None
        leaf_entries = self._leaf_paths_and_rects()
        if not leaf_entries:
            return None, None, True, None

        gap_target = self._drop_target_for_gap(pos)
        if gap_target is not None:
            return gap_target

        # Pick the leaf the cursor is in, or snap to the nearest one across gaps.
        target_leaf = None
        target_rect = None
        target_path: tuple[int, ...] = ()
        for leaf, rect, path in leaf_entries:
            if rect.contains(pos):
                target_leaf = leaf
                target_rect = rect
                target_path = path
                break
        if target_leaf is None:
            best_d2 = None
            for leaf, rect, path in leaf_entries:
                dx = max(rect.x() - pos.x(), 0, pos.x() - (rect.x() + rect.width() - 1))
                dy = max(rect.y() - pos.y(), 0, pos.y() - (rect.y() + rect.height() - 1))
                d2 = dx * dx + dy * dy
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    target_leaf = leaf
                    target_rect = rect
                    target_path = path
            if target_leaf is None:
                return None, None, False, None

        u = (pos.x() - target_rect.x()) / max(target_rect.width(), 1)
        v = (pos.y() - target_rect.y()) / max(target_rect.height(), 1)
        if include_center and 0.25 <= u <= 0.75 and 0.25 <= v <= 0.75:
            return target_path, "center", False, target_leaf.slot_id

        # Insertion/move targets follow the nearest edge of this image cell.
        # This keeps a divider-local drop local even when the leaf belongs to a
        # split whose container spans most of the application window.
        distances = {"left": u, "right": 1 - u, "top": v, "bottom": 1 - v}
        side = min(distances, key=lambda k: distances[k])
        return target_path, side, False, None

    def _drop_target_for_gap(
        self, pos: QPoint
    ) -> tuple[tuple[int, ...], str, bool, None] | None:
        """Resolve the dedicated zones inside an actual split gap.

        A vertical gap is split by height: the top quarter inserts above the
        whole split, the bottom quarter below it, and the middle half inserts
        between the adjacent children. Horizontal gaps use the symmetric
        left/middle/right behavior.
        """
        for split, split_path, divider_index, divider_rect in self._drop_gaps():
            if not divider_rect.contains(pos):
                continue

            adjacent_path = split_path + (divider_index + 1,)
            if split.direction == "h":
                fraction = (pos.y() - divider_rect.y()) / max(
                    divider_rect.height(), 1
                )
                if fraction < 0.25:
                    return split_path, "top", False, None
                if fraction >= 0.75:
                    return split_path, "bottom", False, None
                return adjacent_path, "left", False, None

            fraction = (pos.x() - divider_rect.x()) / max(
                divider_rect.width(), 1
            )
            if fraction < 0.25:
                return split_path, "left", False, None
            if fraction >= 0.75:
                return split_path, "right", False, None
            return adjacent_path, "top", False, None
        return None

    def _drop_gaps(
        self,
    ) -> list[tuple[SplitNode, tuple[int, ...], int, QRect]]:
        """Return split gaps with their tree paths for drop-zone hit-testing."""
        if self.state.root is None:
            return []
        return layout_geometry.drop_gaps(
            self.state.root,
            self.rect(),
            gap=self.CELL_GAP,
        )

    def _leaf_paths_and_rects(self) -> list[tuple[LeafNode, QRect, tuple[int, ...]]]:
        if self.state.root is None or self.width() <= 0 or self.height() <= 0:
            return []
        leaves, _splits = layout_geometry.walk_paths(
            self.state.root,
            self.rect(),
            gap=self.CELL_GAP,
        )
        return leaves

    def _ancestor_splits_with_rects(
        self, leaf_path: tuple[int, ...]
    ) -> list[tuple[SplitNode, QRect, tuple[int, ...]]]:
        """Splits enclosing the leaf, ordered outermost → innermost."""
        if self.state.root is None:
            return []
        _leaves, splits = layout_geometry.walk_paths(
            self.state.root,
            self.rect(),
            only_path=leaf_path,
            gap=self.CELL_GAP,
        )
        return splits

    def _node_rect_at_path(self, path: tuple[int, ...]) -> QRect | None:
        if self.state.root is None:
            return None
        if not path:
            return self.rect()
        # Reuse _walk_paths with only_path; capture both leaf and splits.
        leaves, splits = layout_geometry.walk_paths(
            self.state.root,
            self.rect(),
            only_path=path,
            gap=self.CELL_GAP,
        )
        for _, rect, p in splits:
            if p == path:
                return rect
        for _, rect, p in leaves:
            if p == path:
                return rect
        return None

    # ---- texture management ----

    def upload_image(self, slot: CompareSlot) -> None:
        if slot.image is None:
            return
        self.upload_image_array(slot.id, slot.image)

    def upload_image_array(self, slot_id: int, arr) -> None:
        image = self._numpy_to_qimage(arr)
        if image is None:
            return
        self._renderer.queue_upload(slot_id, image)
        self.update()

    @staticmethod
    def _numpy_to_qimage(arr: np.ndarray) -> QImage | None:
        if arr.ndim == 3:
            h, w, channels = arr.shape
        elif arr.ndim == 2:
            h, w = arr.shape
            channels = 1
        else:
            return None
        if channels == 4:
            img = QImage(arr.tobytes(), w, h, w * 4, QImage.Format.Format_RGBA8888)
        elif channels == 3:
            img = QImage(arr.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
        else:
            img = QImage(arr.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
        return img.convertToFormat(QImage.Format.Format_RGBA8888).copy()

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

        for sid, arr in sources.items():
            if not self._renderer.has_slot_texture(sid):
                self.upload_image_array(sid, arr)
        stale = [sid for sid in self._renderer.slot_texture_ids() if sid not in sources]
        for sid in stale:
            self.remove_texture(sid)

    # ---- QRhi lifecycle ----

    def initialize(self, command_buffer) -> None:
        self._renderer.initialize(command_buffer)

    def releaseResources(self) -> None:
        self._renderer.release()

    def render(self, command_buffer) -> None:
        painted = self._renderer.render(command_buffer)
        if painted and not self._first_frame_emitted:
            self._first_frame_emitted = True
            self.firstFrameRendered.emit()

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
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setAutoFillBackground(True)
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

    # ---- layout: rect computation ----

    def _leaf_rects(self) -> list[tuple[LeafNode, QRect]]:
        if self.state.root is None or self.width() <= 0 or self.height() <= 0:
            return []
        out: list[tuple[LeafNode, QRect]] = []
        self._walk(self.state.root, self.rect(), out, dividers=None)
        return out

    def _walk(
        self,
        node,
        rect: QRect,
        out_leaves: list[tuple[LeafNode, QRect]] | None,
        dividers: list[tuple[SplitNode, int, QRect]] | None,
    ) -> None:
        if isinstance(node, LeafNode):
            if out_leaves is not None:
                out_leaves.append((node, rect))
            return
        assert isinstance(node, SplitNode)
        gap = self.CELL_GAP
        ws = node.normalized_weights()
        n = len(node.children)
        if node.direction == "h":
            total_gap = gap * (n - 1)
            inner = max(rect.width() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            # Correct rounding so sum matches inner.
            sizes[-1] = inner - sum(sizes[:-1])
            x = rect.x()
            for i, (child, size) in enumerate(zip(node.children, sizes)):
                child_rect = QRect(x, rect.y(), size, rect.height())
                self._walk(child, child_rect, out_leaves, dividers)
                if i < n - 1:
                    if dividers is not None:
                        dividers.append(
                            (node, i, QRect(x + size, rect.y(), gap, rect.height()))
                        )
                    x += size + gap
                else:
                    x += size
        else:  # "v"
            total_gap = gap * (n - 1)
            inner = max(rect.height() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            sizes[-1] = inner - sum(sizes[:-1])
            y = rect.y()
            for i, (child, size) in enumerate(zip(node.children, sizes)):
                child_rect = QRect(rect.x(), y, rect.width(), size)
                self._walk(child, child_rect, out_leaves, dividers)
                if i < n - 1:
                    if dividers is not None:
                        dividers.append(
                            (node, i, QRect(rect.x(), y + size, rect.width(), gap))
                        )
                    y += size + gap
                else:
                    y += size

    @staticmethod
    def _clamp_pan_values(pan_x: float, pan_y: float, zoom: float) -> tuple[float, float]:
        """Clamp pan so the image edges never reveal background.

        Derivation: img_uv = (cell_uv − 0.5)/(fit·zoom) + 0.5 − pan. The visible
        image region in cell-uv is [0.5 ± fit/2], at whose ends img_uv = 0 or 1
        before pan. Forcing img_uv ∈ [0, 1] across that range yields
        |pan| ≤ (zoom − 1) / (2·zoom), independent of fit.
        """
        z = max(zoom, 1.0)
        limit = (z - 1.0) / (2.0 * z)
        return max(-limit, min(limit, pan_x)), max(-limit, min(limit, pan_y))

    # ---- aspect-fit helper ----

    @staticmethod
    def _fit_scale_for(slot: CompareSlot, rect: QRect) -> tuple[float, float]:
        if slot.image is None or rect.width() <= 0 or rect.height() <= 0:
            return 1.0, 1.0
        h, w = slot.image.shape[:2]
        if h <= 0 or w <= 0:
            return 1.0, 1.0
        img_ar = w / h
        cell_ar = rect.width() / rect.height()
        if img_ar > cell_ar:
            return 1.0, cell_ar / img_ar
        return img_ar / cell_ar, 1.0

    # ---- input: zoom + pan + divider drag ----

    def wheelEvent(self, event: QWheelEvent) -> None:
        leaf_rects = self._leaf_rects()
        if not leaf_rects:
            event.ignore()
            return

        pos = event.position().toPoint()
        leaf, rect = self._leaf_at(pos, leaf_rects) or (None, None)
        if leaf is None:
            event.ignore()
            return

        slot = next((s for s in self.state.slots if s.id == leaf.slot_id), None)
        if slot is None:
            event.ignore()
            return

        fit_x, fit_y = self._fit_scale_for(slot, rect)
        cell_u = (pos.x() - rect.x()) / rect.width()
        cell_v = (pos.y() - rect.y()) / rect.height()

        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return
        factor = self.ZOOM_STEP if delta > 0 else 1.0 / self.ZOOM_STEP
        z1 = self.state.zoom
        z2 = max(self.ZOOM_MIN, min(self.ZOOM_MAX, z1 * factor))
        if z2 == z1:
            event.accept()
            return

        new_pan_x = self.state.pan_x + (cell_u - 0.5) / max(fit_x, 1e-6) * (1.0 / z2 - 1.0 / z1)
        new_pan_y = self.state.pan_y + (cell_v - 0.5) / max(fit_y, 1e-6) * (1.0 / z2 - 1.0 / z1)
        new_pan_x, new_pan_y = self._clamp_pan_values(new_pan_x, new_pan_y, z2)
        self._do_dispatch(actions.set_zoom(z2, new_pan_x, new_pan_y))
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()

        if event.button() == Qt.MouseButton.RightButton:
            picked = self._leaf_at(pos, self._leaf_rects())
            if picked is None:
                return
            leaf, rect = picked
            slot = next((s for s in self.state.slots if s.id == leaf.slot_id), None)
            open_context_menu(
                ContextMenuRequest(
                    source_widget=self,
                    global_pos=event.globalPosition().toPoint(),
                    local_pos=pos,
                    session_type="multi_compare",
                    target=ContextMenuTarget(
                        kind="multi_compare_slot",
                        id=leaf.slot_id,
                        payload={
                            "rect": rect,
                            "path": slot.path if slot is not None else None,
                            "label": slot.label if slot is not None else "",
                        },
                    ),
                )
            )
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            div = self._divider_at(event.position())
            if div is not None:
                split_path, idx, _drect, direction, weights = div
                self._divider_drag = (split_path, idx, direction, weights)
                self._divider_start_cursor = event.position()
                self.setCursor(
                    Qt.CursorShape.SplitHCursor if direction == "h"
                    else Qt.CursorShape.SplitVCursor
                )
                event.accept()
                return
            # Press on leaf body → arm internal drag.
            picked = self._leaf_at(pos, self._leaf_rects())
            if picked is not None:
                leaf, _ = picked
                self._lmb_press_pos = event.position()
                self._lmb_press_slot_id = leaf.slot_id
                event.accept()
                return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start_pos = event.position()
            self._pan_start_state = (self.state.pan_x, self.state.pan_y)
            leaf_rects = self._leaf_rects()
            picked = self._leaf_at(pos, leaf_rects)
            if picked is not None:
                leaf, rect = picked
                slot = next((s for s in self.state.slots if s.id == leaf.slot_id), None)
                self._pan_ref_rect = rect
                self._pan_ref_fit = self._fit_scale_for(slot, rect) if slot is not None else (1.0, 1.0)
            else:
                self._pan_ref_rect = self.rect()
                self._pan_ref_fit = (1.0, 1.0)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # Internal-drag arm: start QDrag if movement exceeds threshold.
        if (
            self._lmb_press_pos is not None
            and self._lmb_press_slot_id is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.position() - self._lmb_press_pos
            if (delta.x() ** 2 + delta.y() ** 2) >= (QApplication.startDragDistance() ** 2):
                self._start_internal_drag(self._lmb_press_slot_id)
                self._lmb_press_pos = None
                self._lmb_press_slot_id = None
                event.accept()
                return

        if self._divider_drag is not None:
            split_path, idx, direction, start_weights = self._divider_drag
            ws = list(start_weights)
            delta_px = (
                event.position().x() - self._divider_start_cursor.x()
                if direction == "h"
                else event.position().y() - self._divider_start_cursor.y()
            )
            container_size_px = self._split_container_size_at(split_path, direction)
            if container_size_px <= 0:
                return
            total_pair = ws[idx] + ws[idx + 1]
            total_weights = sum(ws) or 1.0
            weight_delta = delta_px / container_size_px * total_weights
            new_left = ws[idx] + weight_delta
            new_right = ws[idx + 1] - weight_delta
            min_w = self._min_pane_weight(
                split_path, direction, container_size_px, total_weights
            )
            # Clamp guarantees each side >= min_w as long as 2*min_w <= total_pair.
            max_w = total_pair - min_w
            if max_w < min_w:
                # Pair is too small for the floor — split evenly instead of fighting.
                new_left = new_right = total_pair / 2.0
            else:
                new_left = max(min_w, min(max_w, new_left))
                new_right = total_pair - new_left
            ws[idx] = new_left
            ws[idx + 1] = new_right
            self._do_dispatch(actions.set_split_weights(split_path, ws))
            event.accept()
            return

        if self._panning:
            ref = self._pan_ref_rect
            if ref.width() <= 0 or ref.height() <= 0:
                return
            fit_x, fit_y = self._pan_ref_fit
            z = max(self.state.zoom, 1e-6)
            delta = event.position() - self._pan_start_pos
            new_pan_x = self._pan_start_state[0] + (delta.x() / ref.width()) / (max(fit_x, 1e-6) * z)
            new_pan_y = self._pan_start_state[1] + (delta.y() / ref.height()) / (max(fit_y, 1e-6) * z)
            new_pan_x, new_pan_y = self._clamp_pan_values(new_pan_x, new_pan_y, self.state.zoom)
            self._do_dispatch(actions.set_pan(new_pan_x, new_pan_y))
            event.accept()
            return

        # Hover: update cursor over dividers.
        div = self._divider_at(event.position())
        if div is not None:
            _path, _idx, _rect, direction, _ws = div
            self.setCursor(
                Qt.CursorShape.SplitHCursor if direction == "h"
                else Qt.CursorShape.SplitVCursor
            )
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._lmb_press_pos = None
            self._lmb_press_slot_id = None
        if self._divider_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._divider_drag = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            div = self._divider_at(event.position())
            if div is not None:
                split_path, _idx, _drect, _direction, weights = div
                n = len(weights)
                if n > 0:
                    self._do_dispatch(
                        actions.set_split_weights(split_path, [1.0] * n)
                    )
                event.accept()
                return
            leaf_rects = self._leaf_rects()
            picked = self._leaf_at(pos, leaf_rects)
            if picked is not None:
                leaf, _ = picked
                new_focus = None if self.state.is_focused else leaf.slot_id
                self._do_dispatch(actions.set_focus(new_focus))
            event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape and self.state.is_focused:
            self._do_dispatch(actions.set_focus(None))
            event.accept()
        elif key == Qt.Key.Key_0:
            self._do_dispatch(actions.reset_view())
            event.accept()
        else:
            super().keyPressEvent(event)

    def _start_internal_drag(self, slot_id: int) -> None:
        slot = next((s for s in self.state.slots if s.id == slot_id), None)
        mime = QMimeData()
        mime.setData(INTERNAL_SLOT_MIME, str(slot_id).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        # Build a small preview pixmap from the slot's image (if available).
        rects = self._leaf_rects()
        rect = next((r for l, r in rects if l.slot_id == slot_id), None)
        if rect is not None and slot is not None and slot.image is not None:
            from PySide6.QtGui import QImage, QPixmap
            h, w = slot.image.shape[:2]
            channels = slot.image.shape[2] if slot.image.ndim == 3 else 1
            fmt = QImage.Format.Format_RGB888 if channels == 3 else QImage.Format.Format_RGBA8888
            qimg = QImage(slot.image.tobytes(), w, h, w * channels, fmt)
            preview = QPixmap.fromImage(qimg).scaledToWidth(
                160, Qt.TransformationMode.SmoothTransformation
            )
            drag.setPixmap(preview)
            drag.setHotSpot(QPoint(preview.width() // 2, preview.height() // 2))
        drag.exec(Qt.DropAction.MoveAction)

    # ---- hit-tests ----

    def _leaf_at(self, pos: QPoint, leaf_rects) -> tuple[LeafNode, QRect] | None:
        for leaf, rect in leaf_rects:
            if rect.contains(pos):
                return leaf, rect
        return None

    def _divider_at(
        self, pos: QPointF
    ) -> tuple[tuple[int, ...], int, QRect, str, list[float]] | None:
        """Return ``(split_path, divider_idx, divider_rect, direction, weights)``.

        ``split_path`` is the chain of child indices from the root tree node to
        the SplitNode that owns this divider. Used by mousePressEvent to drive
        ``SetSplitWeights`` dispatches independent of any specific SplitNode
        identity (the tree is immutable from the store's perspective).
        """
        grab = self.DIVIDER_GRAB_PX
        for split, split_path, idx, drect in self._drop_gaps():
            expanded = drect.adjusted(-grab, -grab, grab, grab)
            if expanded.contains(pos.toPoint()):
                return split_path, idx, drect, split.direction, list(split.weights)
        return None

    def _split_container_size_at(self, split_path: tuple[int, ...], direction: str) -> int:
        """Width / height of the SplitNode container at ``split_path``."""
        rect = self._node_rect_at_path(split_path)
        if rect is None:
            return 0
        return rect.width() if direction == "h" else rect.height()

    # Divider-drag floor knobs. ``MIN_PANE_FRACTION`` keeps each pane at least
    # that share of the container regardless of size. ``MIN_PANE_PIXELS`` is an
    # absolute readability floor so panes can't shrink below a usable size on
    # large screens. ``MAX_CELL_ASPECT`` caps the cell's aspect ratio so a wide
    # image in a tall sliver (or vice-versa) doesn't turn into a thin band with
    # huge letterbox bars.
    MIN_PANE_FRACTION = 0.15
    MIN_PANE_PIXELS = 100
    MAX_CELL_ASPECT = 5.0

    def _min_pane_weight(
        self,
        split_path: tuple[int, ...],
        direction: str,
        container_size_px: int,
        total_weights: float,
    ) -> float:
        """Translate the readability floors into a weight value."""
        rect = self._node_rect_at_path(split_path)
        perp_size_px = 0
        if rect is not None:
            perp_size_px = rect.height() if direction == "h" else rect.width()
        floor_px = self.MIN_PANE_PIXELS
        if perp_size_px > 0:
            floor_px = max(floor_px, int(perp_size_px / self.MAX_CELL_ASPECT))
        floor_px = min(floor_px, container_size_px // 2)
        frac_from_pct = self.MIN_PANE_FRACTION
        frac_from_px = floor_px / container_size_px if container_size_px > 0 else 0.0
        return max(frac_from_pct, frac_from_px) * total_weights
