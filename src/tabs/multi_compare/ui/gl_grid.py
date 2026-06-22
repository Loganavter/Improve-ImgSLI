"""OpenGL grid widget for multi-compare — container-tree layout (i3/sway-style)."""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiScissor,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
    QShader,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtWidgets import QRhiWidget
from ui.widgets.gl_canvas.rhi_backend import (
    configure_rhi_widget,
    log_initialized_rhi_widget,
)

INTERNAL_SLOT_MIME = "application/x-imgsli-multi-slot"

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
    node_at_path,
)

_SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders" / "qrhi"


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid multi_compare shader: {name}")
    return shader


_QUAD_VERTICES = struct.pack(
    "<16f",
    -1.0, -1.0, 0.0, 1.0,
    +1.0, -1.0, 1.0, 1.0,
    -1.0, +1.0, 0.0, 0.0,
    +1.0, +1.0, 1.0, 0.0,
)
_FULLSCREEN_OVERLAY_VERTICES = struct.pack(
    "<16f",
    -1.0, 1.0, 0.0, 0.0,
    -1.0, -1.0, 0.0, 1.0,
    1.0, 1.0, 1.0, 0.0,
    1.0, -1.0, 1.0, 1.0,
)
_SLOT_UNIFORM_SIZE = 96  # mat4(64) + vec2 pan(8) + vec2 fit(8) + float zoom(4) + 12 pad
_OVERLAY_UNIFORM_SIZE = 64

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ImproveImgSLI")


