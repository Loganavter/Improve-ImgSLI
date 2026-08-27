"""Controller for multi-compare tab — load/save with container-tree layout.

Owns wiring (widget signals, settings/ui-mode subscriptions) and instance
state; the actual loading/pyramid/toast and export/save logic live in
``use_cases/loading.py`` and ``use_cases/export.py`` (mirrors image_compare's
``_session_controller.py`` + ``use_cases/`` split) — this class stays a thin
set of delegators plus the state those modules read and write.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS
from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.services.gpu_export import MultiCompareGpuExporter
from tabs.multi_compare.services.save_flow import MultiCompareSaveFlowCoordinator
from tabs.multi_compare.use_cases import export as export_use_cases
from tabs.multi_compare.use_cases import loading as loading_use_cases
from tabs.multi_compare.widget import MultiCompareWidget

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareController:
    """Manages image loading and save composition for the multi-compare widget."""

    SAVE_OUTPUT_W = 1920
    SAVE_OUTPUT_H = 1080
    PREVIEW_MAX_EDGE = 1024

    # Progress checkpoints re-exported from shared (single source).
    @property
    def _DECODE_DONE_PROGRESS(self) -> int:  # type: ignore[override]
        from tabs._shared.loading_toast import DECODE_DONE_PROGRESS as _V

        return _V

    @property
    def _PYRAMID_START_PROGRESS(self) -> int:  # type: ignore[override]
        from tabs._shared.loading_toast import PYRAMID_START_PROGRESS as _V

        return _V

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
        self._save_flow: MultiCompareSaveFlowCoordinator | None = None
        self._last_applied_ui_mode: str | None = None
        # B2/B3 shared coordinators (state-owning collaborators)
        from tabs._shared.loading_toast import LoadingToastCoordinator
        from tabs._shared.pyramid import PyramidBuildCoordinator

        def _mc_get_toast_manager():
            main_window = getattr(self.context, "main_window", None) if self.context else None
            return getattr(main_window, "toast_manager", None) if main_window else None

        self._loading_toast_coordinator = LoadingToastCoordinator(
            get_toast_manager=_mc_get_toast_manager,
            translate=self.translate,
        )
        self._loading_toasts: dict[int, int] = self._loading_toast_coordinator._loading_toasts  # type: ignore[attr-defined]

        def _mc_request_update():
            canvas = getattr(self.widget, "canvas", None)
            if canvas is not None:
                try:
                    canvas.request_view_update()
                except Exception:
                    pass

        self._pyramid_coordinator = PyramidBuildCoordinator(
            get_thread_pool=lambda: getattr(self.context, "thread_pool", None) if self.context else None,
            toast_coordinator=self._loading_toast_coordinator,
            request_view_update=_mc_request_update,
        )
        self._pyramid_builds: set[int] = self._pyramid_coordinator._pyramid_builds
        self._pyramid_toast_slot: dict[int, int] = self._pyramid_coordinator._pyramid_toast_slot

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
        if toolbar is None or not hasattr(toolbar, "apply_ui_mode"):
            return
        toolbar.apply_ui_mode(mode)
        self.widget.sync_divider_toolbar()
        self._last_applied_ui_mode = mode
        # Hidden toolbar slots must drop Find Action rows and shortcuts.
        self._resync_action_shortcuts_after_mode_change()

    def _resync_action_shortcuts_after_mode_change(self) -> None:
        try:
            from ui.actions.binder import resync_action_shortcuts

            window = self.widget.window() if self.widget is not None else None
            resync_action_shortcuts(window, active_tab="multi_compare")
        except Exception:
            logger.debug(
                "[mc-actions] shortcut resync after ui_mode failed",
                exc_info=True,
            )

    def _on_divider_color_picker_requested(self) -> None:
        existing = getattr(self, "_divider_color_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        from ui.widgets.color import ColorPickerDialog

        current = QColor(*self.widget.state.divider_settings.color_rgba)
        dialog = ColorPickerDialog(
            current,
            self.widget.window(),
            title=self.translate("ui.choose_divider_line_color", "Choose divider color"),
            show_alpha=True,
        )
<<<<<<< Updated upstream
        dialog.setModal(False)

        def on_color_selected(color):
            if color.isValid():
                self.widget.apply_divider_color(color)

        def on_finished(_result):
            self._divider_color_dialog = None

        dialog.colorSelected.connect(on_color_selected)
        dialog.finished.connect(on_finished)
        self._divider_color_dialog = dialog
        dialog.show()
=======
        logger.warning(
            "[divider-color-debug] picker closed: current=%s chosen=%s valid=%s",
            current.getRgb(), chosen.getRgb(), chosen.isValid(),
        )
        if chosen.isValid():
            self.widget.apply_divider_color(chosen)
>>>>>>> Stashed changes

    def _on_help_requested(self) -> None:
        self._call_service("show_help_dialog")

    def _on_quick_save_requested(self) -> None:
        export_use_cases.on_quick_save_requested(self)

    def _get_save_flow(self) -> MultiCompareSaveFlowCoordinator:
        return export_use_cases.get_save_flow(self)

    def shutdown(self) -> None:
        if self._save_flow is not None:
            self._save_flow.cancel_all_exports()
        if self._gpu_exporter is not None:
            self._gpu_exporter.shutdown()
            self._gpu_exporter = None

    def load_images(self, paths: list[Path]) -> None:
        for path in paths:
            self._load_single_auto(path)

    def begin_paste_placement(self, paths: list[Path]) -> None:
        """Start cursor-tracked DnD highlight, same cycle as external file drop."""
        self.widget.begin_pending_paste(paths)

    def rehydrate_slots(self, state) -> bool:
        """Decode ``path`` into ``slot.image`` for persisted slots (project load).

        Uses the same ``_read_image`` path as drag-open / file dialog loading.
        """
        changed = False
        for slot in state.slots:
            if slot.path is None or slot.image is not None:
                continue
            path = slot.path if isinstance(slot.path, Path) else Path(slot.path)
            arr = self._read_image(path)
            if arr is not None:
                slot.image = arr
                changed = True
        return changed

    def clear(self) -> None:
        self.widget.store.dispatch(mc_actions.clear())

    def _on_images_dropped(self, paths: list, target, side) -> None:
        loading_use_cases.on_images_dropped(self, paths, target, side)

    def _on_add_requested(self) -> None:
        start_dir = export_use_cases.default_dir(self)
        from shared.image_extensions import IMAGE_FILTER_GLOB

        filters = f"Images ({IMAGE_FILTER_GLOB});;All files (*)"
        paths, _ = QFileDialog.getOpenFileNames(
            self.widget, "Add images to compare", start_dir, filters
        )
        if paths:
            self.load_images([Path(p) for p in paths])

    def _on_save_requested(self) -> None:
        export_use_cases.on_save_requested(self)

    def _read_image(self, path: Path, *, slot_id: int | None = None, start_pyramid: bool = True):
        return loading_use_cases.read_image(
            self, path, slot_id=slot_id, start_pyramid=start_pyramid
        )

    def _start_pyramid_build(self, store, *, slot_id: int | None = None) -> None:
        # Prefer coordinator when present (covers thread_pool + toast routing)
        coord = getattr(self, "_pyramid_coordinator", None)
        if coord is not None:
            # MC abort predicate: not pyramid.valid
            # need pyramid reference for predicate; capture via closure after ensure
            # coordinator's start_build will create predicate if None, but we want
            # correct MC semantics (pyramid.valid). Provide explicit predicate
            # that closes over the resolved pyramid.
            from shared.image_processing.pyramid_registry import ensure_pyramid as _ensure

            _pyr = _ensure(store)

            def _should_abort(_p=_pyr):
                return not getattr(_p, "valid", True) if _p is not None else False

            # If pyramid is None, coordinator will handle finishing toast itself.
            coord.start_build(store, slot_id=slot_id, should_abort=_should_abort)
            return
        loading_use_cases.start_pyramid_build(self, store, slot_id=slot_id)

    def _on_pyramid_level_ready(self, payload=None) -> None:
        coord = getattr(self, "_pyramid_coordinator", None)
        if coord is not None:
            coord.on_level_ready(payload)
            return
        loading_use_cases.on_pyramid_level_ready(self, payload)

<<<<<<< Updated upstream
    def _show_loading_toast(self, slot_id: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.show(slot_id)
=======
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
>>>>>>> Stashed changes
            return
        loading_use_cases.show_loading_toast(self, slot_id)

    def _mark_full_res_ready(self, slot_id: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.mark_full_res_ready(slot_id)
            return
        loading_use_cases.mark_full_res_ready(self, slot_id)

    def _finish_loading_toast(self, slot_id: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.finish(slot_id)
            return
        loading_use_cases.finish_loading_toast(self, slot_id)

    def _dismiss_loading_toast(self, slot_id: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.dismiss(slot_id)
            return
        loading_use_cases.dismiss_loading_toast(self, slot_id)

    def _load_full_resolution_async(self, path: Path, slot_id: int) -> None:
        loading_use_cases.load_full_resolution_async(self, path, slot_id)

    def _on_full_resolution_error(self, path: Path, slot_id: int, err) -> None:
        loading_use_cases.on_full_resolution_error(self, path, slot_id, err)

    def _apply_full_resolution(self, slot_id: int, path: Path, store) -> None:
        loading_use_cases.apply_full_resolution(self, slot_id, path, store)

    def _load_single_auto(self, path: Path) -> None:
        loading_use_cases.load_single_auto(self, path)

    def _native_canvas_size(self) -> tuple[int, int] | None:
        return export_use_cases.native_canvas_size(self)

    def _compose_image(
        self,
        w: int | None = None,
        h: int | None = None,
        *,
        background_color: QColor | None = None,
        fill_background: bool = False,
    ):
        return export_use_cases.compose_image(
            self, w, h, background_color=background_color, fill_background=fill_background
        )