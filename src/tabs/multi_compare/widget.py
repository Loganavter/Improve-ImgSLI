"""Main widget for multi-compare tab — composes toolbar + GL grid + footer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
)
from PySide6.QtWidgets import QVBoxLayout, QWidget

from tabs.multi_compare.context_menu import MultiCompareContextMenuProvider
from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene import MultiCompareStore, actions
from tabs.multi_compare.ui import chrome, divider_sync, drag_drop, font_settings_sync
from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget
from tabs.multi_compare.ui.footer import MultiCompareFooter
from tabs.multi_compare.ui.toolbar import MultiCompareToolbar
from tabs.multi_compare.icons import Icon
from tabs.multi_compare.use_cases import placement
from ui.context_menu.manager import install_context_menu_provider
from ui.widgets.font_settings_flyout import FontSettingsFlyout
from ui.widgets.startup_placeholder import StartupPlaceholder
from ui.widgets.glass_hud import ZoomIndicator

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

FOCUS_DIM_COLOR = QColor(0, 0, 0, 235)


class _FocusDimOverlay(QWidget):
    """Translucent-black chrome dimmer shown while a slot is focused.

    Paints directly (no ``setStyleSheet`` -- disallowed outside theme infra,
    see ``tests/contracts/test_no_manual_theming.py``) so it stays a plain
    always-on-top rect regardless of the active theme/palette. Swallows any
    click landing on it and reports it via ``on_click`` (used to exit focus),
    rather than passing through to the toolbar/footer widgets underneath.
    """

    def __init__(self, parent: QWidget, *, on_click) -> None:
        super().__init__(parent)
        self._on_click = on_click

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), FOCUS_DIM_COLOR)
        painter.end()

    def mousePressEvent(self, event) -> None:
        self._on_click()
        event.accept()


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
        context=None,
    ):
        super().__init__(parent)
        # Bound facade over the core Dispatcher + active session slot; the
        # session slot is the single source of truth (state-unification-plan, private
        # improve-imgsli-internal-docs repo).
        core_store = getattr(context, "store", None) if context is not None else None
        self.store = MultiCompareStore(core_store=core_store)
        self._context = context

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
        self.canvas._ffd_primary = True
        canvas_container_layout.addWidget(self.canvas)
        self.footer = MultiCompareFooter(self)

        # Dims everything outside the canvas (toolbar/footer) while a slot is
        # focused (single-click on a leaf, see drag_drop_overlay's
        # end_slot_press) -- the canvas itself already shows just that one
        # image full-size via composition_builder's focused_slot_id handling,
        # so only the surrounding chrome needs the translucent-black cue.
        self._focus_dim_toolbar = _FocusDimOverlay(self, on_click=self._exit_focus)
        self._focus_dim_footer = _FocusDimOverlay(self, on_click=self._exit_focus)
        self._focus_dim_toolbar.hide()
        self._focus_dim_footer.hide()

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

        from tabs.multi_compare.first_frame_debug import mc_first_frame_debug

        mc_first_frame_debug(self.canvas, "startup placeholder raised")

        self.zoom_indicator = ZoomIndicator(
            self._canvas_container,
            lang_provider=lang_provider or (lambda: "en"),
            target_widget=self.canvas,
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
        chrome.sync_zoom_indicator(self)

    def _on_first_frame(self) -> None:
        chrome.on_first_frame(self)

    def _release_transition_mask(self) -> None:
        chrome.release_transition_mask(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        chrome.resize_event(self, event)

    def _exit_focus(self) -> None:
        chrome.exit_focus(self)

    def _sync_focus_dim_overlays(self) -> None:
        chrome.sync_focus_dim_overlays(self)

    def hideEvent(self, event):
        super().hideEvent(event)
        chrome.hide_event(self, event)

    def showEvent(self, event):
        super().showEvent(event)
        chrome.show_event(self, event)
        try:
            canvas = getattr(self, "canvas", None)
            if canvas is not None and hasattr(canvas, "flush_stale_composition"):
                canvas.flush_stale_composition()
        except Exception:
            pass

    @property
    def state(self) -> MultiCompareState:
        return self.store.state

    def refresh_from_session(self) -> None:
        """Re-read the active session's slot and push it to the canvas.

        Called on session switch / restore: with the slot authoritative, no
        ``replace_state`` round-trip is needed — just re-render from the
        bound session's current state.
        """
        self._on_store_change(None, self.store.state)

    def _on_store_change(self, _action, new_state: MultiCompareState) -> None:
        divider_sync.on_store_change(self, _action, new_state)

    def sync_divider_toolbar(self) -> None:
        divider_sync.sync_divider_toolbar(self)

    def _queue_divider_toolbar_resync(self) -> None:
        divider_sync.queue_divider_toolbar_resync(self)

    def _run_queued_divider_toolbar_sync(self) -> None:
        divider_sync.run_queued_divider_toolbar_sync(self)

    def _sync_divider_toolbar(self) -> None:
        divider_sync._sync_divider_toolbar(self)

    def _on_divider_visible_toggled(self, visible: bool) -> None:
        divider_sync.on_divider_visible_toggled(self, visible)

    def _on_divider_width_changed(self, width: int) -> None:
        divider_sync.on_divider_width_changed(self, width)

    def apply_divider_color(self, color: QColor) -> None:
        divider_sync.apply_divider_color(self, color)

    def _sync_font_settings_flyout(self) -> None:
        font_settings_sync.sync_font_settings_flyout(self)

    def _toggle_font_settings_flyout(self) -> None:
        font_settings_sync.toggle_font_settings_flyout(self)

    def show_font_settings_flyout(self) -> None:
        """Open the text flyout without toggle-close (Find Action reveal/run)."""
        font_settings_sync.show_font_settings_flyout(self)

    def _on_font_settings_closed(self) -> None:
        font_settings_sync.on_font_settings_closed(self)

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
        font_settings_sync.on_font_settings_changed(
            self, size, weight, color, bg_color, draw_bg, _placement, opacity
        )

    def add_image_auto(
        self, path: Path, image: "TiledPixelStore", label: str = ""
    ) -> int | None:
        """Append an image by splitting the largest leaf along its longer axis."""
        return placement.add_image_auto(self, path, image, label)

    def add_image_at(
        self,
        path: Path,
        image: "TiledPixelStore",
        label: str,
        target_path: tuple[int, ...] | None,
        side: str | None,
        target_root: bool,
    ) -> int | None:
        return placement.add_image_at(
            self, path, image, label, target_path, side, target_root
        )

    def _pick_auto_target(self) -> tuple[tuple[int, ...], str]:
        """Pick the existing leaf with the largest rect; split along its longer axis."""
        return placement.pick_auto_target(self)

    def remove_slot(self, slot_id: int) -> None:
        placement.remove_slot(self, slot_id)

    def reset_view(self) -> None:
        placement.reset_view(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        drag_drop.drag_enter_event(self, event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        drag_drop.drag_move_event(self, event)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        drag_drop.drag_leave_event(self, event)

    def dropEvent(self, event: QDropEvent) -> None:
        drag_drop.drop_event(self, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and drag_drop.has_pending_placement(self):
            drag_drop.cancel_pending_placements(self)
            event.accept()
            return
        self.canvas.keyPressEvent(event)

    def begin_pending_duplicate(self, source_slot_id: int) -> None:
        drag_drop.begin_pending_duplicate(self, source_slot_id)

    def begin_pending_paste(self, paths: list[Path]) -> None:
        """Enter external DnD placement: highlight under cursor, click to drop."""
        drag_drop.begin_pending_paste(self, paths)

    def eventFilter(self, watched, event) -> bool:
        return drag_drop.event_filter(self, watched, event)

    def _finalize_pending_paste(
        self,
        target_path: tuple[int, ...] | None,
        side: str | None,
        target_root: bool,
    ) -> None:
        drag_drop.finalize_pending_paste(self, target_path, side, target_root)

    def _finalize_pending_duplicate(
        self,
        target_path: tuple[int, ...] | None,
        side: str | None,
        target_root: bool,
    ) -> None:
        drag_drop.finalize_pending_duplicate(self, target_path, side, target_root)