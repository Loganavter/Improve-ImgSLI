"""Stage 1 Image Gallery widget — browse & dispatch surface (toolkit-compliant).
Audit-Meta: pattern=thin-owner size=exempt reason="thin owner delegating to use_cases/triage+carry+quick look; splitting would create helpers bag"

Thin owner: toolbar + grid view + empty state. No QSS — painter pipeline owns visuals.
Signals mirror the contract expected by ``GalleryController``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

import logging

from sli_ui_toolkit.widgets import Label

from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log
from tabs.image_gallery.models import GalleryItem, ThumbnailStatus

logger = logging.getLogger("ImproveImgSLI")

# Lazy import grid/toolbar/states to avoid circular import at module load.
# They are imported inside __init__ where needed.


class ImageGalleryWidget(QWidget):
    """Folder-browse grid owned by ``ImageGalleryTab``.

    Signals:
        folder_pick_requested — toolbar button pressed.
        analyze_requested — card Analyze triggered (forwarded to controller).
        filter_text_changed — live filter field changed.
    """

    folder_pick_requested = Signal()
    analyze_requested = Signal(object)
    filter_text_changed = Signal(str)

    def close(self, *args, **kwargs):  # type: ignore[override]
        # Make qtbot teardown idempotent: parent close already deletes child page.
        try:
            import shiboken6

            if not shiboken6.isValid(self):
                return True
        except Exception:
            pass
        try:
            return super().close(*args, **kwargs)
        except RuntimeError:
            return True

    def deleteLater(self, *args, **kwargs):  # type: ignore[override]
        try:
            import shiboken6

            if not shiboken6.isValid(self):
                return
        except Exception:
            pass
        try:
            return super().deleteLater(*args, **kwargs)
        except RuntimeError:
            return

    def __init__(self, parent: QWidget | None = None, context=None):
        # Local imports to avoid circular import via ui/__init__.py
        from tabs.image_gallery.ui.grid_view import GalleryGridView
        from tabs.image_gallery.ui.states import GalleryEmptyState
        from tabs.image_gallery.ui.stats_strip import StatsStrip
        from tabs.image_gallery.ui.toolbar import GalleryToolbar

        super().__init__(parent)
        self._context = context
        self._items: list[GalleryItem] = []

        def _tr(key: str, default: str) -> str:
            if context is None:
                return default
            try:
                return context._tr(key, default)
            except Exception:
                return default

        from sli_ui_toolkit.managers import scaled_px

        root = QVBoxLayout(self)
        # real_design.md:0 — horizontal padding 24 fixed, bottom 40 to clear selection HUD (§2.7)
        root.setContentsMargins(24, 12, 24, 40)
        root.setSpacing(scaled_px(12))

        # Toolbar: Button variant="surface" + CustomLineEdit (painter pipeline) — matches svg toolbar 34px
        self.toolbar = GalleryToolbar(self, translate=(context._tr if context is not None else None))
        self.toolbar.setObjectName("image_gallery_toolbar")
        from PySide6.QtWidgets import QSizePolicy as _QSP
        try:
            self.toolbar.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Fixed)
        except Exception:
            pass
        # Keep legacy aliases for controller/tests that may look up _pick_button/_filter_edit
        self._pick_button = self.toolbar.pick_button
        self._pick_button.setObjectName("image_gallery_pick_button")
        self._filter_edit = self.toolbar.filter_edit
        self._filter_edit.setObjectName("image_gallery_filter_edit")
        # Wire toolbar signals outward
        self.toolbar.openClicked.connect(self.folder_pick_requested.emit)
        self.toolbar.filterChanged.connect(self.filter_text_changed.emit)
        # Wave 2c: every filter keystroke is a dispatched GalleryFilterSet
        # (view action, not undoable). The controller debounce connection
        # stays for thumbnail/filter-worker side-effects.
        try:
            self.filter_text_changed.connect(self._on_filter_text_dispatch)
        except Exception:
            pass
        # A1: wiring sort/view signals
        try:
            self.toolbar.sortChanged.connect(self._on_sort_changed)
        except Exception:
            pass
        try:
            self.toolbar.viewToggled.connect(self._on_view_toggled)
        except Exception:
            pass
        root.addWidget(self.toolbar)

        # Stats strip (Stage 2 S2) — Label "40 images · 7 series · 33 redundant" + Buttons + mode chip — svg y114 h34
        self.stats_strip = StatsStrip(self, translate=(context._tr if context is not None else None))
        self.stats_strip.setObjectName("image_gallery_stats_strip")
        try:
            self.stats_strip.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Fixed)
        except Exception:
            pass
        root.addWidget(self.stats_strip)
        # Initially hidden until triage arrives.
        try:
            self.stats_strip.hide()
        except Exception:
            pass
        # Wire strip signals -> use_cases (keep_best_of_series etc).
        try:
            self.stats_strip.keepBestClicked.connect(lambda: self._on_keep_best())
            self.stats_strip.showAllClicked.connect(lambda: self._on_show_all())
            self.stats_strip.cleanClicked.connect(lambda: self._on_clean_rejected())
            self.stats_strip.compareClicked.connect(lambda: self._on_compare_finalists())
        except Exception:
            pass

        # Folder label — svg has no separate folder path label (stats strip replaces it); keep hidden for compat, Fixed
        self._folder_label = Label(_tr("image_gallery.empty_state", "Pick a folder to see images here."), pixel_size=12, parent=self)
        self._folder_label.setObjectName("image_gallery_folder_label")
        self._folder_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._folder_label.setWordWrap(True)
        try:
            self._folder_label.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Fixed)
            self._folder_label.hide()
        except Exception:
            pass
        self._empty_text = _tr("image_gallery.empty_state", "Pick a folder to see images here.")
        # Shown when the grid is emptied by removals (reject/Space/Delete) —
        # files stay on disk, so "pick a folder" would mislead.
        self._empty_view_text = _tr("image_gallery.empty_view", "No images in view.")
        # Not added to layout to match svg (no extra label row) — kept as hidden compat shim
        # root.addWidget(self._folder_label)  # svg v2 has no folder label, only stats

        # Empty state (S0: DropZoneLabel + DragDropOverlay) — should fill when grid hidden
        self._empty_state = GalleryEmptyState(self, translate=(context._tr if context is not None else None))
        self._empty_state.setObjectName("image_gallery_empty_state")
        try:
            self._empty_state.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Expanding)
        except Exception:
            pass
        self._empty_state.openRequested.connect(self.folder_pick_requested.emit)
        try:
            self._empty_state.fileDropped.connect(lambda p: self._on_empty_file_dropped(p))
        except Exception:
            pass

        # Grid view: OverlayScrollArea + OpaqueFillHost + Button pool (toolkit)
        self._grid_view = GalleryGridView(self)
        self._grid_view.setObjectName("image_gallery_grid_view")
        # Legacy aliases for controller compatibility
        self._scroll = self._grid_view.scroll_area
        self._scroll.setObjectName("image_gallery_scroll")
        self._grid_host = self._grid_view.items_host
        self._grid_host.setObjectName("image_gallery_grid_host")
        self._grid = self._grid_view.items_layout
        # Wire grid toggle -> analyze_requested (card click) and context menu
        self._grid_view.configure(on_toggle=self._on_card_toggle, on_context_menu=self._on_card_context)
        # Content stack — avoids QVBoxLayout stretch bug where hidden 1054h EmptyState pushes toolbar
        from PySide6.QtWidgets import QStackedWidget

        self._content_stack = QStackedWidget(self)
        self._content_stack.setObjectName("image_gallery_content_stack")
        try:
            self._content_stack.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Expanding)
        except Exception:
            pass
        self._content_stack.addWidget(self._empty_state)
        self._content_stack.addWidget(self._grid_view)
        root.addWidget(self._content_stack, 1)
        # Default: empty
        try:
            self._content_stack.setCurrentWidget(self._empty_state)
        except Exception:
            pass

        # Internal card tracking mirrors grid_view for refresh_card compatibility
        self._cards: dict[Path, object] = {}
        self._card_labels: dict[Path, object] = {}
        # Keep empty label alias for tests that may access _empty_label (toolkit Label, not QLabel)
        self._empty_label = Label(self._empty_text, pixel_size=12, parent=self)
        self._empty_label.setObjectName("image_gallery_empty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        # DnD helpers — reused by widget and Tab.handle_drop
        from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _ACCEPTED_EXTS
        self._ACCEPTED_EXTS = _ACCEPTED_EXTS  # type: ignore[attr-defined]

        # Not added to layout — empty_state owns S0 visuals; this label is compat shim
        # Triage state (Stage 2): series/mode/source populated via set_triage (worker).
        self._series: list = []
        self._mode = None
        self._source_path: Path | None = None
        self._collapsed: dict[int, bool] = {}

        # Keyboard: widget handles Space/B/Enter/Esc/arrows → triage (design.md:129).
        try:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self._grid_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        except Exception:
            pass
        # Clean review overlay (S3) — created lazily.
        self._clean_overlay = None  # type: ignore[assignment]
        # Quick look overlay (S4) — created lazily.
        self._quick_look_overlay = None  # type: ignore[assignment]
        # Selection HUD collaborator — BaseFlyout pinned bottom-center group gallery_selection (A3)
        self._selection_hud = None  # type: ignore[assignment]
        try:
            from tabs.image_gallery.ui.selection_hud import SelectionHudController

            def _hud_clear():
                try:
                    from tabs.image_gallery.use_cases import selection as _sel

                    _sel.clear_selection(self._owner_for_triage())
                except Exception:
                    pass

            def _hud_carry():
                try:
                    from tabs.image_gallery.use_cases import carry as _carry

                    _carry.carry_selected(self._owner_for_triage())
                except Exception:
                    pass

            def _hud_analyze():
                try:
                    owner = self._owner_for_triage()
                    # Analyze first selected
                    sel = getattr(getattr(owner, "state", None), "selected_paths", None) or set()
                    if sel:
                        p = next(iter(sel))
                        owner.analyze_item_by_path(p)  # type: ignore[attr-defined]
                except Exception:
                    pass

            def _hud_find():
                try:
                    from tabs.image_gallery.use_cases.carry import find_similar_selected

                    find_similar_selected(self._owner_for_triage())
                except Exception:
                    pass

            tr_fn = (context._tr if context is not None else None)
            self._selection_hud = SelectionHudController(
                self,
                translate=tr_fn,
                on_clear=_hud_clear,
                on_carry=_hud_carry,
                on_analyze=_hud_analyze,
                on_find_similar=_hud_find,
            )
        except Exception:
            self._selection_hud = None

        # Enable drops on the whole widget (not just DropZoneLabel) — fixes DnD not working
        try:
            self.setAcceptDrops(True)
            self._grid_view.setAcceptDrops(True)
            self._empty_state.setAcceptDrops(True)
        except Exception:
            pass
        # W12-D: forward zone-surface drops (full mime) to the unified router —
        # the zone label alone would re-emit only the first path.
        try:
            from tabs.image_gallery.ui import drag_drop as _drag_drop

            _drag_drop.install_zone_drop_forwarding(self)
        except Exception:
            pass

        # Update initial state
        self._empty_state.set_state("empty")
        self._grid_view.hide()

        # Raw input firehose (DEBUGGING.md rule 5): app-wide, env-gated,
        # session-only. Installed, never consumed.
        try:
            from tabs.image_gallery.ui.events_firehose import install_events_firehose

            install_events_firehose()
        except Exception:
            pass

        # Wave 2c: subscribe renders to the ``gallery`` slot (fail-open —
        # no store in tests / unbootstrapped tabs means no subscription).
        self._gallery_store_connected = False
        try:
            self._init_gallery_store_subscription()
        except Exception:
            pass

        # TEMP-DIAG (remove after load-cycle diagnosed): per-turn visibility
        # sampler. Logs the actually-painted signature whenever it changes —
        # catches flat-grid paints from ANY path, including ones with no
        # view-cycle line. Gated by IMGSLI_GALLERY_DEBUG=1, zero impact off.
        try:
            from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_on

            if _dbg_on():
                from PySide6.QtCore import QTimer as _QTimer

                self._view_frame_sig: str | None = None
                self._view_frame_timer = _QTimer(self)
                self._view_frame_timer.setInterval(50)
                self._view_frame_timer.timeout.connect(self._sample_view_frame)
                self._view_frame_timer.start()
        except Exception:
            pass

    # -- Redux: gesture dispatch + subscribed renders (Wave 2c) -------------

    def _on_filter_text_dispatch(self, text: str) -> None:
        """Dispatch ``GalleryFilterSet`` for a filter gesture (fail-open)."""
        try:
            from core.state_management.gallery_actions import GalleryFilterSet
            from tabs.image_gallery.ui.gallery_store import dispatch_gallery

            dispatch_gallery(self, GalleryFilterSet(filter_text=text or ""))
        except Exception:
            pass

    def _init_gallery_store_subscription(self) -> None:
        """Render grid/selection/filter from the ``gallery`` slot on emit."""
        try:
            from tabs.image_gallery.ui.gallery_store import resolve_store

            store = resolve_store(self)
        except Exception:
            return
        if store is None:
            return
        try:
            qt_signal = getattr(store, "state_changed", None)
            if qt_signal is not None and hasattr(qt_signal, "connect"):
                qt_signal.connect(self._on_gallery_store_changed)
                self._gallery_store_connected = True
                return
        except Exception:
            pass
        try:
            if hasattr(store, "on_change"):
                store.on_change(self._on_gallery_store_changed)
                self._gallery_store_connected = True
        except Exception:
            pass

    def _on_gallery_store_changed(self, scope: str) -> None:
        try:
            if scope != "gallery":
                return
        except Exception:
            return
        try:
            self._render_from_gallery_slot()
        except Exception:
            pass

    def _render_from_gallery_slot(self) -> None:
        """Re-render selection/filter/folder/pool from slot reads (no dispatch)."""
        try:
            from tabs.image_gallery.ui.gallery_store import read_gallery_slot

            slot = read_gallery_slot(self)
        except Exception:
            return
        if slot is None:
            # No Redux state (foreign session, pre-first-dispatch) — never clear.
            return
        try:
            from tabs.image_gallery.state import selectors as _sel2

            self._render_gallery_selection(_sel2.get_selection(slot))
            self._render_gallery_filter(_sel2.get_filter_text(slot))
            self._render_gallery_folder(_sel2.get_folder(slot))
            self._render_gallery_pool(slot)
        except Exception:
            pass

    def _render_gallery_selection(self, selected_ids: list) -> None:
        """Apply slot selection to grid + HUD (visuals only, no dispatch)."""
        try:
            wanted = set(str(s) for s in (selected_ids or []))
        except Exception:
            return
        try:
            current = set()
            for p in (self._grid_view._selection or set()):
                current.add(str(p))
        except Exception:
            current = set()
        if wanted == current:
            pass
        try:
            self._grid_view.apply_selection(set(wanted))
        except Exception:
            pass
        try:
            hud = getattr(self, "_selection_hud", None)
            if hud is not None:
                n = len(wanted)
                try:
                    if hasattr(hud, "update"):
                        hud.update(n)
                    elif hasattr(hud, "set_count"):
                        hud.set_count(n)
                except Exception:
                    pass
                try:
                    if n > 0 and hasattr(hud, "show"):
                        hud.show()
                    elif n == 0 and hasattr(hud, "hide"):
                        hud.hide()
                except Exception:
                    pass
        except Exception:
            pass

    def _render_gallery_filter(self, filter_text: str) -> None:
        """Sync the filter edit from the slot (signal-blocked, no loop)."""
        try:
            want = str(filter_text or "")
        except Exception:
            return
        try:
            edit = getattr(self.toolbar, "_filter_edit", None) or getattr(self, "_filter_edit", None)
            if edit is None:
                return
            try:
                cur = str(edit.text())
            except Exception:
                return
            if cur == want:
                return
            try:
                edit.blockSignals(True)
                edit.setText(want)
            finally:
                try:
                    edit.blockSignals(False)
                except Exception:
                    pass
        except Exception:
            pass

    def _render_gallery_folder(self, folder: str | None) -> None:
        """Sync the compat folder label from the slot (folder set only)."""
        if not folder:
            return
        try:
            label = getattr(self, "_folder_label", None)
            if label is None:
                return
            try:
                cur = str(label.text())
            except Exception:
                cur = ""
            if cur != str(folder):
                label.setText(str(folder))
        except Exception:
            pass

    def _render_gallery_pool(self, slot) -> None:
        """Reconcile flat-grid membership with the slot pool (no dispatch).

        Skipped while a triage series view is active — grouping is owned by
        the controller triage reaction (W2b). New paths materialize as bare
        ``GalleryItem``\\ s WITHOUT pixmaps: thumbnail fetch for
        slot-materialized items is a missing controller reaction (see
        DONE.md) — during transition the legacy ``ctrl.open_*`` call that
        follows each gesture loads thumbnails right after this reconcile.
        """
        try:
            if getattr(self, "_series", None):
                return
            from tabs.image_gallery.state import selectors as _selectors

            slot_paths = [str(p) for p in _selectors.get_item_paths(slot)]
        except Exception:
            return
        try:
            cur_paths = [str(it.path) for it in (self._items or [])]
        except Exception:
            return
        if slot_paths == cur_paths:
            return
        _dbg("_render_gallery_pool reconcile slot=%d local=%d", len(slot_paths), len(cur_paths))
        try:
            from tabs.image_gallery.state import selectors as _sel3

            metas = {m.path: m for m in _sel3.get_items(slot)}
        except Exception:
            metas = {}
        try:
            by_path = {}
            for it in (self._items or []):
                try:
                    by_path[str(it.path)] = it
                except Exception:
                    continue
            merged: list = []
            for sp in slot_paths:
                it = by_path.get(sp)
                if it is None:
                    try:
                        meta = metas.get(sp)
                        mtime = int(getattr(meta, "mtime_ns", 0) or 0)
                    except Exception:
                        mtime = 0
                    try:
                        it = GalleryItem(path=Path(sp), mtime_ns=mtime)
                    except Exception:
                        continue
                merged.append(it)
            self.rebuild_grid(merged)
        except Exception:
            pass

    # -- wiring for toolbar sort/view (A1) ---------------------------------

    def _on_sort_changed(self, text: str) -> None:
        # S2: toolbar sort combo "Sort: Rank/Name/Date" — reorder grid.
        # Wave 2c note: the frozen seam has no GALLERY_* sort action, so
        # sort stays view-local (grid order only, no slot write) by design.
        # Thin owner: delegate to filtering/sorting helper if available, else sort items in place.
        try:
            key = str(text or "").lower()
            keyfunc = self._sort_keyfunc(key)
            if keyfunc is None:
                return
            items = list(self._items or [])
            # Rebuild grid preserving series grouping if active
            if self._series:
                # Sort applies to grouped series: members within each
                # cluster AND cluster order (by first member), then ONE
                # rebuild via set_triage (stats/hubs recomputed there).
                # The old flat rebuild_grid first was a wasted pass whose
                # order set_triage discarded anyway.
                sorted_series = []
                for cl in self._series:
                    try:
                        sorted_series.append(sorted(cl, key=keyfunc))
                    except Exception:
                        sorted_series.append(list(cl))
                try:
                    sorted_series.sort(key=lambda cl: keyfunc(cl[0]))
                except Exception:
                    pass
                try:
                    member_paths = {
                        str(it.path) for cl in sorted_series for it in cl
                    }
                except Exception:
                    member_paths = set()
                try:
                    ungrouped = sorted(
                        (
                            it for it in (self._items or [])
                            if str(it.path) not in member_paths
                        ),
                        key=keyfunc,
                    )
                except Exception:
                    ungrouped = [
                        it for it in (self._items or [])
                        if str(it.path) not in member_paths
                    ]
                self._items = [it for cl in sorted_series for it in cl] + ungrouped
                try:
                    self.set_triage(sorted_series, self._mode, self._source_path)
                except Exception:
                    pass
            else:
                try:
                    items.sort(key=keyfunc)
                except Exception:
                    pass
                self.rebuild_grid(items)
        except Exception:
            pass

    @staticmethod
    def _sort_keyfunc(key: str):
        """Sort key for a toolbar sort label, or None for unknown labels."""
        if "name" in key:
            return lambda it: (
                getattr(getattr(it, "path", None), "name", "") or ""
            ).lower()
        if "date" in key:
            # Newest first: use mtime_ns descending
            return lambda it: -int(getattr(it, "mtime_ns", 0) or 0)
        if "rank" in key:
            # Rank 1 first, then embedding distance
            def _rank_key(it):
                r = getattr(it, "rank", None) or getattr(it, "crown_rank", None)
                try:
                    rk = int(r) if r is not None else 999
                except Exception:
                    rk = 999
                metrics = getattr(it, "metrics", None)
                d = metrics.get("embedding_dist_to_centroid") if isinstance(metrics, dict) else None
                try:
                    df = float(d) if d is not None else 1e9
                except Exception:
                    df = 1e9
                return (rk, df)

            return _rank_key
        return None

    def _on_view_toggled(self, checked: bool) -> None:
        # View switch toggle (grid/list) — view-local only (no GALLERY_*
        # action in the frozen seam); keep state for future parity.
        try:
            self._view_mode = bool(checked)
        except Exception:
            pass
        # No layout change for Stage 2 — placeholder for parity with mockup toggle.
        try:
            _dbg("view toggled %s", bool(checked))
        except Exception:
            pass

    # -- card interaction -------------------------------------------------

    def _on_card_toggle(self, path: Path, additive: bool = False) -> None:
        # Click opens, Ctrl+click selects (manual selection stays orthogonal
        # to triage — Ctrl-click/marquee → HUD; plain click → quick look).
        if not additive:
            try:
                self.show_quick_look(path)
                return
            except Exception:
                pass
        try:
            from tabs.image_gallery.use_cases import selection as _sel

            owner = self._owner_for_triage()
            _sel.toggle_card(owner, path, additive=additive)
        except Exception:
            try:
                self.analyze_requested.emit(path)
            except Exception:
                pass

    def _on_card_context(self, path: Path) -> None:
        # S2a: ContextMenu mirrors hover mini-capsule (★ make best · ✕ reject · ⇄ compare).
        # Use public sli_ui_toolkit.widgets ContextMenu via card helper.
        from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

        import time as _time

        _dbg_on = _dbg_enabled()
        _t0 = _time.perf_counter() if _dbg_on else 0.0
        if _dbg_on:
            _dbg("ctx menu entry path=%s", path)
        try:
            # Resolve owner: try controller via parent tab, else self.
            owner = None
            for attr in ("_controller", "_owner", "_gallery_controller"):
                owner = getattr(self, attr, None)
                if owner is not None:
                    break
            if owner is None:
                # Widget itself can act as owner for triage (has state).
                # If hosted by GalleryController, find via window.
                try:
                    win = self.window()
                    owner = getattr(win, "_gallery_controller", None) or self
                except Exception:
                    owner = self
            if _dbg_on:
                _t_owner = _time.perf_counter()
            card = self._grid_view.card_for(path) if hasattr(self, "_grid_view") else None
            anchor = card if card is not None else self
            if _dbg_on:
                _dbg(
                    "ctx menu phase resolve=%.1fms card_for=%.1fms anchor=%s owner=%s",
                    (_t_owner - _t0) * 1000.0,
                    (_time.perf_counter() - _t_owner) * 1000.0,
                    type(anchor).__name__,
                    type(owner).__name__ if owner is not None else "None",
                )
            # Try hover helper popup.
            from tabs.image_gallery.ui.card import popup_gallery_card_context_menu

            try:
                from PySide6.QtGui import QCursor

                gp = QCursor.pos()
            except Exception:
                gp = None
            popup_gallery_card_context_menu(anchor, owner, Path(path), global_pos=gp)
            if _dbg_on:
                _dbg("ctx menu done total=%.1fms path=%s", (_time.perf_counter() - _t0) * 1000.0, path)
        except Exception:
            if _dbg_on:
                _dbg("ctx menu raised path=%s", path, exc_info=True)
            pass

    def _on_empty_file_dropped(self, path_str: str) -> None:
        from tabs.image_gallery.ui import drag_drop as _drag_drop

        _drag_drop.on_empty_file_dropped(self, path_str)

    # -- S4 quick look ----------------------------------------------------------

    def show_quick_look(self, item_or_path) -> None:  # type: ignore[no-untyped-def]
        from tabs.image_gallery.ui import quick_look_hooks

        return quick_look_hooks.show_quick_look(self, item_or_path)

    def refresh_quick_look(self, item) -> None:  # type: ignore[no-untyped-def]
        from tabs.image_gallery.ui import quick_look_hooks

        return quick_look_hooks.refresh_quick_look(self, item)

    def refresh_artifacts_for(self, item) -> None:  # alias
        from tabs.image_gallery.ui import quick_look_hooks

        return quick_look_hooks.refresh_artifacts_for(self, item)

    def _install_quick_look_hooks(self) -> None:
        from tabs.image_gallery.ui import quick_look_hooks

        return quick_look_hooks.install_hooks(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        from tabs.image_gallery.ui import quick_look_hooks

        return quick_look_hooks.event_filter(self, watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        try:
            hud = getattr(self, "_selection_hud", None)
            if hud is not None:
                hud.reposition()
        except Exception:
            pass

    # -- keyboard: Space/Delete remove card, B make best, Enter compare, Esc close/back, arrows navigate
    # widget keyPressEvent -> triage functions (design.md:129) ----------------

    def _owner_for_triage(self):
        from tabs.image_gallery.use_cases import triage_ui

        return triage_ui.owner_for_triage(self)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        from tabs.image_gallery.use_cases import triage_ui

        return triage_ui.handle_key(self, event)

    # -- S3 clean review helpers -----------------------------------------------

    def show_clean_review(self, owner=None) -> None:
        """Open S3 clean review overlay (TopLevelInWindowOverlay + Toast Undo)."""
        try:
            from tabs.image_gallery.ui.clean_review import CleanReviewOverlay

            actual_owner = owner if owner is not None else self._owner_for_triage()
            # Ensure overlay exists.
            overlay = getattr(self, "_clean_overlay", None)
            if overlay is None:
                parent = self.window() or self
                overlay = CleanReviewOverlay(parent, actual_owner)
                self._clean_overlay = overlay
            else:
                try:
                    overlay._owner = actual_owner  # type: ignore[attr-defined]
                except Exception:
                    pass
            overlay.show_for(actual_owner)
        except Exception:
            pass

    # -- A1 scanning/triage done (toolbar + empty state) ---------------------

    def set_scanning(self, n: int, total: int) -> None:
        """S1: progressive scanning n/N — toolbar spinner + empty_state."""
        try:
            n_i = int(n)
            t_i = int(total)
        except Exception:
            n_i = int(n) if isinstance(n, int) else 0
            t_i = int(total) if isinstance(total, int) else 0
        _dbg("view-cycle scanning cover n=%d total=%d", n_i, t_i)
        try:
            self.toolbar.set_scanning(n_i, t_i)
        except Exception:
            pass
        try:
            self._empty_state.set_state("scanning", n_i, t_i)
        except TypeError:
            try:
                self._empty_state.set_state("scanning", n_i)
            except Exception:
                pass
        except Exception:
            pass
        try:
            # Stack switch — empty stays visible during scanning
            if hasattr(self, "_content_stack"):
                self._content_stack.setCurrentWidget(self._empty_state)
                self._empty_state.show()
                self._grid_view.show()  # keep in stack but not current
            else:
                self._empty_state.show()
                self._grid_view.hide()
        except Exception:
            pass

    def set_background_scanning(self, n: int, total: int) -> None:
        """S1 progress without hiding the grid (append path).

        Same toolbar spinner as :meth:`set_scanning`, but the current
        series view stays visible — appending one image must not tear
        down good groups behind a spinner while the pool retriages.
        """
        try:
            n_i = int(n)
            t_i = int(total)
        except Exception:
            n_i = int(n) if isinstance(n, int) else 0
            t_i = int(total) if isinstance(total, int) else 0
        _dbg("view-cycle scanning background n=%d total=%d", n_i, t_i)
        try:
            self.toolbar.set_scanning(n_i, t_i)
        except Exception:
            pass

    def set_triage_done(self) -> None:
        """S2: triage complete — hide spinner."""
        try:
            self.toolbar.set_triage_done()
        except Exception:
            pass
        try:
            self._empty_state.set_state("ready")
        except Exception:
            pass

    # -- API expected by GalleryController ---------------------------------

    def set_folder_label(self, folder: Path) -> None:
        self._folder_label.setText(str(folder))

    def rebuild_grid(self, items: list[GalleryItem]) -> None:
        had_items = bool(self._items)
        # Snapshot the active series view — the flat rebuild below clears
        # grid_view._series (headers). Every triage action funnels through
        # here (toggle/make-best/keep-best/remove), so without a re-apply
        # any of them flattens the SERIES grouping.
        saved_series = None
        pre_paths: set[str] = set()
        try:
            gv = getattr(self, "_grid_view", None)
            if gv is not None and getattr(gv, "_series", None) is not None:
                saved_series = (
                    list(gv._series),
                    list(getattr(gv, "_hub_names", []) or []),
                    dict(getattr(gv, "_collapsed", {}) or {}),
                )
        except Exception:
            saved_series = None
        try:
            for it in (self._items or []):
                pre_paths.add(str(getattr(it, "path", None)))
        except Exception:
            pass
        # Append fast-path: pure pool growth with a live series view keeps
        # every painted card/header in place (no flat teardown + restore —
        # that demolished headers twice per drop). New cards land in the
        # UNGROUPED tail via grid_view.append_new_cards; the imminent
        # background triage regroups once if clustering actually moved them.
        # Strict order check: old pool must appear first and unchanged
        # (reorders still take the full path).
        try:
            gv_fast = getattr(self, "_grid_view", None)
            if saved_series is not None and pre_paths and (items or []):
                try:
                    new_paths = [str(getattr(it, "path", None)) for it in list(items)]
                    old_paths = [str(getattr(it, "path", None)) for it in list(self._items or [])]
                except Exception:
                    new_paths, old_paths = [], []
                if (
                    len(new_paths) > len(old_paths)
                    and gv_fast is not None
                    and getattr(gv_fast, "_rebuild_pending", None) is None
                    and [p for p in new_paths if p in set(old_paths)] == list(old_paths)
                ):
                    try:
                        old_set = set(old_paths)
                        fresh = [it for it in list(items) if str(getattr(it, "path", None)) not in old_set]
                    except Exception:
                        fresh = []
                    if fresh:
                        self._items = list(items)
                        _dbg(
                            "view-cycle rebuild n=%d append-fast-path new=%d",
                            len(self._items),
                            len(fresh),
                        )
                        try:
                            gv_fast.append_new_cards(fresh)
                        except Exception:
                            gv_fast = None
                        if gv_fast is not None:
                            try:
                                for it in fresh:
                                    card = gv_fast.card_for(it.path)
                                    if card is not None:
                                        self._cards[it.path] = card
                                        self._card_labels[it.path] = card  # type: ignore[assignment]
                            except Exception:
                                pass
                            # Fresh cards are content-current from acquire;
                            # tooltips only (no sweep: selection untouched).
                            try:
                                for item in fresh:
                                    self._refresh_tooltip(item)
                            except Exception:
                                pass
                            try:
                                self._install_quick_look_hooks()
                            except Exception:
                                pass
                            return
        except Exception:
            pass
        self._items = list(items)
        _dbg("rebuild_grid n=%d branch=%s", len(self._items), "empty" if not items else "grid")
        _dbg(
            "view-cycle rebuild n=%d saved_series=%s pre=%d",
            len(self._items),
            "yes" if saved_series is not None else "no",
            len(pre_paths),
        )
        if not items:
            if had_items:
                # Emptied by removals (reject/Space/Delete) — files stay on
                # disk, so the pick-a-folder message would mislead.
                try:
                    self._empty_state.set_empty_message(self._empty_view_text)
                except Exception:
                    pass
                empty_text = self._empty_view_text
            else:
                try:
                    self._empty_state.restore_empty_message()
                except Exception:
                    pass
                empty_text = self._empty_text
            self._empty_state.set_state("empty")
            try:
                if hasattr(self, "_content_stack"):
                    self._content_stack.setCurrentWidget(self._empty_state)
                else:
                    self._empty_state.show()
                    self._grid_view.hide()
            except Exception:
                pass
            # Compat shim only (never in a layout — show() would pin it at
            # (0,0) over the corner). S0 visuals belong to _empty_state.
            self._empty_label.setText(empty_text)
            self._empty_label.hide()
            # Clear grid
            try:
                self._grid_view.rebuild_grid([])
            except Exception:
                pass
            return
        self._empty_state.set_state("ready")
        self._empty_label.hide()
        try:
            if hasattr(self, "_content_stack"):
                self._content_stack.setCurrentWidget(self._grid_view)
            else:
                self._empty_state.hide()
                self._grid_view.show()
        except Exception:
            pass
        try:
            try:
                self._grid_view.rebuild_grid(items, paint_selection=saved_series is None)
            except TypeError:
                # Legacy doubles predate the paint_selection kwarg.
                self._grid_view.rebuild_grid(items)
        except Exception:
            pass
        # Keep compat dicts in sync with grid_view's pool
        self._cards.clear()
        self._card_labels.clear()
        for it in items:
            card = self._grid_view.card_for(it.path)
            if card is not None:
                self._cards[it.path] = card
                # card is Button, not QLabel — store dummy for refresh compatibility
                self._card_labels[it.path] = card  # type: ignore[assignment]

        # Re-apply the series view snapshotted above (if clusters survive).
        # The restore paints via set_series when it acts (returns True) —
        # only a non-restored flat grid needs the post-build paint below.
        restored = False
        if saved_series is not None:
            try:
                restored = bool(self._restore_series_view(saved_series, pre_paths=pre_paths))
            except Exception:
                restored = False
        if not restored:
            self._refresh_rebuilt_cards(items, sweep=True)
            # Hook double-click → quick look (restored views hook inside).
            try:
                self._install_quick_look_hooks()
            except Exception:
                pass

    def _restore_series_view(self, saved, pre_paths=None) -> bool:
        """Re-apply a series view snapshot taken before the flat rebuild.

        Clusters are pruned to current membership (removals); clusters
        shrinking below 2 members fall out — ``set_series`` lands their
        survivors in the UNGROUPED tail. When every cluster dissolved but
        items remain from the same pool (pure removal, e.g. deleted a
        whole group), survivors get an explicit UNGROUPED view instead of
        hanging header-less. A wholly new pool (folder switch — every
        alive path is new) stays flat, no stale headers.

        Returns True when the view was (re)painted via set_series.
        """
        try:
            series, hub_names, collapsed = saved
        except Exception:
            return
        alive: set[str] = set()
        for it in (self._items or []):
            try:
                alive.add(str(it.path))
            except Exception:
                continue
        kept: list = []
        kept_hubs: list = []
        for idx, cl in enumerate(list(series or [])):
            try:
                members = [m for m in list(cl) if str(getattr(m, "path", None)) in alive]
            except Exception:
                continue
            if len(members) >= 2:
                kept.append(members)
                try:
                    if idx < len(hub_names):
                        kept_hubs.append(hub_names[idx])
                except Exception:
                    pass
        if not kept:
            # Every cluster dissolved. Same-pool removals (no brand-new
            # paths) → explicit UNGROUPED so survivors don't hang without
            # a series; replacement pool (folder switch) → stay flat.
            try:
                alive_paths = {str(getattr(it, "path", None)) for it in (self._items or [])}
            except Exception:
                alive_paths = set(alive)
            if not alive_paths:
                _dbg("view-cycle restore dissolved pool=empty → empty-state")
                return False
            try:
                pre = set(pre_paths or set())
            except Exception:
                pre = set()
            try:
                added = set(alive_paths) - set(pre)
            except Exception:
                added = set()
            if added:
                _dbg("view-cycle restore dissolved added=%d → flat (replacement pool)", len(added))
                return False
            _dbg("view-cycle restore dissolved same-pool → UNGROUPED n=%d", len(alive_paths))
            try:
                self._grid_view.set_series([], hub_names=[], collapsed={})
            except Exception:
                return False
            try:
                self._series = []
            except Exception:
                pass
            try:
                self._stats_sync_after_dissolve()
            except Exception:
                pass
            try:
                self._cards.clear()
                self._card_labels.clear()
                for it in (self._items or []):
                    card = self._grid_view.card_for(it.path)
                    if card is not None:
                        self._cards[it.path] = card
                        self._card_labels[it.path] = card  # type: ignore[assignment]
            except Exception:
                pass
            try:
                for item in (self._items or []):
                    self._refresh_tooltip(item)
            except Exception:
                pass
            try:
                self._install_quick_look_hooks()
            except Exception:
                pass
            return True
        try:
            self._series = [list(cl) for cl in kept]
        except Exception:
            pass
        try:
            collapsed = {int(k): bool(v) for k, v in dict(collapsed or {}).items() if 0 <= int(k) < len(kept)}
        except Exception:
            collapsed = {}
        _dbg("rebuild_grid restore series clusters=%d", len(kept))
        _dbg("view-cycle restore kept=%d alive=%d → set_series", len(kept), len(alive))
        try:
            self._grid_view.set_series(kept, hub_names=kept_hubs, collapsed=collapsed)
        except Exception:
            return False
        try:
            self._collapsed = dict(getattr(self._grid_view, "_collapsed", {}) or collapsed)
        except Exception:
            pass
        # set_series recycled cards again — re-sync compat dicts (mirrors set_triage).
        try:
            self._cards.clear()
            self._card_labels.clear()
            for it in (self._items or []):
                card = self._grid_view.card_for(it.path)
                if card is not None:
                    self._cards[it.path] = card
                    self._card_labels[it.path] = card  # type: ignore[assignment]
        except Exception:
            pass
        # set_series already swept selection once — tooltips only (no O(N²)).
        try:
            for item in (self._items or []):
                self._refresh_tooltip(item)
        except Exception:
            pass
        try:
            self._install_quick_look_hooks()
        except Exception:
            pass
        return True

    def _sample_view_frame(self) -> None:
        """TEMP-DIAG: log the painted signature on change (see __init__)."""
        try:
            gv = getattr(self, "_grid_view", None)
            if gv is None:
                return
            try:
                cur = self._content_stack.currentWidget()
                stack = type(cur).__name__
            except Exception:
                stack = "?"
            try:
                series = getattr(gv, "_series", None)
                series_n = None if series is None else len(series)
            except Exception:
                series_n = "?"
            try:
                headers = [(h, bool(h.isVisible())) for h in list(getattr(gv, "_series_headers", []) or [])]
                n_hdr_vis = sum(1 for _, v in headers if v)
            except Exception:
                n_hdr_vis = "?"
            try:
                cards = list(getattr(gv, "_cards_by_path", {}).values())
                n_cards_vis = sum(1 for c in cards if bool(c.isVisible()))
                n_cards = len(cards)
            except Exception:
                n_cards_vis, n_cards = "?", "?"
            sig = f"stack={stack} series={series_n} headers={n_hdr_vis} cards={n_cards_vis}/{n_cards}"
            if sig != getattr(self, "_view_frame_sig", None):
                self._view_frame_sig = sig
                _dbg("view-frame %s", sig)
        except Exception:
            pass

    def _stats_sync_after_dissolve(self) -> None:
        """Sync the stats strip after all series dissolved to UNGROUPED.

        The strip otherwise keeps showing the pre-removal series count
        next to a grid that has no SERIES headers left.
        """
        try:
            total = len(list(self._items or []))
        except Exception:
            return
        try:
            self.stats_strip.set_stats(int(total), 0, 0)
        except Exception:
            pass

    def refresh_card(self, item: GalleryItem) -> None:
        # Delegate to grid_view (Button region update)
        try:
            self._grid_view.refresh_card(item)
        except Exception:
            pass
        # Also handle legacy QLabel thumb path if present (for tests that inspect thumb)
        thumb = self._card_labels.get(item.path)
        # If thumb is actually a Button, grid_view already handled pixmap; no QLabel logic needed.
        # Keep tooltip logic for Button cards
        self._refresh_tooltip(item)

    def _refresh_tooltip(self, item: GalleryItem) -> None:
        """Sync the card tooltip for *item* (no content update, no sweep)."""
        try:
            card = self._cards.get(item.path) or self._grid_view.card_for(item.path)
        except Exception:
            return
        if card is not None:
            try:
                tip_parts = [item.name]
                if item.analysis is not None:
                    tip_parts.append(item.analysis.description)
                    if item.analysis.tags:
                        tip_parts.append(", ".join(item.analysis.tags))
                if item.analysis_error:
                    tip_parts.append(item.analysis_error)
                card.setToolTip("\n".join(tip_parts))
            except Exception:
                pass

    def _refresh_rebuilt_cards(self, items, *, sweep: bool) -> None:
        """Post-(re)build paint without the O(N²) sweep cascade.

        Content is already current from the acquire/update pass — only
        tooltips (stale on pool-recycled cards) plus a single selection
        sweep. Replaces per-item ``refresh_card`` loops, each of which
        re-swept selection over the whole grid.
        """
        try:
            for item in list(items or []):
                self._refresh_tooltip(item)
        except Exception:
            pass
        if sweep:
            try:
                self._grid_view.apply_selection(None)
            except Exception:
                pass

    def refresh_cards(self, items) -> None:
        """Batch passthrough to ``grid_view.refresh_cards`` (single selection sweep).

        Falls back to per-card refresh when the grid view predates the batch
        API (tests with stubbed grid views). Single-card semantics (incl.
        the legacy tooltip tail) live in ``refresh_card``.
        """
        try:
            batch = getattr(self._grid_view, "refresh_cards", None)
            if callable(batch):
                batch(items)
                return
        except Exception:
            pass
        try:
            for item in list(items or []):
                self.refresh_card(item)
        except Exception:
            pass

    def set_card_visible(self, path: Path, visible: bool) -> None:
        try:
            self._grid_view.set_card_visible(path, visible)
        except Exception:
            pass
        card = self._cards.get(path)
        if card is not None:
            try:
                card.setVisible(visible)
            except Exception:
                pass

    # -- DnD: accept drops anywhere on the widget (fixes "после скидывания ничего") --

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        from tabs.image_gallery.ui import drag_drop as _drag_drop

        _drag_drop.drag_enter_event(self, event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        from tabs.image_gallery.ui import drag_drop as _drag_drop

        _drag_drop.drag_move_event(self, event)

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        from tabs.image_gallery.ui import drag_drop as _drag_drop

        _drag_drop.drag_leave_event(self, event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        from tabs.image_gallery.ui import drag_drop as _drag_drop

        _drag_drop.drop_event(self, event)

    def pick_folder_dialog(self, start_dir: str = "") -> str | None:
        from tabs.image_gallery.use_cases import dialog as _dialog

        return _dialog.pick_folder_dialog(self, start_dir)

    # -- triage (Stage 2 Pass 1) -----------------------------------------------

    def _on_keep_best(self) -> None:
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            _triage.keep_best_of_series(self._owner_for_triage())
        except Exception:
            pass

    def _on_show_all(self) -> None:
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            _triage.show_all(self._owner_for_triage())
        except Exception:
            pass

    def _on_clean_rejected(self) -> None:
        try:
            # Prefer S3 overlay if rejected items exist.
            owner = self._owner_for_triage()
            # Check rejected count.
            n = 0
            try:
                st = getattr(owner, "state", None) or getattr(self, "_state", None)
                items = list(getattr(st, "items", []) or []) if st is not None else list(self._items or [])
                n = sum(1 for it in items if bool(getattr(it, "rejected", False)))
            except Exception:
                n = 0
            if n > 0:
                self.show_clean_review(owner)
            else:
                from tabs.image_gallery.use_cases import triage as _triage

                _triage.clean_rejected(owner)
        except Exception:
            pass

    def _on_compare_finalists(self) -> None:
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            _triage.compare_finalists(self._owner_for_triage())
        except Exception:
            pass

    def _series_view_matches(self, norm_series, prev_mode, prev_source, mode, source) -> bool:
        """True when the painted series view already equals the incoming one.

        Compares ordered cluster membership (path strings), the UNGROUPED
        tail derived from ``self._items``, object identity per path (fresh
        objects need card refresh, not a skip), plus mode/source (dot
        palette + strip label depend on them). Lets repeat triage over an
        unchanged pool skip the full card recycle.
        """
        try:
            if mode != prev_mode:
                return False
        except Exception:
            return False
        try:
            if str(source) != str(prev_source):
                return False
        except Exception:
            return False
        try:
            gv = getattr(self, "_grid_view", None)
            if gv is None:
                return False
            cur_clusters = [list(cl) for cl in (getattr(gv, "_series", None) or [])]
            new_clusters = [list(cl) for cl in (norm_series or []) if len(list(cl)) >= 2]
            if len(cur_clusters) != len(new_clusters):
                return False
            try:
                by_path = {}
                for it in (self._items or []):
                    try:
                        by_path[str(it.path)] = it
                    except Exception:
                        continue
            except Exception:
                by_path = {}
            for cur_cl, new_cl in zip(cur_clusters, new_clusters):
                try:
                    cur_paths = [str(getattr(m, "path", None)) for m in list(cur_cl)]
                    new_paths = [str(getattr(m, "path", None)) for m in list(new_cl)]
                except Exception:
                    return False
                if cur_paths != new_paths:
                    return False
                for m in list(new_cl):
                    try:
                        if m is not by_path.get(str(getattr(m, "path", None))):
                            return False
                    except Exception:
                        return False
            try:
                cur_members = {p for cl in cur_clusters for p in [str(getattr(m, "path", None)) for m in list(cl)]}
                new_members = {p for cl in new_clusters for p in [str(getattr(m, "path", None)) for m in list(cl)]}
                cur_all = set(by_path)
            except Exception:
                return False
            if cur_members != new_members:
                return False
            if (cur_all - cur_members) != (cur_all - new_members):
                return False
            return True
        except Exception:
            return False

    def _rebuild_series_view(self, norm_series, hub_names, collapsed) -> None:
        """Paint the series-grouped grid (extracted from set_triage)."""
        try:
            if norm_series:
                self._grid_view.set_series(norm_series, hub_names=hub_names, collapsed=collapsed)
                # Sync collapsed back (grid may have normalized)
                try:
                    self._collapsed = dict(getattr(self._grid_view, "_collapsed", {}) or collapsed)
                except Exception:
                    pass
            else:
                # No series: show UNGROUPED header for all items (real_design.md:59)
                self._grid_view.set_series([], hub_names=[], collapsed=collapsed)
            # set_scanning hid the grid for S1 — S2 content exists again, show it
            if self._items or norm_series:
                try:
                    if hasattr(self, "_content_stack"):
                        self._content_stack.setCurrentWidget(self._grid_view)
                    else:
                        self._grid_view.show()
                except Exception:
                    pass
            # Keep compat dicts in sync after series rebuild
            self._cards.clear()
            self._card_labels.clear()
            for it in (self._items or []):
                card = self._grid_view.card_for(it.path)
                if card is not None:
                    self._cards[it.path] = card
                    self._card_labels[it.path] = card  # type: ignore[assignment]
            # Re-hook double-click for newly pooled cards
            try:
                self._install_quick_look_hooks()
            except Exception:
                pass
        except Exception:
            pass

    def set_triage(self, series, mode, source) -> None:
        """Stage 2: update stats strip + series-grouped grid.

        *series* — list of clusters (each ≥2) as ``list[list[GalleryItem]]``
        or ``list[Series]``. Singles are derived as items not in any cluster
        and shown under an ``UNGROUPED`` tail. *mode* is ``fidelity`` |
        ``camera`` | ``batch_synthetic`` and *source* is the hub/source file
        for fidelity mode.
        """
        # Normalize series to list[list[GalleryItem]]
        norm_series: list[list] = []
        try:
            if series is None:
                norm_series = []
            else:
                for entry in list(series):
                    # Accept Series dataclass (has .members) or plain list.
                    if hasattr(entry, "members"):
                        members = list(getattr(entry, "members") or [])
                    else:
                        members = list(entry) if isinstance(entry, (list, tuple)) else [entry]
                    if members:
                        norm_series.append(members)
        except Exception:
            norm_series = []

        try:
            self._series = list(norm_series)
        except Exception:
            self._series = []
        try:
            prev_mode = self._mode
        except Exception:
            prev_mode = None
        try:
            prev_source = self._source_path
        except Exception:
            prev_source = None
        self._mode = mode
        try:
            self._source_path = Path(source) if source is not None else None
        except Exception:
            self._source_path = None
        try:
            view_unchanged = self._series_view_matches(
                norm_series, prev_mode, prev_source, mode, source
            )
        except Exception:
            view_unchanged = False

        # Stats strip — "40 images · 7 series · 33 redundant" synced with grid (real_design §2.3)
        try:
            filtered = [cl for cl in norm_series if len(cl) >= 2]
            series_cnt = len(filtered)
            try:
                member_paths = {str(it.path) for cl in filtered for it in cl}
            except Exception:
                member_paths = set()
            # Total synced: prefer grid contents (series+ungrouped) over stale _items
            if filtered:
                try:
                    # ungrouped from _items or derived
                    if self._items:
                        ungrouped_cnt = sum(1 for it in self._items if str(it.path) not in member_paths)
                    else:
                        ungrouped_cnt = 0
                    total = sum(len(cl) for cl in filtered) + int(ungrouped_cnt)
                except Exception:
                    total = len(self._items) if isinstance(self._items, list) else sum(len(cl) for cl in filtered)
            else:
                total = len(self._items) if isinstance(self._items, list) else 0
                ungrouped_cnt = total  # all ungrouped when no series
                # but spec expects UNGROUPED · N header, so series 0
            redundant = max(0, int(total) - int(series_cnt) - int(ungrouped_cnt)) if total else 0
            # When total from _items mismatches series (e.g. _items 1 but series 2), recompute total from series
            try:
                series_total = sum(len(cl) for cl in filtered) + int(ungrouped_cnt)
                if series_total > total:
                    total = series_total
                    redundant = max(0, int(total) - int(series_cnt) - int(ungrouped_cnt))
            except Exception:
                pass
            # Live rejected count
            rejected_n = 0
            try:
                rejected_n = sum(1 for it in (self._items or []) if bool(getattr(it, "rejected", False)))
            except Exception:
                pass
            self.stats_strip.set_stats(total, series_cnt, redundant)
            self.stats_strip.set_rejected_count(rejected_n)
            try:
                from tabs.image_gallery.use_cases.triage import should_show_all as _should_show_all

                groups = [cl for cl in (filtered or []) if len(cl) >= 2]
                if not groups:
                    # Flat fallback: group grid items by series_id.
                    try:
                        from tabs.image_gallery.use_cases.triage import _flat_series_groups

                        groups = _flat_series_groups(self._items or [])
                    except Exception:
                        groups = []
                self.stats_strip.set_keep_mode(
                    "show" if _should_show_all(self._items or [], groups) else "keep"
                )
            except Exception:
                pass
            self.stats_strip.set_mode(str(mode or "fidelity"), self._source_path)
            self.stats_strip.show()
        except Exception:
            pass

        # Hub names + collapsed for grid_view (A1 parity: SERIES i · hub · n VARIANTS ▾)
        hub_names: list[str | None] = []
        try:
            for cl in [c for c in norm_series if len(c) >= 2]:
                # Hub = rank 1 member name uppercased, else smallest area fallback
                hub_item = None
                try:
                    # Prefer rank 1
                    ranked = sorted(cl, key=lambda it: int(getattr(it, "rank", 999) or 999))
                    hub_item = ranked[0] if ranked else cl[0]
                except Exception:
                    hub_item = cl[0] if cl else None
                if hub_item is not None:
                    try:
                        hub_names.append(Path(hub_item.path).name.upper())
                    except Exception:
                        hub_names.append(str(getattr(hub_item, "name", "")) .upper() or None)
                else:
                    hub_names.append(None)
        except Exception:
            hub_names = []

        # Ensure collapsed dict persists
        try:
            collapsed = dict(getattr(self, "_collapsed", {}) or {})
        except Exception:
            collapsed = {}

        # Series-grouped grid — headers only for clusters ≥2, singles under UNGROUPED tail.
        # Identical re-triage (append/change that moved nothing) skips the
        # full recycle: stats above already synced, cards are current.
        if view_unchanged:
            _dbg("set_triage skip rebuild: view identical")
            _dbg("view-cycle triage series=%d → skip (identical)", len([cl for cl in norm_series if len(cl) >= 2]))
        else:
            _dbg(
                "view-cycle triage series=%d → rebuild",
                len([cl for cl in norm_series if len(cl) >= 2]),
            )
            try:
                self._rebuild_series_view(norm_series, hub_names, collapsed)
            except Exception:
                pass
        # No setStyleSheet — painter pipeline owns visuals.
        # Mark triage done (S2) — toolbar ✓
        try:
            self.set_triage_done()
        except Exception:
            pass
        # No setStyleSheet — painter pipeline owns visuals.
