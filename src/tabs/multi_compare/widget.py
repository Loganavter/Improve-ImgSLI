"""Main widget for multi-compare tab — composes toolbar + GL grid + footer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
)
from PySide6.QtWidgets import QVBoxLayout, QWidget

from domain.qt_adapters import ensure_visible_qcolor
from domain.types import Color
from tabs.multi_compare.context_menu import MultiCompareContextMenuProvider
from tabs.multi_compare.models import (
    DEFAULT_DIVIDER_COLOR_RGBA,
    MultiCompareDividerSettings,
    MultiCompareLabelSettings,
    MultiCompareState,
    leaves,
    node_at_path,
    slot_ids_in_tree,
)
from tabs.multi_compare.scene import MultiCompareStore, actions
from tabs.multi_compare.ui.canvas_widget import (
    INTERNAL_SLOT_MIME,
    MultiCompareCanvasWidget,
)
from tabs.multi_compare.ui.footer import MultiCompareFooter
from tabs.multi_compare.ui.toolbar import MultiCompareToolbar
from tabs.multi_compare.icons import Icon
from ui.context_menu.manager import install_context_menu_provider
from ui.widgets.font_settings_flyout import FontSettingsFlyout
from ui.widgets.startup_placeholder import StartupPlaceholder
from ui.widgets.zoom_indicator import ZoomIndicator

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


class MultiCompareFontSettingsFlyout(FontSettingsFlyout):
    """Multi-compare subset of the shared filename text flyout."""

    def __init__(self, parent: QWidget, *, translate) -> None:
        self._translate = translate
        super().__init__(parent)
        self._placement_label.hide()
        for radio in self._pos_radios.values():
            radio.hide()

    def _tr(self, key: str) -> str:
        return self._translate(key, key.rsplit(".", 1)[-1].replace("_", " ").title())


class MultiCompareWidget(QWidget):
    """Composite widget: toolbar + GL grid + footer + smart DnD.

    State lives in a local Redux-style ``MultiCompareStore``. UI changes go
    through ``self.store.dispatch(...)``; the widget re-pushes the new state
    into the canvas via the store subscription.
    """

    images_dropped = Signal(list, object, object)
    add_requested = Signal()
    save_requested = Signal()
    quick_save_requested = Signal()
    settings_requested = Signal()
    help_requested = Signal()
    divider_color_picker_requested = Signal()

    def __init__(
        self,
        parent=None,
        *,
        translate=None,
        lang_provider=None,
    ):
        super().__init__(parent)
        self.store = MultiCompareStore()

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toolbar = MultiCompareToolbar(self)
        self._canvas_container = QWidget(self)
        canvas_container_layout = QVBoxLayout(self._canvas_container)
        canvas_container_layout.setContentsMargins(0, 0, 0, 0)
        canvas_container_layout.setSpacing(0)
        self.canvas = MultiCompareCanvasWidget(self._canvas_container, translate=translate)
        canvas_container_layout.addWidget(self.canvas)
        self.footer = MultiCompareFooter(self)
        self._translate = translate or (lambda _key, default=None: default or _key)
        self._pending_duplicate_source: int | None = None
        self._pending_paste_paths: list[Path] | None = None
        self._divider_toolbar_sync_pending = False
        self._context_menu_provider = install_context_menu_provider(
            MultiCompareContextMenuProvider(self)
        )
        self.font_settings_flyout = MultiCompareFontSettingsFlyout(
            self,
            translate=self._translate,
        )
        self.font_settings_flyout.hide()
        self._font_popup_open = False

        layout.addWidget(self.toolbar)
        layout.addWidget(self._canvas_container, 1)
        layout.addWidget(self.footer)

        self.canvas.set_dispatch(self.store.dispatch)
        self.canvas.set_state(self.store.state)
        self.store.subscribe(self._on_store_change)

        self.toolbar.add_clicked.connect(self.add_requested)
        self.toolbar.text_settings_clicked.connect(self._toggle_font_settings_flyout)
        self.toolbar.quick_save_clicked.connect(self.quick_save_requested)
        self.toolbar.settings_clicked.connect(self.settings_requested)
        self.toolbar.help_clicked.connect(self.help_requested)
        self.toolbar.divider_visible_toggled.connect(self._on_divider_visible_toggled)
        self.toolbar.divider_width_changed.connect(self._on_divider_width_changed)
        self.toolbar.divider_color_clicked.connect(self.divider_color_picker_requested)
        self.footer.save_clicked.connect(self.save_requested)
        self._sync_divider_toolbar()

        self._startup_placeholder = StartupPlaceholder(
            self, target_widget=self._canvas_container
        )
        self._startup_placeholder.set_background_color(
            self.canvas._theme_or_palette_bg()
        )
        self._startup_placeholder.raise_()
        self.canvas.firstFrameRendered.connect(self._on_first_frame)

        self.zoom_indicator = ZoomIndicator(
            self,
            lang_provider=lang_provider or (lambda: "en"),
            target_widget=self._canvas_container,
            reset_icon=Icon.SYNC,
        )
        self.zoom_indicator.btn_zoom_reset.clicked.connect(
            lambda: self.store.dispatch(actions.reset_view())
        )
        self._sync_zoom_indicator()
        self.font_settings_flyout.settings_changed.connect(
            self._on_font_settings_changed
        )
        self.font_settings_flyout.closed.connect(self._on_font_settings_closed)

    def _sync_zoom_indicator(self) -> None:
        indicator = getattr(self, "zoom_indicator", None)
        if indicator is None:
            return
        st = self.store.state
        indicator.update_zoom(
            float(getattr(st, "zoom", 1.0)),
            float(getattr(st, "pan_x", 0.0)),
            float(getattr(st, "pan_y", 0.0)),
        )

    def _on_first_frame(self) -> None:
        if self._startup_placeholder is not None:
            self._startup_placeholder.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        placeholder = getattr(self, "_startup_placeholder", None)
        if placeholder is not None and placeholder.isVisible():
            placeholder.sync_geometry()
        indicator = getattr(self, "zoom_indicator", None)
        if indicator is not None and indicator.isVisible():
            indicator.sync_position()

    @property
    def state(self) -> MultiCompareState:
        return self.store.state

    def _on_store_change(self, _action, new_state: MultiCompareState) -> None:
        self.canvas.set_state(new_state)
        # Indicator show/hide sits above the QRhi canvas; sync after set_state,
        # then poke another view update so reset-from-overlay cannot leave a
        # stale backing frame (see MultiCompareCanvasWidget.request_view_update).
        self._sync_zoom_indicator()
        action_type = getattr(_action, "type", "") or ""
        if action_type in {
            "multi_compare/set_zoom",
            "multi_compare/set_pan",
            "multi_compare/reset_view",
        }:
            from ui.widgets.canvas.rhi_present_sync import schedule_compositor_sync

            self.canvas.request_view_update()
            # Flush the Wayland/Vulkan catch-up on gesture settle — otherwise
            # the first flyout after zoom restacks and the image jumps while
            # the zoom % chip stays unchanged.
            schedule_compositor_sync(self.canvas, reason=action_type)
        self.sync_divider_toolbar()
        if self._font_popup_open:
            self._sync_font_settings_flyout()

    def sync_divider_toolbar(self) -> None:
        self._sync_divider_toolbar()
        self._queue_divider_toolbar_resync()

    def _queue_divider_toolbar_resync(self) -> None:
        if self._divider_toolbar_sync_pending:
            return
        self._divider_toolbar_sync_pending = True
        QTimer.singleShot(0, self._run_queued_divider_toolbar_sync)

    def _run_queued_divider_toolbar_sync(self) -> None:
        self._divider_toolbar_sync_pending = False
        self._sync_divider_toolbar()

    def _sync_divider_toolbar(self) -> None:
        ds = self.store.state.divider_settings
        btn = self.toolbar.btn_divider_visible
        btn.blockSignals(True)
        btn.setChecked(not ds.visible)
        btn.blockSignals(False)
        width_btn = self.toolbar.btn_divider_width
        if hasattr(width_btn, "get_value") and hasattr(width_btn, "set_value"):
            ui_value = ds.thickness if ds.visible else 0
            if width_btn.get_value() != ui_value:
                width_btn.blockSignals(True)
                width_btn.set_value(ui_value)
                width_btn.blockSignals(False)
        color = ensure_visible_qcolor(
            ds.color_rgba, fallback=Color(*DEFAULT_DIVIDER_COLOR_RGBA)
        )
        if hasattr(self.toolbar.btn_divider_color, "setUnderlineColor"):
            self.toolbar.btn_divider_color.setUnderlineColor(color)
        if hasattr(width_btn, "setUnderlineColor"):
            width_btn.setUnderlineColor(color)

    def _on_divider_visible_toggled(self, visible: bool) -> None:
        ds = self.store.state.divider_settings
        new_ds = MultiCompareDividerSettings(
            visible=bool(visible),
            thickness=ds.thickness,
            color_rgba=ds.color_rgba,
        )
        self.store.dispatch(actions.set_divider_settings(new_ds))

    def _on_divider_width_changed(self, width: int) -> None:
        ds = self.store.state.divider_settings
        thickness = max(0, int(width))
        new_ds = MultiCompareDividerSettings(
            visible=thickness > 0,
            thickness=thickness if thickness > 0 else ds.thickness,
            color_rgba=ds.color_rgba,
        )
        if new_ds == ds:
            return
        self.store.dispatch(actions.set_divider_settings(new_ds))

    def apply_divider_color(self, color: QColor) -> None:
        if color is None or not color.isValid():
            return
        visible = ensure_visible_qcolor(
            color, fallback=Color(*DEFAULT_DIVIDER_COLOR_RGBA)
        )
        ds = self.store.state.divider_settings
        new_ds = MultiCompareDividerSettings(
            visible=ds.visible,
            thickness=ds.thickness,
            color_rgba=(
                visible.red(),
                visible.green(),
                visible.blue(),
                visible.alpha(),
            ),
        )
        self.store.dispatch(actions.set_divider_settings(new_ds))

    def _sync_font_settings_flyout(self) -> None:
        from domain.qt_adapters import ensure_visible_qcolor
        from domain.types import Color

        st = self.state.label_settings
        self.font_settings_flyout.set_values(
            st.font_size_percent,
            st.font_weight,
            ensure_visible_qcolor(st.text_rgba, fallback=Color(255, 255, 255, 255)),
            ensure_visible_qcolor(st.bg_rgba, fallback=Color(0, 0, 0, 255)),
            st.draw_background,
            "edges",
            st.text_alpha_percent,
        )

    def _toggle_font_settings_flyout(self) -> None:
        if self._font_popup_open:
            self.font_settings_flyout.hide()
            return
        self.show_font_settings_flyout()

    def show_font_settings_flyout(self) -> None:
        """Open the text flyout without toggle-close (Find Action reveal/run)."""
        if self._font_popup_open:
            return
        self._sync_font_settings_flyout()
        self.font_settings_flyout.show_aligned(
            self.toolbar.btn_text_settings,
            anchor_point="bottom-right",
            flyout_point="top-left",
            offset=10,
            animation="slide",
        )
        if hasattr(self.toolbar.btn_text_settings, "setFlyoutOpen"):
            self.toolbar.btn_text_settings.setFlyoutOpen(True)
        self._font_popup_open = True

    def _on_font_settings_closed(self) -> None:
        self._font_popup_open = False
        if hasattr(self.toolbar.btn_text_settings, "setFlyoutOpen"):
            self.toolbar.btn_text_settings.setFlyoutOpen(False)

    def _on_font_settings_changed(
        self,
        size: int,
        weight: int,
        color: QColor,
        bg_color: QColor,
        draw_bg: bool,
        _placement: str,
        opacity: int,
    ) -> None:
        settings = MultiCompareLabelSettings(
            font_size_percent=max(1, int(size)),
            font_weight=max(0, int(weight)),
            text_rgba=(
                color.red(),
                color.green(),
                color.blue(),
                color.alpha(),
            ),
            bg_rgba=(
                bg_color.red(),
                bg_color.green(),
                bg_color.blue(),
                bg_color.alpha(),
            ),
            draw_background=bool(draw_bg),
            text_alpha_percent=max(0, min(100, int(opacity))),
        )
        self.store.dispatch(actions.set_label_settings(settings))

    def add_image_auto(
        self, path: Path, image: "TiledPixelStore", label: str = ""
    ) -> int | None:
        """Append an image by splitting the largest leaf along its longer axis."""
        if len(self.state.slots) >= self.state.max_slots:
            return None
        if self.state.root is None:
            target_path, side, target_root = None, None, True
        else:
            target_path, side = self._pick_auto_target()
            target_root = False
        before = len(self.state.slots)
        self.store.dispatch(
            actions.add_slot(
                path=path,
                image=image,
                label=label or path.stem,
                target_path=target_path,
                side=side,
                target_root=target_root,
            )
        )
        return self.state.slots[-1].id if len(self.state.slots) > before else None

    def add_image_at(
        self,
        path: Path,
        image: "TiledPixelStore",
        label: str,
        target_path: tuple[int, ...] | None,
        side: str | None,
        target_root: bool,
    ) -> int | None:
        if len(self.state.slots) >= self.state.max_slots:
            return None

        if (
            not target_root
            and (target_path is None or side is None)
            and self.state.root is not None
        ):
            target_path, side = self._pick_auto_target()
        before = len(self.state.slots)
        self.store.dispatch(
            actions.add_slot(
                path=path,
                image=image,
                label=label or path.stem,
                target_path=target_path,
                side=side,
                target_root=target_root or self.state.root is None,
            )
        )
        return self.state.slots[-1].id if len(self.state.slots) > before else None

    def _pick_auto_target(self) -> tuple[tuple[int, ...], str]:
        """Pick the existing leaf with the largest rect; split along its longer axis."""
        entries = self.canvas._leaf_paths_and_rects()
        if not entries:
            return (), "right"
        leaf, rect, path = max(entries, key=lambda e: e[1].width() * e[1].height())
        side = "right" if rect.width() >= rect.height() else "bottom"
        return path, side

    def remove_slot(self, slot_id: int) -> None:
        self.store.dispatch(actions.remove_slot(slot_id))

    def reset_view(self) -> None:
        self.store.dispatch(actions.reset_view())

    def _has_image_urls(self, mime) -> bool:
        if not mime.hasUrls():
            return False
        for url in mime.urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in _IMAGE_EXTENSIONS:
                return True
        return False

    def _has_internal_slot(self, mime) -> bool:
        return mime.hasFormat(INTERNAL_SLOT_MIME)

    def _internal_source_slot_id(self, mime) -> int | None:
        if not mime.hasFormat(INTERNAL_SLOT_MIME):
            return None
        try:
            return int(bytes(mime.data(INTERNAL_SLOT_MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _grid_local_pos(self, pos):
        return self.canvas.mapFrom(self, pos)

    def _resolve_drop_target(self, pos, *, internal: bool):
        local = self._grid_local_pos(pos)
        if internal:
            return self.canvas.compute_drop_target(local, include_center=True)
        if len(slot_ids_in_tree(self.state.root)) >= self.state.max_slots:
            return None, None, False, None
        return self.canvas.compute_drop_target(local)

    def _apply_drag_preview(self, event, internal: bool) -> None:
        tgt_path, side, root_tgt, swap_id = self._resolve_drop_target(
            event.position().toPoint(), internal=internal
        )
        source_id = (
            self._internal_source_slot_id(event.mimeData()) if internal else None
        )
        self.store.dispatch(
            actions.set_drag_state(
                active=True,
                internal=internal,
                source_slot_id=source_id,
                target_path=tgt_path,
                target_side=side,
                target_root=root_tgt,
                target_swap_slot_id=swap_id,
            )
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        self._cancel_pending_placements()
        if self._has_internal_slot(event.mimeData()):
            self._apply_drag_preview(event, internal=True)
            event.acceptProposedAction()
            return
        if self._has_image_urls(event.mimeData()):
            self._apply_drag_preview(event, internal=False)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._has_internal_slot(event.mimeData()):
            self._apply_drag_preview(event, internal=True)
            event.acceptProposedAction()
            return
        if self._has_image_urls(event.mimeData()):
            self._apply_drag_preview(event, internal=False)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.store.dispatch(actions.set_drag_state(active=False))
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        if self._has_internal_slot(mime):
            source_id = self._internal_source_slot_id(mime)
            tgt_path, side, _, swap_id = self._resolve_drop_target(
                event.position().toPoint(), internal=True
            )
            self.store.dispatch(actions.set_drag_state(active=False))
            if source_id is not None and side is not None:
                self._apply_internal_drop(source_id, tgt_path, side, swap_id)
            event.acceptProposedAction()
            return

        tgt_path, side, root_tgt, _ = self._resolve_drop_target(
            event.position().toPoint(), internal=False
        )
        self.store.dispatch(actions.set_drag_state(active=False))
        paths = []
        for url in mime.urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
                paths.append(path)
        if paths:
            self.images_dropped.emit(paths, (tgt_path, root_tgt), side)
            event.acceptProposedAction()

    def _apply_internal_drop(
        self,
        source_id: int,
        target_path: tuple[int, ...] | None,
        side: str,
        swap_slot_id: int | None,
    ) -> None:
        if side == "center" and swap_slot_id is not None and swap_slot_id != source_id:
            self.store.dispatch(actions.swap_slots(source_id, swap_slot_id))
            return
        if target_path is None:
            return
        anchor_slot = self._anchor_slot_for_path(target_path)
        if anchor_slot is None or anchor_slot == source_id:
            return
        self.store.dispatch(
            actions.move_slot(
                source_slot_id=source_id,
                target_path=target_path,
                target_anchor_slot_id=anchor_slot,
                side=side,
            )
        )

    def _anchor_slot_for_path(self, path: tuple[int, ...]) -> int | None:
        """Return slot_id of the first leaf inside the subtree at ``path``."""
        node = node_at_path(self.state.root, path)
        if node is None:
            return None
        first = leaves(node)
        return first[0].slot_id if first else None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._has_pending_placement():
            self._cancel_pending_placements()
            event.accept()
            return
        self.canvas.keyPressEvent(event)

    def begin_pending_duplicate(self, source_slot_id: int) -> None:
        self._cancel_pending_placements()
        source = next((s for s in self.state.slots if s.id == source_slot_id), None)
        if source is None or source.image is None:
            return
        if len(self.state.slots) >= self.state.max_slots:
            return
        self._pending_duplicate_source = source_slot_id
        self._arm_pending_placement_input()
        self._update_pending_drag_preview(self._canvas_cursor_pos(), internal=True)

    def begin_pending_paste(self, paths: list[Path]) -> None:
        """Enter external DnD placement: highlight under cursor, click to drop."""
        self._cancel_pending_placements()
        valid = [Path(p) for p in paths if Path(p).is_file()]
        if not valid:
            return
        if len(slot_ids_in_tree(self.state.root)) >= self.state.max_slots:
            return
        self._pending_paste_paths = valid
        self._arm_pending_placement_input()
        self._update_pending_drag_preview(self._canvas_cursor_pos(), internal=False)

    def _has_pending_placement(self) -> bool:
        return (
            self._pending_duplicate_source is not None
            or self._pending_paste_paths is not None
        )

    def _cancel_pending_placements(self) -> None:
        had = self._has_pending_placement()
        self._pending_duplicate_source = None
        self._pending_paste_paths = None
        if not had:
            return
        try:
            self.canvas.removeEventFilter(self)
        except Exception:
            pass
        self.canvas.unsetCursor()
        self.store.dispatch(actions.set_drag_state(active=False))

    def _arm_pending_placement_input(self) -> None:
        self.canvas.setCursor(Qt.CursorShape.DragCopyCursor)
        self.canvas.installEventFilter(self)
        self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def _canvas_cursor_pos(self):
        from PySide6.QtGui import QCursor

        return self.canvas.mapFromGlobal(QCursor.pos())

    def _update_pending_drag_preview(self, pos, *, internal: bool) -> None:
        include_center = internal
        if internal:
            tgt_path, side, root_tgt, swap_id = self.canvas.compute_drop_target(
                pos, include_center=include_center
            )
            self.store.dispatch(
                actions.set_drag_state(
                    active=True,
                    internal=True,
                    source_slot_id=self._pending_duplicate_source,
                    target_path=tgt_path,
                    target_side=side,
                    target_root=root_tgt,
                    target_swap_slot_id=swap_id,
                )
            )
            return
        if len(slot_ids_in_tree(self.state.root)) >= self.state.max_slots:
            self.store.dispatch(actions.set_drag_state(active=False))
            return
        tgt_path, side, root_tgt, _ = self.canvas.compute_drop_target(pos)
        self.store.dispatch(
            actions.set_drag_state(
                active=True,
                internal=False,
                target_path=tgt_path,
                target_side=side,
                target_root=root_tgt,
            )
        )

    def eventFilter(self, watched, event) -> bool:
        if not self._has_pending_placement() or watched is not self.canvas:
            return False
        internal = self._pending_duplicate_source is not None
        et = event.type()
        if et == QEvent.Type.MouseMove:
            pos = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            self._update_pending_drag_preview(pos, internal=internal)
            return True
        if et == QEvent.Type.MouseButtonPress:
            button = event.button()
            if button == Qt.MouseButton.LeftButton:
                pos = (
                    event.position().toPoint()
                    if hasattr(event, "position")
                    else event.pos()
                )
                if internal:
                    tgt_path, side, root_tgt, _ = self.canvas.compute_drop_target(
                        pos, include_center=False
                    )
                    self._finalize_pending_duplicate(tgt_path, side, root_tgt)
                else:
                    tgt_path, side, root_tgt, _ = self.canvas.compute_drop_target(pos)
                    self._finalize_pending_paste(tgt_path, side, root_tgt)
                self._cancel_pending_placements()
                return True
            if button == Qt.MouseButton.RightButton:
                self._cancel_pending_placements()
                return True
        if et == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._cancel_pending_placements()
            return True
        return False

    def _finalize_pending_paste(
        self,
        target_path: tuple[int, ...] | None,
        side: str | None,
        target_root: bool,
    ) -> None:
        paths = self._pending_paste_paths
        if not paths:
            return
        # Empty canvas: compute_drop_target returns (None, None, True, None).
        # Real file dropEvent still emits; add_image_at treats target_root.
        if side is None and not target_root:
            return
        self.images_dropped.emit(list(paths), (target_path, target_root), side)

    def _finalize_pending_duplicate(
        self,
        target_path: tuple[int, ...] | None,
        side: str | None,
        target_root: bool,
    ) -> None:
        source_id = self._pending_duplicate_source
        if source_id is None or side is None:
            return
        source = next((s for s in self.state.slots if s.id == source_id), None)
        if source is None or source.image is None:
            return
        if len(self.state.slots) >= self.state.max_slots:
            return
        image = source.image.copy() if hasattr(source.image, "copy") else source.image
        self.store.dispatch(
            actions.add_slot(
                path=source.path or Path(),
                image=image,
                label=source.label,
                target_path=tuple(target_path or ()),
                side=side,
                target_root=target_root,
            )
        )
