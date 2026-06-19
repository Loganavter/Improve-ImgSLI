"""Controller for multi-compare tab — load/save with container-tree layout."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QFileDialog

from tabs.multi_compare.models import (
    LeafNode,
    MultiCompareState,
    SplitNode,
    slot_ids_in_tree,
)
from tabs.multi_compare.services.image_export import save_composite
from tabs.multi_compare.widget import MultiCompareWidget

logger = logging.getLogger("ImproveImgSLI")

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


class MultiCompareController:
    """Manages image loading and save composition for the multi-compare widget."""

    SAVE_OUTPUT_W = 1920
    SAVE_OUTPUT_H = 1080
    SAVE_CELL_GAP = 4
    SAVE_LABEL_FONT_PT = 14

    def __init__(
        self,
        widget: MultiCompareWidget,
        store: Any = None,
        *,
        translate=None,
        dialog_parent=None,
        open_export_dialog=None,
    ):
        self.widget = widget
        self.store = store
        self.translate = translate or (lambda _key, default=None: default or _key)
        self.dialog_parent = dialog_parent or widget
        self.open_export_dialog = open_export_dialog
        self.state = MultiCompareState()

        self.widget.images_dropped.connect(self._on_images_dropped)
        self.widget.add_requested.connect(self._on_add_requested)
        self.widget.save_requested.connect(self._on_save_requested)
        self.widget.set_state(self.state)

    # ---- public ----

    def load_images(self, paths: list[Path]) -> None:
        for path in paths:
            self._load_single_auto(path)
        self.widget.set_state(self.widget.state)

    def clear(self) -> None:
        self.state = MultiCompareState()
        self.widget.set_state(self.state)

    # ---- signals ----

    def _on_images_dropped(self, paths: list, target, side) -> None:
        """target: tuple (target_path_or_None, target_root_bool); side: 'left'/'right'/..."""
        from tabs.multi_compare.models import find_path
        target_path, target_root = target if isinstance(target, tuple) else (None, False)
        # First image goes to the cursor's drop zone; subsequent ones auto-tile
        # next to the just-added leaf (chain on its right/bottom).
        last_added: int | None = None
        for i, raw_path in enumerate(paths):
            path = Path(raw_path) if not isinstance(raw_path, Path) else raw_path
            arr = self._read_image(path)
            if arr is None:
                continue
            if i == 0:
                sid = self.widget.add_image_at(
                    path, arr, path.stem, target_path, side, target_root
                )
            else:
                next_side = "right" if side in ("left", "right") else "bottom"
                next_path: tuple[int, ...] | None = None
                if last_added is not None:
                    found = find_path(self.widget.state.root, last_added)
                    next_path = tuple(found) if found is not None else None
                if next_path is None:
                    sid = self.widget.add_image_auto(path, arr, path.stem)
                else:
                    sid = self.widget.add_image_at(
                        path, arr, path.stem, next_path, next_side, False
                    )
            if sid is not None:
                last_added = sid

    def _on_add_requested(self) -> None:
        start_dir = self._default_dir()
        filters = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"
        paths, _ = QFileDialog.getOpenFileNames(
            self.widget, "Add images to compare", start_dir, filters
        )
        if paths:
            self.load_images([Path(p) for p in paths])

    def _on_save_requested(self) -> None:
        if not slot_ids_in_tree(self.widget.state.root):
            return
        native_size = self._live_view_size()
        if not callable(self.open_export_dialog):
            logger.error("Multi Compare export dialog service is unavailable")
            return
        preview = self._render_export_preview(
            *native_size,
            self._background_color_from_settings(
                getattr(self.store, "settings", None)
            ),
            bool(
                getattr(
                    getattr(self.store, "settings", None),
                    "export_fill_background",
                    True,
                )
            ),
        )
        result_code, options = self.open_export_dialog(
            preview_image=preview,
            suggested_filename="multi_compare",
            native_size=native_size,
        )
        if int(result_code) != int(QDialog.DialogCode.Accepted):
            return
        try:
            image = self._compose_image(
                int(options["width"]),
                int(options["height"]),
                background_color=QColor(*options["background_color"]),
                fill_background=bool(options["fill_background"]),
            )
            saved_path = save_composite(image, options)
            self._persist_export_preferences(options)
            logger.info("Multi Compare composite saved to %s", saved_path)
        except Exception:
            logger.exception("Composite save failed")

    # ---- internals ----

    def _live_view_size(self) -> tuple[int, int]:
        width = max(1, int(self.widget.gl_grid.width()))
        height = max(1, int(self.widget.gl_grid.height()))
        return width, height

    def _render_export_preview(
        self,
        width: int,
        height: int,
        background_color: QColor,
        fill_background: bool,
    ) -> QPixmap:
        return QPixmap.fromImage(
            self._compose_image(
                width,
                height,
                background_color=background_color,
                fill_background=fill_background,
            )
        )

    def _default_dir(self) -> str:
        if self.store is not None:
            settings = getattr(self.store, "settings", None)
            if settings is not None:
                d = getattr(settings, "export_default_dir", None)
                if d:
                    return d
        return str(Path.home())

    @staticmethod
    def _background_color_from_settings(settings) -> QColor:
        color = getattr(settings, "export_background_color", None)
        if color is None:
            return QColor(20, 20, 20)
        if isinstance(color, QColor):
            return QColor(color)
        channels = (
            getattr(color, "r", 20),
            getattr(color, "g", 20),
            getattr(color, "b", 20),
            getattr(color, "a", 255),
        )
        return QColor(*channels)

    def _persist_export_preferences(self, options: dict) -> None:
        settings = getattr(self.store, "settings", None)
        if settings is None:
            return
        settings.export_default_dir = options["output_dir"]
        if "favorite_dir" in options:
            settings.export_favorite_dir = options["favorite_dir"]
        settings.export_last_format = options["format"]
        settings.export_quality = int(options["quality"])
        settings.export_fill_background = bool(options["fill_background"])
        try:
            from domain.types import Color

            settings.export_background_color = Color(*options["background_color"])
        except Exception:
            pass

    def _read_image(self, path: Path):
        try:
            from PIL import Image
            img = Image.open(path).convert("RGB")
            return np.ascontiguousarray(np.array(img, dtype=np.uint8))
        except Exception as e:
            logger.error("Failed to load %s: %s", path, e)
            return None

    def _load_single_auto(self, path: Path) -> None:
        arr = self._read_image(path)
        if arr is None:
            return
        self.widget.add_image_auto(path, arr, label=path.stem)

    # ---- compose ----

    def _compose_image(
        self,
        w: int | None = None,
        h: int | None = None,
        *,
        background_color: QColor | None = None,
        fill_background: bool = True,
    ) -> QImage:
        w = max(1, int(w or self.SAVE_OUTPUT_W))
        h = max(1, int(h or self.SAVE_OUTPUT_H))
        out = QImage(w, h, QImage.Format.Format_RGBA8888)
        out.fill(
            background_color
            if fill_background and background_color is not None
            else QColor(0, 0, 0, 0)
        )

        slot_by_id = {s.id: s for s in self.widget.state.slots}
        live_w, live_h = self._live_view_size()
        scale = min(w / live_w, h / live_h)
        gap = max(1, int(round(self.widget.gl_grid.CELL_GAP * scale)))
        focused_id = (
            self.widget.state.focused_slot_id
            if self.widget.state.is_focused
            else None
        )
        if focused_id is None:
            leaves = self._walk_compose(
                self.widget.state.root,
                QRect(0, 0, w, h),
                gap=gap,
            )
        else:
            leaves = [(focused_id, QRect(0, 0, w, h))]

        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font = QFont(painter.font())
        font.setPointSizeF(max(1.0, self.widget.gl_grid.LABEL_FONT_PT * scale))
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()

        for slot_id, rect in leaves:
            slot = slot_by_id.get(slot_id)
            if slot is None:
                continue
            if slot.image is not None:
                self._paint_slot_image(
                    painter,
                    rect,
                    slot.image,
                    zoom=self.widget.state.zoom,
                    pan_x=self.widget.state.pan_x,
                    pan_y=self.widget.state.pan_y,
                )
            if slot.label:
                self._paint_label(
                    painter,
                    fm,
                    rect,
                    slot.label,
                    scale=scale,
                )

        painter.end()
        return out

    def _walk_compose(
        self,
        node,
        rect: QRect,
        *,
        gap: int | None = None,
    ) -> list[tuple[int, QRect]]:
        if node is None:
            return []
        if isinstance(node, LeafNode):
            return [(node.slot_id, rect)]
        assert isinstance(node, SplitNode)
        gap = max(0, int(self.SAVE_CELL_GAP if gap is None else gap))
        ws = node.normalized_weights()
        n = len(node.children)
        out: list[tuple[int, QRect]] = []
        if node.direction == "h":
            total_gap = gap * (n - 1)
            inner = max(rect.width() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            sizes[-1] = inner - sum(sizes[:-1])
            x = rect.x()
            for child, size in zip(node.children, sizes):
                child_rect = QRect(x, rect.y(), size, rect.height())
                out.extend(self._walk_compose(child, child_rect, gap=gap))
                x += size + gap
        else:
            total_gap = gap * (n - 1)
            inner = max(rect.height() - total_gap, 1)
            sizes = [int(inner * w) for w in ws]
            sizes[-1] = inner - sum(sizes[:-1])
            y = rect.y()
            for child, size in zip(node.children, sizes):
                child_rect = QRect(rect.x(), y, rect.width(), size)
                out.extend(self._walk_compose(child, child_rect, gap=gap))
                y += size + gap
        return out

    def _paint_slot_image(
        self,
        painter: QPainter,
        cell_rect: QRect,
        image: np.ndarray,
        *,
        zoom: float,
        pan_x: float,
        pan_y: float,
    ) -> None:
        image_h, image_w = image.shape[:2]
        if image.ndim == 3 and image.shape[2] == 3:
            qimg = QImage(
                image.tobytes(),
                image_w,
                image_h,
                3 * image_w,
                QImage.Format.Format_RGB888,
            )
        elif image.ndim == 3 and image.shape[2] == 4:
            qimg = QImage(
                image.tobytes(),
                image_w,
                image_h,
                4 * image_w,
                QImage.Format.Format_RGBA8888,
            )
        else:
            return

        image_ar = image_w / max(image_h, 1)
        cell_ar = cell_rect.width() / max(cell_rect.height(), 1)
        if image_ar > cell_ar:
            fit_x, fit_y = 1.0, cell_ar / image_ar
        else:
            fit_x, fit_y = image_ar / cell_ar, 1.0

        # Forward form of the GL shader:
        # tex = .5 + fit * zoom * (source_uv - .5 + pan).
        target_x = cell_rect.x() + cell_rect.width() * (
            0.5 + fit_x * zoom * (-0.5 + pan_x)
        )
        target_y = cell_rect.y() + cell_rect.height() * (
            0.5 + fit_y * zoom * (-0.5 + pan_y)
        )
        target_w = cell_rect.width() * fit_x * zoom
        target_h = cell_rect.height() * fit_y * zoom

        painter.save()
        painter.setClipRect(cell_rect)
        painter.fillRect(cell_rect, QColor(0, 0, 0, 255))
        painter.drawImage(
            QRect(
                int(round(target_x)),
                int(round(target_y)),
                max(1, int(round(target_w))),
                max(1, int(round(target_h))),
            ),
            qimg,
        )
        painter.restore()

    def _paint_label(
        self,
        painter: QPainter,
        fm,
        cell_rect: QRect,
        label: str,
        *,
        scale: float = 1.0,
    ) -> None:
        text_w = fm.horizontalAdvance(label)
        text_h = fm.height()
        pad = max(1, int(round(self.widget.gl_grid.LABEL_PADDING * scale)))
        margin = max(1, int(round(6 * scale)))
        bottom_margin = max(1, int(round(4 * scale)))
        bg_w = min(text_w + pad * 2, cell_rect.width() - margin * 2)
        bg = QRect(
            cell_rect.x() + margin,
            cell_rect.bottom() - text_h - pad * 2 - bottom_margin,
            bg_w,
            text_h + pad * 2,
        )
        if bg.width() <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QBrush(QColor(0, 0, 0, self.widget.gl_grid.LABEL_BG_ALPHA))
        )
        radius = max(1, int(round(4 * scale)))
        painter.drawRoundedRect(bg, radius, radius)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(
            bg.adjusted(pad, 0, -pad, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            fm.elidedText(label, Qt.TextElideMode.ElideMiddle, bg.width() - pad * 2),
        )