class GLGridWidget(QRhiWidget):
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
        configure_rhi_widget(self)
        self._translate = translate or (lambda _key, default=None: default or _key)

        self.state = MultiCompareState()

        # QRhi resources
        self._rhi = None
        self._render_target = None
        self._pipeline = None
        self._overlay_pipeline = None
        self._vertex_buffer = None
        self._overlay_vertex_buffer = None
        self._sampler = None
        self._placeholder = None
        # per-slot resources
        self._slot_textures: dict[int, QRhiTexture] = {}
        self._slot_texture_sizes: dict[int, tuple[int, int]] = {}
        self._slot_uniform_buffers: list[object] = []
        self._slot_srbs: list[object] = []
        # overlay: QPainter → QImage → QRhiTexture each frame
        self._overlay_uniform_buffer = None
        self._overlay_texture = None
        self._overlay_texture_size: QSize | None = None
        self._overlay_srb = None
        # per-frame draw state
        self._draw_items: list[dict] = []
        # pending texture uploads to apply in render()
        self._pending_uploads: list[tuple[int, QImage]] = []
        self._pending_removes: list[int] = []

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
        if slot.image is None:
            return
        image = self._numpy_to_qimage(slot.image)
        if image is None:
            return
        self._pending_uploads.append((slot.id, image))
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
        self._pending_removes.append(slot_id)
        self.update()

    def _sync_textures(self) -> None:
        for slot in self.state.slots:
            if slot.id not in self._slot_textures and slot.image is not None:
                self.upload_image(slot)
        active_ids = {s.id for s in self.state.slots}
        stale = [sid for sid in self._slot_textures if sid not in active_ids]
        for sid in stale:
            self.remove_texture(sid)

    # ---- QRhi lifecycle ----

    def initialize(self, command_buffer) -> None:
        log_initialized_rhi_widget(self)
        rhi = self.rhi()
        target = self.renderTarget()
        if rhi is None or target is None:
            return
        self._rhi = rhi
        self._render_target = target

        self._vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Immutable,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(_QUAD_VERTICES),
        )
        self._vertex_buffer.create()

        self._overlay_vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Immutable,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(_FULLSCREEN_OVERLAY_VERTICES),
        )
        self._overlay_vertex_buffer.create()

        self._sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear, QRhiSampler.Filter.Linear, QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge, QRhiSampler.AddressMode.ClampToEdge,
        )
        self._sampler.create()

        self._placeholder = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        self._placeholder.create()

        self._overlay_uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _OVERLAY_UNIFORM_SIZE,
        )
        self._overlay_uniform_buffer.create()
        self._overlay_texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        self._overlay_texture.create()
        self._overlay_texture_size = QSize(1, 1)

        slot_pipeline = rhi.newGraphicsPipeline()
        slot_pipeline.setShaderStages([
            QRhiShaderStage(QRhiShaderStage.Type.Vertex, _load_shader("multi_compare.vert.qsb")),
            QRhiShaderStage(QRhiShaderStage.Type.Fragment, _load_shader("multi_compare.frag.qsb")),
        ])
        slot_pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        slot_pipeline.setSampleCount(target.sampleCount())
        slot_pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        slot_pipeline.setFlags(QRhiGraphicsPipeline.Flag.UsesScissor)
        first_srb = self._build_slot_srb(self._placeholder, None)
        slot_pipeline.setShaderResourceBindings(first_srb)
        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(16)])
        layout.setAttributes([
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
        ])
        slot_pipeline.setVertexInputLayout(layout)
        if not slot_pipeline.create():
            raise RuntimeError("Failed to create multi_compare slot pipeline")
        self._pipeline = slot_pipeline
        try:
            first_srb.destroy()
        except RuntimeError:
            pass

        overlay_pipeline = rhi.newGraphicsPipeline()
        overlay_pipeline.setShaderStages([
            QRhiShaderStage(QRhiShaderStage.Type.Vertex, _load_shader("overlay.vert.qsb")),
            QRhiShaderStage(QRhiShaderStage.Type.Fragment, _load_shader("overlay.frag.qsb")),
        ])
        overlay_pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        overlay_pipeline.setSampleCount(target.sampleCount())
        overlay_pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        overlay_pipeline.setTargetBlends([blend])
        self._overlay_srb = self._build_overlay_srb()
        overlay_pipeline.setShaderResourceBindings(self._overlay_srb)
        overlay_layout = QRhiVertexInputLayout()
        overlay_layout.setBindings([QRhiVertexInputBinding(16)])
        overlay_layout.setAttributes([
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
        ])
        overlay_pipeline.setVertexInputLayout(overlay_layout)
        if not overlay_pipeline.create():
            raise RuntimeError("Failed to create multi_compare overlay pipeline")
        self._overlay_pipeline = overlay_pipeline

        upload = rhi.nextResourceUpdateBatch()
        upload.uploadStaticBuffer(self._vertex_buffer, _QUAD_VERTICES)
        upload.uploadStaticBuffer(self._overlay_vertex_buffer, _FULLSCREEN_OVERLAY_VERTICES)
        ph = QImage(1, 1, QImage.Format.Format_RGBA8888)
        ph.fill(0)
        upload.uploadTexture(self._placeholder, ph)
        upload.uploadTexture(self._overlay_texture, ph)
        command_buffer.resourceUpdate(upload)

        self._initialized = True
        self._sync_textures()

    def releaseResources(self) -> None:
        for res in (
            self._pipeline, self._overlay_pipeline,
            self._vertex_buffer, self._overlay_vertex_buffer,
            self._sampler, self._placeholder,
            self._overlay_uniform_buffer, self._overlay_texture, self._overlay_srb,
            *self._slot_uniform_buffers, *self._slot_srbs, *self._slot_textures.values(),
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self._pipeline = None
        self._overlay_pipeline = None
        self._vertex_buffer = None
        self._overlay_vertex_buffer = None
        self._sampler = None
        self._placeholder = None
        self._overlay_uniform_buffer = None
        self._overlay_texture = None
        self._overlay_srb = None
        self._slot_uniform_buffers = []
        self._slot_srbs = []
        self._slot_textures = {}
        self._slot_texture_sizes = {}
        self._overlay_texture_size = None
        self._rhi = None
        self._render_target = None
        self._initialized = False

    def _build_slot_srb(self, texture, uniform):
        srb = self._rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        bindings = []
        if uniform is not None:
            bindings.append(QRhiShaderResourceBinding.uniformBuffer(0, stages, uniform))
        else:
            # Reuse overlay uniform buffer just so pipeline creation has a binding;
            # this SRB will not be used at draw time.
            placeholder_uniform = self._rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                _SLOT_UNIFORM_SIZE,
            )
            placeholder_uniform.create()
            self._slot_uniform_buffers.append(placeholder_uniform)
            bindings.append(QRhiShaderResourceBinding.uniformBuffer(0, stages, placeholder_uniform))
        bindings.append(
            QRhiShaderResourceBinding.sampledTexture(1, fragment, texture, self._sampler)
        )
        srb.setBindings(bindings)
        if not srb.create():
            raise RuntimeError("Failed to create multi_compare slot SRB")
        return srb

    def _build_overlay_srb(self):
        srb = self._rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings([
            QRhiShaderResourceBinding.uniformBuffer(0, stages, self._overlay_uniform_buffer),
            QRhiShaderResourceBinding.sampledTexture(
                1, fragment, self._overlay_texture or self._placeholder, self._sampler
            ),
        ])
        if not srb.create():
            raise RuntimeError("Failed to create multi_compare overlay SRB")
        return srb

    def _ensure_slot_resources(self, count: int) -> None:
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        while len(self._slot_uniform_buffers) < count:
            buf = self._rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                _SLOT_UNIFORM_SIZE,
            )
            buf.create()
            self._slot_uniform_buffers.append(buf)
        while len(self._slot_srbs) < count:
            srb = self._rhi.newShaderResourceBindings()
            fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
            srb.setBindings([
                QRhiShaderResourceBinding.uniformBuffer(
                    0, stages, self._slot_uniform_buffers[len(self._slot_srbs)]
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, self._placeholder, self._sampler
                ),
            ])
            srb.create()
            self._slot_srbs.append(srb)

    def _apply_pending_texture_ops(self, updates) -> None:
        for sid in self._pending_removes:
            tex = self._slot_textures.pop(sid, None)
            if tex is not None:
                try:
                    tex.destroy()
                except RuntimeError:
                    pass
            self._slot_texture_sizes.pop(sid, None)
        self._pending_removes.clear()
        for sid, image in self._pending_uploads:
            size = (image.width(), image.height())
            existing = self._slot_textures.get(sid)
            if existing is None or self._slot_texture_sizes.get(sid) != size:
                if existing is not None:
                    try:
                        existing.destroy()
                    except RuntimeError:
                        pass
                tex = self._rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(*size))
                tex.create()
                self._slot_textures[sid] = tex
                self._slot_texture_sizes[sid] = size
            updates.uploadTexture(self._slot_textures[sid], image)
        self._pending_uploads.clear()

    def _rebuild_slot_srb(self, index: int, texture) -> None:
        old = self._slot_srbs[index]
        try:
            old.destroy()
        except RuntimeError:
            pass
        srb = self._rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings([
            QRhiShaderResourceBinding.uniformBuffer(0, stages, self._slot_uniform_buffers[index]),
            QRhiShaderResourceBinding.sampledTexture(1, fragment, texture, self._sampler),
        ])
        srb.create()
        self._slot_srbs[index] = srb

    def render(self, command_buffer) -> None:
        if not self._initialized or self._rhi is None:
            return
        target = self.renderTarget()
        if target is None:
            return
        target_size = target.pixelSize()
        fb_w = float(target_size.width())
        fb_h = float(target_size.height())
        dpr = max(1.0, float(self.devicePixelRatioF()))

        updates = self._rhi.nextResourceUpdateBatch()
        self._sync_textures()
        self._apply_pending_texture_ops(updates)

        # Build per-slot draw items
        leaf_rects = self._leaf_rects()
        slot_by_id = {s.id: s for s in self.state.slots}
        focused_id = self.state.focused_slot_id if self.state.is_focused else None
        matrix = tuple(float(v) for v in self._rhi.clipSpaceCorrMatrix().data())

        draw_items: list[tuple[int, QRect, float, float]] = []
        for leaf, rect in leaf_rects:
            slot = slot_by_id.get(leaf.slot_id)
            if slot is None:
                continue
            if leaf.slot_id not in self._slot_textures:
                continue
            if focused_id is not None and leaf.slot_id != focused_id:
                continue
            draw_rect = self.rect() if focused_id is not None else rect
            fit_x, fit_y = self._fit_scale_for(slot, draw_rect)
            draw_items.append((leaf.slot_id, draw_rect, fit_x, fit_y))

        self._ensure_slot_resources(len(draw_items))
        for index, (slot_id, _draw_rect, fit_x, fit_y) in enumerate(draw_items):
            block = struct.pack(
                "<16f 2f 2f f 3f",
                *matrix,
                float(self.state.pan_x), float(self.state.pan_y),
                max(fit_x, 1e-6), max(fit_y, 1e-6),
                float(self.state.zoom),
                0.0, 0.0, 0.0,
            )
            updates.updateDynamicBuffer(self._slot_uniform_buffers[index], 0, block)
            self._rebuild_slot_srb(index, self._slot_textures[slot_id])

        # Build overlay
        overlay_image = self._build_overlay_image(leaf_rects, slot_by_id)
        if overlay_image is not None and not overlay_image.isNull():
            overlay_size = overlay_image.size()
            if self._overlay_texture_size != overlay_size:
                try:
                    self._overlay_texture.destroy()
                except RuntimeError:
                    pass
                self._overlay_texture = self._rhi.newTexture(QRhiTexture.Format.RGBA8, overlay_size)
                self._overlay_texture.create()
                self._overlay_texture_size = overlay_size
                try:
                    self._overlay_srb.destroy()
                except RuntimeError:
                    pass
                self._overlay_srb = self._build_overlay_srb()
            updates.uploadTexture(self._overlay_texture, overlay_image)
            updates.updateDynamicBuffer(
                self._overlay_uniform_buffer, 0,
                struct.pack("<16f", *matrix),
            )
            has_overlay = True
        else:
            has_overlay = False

        # Clear color
        bg = self._theme_or_palette_bg()
        from PySide6.QtGui import QColor as _QColor
        from PySide6.QtGui import QRhiDepthStencilClearValue
        clear_color = _QColor(bg)
        command_buffer.beginPass(
            target,
            clear_color,
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )

        if draw_items:
            command_buffer.setGraphicsPipeline(self._pipeline)
            command_buffer.setVertexInput(0, [(self._vertex_buffer, 0)])
            for index, (_slot_id, draw_rect, _fx, _fy) in enumerate(draw_items):
                rx = int(round(draw_rect.x() * dpr))
                ry = int(round(draw_rect.y() * dpr))
                rw = max(1, int(round(draw_rect.width() * dpr)))
                rh = max(1, int(round(draw_rect.height() * dpr)))
                if self._rhi.isYUpInFramebuffer():
                    ry = max(0, int(fb_h) - (ry + rh))
                command_buffer.setViewport(QRhiViewport(float(rx), float(ry), float(rw), float(rh)))
                command_buffer.setScissor(QRhiScissor(rx, ry, rw, rh))
                command_buffer.setShaderResources(self._slot_srbs[index])
                command_buffer.draw(4)

        if has_overlay:
            command_buffer.setGraphicsPipeline(self._overlay_pipeline)
            command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
            command_buffer.setShaderResources(self._overlay_srb)
            command_buffer.setVertexInput(0, [(self._overlay_vertex_buffer, 0)])
            command_buffer.draw(4)

        command_buffer.endPass()

    def _theme_or_palette_bg(self) -> QColor:
        bg = getattr(self, "_theme_background_color", None)
        if not isinstance(bg, QColor) or not bg.isValid():
            bg = self.palette().color(QPalette.ColorRole.Window)
        if not bg.isValid():
            bg = QColor(30, 30, 30)
        return bg

    def _build_overlay_image(self, leaf_rects, slot_by_id) -> QImage | None:
        w = max(1, self.width())
        h = max(1, self.height())
        dpr = max(1.0, float(self.devicePixelRatioF()))
        phys_w = max(1, int(round(w * dpr)))
        phys_h = max(1, int(round(h * dpr)))
        img = QImage(phys_w, phys_h, QImage.Format.Format_RGBA8888_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.scale(dpr, dpr)

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
        return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)

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
