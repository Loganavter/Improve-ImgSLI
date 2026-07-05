"""Controller for multi-compare tab — load/save with container-tree layout."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QFileDialog

from tabs.multi_compare.models import slot_ids_in_tree
from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.services.composition_builder import build_composition_plan
from tabs.multi_compare.services.gpu_export import MultiCompareGpuExporter
from tabs.multi_compare.services.image_export import save_composite
from tabs.multi_compare.widget import MultiCompareWidget
from ui.canvas_presentation.composition import compute_native_canvas_size

logger = logging.getLogger("ImproveImgSLI")

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


class MultiCompareController:
    """Manages image loading and save composition for the multi-compare widget."""

    SAVE_OUTPUT_W = 1920
    SAVE_OUTPUT_H = 1080
    NATIVE_CANVAS_MAX_EDGE = 16384
    PREVIEW_MAX_EDGE = 1024

    def __init__(
        self,
        widget: MultiCompareWidget,
        store: Any = None,
        *,
        translate=None,
        dialog_parent=None,
        open_export_dialog=None,
        context=None,
    ):
        self.widget = widget
        self.store = store
        self.translate = translate or (lambda _key, default=None: default or _key)
        self.dialog_parent = dialog_parent or widget
        self.open_export_dialog = open_export_dialog
        self.context = context
        self._gpu_exporter: MultiCompareGpuExporter | None = None
        self._last_applied_ui_mode: str | None = None

        self.widget.images_dropped.connect(self._on_images_dropped)
        self.widget.add_requested.connect(self._on_add_requested)
        self.widget.save_requested.connect(self._on_save_requested)
        self.widget.quick_save_requested.connect(self._on_quick_save_requested)
        self.widget.settings_requested.connect(self._on_settings_requested)
        self.widget.help_requested.connect(self._on_help_requested)
        self.widget.divider_color_picker_requested.connect(
            self._on_divider_color_picker_requested
        )
        self._apply_ui_mode_to_toolbar()
        self._subscribe_to_ui_mode_changes()
        self._subscribe_to_settings_store_changes()

    def _call_service(self, name: str) -> None:
        if self.context is None:
            return
        try:
            self.context.call_service(name)
        except Exception:
            logger.exception("Tab service %s failed", name)

    def _on_settings_requested(self) -> None:
        self._call_service("show_settings_dialog")

    def _apply_ui_mode_to_toolbar(self) -> None:
        settings = getattr(self.store, "settings", None) if self.store else None
        mode = getattr(settings, "ui_mode", "beginner") or "beginner"
        self._apply_ui_mode(mode, source="initial-or-store-read")

    def _subscribe_to_ui_mode_changes(self) -> None:
        """React to global ui_mode switches the same way image-compare's LayoutPlugin does."""
        event_bus = getattr(self.context, "event_bus", None) if self.context else None
        if event_bus is None:
            return
        try:
            from plugins.settings.events import SettingsUIModeChangedEvent
        except Exception:
            return
        event_bus.subscribe(
            SettingsUIModeChangedEvent,
            self._on_ui_mode_changed_event,
        )

    def _on_ui_mode_changed_event(self, event) -> None:
        mode = getattr(event, "ui_mode", "beginner") or "beginner"
        self._apply_ui_mode(mode, source="event")

    def _subscribe_to_settings_store_changes(self) -> None:
        if self.store is None or not hasattr(self.store, "on_change"):
            return
        self.store.on_change(self._on_store_changed)

    def _on_store_changed(self, scope: str) -> None:
        settings = getattr(self.store, "settings", None) if self.store else None
        mode = getattr(settings, "ui_mode", "beginner") or "beginner"
        mode_changed = mode != self._last_applied_ui_mode
        if scope != "settings" and not mode_changed:
            return
        self._apply_ui_mode(mode, source=f"store:{scope}")

    def _apply_ui_mode(self, mode: str, *, source: str) -> None:
        toolbar = getattr(self.widget, "toolbar", None)
        if not hasattr(toolbar, "apply_ui_mode"):
            return
        toolbar.apply_ui_mode(mode)
        self.widget.sync_divider_toolbar()
        self._last_applied_ui_mode = mode

    def _on_divider_color_picker_requested(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        current = QColor(*self.widget.state.divider_settings.color_rgba)
        chosen = QColorDialog.getColor(
            current,
            None,
            self.translate("ui.choose_divider_line_color", "Choose divider color"),
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        logger.warning(
            "[divider-color-debug] picker closed: current=%s chosen=%s valid=%s",
            current.getRgb(), chosen.getRgb(), chosen.isValid(),
        )
        if chosen.isValid():
            self.widget.apply_divider_color(chosen)

    def _on_help_requested(self) -> None:
        self._call_service("show_help_dialog")

    def _on_quick_save_requested(self) -> None:
        self._on_save_requested()

    def shutdown(self) -> None:
        if self._gpu_exporter is not None:
            self._gpu_exporter.shutdown()
            self._gpu_exporter = None

    def load_images(self, paths: list[Path]) -> None:
        for path in paths:
            self._load_single_auto(path)

    def clear(self) -> None:
        self.widget.store.dispatch(mc_actions.clear())

    def _on_images_dropped(self, paths: list, target, side) -> None:
        """target: tuple (target_path_or_None, target_root_bool); side: 'left'/'right'/..."""
        from tabs.multi_compare.models import find_path

        target_path, target_root = (
            target if isinstance(target, tuple) else (None, False)
        )

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
        import time

        t_start = time.perf_counter()
        logger.info("[mc-export] save requested")
        if not slot_ids_in_tree(self.widget.state.root):
            logger.info("[mc-export] no slots in tree, abort")
            return

        t0 = time.perf_counter()
        native_size = self._native_canvas_size() or self._live_view_size()
        logger.info(
            "[mc-export] native_size=%s computed in %.1f ms",
            native_size,
            (time.perf_counter() - t0) * 1000.0,
        )

        if not callable(self.open_export_dialog):
            self.open_export_dialog = self._open_local_export_dialog

        t0 = time.perf_counter()
        preview = self._render_export_preview(
            *native_size,
            self._background_color_from_settings(getattr(self.store, "settings", None)),
            bool(
                getattr(
                    getattr(self.store, "settings", None),
                    "export_fill_background",
                    True,
                )
            ),
        )
        logger.info(
            "[mc-export] preview rendered in %.1f ms (size=%dx%d)",
            (time.perf_counter() - t0) * 1000.0,
            preview.width() if preview is not None else -1,
            preview.height() if preview is not None else -1,
        )

        t0 = time.perf_counter()
        logger.info("[mc-export] opening export dialog...")
        result_code, options = self.open_export_dialog(
            preview_image=preview,
            suggested_filename="multi_compare",
            native_size=native_size,
        )
        logger.info(
            "[mc-export] dialog closed in %.1f ms (result=%s)",
            (time.perf_counter() - t0) * 1000.0,
            result_code,
        )

        if int(result_code) != int(QDialog.DialogCode.Accepted):
            logger.info(
                "[mc-export] dialog cancelled, total=%.1f ms",
                (time.perf_counter() - t_start) * 1000.0,
            )
            return
        try:
            t0 = time.perf_counter()
            logger.info(
                "[mc-export] composing final image %dx%d",
                int(options["width"]),
                int(options["height"]),
            )
            image = self._compose_image(
                int(options["width"]),
                int(options["height"]),
                background_color=QColor(*options["background_color"]),
                fill_background=bool(options["fill_background"]),
            )
            logger.info(
                "[mc-export] composed in %.1f ms (qimage=%dx%d)",
                (time.perf_counter() - t0) * 1000.0,
                image.width(),
                image.height(),
            )

            t0 = time.perf_counter()
            saved_path = save_composite(image, options)
            logger.info(
                "[mc-export] save_composite in %.1f ms -> %s",
                (time.perf_counter() - t0) * 1000.0,
                saved_path,
            )

            self._persist_export_preferences(options)
            logger.info(
                "Multi Compare composite saved to %s (total=%.1f ms)",
                saved_path,
                (time.perf_counter() - t_start) * 1000.0,
            )
        except Exception:
            logger.exception("Composite save failed")

    def _open_local_export_dialog(
        self,
        *,
        preview_image,
        suggested_filename: str,
        native_size: tuple[int, int],
    ):
        from resources.translations import tr

        from tabs.multi_compare.plugins.export import (
            MultiCompareExportDialog,
            MultiCompareExportDialogState,
        )

        settings = getattr(self.store, "settings", None)
        state = MultiCompareExportDialogState(
            current_language=getattr(settings, "current_language", "en"),
            output_dir=self._default_dir(),
            favorite_dir=getattr(settings, "export_favorite_dir", None),
            last_format=getattr(settings, "export_last_format", "PNG"),
            quality=int(getattr(settings, "export_quality", 95) or 95),
            png_compress_level=int(
                getattr(settings, "export_png_compress_level", 9) or 9
            ),
            fill_background=bool(getattr(settings, "export_fill_background", True)),
            background_color=self._background_color_from_settings(settings),
            comment_text=getattr(settings, "export_comment_text", "") or "",
            comment_keep_default=bool(
                getattr(settings, "export_comment_keep_default", False)
            ),
            resolution_scale=float(
                getattr(settings, "export_resolution_scale", 1.0) or 1.0
            ),
        )
        dialog = MultiCompareExportDialog(
            state,
            preview_image=preview_image,
            suggested_filename=suggested_filename,
            native_size=native_size,
            tr_func=tr,
            on_set_favorite_dir=self._set_favorite_dir,
            parent=None,
        )
        return dialog.exec(), dialog.get_export_options()

    def _live_view_size(self) -> tuple[int, int]:
        width = max(1, int(self.widget.canvas.width()))
        height = max(1, int(self.widget.canvas.height()))
        return width, height

    def _native_canvas_size(self) -> tuple[int, int] | None:
        """Smallest canvas where every loaded slot renders at native resolution.

        Delegates to the composition module so live render, export, and the
        export dialog's suggested resolution all share one source of truth.
        """
        plan = build_composition_plan(self.widget.state, include_labels=False)
        if plan is None:
            return None
        return compute_native_canvas_size(
            plan.root, max_edge=self.NATIVE_CANVAS_MAX_EDGE
        )

    def _render_export_preview(
        self,
        width: int,
        height: int,
        background_color: QColor,
        fill_background: bool,
    ) -> QPixmap:

        longest = max(int(width), int(height))
        if longest > self.PREVIEW_MAX_EDGE:
            scale = self.PREVIEW_MAX_EDGE / float(longest)
            width = max(1, int(round(width * scale)))
            height = max(1, int(round(height * scale)))
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
        if "png_compress_level" in options:
            settings.export_png_compress_level = int(options["png_compress_level"])
        if "png_optimize" in options:
            settings.export_png_optimize = bool(options["png_optimize"])
        settings.export_fill_background = bool(options["fill_background"])
        if "resolution_scale" in options:
            settings.export_resolution_scale = float(options["resolution_scale"])
        if "comment_text" in options:
            settings.export_comment_text = options["comment_text"]
        if "comment_keep_default" in options:
            settings.export_comment_keep_default = bool(options["comment_keep_default"])
        try:
            from domain.types import Color

            settings.export_background_color = Color(*options["background_color"])
        except Exception:
            pass

    def _set_favorite_dir(self, path: str) -> None:
        settings = getattr(self.store, "settings", None)
        if settings is not None:
            settings.export_favorite_dir = path

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

    def _compose_image(
        self,
        w: int | None = None,
        h: int | None = None,
        *,
        background_color: QColor | None = None,
        fill_background: bool = True,
    ) -> QImage:
        """Render the multi-compare scene at ``w × h``.

        The composition canvas is always the native size (image-extent driven);
        ``w × h`` is the framebuffer / output. The renderer letterboxes the
        canvas into it via ``sr = min(w/canvas_w, h/canvas_h)``.
        """
        import time

        t0 = time.perf_counter()
        state = self.widget.state
        composition = build_composition_plan(state)
        logger.info(
            "[mc-export] build_composition_plan in %.1f ms (canvas=%s)",
            (time.perf_counter() - t0) * 1000.0,
            (composition.canvas_w, composition.canvas_h) if composition else None,
        )
        if composition is None:
            return QImage(
                max(1, int(w or self.SAVE_OUTPUT_W)),
                max(1, int(h or self.SAVE_OUTPUT_H)),
                QImage.Format.Format_RGBA8888,
            )
        output_w = int(w) if w else composition.canvas_w
        output_h = int(h) if h else composition.canvas_h
        if self._gpu_exporter is None:
            logger.info("[mc-export] creating MultiCompareGpuExporter")
            self._gpu_exporter = MultiCompareGpuExporter()
        logger.info(
            "[mc-export] gpu.render_to_qimage start fb=%dx%d (canvas=%dx%d)",
            output_w,
            output_h,
            composition.canvas_w,
            composition.canvas_h,
        )
        t0 = time.perf_counter()
        image = self._gpu_exporter.render_to_qimage(
            composition,
            output_w=output_w,
            output_h=output_h,
            background_color=background_color,
            fill_background=fill_background,
        )
        logger.info(
            "[mc-export] gpu.render_to_qimage done in %.1f ms",
            (time.perf_counter() - t0) * 1000.0,
        )
        return image
