"""OpenGL grid widget for multi-compare — container-tree layout (i3/sway-style)."""

from __future__ import annotations

import ctypes
import logging
from typing import TYPE_CHECKING

import numpy as np
from OpenGL import GL as gl
from PyQt6.QtCore import QMimeData, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QWheelEvent,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QApplication, QWidget

INTERNAL_SLOT_MIME = "application/x-imgsli-multi-slot"

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
    node_at_path,
)
from tabs.multi_compare.shaders import FRAGMENT_SHADER, VERTEX_SHADER
from ui.widgets.gl_canvas.runtime import build_canvas_surface_format

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ImproveImgSLI")


class GLGridWidget(QOpenGLWidget):
    """GPU-accelerated container-tree image grid with resizable dividers."""

    CELL_GAP = 4
    DIVIDER_GRAB_PX = 8

    LABEL_PADDING = 6
    LABEL_BG_ALPHA = 170
    LABEL_FONT_PT = 10

    ZOOM_MIN = 1.0
    ZOOM_MAX = 50.0
    ZOOM_STEP = 1.1

    # exposed for widget DnD
    dropTargetChanged = None  # set up by widget if needed

    def __init__(self, parent: QWidget | None = None, *, translate=None):
        super().__init__(parent)
        self.setFormat(build_canvas_surface_format())
        self._translate = translate or (lambda _key, default=None: default or _key)

        self.state = MultiCompareState()
        self._textures: dict[int, int] = {}
        self._program = 0
        self._vao = 0
        self._vbo = 0
        self._initialized = False

        # pan
        self._panning = False
        self._pan_start_pos = QPointF()
        self._pan_start_state = (0.0, 0.0)
        self._pan_ref_rect = QRect()
        self._pan_ref_fit = (1.0, 1.0)

        # divider drag
        self._divider_drag: tuple[SplitNode, int, QRect, list[float]] | None = None
        self._divider_axis: str | None = None  # "h" → vertical divider → resize x
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
        self.update()

    def set_drag_state(
        self,
        active: bool,
        target_path: tuple[int, ...] | None = None,
        side: str | None = None,
        target_root: bool = False,
        swap_slot_id: int | None = None,
    ) -> None:
        self.state.drag_active = active
        self.state.drag_target_path = target_path
        self.state.drag_target_side = side
        self.state.drag_target_root = target_root
        self.state.drag_target_swap_slot_id = swap_slot_id
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
        gaps: list[tuple[SplitNode, tuple[int, ...], int, QRect]] = []
        self._walk_drop_gaps(self.state.root, self.rect(), (), gaps)
        return gaps

    def _walk_drop_gaps(
        self,
        node,
        rect: QRect,
        path: tuple[int, ...],
        gaps: list[tuple[SplitNode, tuple[int, ...], int, QRect]],
    ) -> None:
        if isinstance(node, LeafNode):
            return
        assert isinstance(node, SplitNode)
        gap = self.CELL_GAP
        weights = node.normalized_weights()
        child_count = len(node.children)

        if node.direction == "h":
            inner = max(rect.width() - gap * (child_count - 1), 1)
            sizes = [int(inner * weight) for weight in weights]
            sizes[-1] = inner - sum(sizes[:-1])
            x = rect.x()
            for index, (child, size) in enumerate(zip(node.children, sizes)):
                child_rect = QRect(x, rect.y(), size, rect.height())
                self._walk_drop_gaps(child, child_rect, path + (index,), gaps)
                if index < child_count - 1:
                    gaps.append(
                        (
                            node,
                            path,
                            index,
                            QRect(x + size, rect.y(), gap, rect.height()),
                        )
                    )
                x += size + (gap if index < child_count - 1 else 0)
            return

        inner = max(rect.height() - gap * (child_count - 1), 1)
        sizes = [int(inner * weight) for weight in weights]
        sizes[-1] = inner - sum(sizes[:-1])
        y = rect.y()
        for index, (child, size) in enumerate(zip(node.children, sizes)):
            child_rect = QRect(rect.x(), y, rect.width(), size)
            self._walk_drop_gaps(child, child_rect, path + (index,), gaps)
            if index < child_count - 1:
                gaps.append(
                    (
                        node,
                        path,
                        index,
                        QRect(rect.x(), y + size, rect.width(), gap),
                    )
                )
            y += size + (gap if index < child_count - 1 else 0)

    def _leaf_paths_and_rects(self) -> list[tuple[LeafNode, QRect, tuple[int, ...]]]:
        if self.state.root is None or self.width() <= 0 or self.height() <= 0:
            return []
        out: list[tuple[LeafNode, QRect, tuple[int, ...]]] = []
        self._walk_paths(self.state.root, self.rect(), (), out, None)
        return out

    def _ancestor_splits_with_rects(
        self, leaf_path: tuple[int, ...]
    ) -> list[tuple[SplitNode, QRect, tuple[int, ...]]]:
        """Splits enclosing the leaf, ordered outermost → innermost."""
        if self.state.root is None:
            return []
        splits: list[tuple[SplitNode, QRect, tuple[int, ...]]] = []
        self._walk_paths(self.state.root, self.rect(), (), None, splits, only_path=leaf_path)
        return splits

    def _walk_paths(
        self,
        node,
        rect: QRect,
        path: tuple[int, ...],
        leaves_out: list[tuple[LeafNode, QRect, tuple[int, ...]]] | None,
        splits_out: list[tuple[SplitNode, QRect, tuple[int, ...]]] | None,
        only_path: tuple[int, ...] | None = None,
    ) -> None:
        # only_path restricts traversal: visit just the nodes on the path from
        # root to that node (inclusive).
        on_path = only_path is None or only_path[: len(path)] == path
        if not on_path:
            return
        if isinstance(node, LeafNode):
            if leaves_out is not None and (only_path is None or only_path == path):
                leaves_out.append((node, rect, path))
            return
        assert isinstance(node, SplitNode)
        if splits_out is not None:
            splits_out.append((node, rect, path))
        gap = self.CELL_GAP
        ws = node.normalized_weights()
        n = len(node.children)
        depth = len(path)
        if node.direction == "h":
            total_gap = gap * (n - 1)
            inner = max(rect.width() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            sizes[-1] = inner - sum(sizes[:-1])
            x = rect.x()
            for i, (child, size) in enumerate(zip(node.children, sizes)):
                child_rect = QRect(x, rect.y(), size, rect.height())
                if only_path is None or (
                    depth < len(only_path) and only_path[depth] == i
                ):
                    self._walk_paths(
                        child, child_rect, path + (i,), leaves_out, splits_out, only_path
                    )
                x += size + gap
        else:
            total_gap = gap * (n - 1)
            inner = max(rect.height() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            sizes[-1] = inner - sum(sizes[:-1])
            y = rect.y()
            for i, (child, size) in enumerate(zip(node.children, sizes)):
                child_rect = QRect(rect.x(), y, rect.width(), size)
                if only_path is None or (
                    depth < len(only_path) and only_path[depth] == i
                ):
                    self._walk_paths(
                        child, child_rect, path + (i,), leaves_out, splits_out, only_path
                    )
                y += size + gap

    def _node_rect_at_path(self, path: tuple[int, ...]) -> QRect | None:
        if self.state.root is None:
            return None
        if not path:
            return self.rect()
        # Reuse _walk_paths with only_path; capture both leaf and splits.
        leaves: list[tuple[LeafNode, QRect, tuple[int, ...]]] = []
        splits: list[tuple[SplitNode, QRect, tuple[int, ...]]] = []
        self._walk_paths(self.state.root, self.rect(), (), leaves, splits, only_path=path)
        for _, rect, p in splits:
            if p == path:
                return rect
        for _, rect, p in leaves:
            if p == path:
                return rect
        return None

    # ---- texture management ----

    def upload_image(self, slot: CompareSlot) -> None:
        if not self._initialized or slot.image is None:
            return
        self.makeCurrent()
        tex = self._textures.get(slot.id)
        if tex is None:
            tex = gl.glGenTextures(1)
            self._textures[slot.id] = tex

        h, w = slot.image.shape[:2]
        channels = slot.image.shape[2] if slot.image.ndim == 3 else 1
        if channels == 4:
            fmt, internal = gl.GL_RGBA, gl.GL_RGBA8
        elif channels == 3:
            fmt, internal = gl.GL_RGB, gl.GL_RGB8
        else:
            fmt, internal = gl.GL_RED, gl.GL_R8

        gl.glBindTexture(gl.GL_TEXTURE_2D, tex)
        gl.glTexImage2D(
            gl.GL_TEXTURE_2D, 0, internal, w, h, 0,
            fmt, gl.GL_UNSIGNED_BYTE, slot.image.tobytes(),
        )
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        self.doneCurrent()

    def remove_texture(self, slot_id: int) -> None:
        tex = self._textures.pop(slot_id, None)
        if tex is not None and self._initialized:
            self.makeCurrent()
            gl.glDeleteTextures(1, [tex])
            self.doneCurrent()

    def _sync_textures(self) -> None:
        if not self._initialized:
            return
        for slot in self.state.slots:
            if slot.id not in self._textures and slot.image is not None:
                self.upload_image(slot)

        active_ids = {s.id for s in self.state.slots}
        stale = [sid for sid in self._textures if sid not in active_ids]
        for sid in stale:
            self.remove_texture(sid)

    # ---- GL lifecycle ----

    def initializeGL(self) -> None:
        self._program = self._compile_program()
        self._vao, self._vbo = self._create_quad()
        self._initialized = True
        self._sync_textures()

    def resizeGL(self, w: int, h: int) -> None:
        gl.glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        self._clear_background()
        leaf_rects = self._leaf_rects()
        slot_by_id = {s.id: s for s in self.state.slots}

        if leaf_rects:
            gl.glUseProgram(self._program)
            gl.glBindVertexArray(self._vao)

            focused_id = self.state.focused_slot_id if self.state.is_focused else None
            for leaf, rect in leaf_rects:
                slot = slot_by_id.get(leaf.slot_id)
                if slot is None:
                    continue
                tex = self._textures.get(leaf.slot_id)
                if tex is None:
                    continue
                if focused_id is not None and leaf.slot_id != focused_id:
                    continue
                draw_rect = self.rect() if focused_id is not None else rect
                fit_x, fit_y = self._fit_scale_for(slot, draw_rect)
                self._draw_slot(draw_rect, tex, fit_x, fit_y)

            gl.glBindVertexArray(0)
            gl.glUseProgram(0)

        self._paint_overlay(leaf_rects, slot_by_id)

    # ---- layout: rect computation ----

    def _leaf_rects(self) -> list[tuple[LeafNode, QRect]]:
        if self.state.root is None or self.width() <= 0 or self.height() <= 0:
            return []
        out: list[tuple[LeafNode, QRect]] = []
        self._walk(self.state.root, self.rect(), out, dividers=None)
        return out

    def _all_dividers(self) -> list[tuple[SplitNode, int, QRect]]:
        """List of (split_node, child_index_left/top_of_divider, divider_rect)."""
        if self.state.root is None:
            return []
        dividers: list[tuple[SplitNode, int, QRect]] = []
        self._walk(self.state.root, self.rect(), [], dividers=dividers)
        return dividers

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

    def _clamp_pan(self) -> None:
        """Clamp pan so the image edges never reveal background.

        Derivation: img_uv = (cell_uv − 0.5)/(fit·zoom) + 0.5 − pan. The visible
        image region in cell-uv is [0.5 ± fit/2], at whose ends img_uv = 0 or 1
        before pan. Forcing img_uv ∈ [0, 1] across that range yields
        |pan| ≤ (zoom − 1) / (2·zoom), independent of fit.
        """
        z = max(self.state.zoom, 1.0)
        limit = (z - 1.0) / (2.0 * z)
        self.state.pan_x = max(-limit, min(limit, self.state.pan_x))
        self.state.pan_y = max(-limit, min(limit, self.state.pan_y))

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

    # ---- rendering primitives ----

    def _clear_background(self) -> None:
        bg = getattr(self, "_theme_background_color", None)
        if not isinstance(bg, QColor) or not bg.isValid():
            bg = self.palette().color(QPalette.ColorRole.Window)
        if not bg.isValid():
            bg = QColor(30, 30, 30)
        gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

    def _draw_slot(self, rect: QRect, tex: int, fit_x: float, fit_y: float) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        gl_y = h - rect.y() - rect.height()
        gl.glEnable(gl.GL_SCISSOR_TEST)
        gl.glScissor(rect.x(), gl_y, rect.width(), rect.height())
        gl.glViewport(rect.x(), gl_y, rect.width(), rect.height())

        loc_zoom = gl.glGetUniformLocation(self._program, "zoom")
        loc_pan = gl.glGetUniformLocation(self._program, "panOffset")
        loc_img = gl.glGetUniformLocation(self._program, "image")
        loc_fit = gl.glGetUniformLocation(self._program, "fitScale")

        gl.glUniform1f(loc_zoom, self.state.zoom)
        gl.glUniform2f(loc_pan, self.state.pan_x, self.state.pan_y)
        gl.glUniform2f(loc_fit, max(fit_x, 1e-6), max(fit_y, 1e-6))
        gl.glUniform1i(loc_img, 0)

        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, tex)

        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        gl.glDisable(gl.GL_SCISSOR_TEST)
        gl.glViewport(0, 0, w, h)

    def _paint_overlay(self, leaf_rects, slot_by_id) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font = QFont(painter.font())
        font.setPointSize(self.LABEL_FONT_PT)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()

        focused_id = self.state.focused_slot_id if self.state.is_focused else None

        if focused_id is not None:
            slot = slot_by_id.get(focused_id)
            if slot is not None and slot.label:
                self._paint_label(painter, fm, self.rect(), slot.label)
        else:
            for leaf, rect in leaf_rects:
                slot = slot_by_id.get(leaf.slot_id)
                if slot is not None and slot.label:
                    self._paint_label(painter, fm, rect, slot.label)

        if self.state.drag_active:
            if self.state.drag_internal and self.state.drag_source_slot_id is not None:
                self._paint_drag_source(painter, leaf_rects)
            self._paint_drop_preview(painter, leaf_rects)

        painter.end()

    def _paint_label(self, painter: QPainter, fm, rect: QRect, label: str) -> None:
        text_w = fm.horizontalAdvance(label)
        text_h = fm.height()
        pad = self.LABEL_PADDING
        bg_rect = QRect(
            rect.x() + 6,
            rect.bottom() - text_h - pad * 2 - 4,
            min(text_w + pad * 2, rect.width() - 12),
            text_h + pad * 2,
        )
        if bg_rect.width() <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, self.LABEL_BG_ALPHA)))
        painter.drawRoundedRect(bg_rect, 4, 4)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(
            bg_rect.adjusted(pad, 0, -pad, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            fm.elidedText(label, Qt.TextElideMode.ElideMiddle, bg_rect.width() - pad * 2),
        )

    def _paint_drop_preview(self, painter: QPainter, leaf_rects) -> None:
        if self.state.drag_target_root or not leaf_rects:
            target_rect = self.rect()
        else:
            path = self.state.drag_target_path
            if path is None:
                return
            node_rect = self._node_rect_at_path(path)
            if node_rect is None:
                return
            target_rect = self._side_subrect(node_rect, self.state.drag_target_side)
            if target_rect is None:
                return

        accent = self._accent_color()
        fill = QColor(accent)
        fill.setAlpha(70)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine))
        painter.drawRoundedRect(target_rect.adjusted(2, 2, -2, -2), 6, 6)

        painter.save()
        text_font = QFont(painter.font())
        text_font.setPointSize(max(self.LABEL_FONT_PT + 2, 12))
        text_font.setBold(True)
        painter.setFont(text_font)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(target_rect, int(Qt.AlignmentFlag.AlignCenter), self._drop_hint_text())
        painter.restore()

    def _internal_drop_text(self) -> str:
        if self.state.drag_target_side == "center":
            return self._translate("drop_swap", "Swap")
        return self._translate("drop_move_here", "Move here")

    def _paint_drag_source(self, painter: QPainter, leaf_rects) -> None:
        source_id = self.state.drag_source_slot_id
        rect = next((r for l, r in leaf_rects if l.slot_id == source_id), None)
        if rect is None:
            return
        accent = self._accent_color()
        painter.save()
        # Dim the source so the user sees where the image originates.
        dim = QColor(0, 0, 0, 110)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dim))
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 6, 6)
        # Outline in accent color, dashed, so it reads as "this is the moving one".
        pen = QPen(accent, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 6, 6)
        painter.restore()

    @staticmethod
    def _side_subrect(rect: QRect, side: str | None) -> QRect | None:
        if side is None:
            return None
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        if side == "left":
            return QRect(x, y, w // 2, h)
        if side == "right":
            return QRect(x + w // 2, y, w - w // 2, h)
        if side == "top":
            return QRect(x, y, w, h // 2)
        if side == "bottom":
            return QRect(x, y + h // 2, w, h - h // 2)
        if side == "center":
            return QRect(x, y, w, h)
        return None

    def _accent_color(self) -> QColor:
        c = self.palette().color(QPalette.ColorRole.Highlight)
        if c.isValid() and c.alpha() > 0:
            return c
        return QColor(64, 156, 255)

    def _drop_hint_text(self) -> str:
        if self.state.drag_internal:
            return self._internal_drop_text()
        return self._translate("drop_image_here", "Drop image here")

    # ---- shaders ----

    def _compile_program(self) -> int:
        vs = gl.glCreateShader(gl.GL_VERTEX_SHADER)
        gl.glShaderSource(vs, VERTEX_SHADER)
        gl.glCompileShader(vs)
        if not gl.glGetShaderiv(vs, gl.GL_COMPILE_STATUS):
            logger.error(f"Vertex shader error: {gl.glGetShaderInfoLog(vs)}")

        fs = gl.glCreateShader(gl.GL_FRAGMENT_SHADER)
        gl.glShaderSource(fs, FRAGMENT_SHADER)
        gl.glCompileShader(fs)
        if not gl.glGetShaderiv(fs, gl.GL_COMPILE_STATUS):
            logger.error(f"Fragment shader error: {gl.glGetShaderInfoLog(fs)}")

        prog = gl.glCreateProgram()
        gl.glAttachShader(prog, vs)
        gl.glAttachShader(prog, fs)
        gl.glLinkProgram(prog)
        if not gl.glGetProgramiv(prog, gl.GL_LINK_STATUS):
            logger.error(f"Program link error: {gl.glGetProgramInfoLog(prog)}")

        gl.glDeleteShader(vs)
        gl.glDeleteShader(fs)
        return prog

    def _create_quad(self) -> tuple[int, int]:
        vertices = np.array([
            -1.0, -1.0, 0.0, 1.0,
            +1.0, -1.0, 1.0, 1.0,
            -1.0, +1.0, 0.0, 0.0,
            +1.0, +1.0, 1.0, 0.0,
        ], dtype=np.float32)

        vao = gl.glGenVertexArrays(1)
        vbo = gl.glGenBuffers(1)

        gl.glBindVertexArray(vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_STATIC_DRAW)

        stride = 4 * 4
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(8))

        gl.glBindVertexArray(0)
        return vao, vbo

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

        self.state.pan_x += (cell_u - 0.5) / max(fit_x, 1e-6) * (1.0 / z2 - 1.0 / z1)
        self.state.pan_y += (cell_v - 0.5) / max(fit_y, 1e-6) * (1.0 / z2 - 1.0 / z1)
        self.state.zoom = z2
        self._clamp_pan()
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()

        if event.button() == Qt.MouseButton.LeftButton:
            div = self._divider_at(event.position())
            if div is not None:
                split, idx, drect = div
                self._divider_drag = (split, idx, drect, list(split.weights))
                self._divider_axis = split.direction
                self._divider_start_cursor = event.position()
                self.setCursor(
                    Qt.CursorShape.SplitHCursor if split.direction == "h"
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
            split, idx, drect, start_weights = self._divider_drag
            ws = list(start_weights)
            # Determine the rect covering split's two adjacent children, in the
            # split direction.
            delta_px = (
                event.position().x() - self._divider_start_cursor.x()
                if split.direction == "h"
                else event.position().y() - self._divider_start_cursor.y()
            )
            # Pair total weight is preserved → only redistribute between ws[idx] and ws[idx+1].
            # Convert pixel delta to weight delta using the split's container size.
            container_size_px = self._split_container_size(split, drect)
            if container_size_px <= 0:
                return
            total_pair = ws[idx] + ws[idx + 1]
            total_weights = sum(ws) or 1.0
            # Pixel fraction → weight fraction.
            weight_delta = delta_px / container_size_px * total_weights
            new_left = ws[idx] + weight_delta
            new_right = ws[idx + 1] - weight_delta
            min_w = 0.08 * total_weights  # ~8% min per pane
            if new_left < min_w:
                new_left, new_right = min_w, total_pair - min_w
            elif new_right < min_w:
                new_right, new_left = min_w, total_pair - min_w
            ws[idx] = new_left
            ws[idx + 1] = new_right
            split.weights = ws
            self.update()
            event.accept()
            return

        if self._panning:
            ref = self._pan_ref_rect
            if ref.width() <= 0 or ref.height() <= 0:
                return
            fit_x, fit_y = self._pan_ref_fit
            z = max(self.state.zoom, 1e-6)
            delta = event.position() - self._pan_start_pos
            self.state.pan_x = self._pan_start_state[0] + (delta.x() / ref.width()) / (max(fit_x, 1e-6) * z)
            self.state.pan_y = self._pan_start_state[1] + (delta.y() / ref.height()) / (max(fit_y, 1e-6) * z)
            self._clamp_pan()
            self.update()
            event.accept()
            return

        # Hover: update cursor over dividers.
        div = self._divider_at(event.position())
        if div is not None:
            split, _, _ = div
            self.setCursor(
                Qt.CursorShape.SplitHCursor if split.direction == "h"
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
            self._divider_axis = None
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
                split, _, _ = div
                # Equalize weights of all children.
                n = len(split.children)
                if n > 0:
                    split.weights = [1.0] * n
                    self.update()
                event.accept()
                return
            leaf_rects = self._leaf_rects()
            picked = self._leaf_at(pos, leaf_rects)
            if picked is not None:
                leaf, _ = picked
                if self.state.is_focused:
                    self.state.focused_slot_id = None
                else:
                    self.state.focused_slot_id = leaf.slot_id
                self.update()
            event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape and self.state.is_focused:
            self.state.focused_slot_id = None
            self.update()
            event.accept()
        elif key == Qt.Key.Key_0:
            self.state.zoom = 1.0
            self.state.pan_x = 0.0
            self.state.pan_y = 0.0
            self.update()
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
            from PyQt6.QtGui import QImage, QPixmap
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

    def _divider_at(self, pos: QPointF) -> tuple[SplitNode, int, QRect] | None:
        grab = self.DIVIDER_GRAB_PX
        for split, idx, drect in self._all_dividers():
            expanded = drect.adjusted(-grab, -grab, grab, grab) if split.direction == "h" else drect.adjusted(-grab, -grab, grab, grab)
            if expanded.contains(pos.toPoint()):
                return split, idx, drect
        return None

    def _split_container_size(self, split: SplitNode, divider_rect: QRect) -> int:
        # Walk tree to find the rect of this split's container.
        if self.state.root is None:
            return 0
        return self._find_split_container_size(self.state.root, self.rect(), split)

    def _find_split_container_size(self, node, rect: QRect, target: SplitNode) -> int:
        if isinstance(node, LeafNode):
            return 0
        assert isinstance(node, SplitNode)
        if node is target:
            return rect.width() if node.direction == "h" else rect.height()
        # Recurse with sub-rects (same layout math).
        gap = self.CELL_GAP
        ws = node.normalized_weights()
        n = len(node.children)
        if node.direction == "h":
            total_gap = gap * (n - 1)
            inner = max(rect.width() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            sizes[-1] = inner - sum(sizes[:-1])
            x = rect.x()
            for child, size in zip(node.children, sizes):
                child_rect = QRect(x, rect.y(), size, rect.height())
                r = self._find_split_container_size(child, child_rect, target)
                if r:
                    return r
                x += size + gap
        else:
            total_gap = gap * (n - 1)
            inner = max(rect.height() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            sizes[-1] = inner - sum(sizes[:-1])
            y = rect.y()
            for child, size in zip(node.children, sizes):
                child_rect = QRect(rect.x(), y, rect.width(), size)
                r = self._find_split_container_size(child, child_rect, target)
                if r:
                    return r
                y += size + gap
        return 0
