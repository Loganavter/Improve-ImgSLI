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
        # Subtree translator root (W1 toolkit API): bind the tab-injected
        # translator ONCE here so every descendant implementing the
        # duck-typed protocol (declarative ``text_key``/``badge_key`` on
        # Button/Label/Text/ContextMenu, plus the toolbar/stats ``retranslate``
        # hooks) resolves ``translator_for(self)`` to it. Guarded: storeless
        # tests construct the widget with ``context=None``.
        try:
            if context is not None:
                from sli_ui_toolkit.i18n import install_translator

                install_translator(self, (lambda k, lang: context._tr_lang(k, lang)))
        except Exception:
            pass
        # Page background: paint our OWN opaque themed surface and repaint on
        # theme flip. The page must not rely on an ancestor host — under the
        # translucent CSD shell a transparent page does not get the host's
        # surface re-composited on a live switch, so the empty-state area kept
        # the previous theme's fill until an app restart.
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self.update)
        except Exception:
            pass
        # Jank watchdog (diagnosis only): QTimer ticks on the GUI thread —
        # worker threads keep logging while the GUI loop is stuck, so plain
        # log gaps cannot prove GUI blocks. Any inter-tick gap over the
        # threshold is a GUI-thread stall, whatever its cause.
        try:
            import os as _os
            import time as _time

            if _os.environ.get("IMGSLI_JANK_WATCH", "") not in ("", "0", "no", "off"):
                from PySide6.QtCore import QTimer as _QTimer

                _last = [_time.monotonic()]

                def _jank_tick():
                    try:
                        now = _time.monotonic()
                        gap = now - _last[0]
                        _last[0] = now
                        if gap >= 0.15:
                            logger.warning("[jank] gui-loop gap %.0fms", gap * 1000.0)
                    except Exception:
                        pass

                self._jank_timer = _QTimer(self)
                try:
                    self._jank_timer.setInterval(50)
                except Exception:
                    pass
                try:
                    self._jank_timer.timeout.connect(_jank_tick)
                except Exception:
                    pass
                try:
                    self._jank_timer.start()
                except Exception:
                    pass
                try:
                    logger.warning("[jank] watchdog armed (50ms tick, >=150ms gaps)")
                except Exception:
                    pass
        except Exception:
            pass
        # G2 gallery contract: controller attached once via attach_controller
        # (called by ImageGalleryTab.create_page). Until attached, the widget
        # acts as its own triage owner (storeless unit tests, fail-open).
        self._attached_controller = None
        # Session isolation (Wave ISO): this live copy addresses its OWN
        # session id for every slot read — never the active session per
        # read. The tab binds authoritatively via bind_gallery_session;
        # unbound copies fail open to legacy (active) behavior.
        self._gallery_session_id: str | None = None
        self._items: list[GalleryItem] = []
        # View switch state: False grid, True list. Mirrors the toolbar
        # segmented switch; grid_view owns the per-card builders
        # (set_view_mode swaps ui/card <-> ui/list in place).
        self._view_mode = False
        # Judgment domain served by the toolbar switch (plan-gallery-two-domain-
        # axes W2): "algorithms" (local detectors) or "ai". Transient view
        # state — session-slot persistence is a follow-up.
        self._judgment_domain = "algorithms"

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
        try:
            self.toolbar.domainChanged.connect(self._on_domain_changed)
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
        # Explicit back-ref (owner hands its own child a ref to itself):
        # marquee plumbing lives on the grid_view and resolves the triage
        # controller via ``_gallery_widget._owner_for_triage()``. A parent
        # walk is unreliable (the grid is reparented into the content
        # stack), so the owner passes itself here at construction.
        self._grid_view._gallery_widget = self  # type: ignore[attr-defined]
        self._grid_view.setObjectName("image_gallery_grid_view")
        # Legacy aliases for controller compatibility
        self._scroll = self._grid_view.scroll_area
        self._scroll.setObjectName("image_gallery_scroll")
        self._grid_host = self._grid_view.items_host
        self._grid_host.setObjectName("image_gallery_grid_host")
        self._grid = self._grid_view.items_layout
        # Wire grid toggle -> analyze_requested (card click) and context menu
        self._grid_view.configure(
            on_toggle=self._on_card_toggle,
            on_context_menu=self._on_card_context,
            on_empty_context_menu=self._on_empty_host_context,
            on_series_context_menu=self._on_series_context_menu,
        )
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
        # Session-only custom series names (series_id → display name). The
        # derived header names, so a plain dict keyed by the stable id is
        # enough; never persisted (series themselves are in-memory only).
        self._series_names: dict[str, str] = {}

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
        # Language switch: keep the lazily-created overlays in sync with the
        # active translator (they capture ``_tr`` once at construction).
        # ``translatable_callback`` ties the connection to this widget's
        # lifetime (auto-disconnect on destroy) — the toolkit idiom.
        try:
            from sli_ui_toolkit.i18n import translatable_callback

            translatable_callback(self, lambda _lang: self._retranslate_chrome())
        except Exception:
            pass
        # Selection actions live in the card context menu (ex-HUD flyout removed).
        # Kept as None for back-compat getattr hooks (hover/list/clean_review).
        self._selection_hud = None  # type: ignore[assignment]

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
        """Thin delegator to ``ui/widget_parts.gallery_slot._on_filter_text_dispatch``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._on_filter_text_dispatch(self, text)

    def _init_gallery_store_subscription(self) -> None:
        """Thin delegator to ``ui/widget_parts.gallery_slot._init_gallery_store_subscription``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._init_gallery_store_subscription(self)

    def bind_gallery_session(self, session_id: str | None) -> None:
        """(Re)bind this live copy to its OWN session id.

        Thin delegator to ``ui/widget_parts.gallery_slot.bind_gallery_session``;
        the ONLY place the binding changes — slot reads never re-resolve.
        """
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot.bind_gallery_session(self, session_id)

    def _is_active_gallery_tab(self) -> bool:
        """THE sanctioned active read: own id vs active session METADATA.

        Thin delegator to ``ui/widget_parts.gallery_slot._is_active_gallery_tab``.
        """
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._is_active_gallery_tab(self)

    def _on_gallery_store_changed(self, scope: str) -> None:
        """Thin delegator to ``ui/widget_parts.gallery_slot._on_gallery_store_changed``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._on_gallery_store_changed(self, scope)

    def _render_from_gallery_slot(self) -> None:
        """Thin delegator to ``ui/widget_parts.gallery_slot._render_from_gallery_slot``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._render_from_gallery_slot(self)

    def _render_gallery_selection(self, selected_ids: list) -> None:
        """Thin delegator to ``ui/widget_parts.gallery_slot._render_gallery_selection``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._render_gallery_selection(self, selected_ids)

    def _render_gallery_filter(self, filter_text: str) -> None:
        """Thin delegator to ``ui/widget_parts.gallery_slot._render_gallery_filter``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._render_gallery_filter(self, filter_text)

    def _render_gallery_folder(self, folder: str | None) -> None:
        """Thin delegator to ``ui/widget_parts.gallery_slot._render_gallery_folder``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._render_gallery_folder(self, folder)

    def _render_gallery_pool(self, slot) -> None:
        """Thin delegator to ``ui/widget_parts.gallery_slot._render_gallery_pool``."""
        from tabs.image_gallery.ui.widget_parts import gallery_slot

        return gallery_slot._render_gallery_pool(self, slot)

    # -- wiring for toolbar sort/view (A1) ---------------------------------

    def _on_sort_changed(self, text: str) -> None:
        """Thin delegator to ``ui/widget_parts.view_prefs._on_sort_changed``."""
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs._on_sort_changed(self, text)

    @staticmethod
    def _sort_keyfunc(key: str):
        """Thin delegator to ``ui/widget_parts.view_prefs._sort_keyfunc``."""
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs._sort_keyfunc(None, key)

    def _on_view_toggled(self, checked: bool) -> None:
        """Thin delegator to ``ui/widget_parts.view_prefs._on_view_toggled``."""
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs._on_view_toggled(self, checked)

    def _on_domain_changed(self, domain: str) -> None:
        """Toolbar domain switch changed — normalize, store, mirror.

        Thin delegator to ``ui/widget_parts.view_prefs._on_domain_changed``.
        """
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs._on_domain_changed(self, domain)

    def attach_session_state(self, state) -> None:
        """Attach the tab's ``SessionState`` facade (toolbar chrome writes).

        Thin delegator to ``ui/widget_parts.view_prefs.attach_session_state``.
        """
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs.attach_session_state(self, state)

    def _persist_view_prefs(self) -> None:
        """Thin delegator to ``ui/widget_parts.view_prefs._persist_view_prefs``."""
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs._persist_view_prefs(self)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Thin delegator to ``ui/widget_parts.view_prefs.paint_event``.

        Qt looks this up by name; the body (opaque themed page background,
        live on theme flip) lives in the module.
        """
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs.paint_event(self, event)

    def apply_view_prefs(self, *, view_list: bool, judgment_domain: str) -> None:
        """Thin delegator to ``ui/widget_parts.view_prefs.apply_view_prefs``."""
        from tabs.image_gallery.ui.widget_parts import view_prefs

        return view_prefs.apply_view_prefs(
            self, view_list=view_list, judgment_domain=judgment_domain
        )

    # -- card interaction -------------------------------------------------

    def _on_card_toggle(self, path: Path, additive: bool = False) -> None:
        # Click opens, Ctrl+click selects (manual selection stays orthogonal
        # to triage — Ctrl-click/marquee → selection; plain click → quick look).
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

    def _on_empty_host_context(self, global_pos) -> None:
        # FM background menu on empty canvas: Sort by / View (toolbar state).
        try:
            from PySide6.QtGui import QCursor

            gp = global_pos if global_pos is not None else QCursor.pos()
        except Exception:
            gp = global_pos
        try:
            sort_index = int(self.toolbar.sort_index)
        except Exception:
            sort_index = None
        try:
            view_is_list: bool | None = bool(self.toolbar._is_list)
        except Exception:
            view_is_list = None
        try:
            # ``_context`` is the TabContext the widget was built with (see
            # __init__) — the only translator source (the legacy
            # ``_gallery_context`` alias was never assigned).
            _ctx = getattr(self, "_context", None)
            tr = getattr(_ctx, "_tr", None) if _ctx is not None else None
        except Exception:
            tr = None
        try:
            from tabs.image_gallery.ui.card.sort_view_menu import (
                popup_empty_context_menu,
            )

            popup_empty_context_menu(
                self._grid_view,
                gp,
                tr,
                sort_index,
                self.toolbar.set_sort_index,
                view_is_list,
                self.toolbar.set_view_list,
            )
        except Exception:
            pass

    def _on_card_context(self, path: Path) -> None:
        # ContextMenu under cursor: selection section (ex-HUD) + per-card actions.
        # Use public sli_ui_toolkit.widgets ContextMenu via card helper.
        from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

        import time as _time

        _dbg_on = _dbg_enabled()
        _t0 = _time.perf_counter() if _dbg_on else 0.0
        if _dbg_on:
            _dbg("ctx menu entry path=%s", path)
        try:
            # Owner is the attached controller (self when unattached) —
            # no attribute scan, no window walk (G2 gallery contract).
            owner = self._owner_for_triage()
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
            def _ctx_owner():
                try:
                    return self._owner_for_triage()
                except Exception:
                    return owner

            def _ctx_carry():
                try:
                    from tabs.image_gallery.use_cases import carry as _carry

                    _carry.carry_selected(_ctx_owner())
                except Exception:
                    pass

            def _ctx_analyze():
                try:
                    tri = _ctx_owner()
                    sel = getattr(getattr(tri, "state", None), "selected_paths", None) or set()
                    if sel:
                        tri.analyze_item_by_path(next(iter(sel)))  # type: ignore[attr-defined]
                except Exception:
                    pass

            def _ctx_find():
                try:
                    from tabs.image_gallery.use_cases.carry import find_similar_selected

                    find_similar_selected(_ctx_owner())
                except Exception:
                    pass

            def _ctx_ask(scope_kind: str):
                try:
                    tri = _ctx_owner()
                    fn = getattr(tri, "open_ask_ai", None)
                    if callable(fn):
                        fn(scope_kind, card, Path(path))
                except Exception:
                    pass

            try:
                sel_set = getattr(getattr(owner, "state", None), "selected_paths", None) or set()
                sel_n = len(sel_set)
            except Exception:
                sel_n = 0
            try:
                # Same fix as the empty-canvas menu: the translator lives on
                # ``_context`` only.
                _ctx = getattr(self, "_context", None)
                _tr = getattr(_ctx, "_tr", None) if _ctx is not None else None
            except Exception:
                _tr = None
            popup_gallery_card_context_menu(
                anchor,
                owner,
                Path(path),
                global_pos=gp,
                selection_count=sel_n,
                on_carry=_ctx_carry,
                on_analyze=_ctx_analyze,
                on_find_similar=_ctx_find,
                on_ask_ai=_ctx_ask,
                translate=_tr,
            )
            if _dbg_on:
                _dbg("ctx menu done total=%.1fms path=%s", (_time.perf_counter() - _t0) * 1000.0, path)
        except Exception:
            if _dbg_on:
                _dbg("ctx menu raised path=%s", path, exc_info=True)
            pass

    def _on_empty_file_dropped(self, path_str: str) -> None:
        from tabs.image_gallery.ui import drag_drop as _drag_drop

        _drag_drop.on_empty_file_dropped(self, path_str, self._owner_for_triage())

    # -- Ask AI (A3 surface; async lives in the controller) ----------------------

    def _ensure_ask_ai_flyout(self):
        flyout = getattr(self, "_ask_ai_flyout", None)
        if flyout is None:
            from tabs.image_gallery.ui.ask_ai import AskAiFlyout

            flyout = AskAiFlyout(self)
            try:
                flyout.setObjectName("gallery_ask_ai_flyout")
            except Exception:
                pass
            # An answer's image link opens Quick Look for that image.
            try:
                flyout.imageActivated.connect(self._on_ask_ai_image_activated)
            except Exception:
                pass
            self._ask_ai_flyout = flyout
        return flyout

    def _on_ask_ai_image_activated(self, path: str) -> None:
        """Open Quick Look for an image named in the Ask AI answer.

        The flyout closes first: leaving it open over Quick Look strands
        its (link-clicked) text caret on screen.
        """
        try:
            flyout = getattr(self, "_ask_ai_flyout", None)
            if flyout is not None and flyout.isVisible():
                flyout.hide()
        except Exception:
            pass
        try:
            self.show_quick_look(str(path))
        except Exception:
            logger.debug("ask-ai image activation failed", exc_info=True)

    def open_ask_ai(
        self, anchor, scope, *, default_prompt: str = "What matters here?", texts=None, grow_up: bool = False, show_images_toggle: bool = True
    ) -> None:
        """Show the Ask AI flyout; submit routes to ``controller.ask_ai_question``."""
        flyout = self._ensure_ask_ai_flyout()
        if texts:
            try:
                flyout.set_texts(**texts)
            except Exception:
                pass
        # Re-invoking on the SAME scope toggles closed instead of re-running
        # the show animation (a second right-click looked like "reopening").
        scope_key = self._ask_scope_key(scope)
        try:
            if flyout.isVisible() and getattr(self, "_ask_ai_scope_key", None) == scope_key:
                flyout.hide()
                return
        except Exception:
            pass
        # One live scope per open: drop the previous submit binding (disconnect
        # the exact slot; a bare disconnect() warns when nothing is bound).
        bound = getattr(self, "_ask_ai_submit_slot", None)
        if bound is not None:
            try:
                flyout.submitted.disconnect(bound)
            except Exception:
                pass
        slot = lambda question, _s=scope: self._submit_ask_ai(_s, question)  # noqa: E731
        self._ask_ai_submit_slot = slot
        flyout.submitted.connect(slot)
        try:
            label = getattr(scope, "label", "") or ""
        except Exception:
            label = ""
        self._ask_ai_anchor = anchor or self
        self._ask_ai_scope = scope
        self._ask_ai_scope_key = scope_key
        # Preserve the last answer across hide/reopen, seeding it BEFORE the
        # show animation (seeding after the show calls reposition() mid-fade,
        # which flashes the panel white).
        initial_result = None
        initial_error = ""
        initial_links: dict = {}
        if getattr(self, "_ask_ai_last_key", None) == getattr(
            self, "_ask_ai_scope_key", None
        ):
            if getattr(self, "_ask_ai_last_result", None) is not None:
                initial_result = self._ask_ai_last_result
                initial_links = dict(getattr(self, "_ask_ai_last_links", None) or {})
            elif getattr(self, "_ask_ai_last_error", None):
                initial_error = self._ask_ai_last_error
        flyout.open_for(
            self._ask_ai_anchor,
            scope_label=label,
            default_prompt=default_prompt,
            initial_result=initial_result,
            initial_error=initial_error,
            initial_links=initial_links,
            grow_up=grow_up,
            show_images_toggle=show_images_toggle,
        )

    @staticmethod
    def _ask_scope_key(scope):
        """Stable identity for one ask scope (used to restore the last answer)."""
        try:
            paths = tuple(sorted(str(p) for p in (getattr(scope, "paths", ()) or ())))
            return (
                str(getattr(scope, "kind", "")),
                paths,
                str(getattr(scope, "series_id", "") or ""),
                str(getattr(scope, "label", "") or ""),
                tuple(getattr(scope, "box", ()) or ()),
            )
        except Exception:
            return None

    def _submit_ask_ai(self, scope, question: str) -> None:
        owner = self._owner_for_triage()
        fn = getattr(owner, "ask_ai_question", None)
        if callable(fn):
            include = False
            try:
                flyout = getattr(self, "_ask_ai_flyout", None)
                inc = getattr(flyout, "include_images", None)
                if callable(inc):
                    include = bool(inc())
            except Exception:
                include = False
            try:
                fn(scope, question, include_images=include)
            except TypeError:
                fn(scope, question)
            return
        self.show_ask_ai_error("AI is unavailable.")

    def show_ask_ai_busy(self) -> None:
        try:
            self._ensure_ask_ai_flyout().set_busy(True)
        except Exception:
            pass

    def show_ask_ai_result(self, result, model: str = "", links: dict | None = None) -> None:
        try:
            flyout = self._ensure_ask_ai_flyout()
            flyout.set_busy(False)
            flyout.show_result(
                getattr(result, "text", "") or "",
                model=model,
                backend=getattr(result, "backend", "") or "",
                cached=bool(getattr(result, "cached", False)),
                links=links,
            )
            self._ask_ai_last_key = getattr(self, "_ask_ai_scope_key", None)
            self._ask_ai_last_result = result
            self._ask_ai_last_links = dict(links or {})
            self._ask_ai_last_error = None
            self._resume_ask_ai_if_hidden(flyout)
        except Exception:
            pass

    def show_ask_ai_error(self, message: str) -> None:
        try:
            flyout = self._ensure_ask_ai_flyout()
            flyout.set_busy(False)
            flyout.show_error(message)
            self._ask_ai_last_key = getattr(self, "_ask_ai_scope_key", None)
            self._ask_ai_last_result = None
            self._ask_ai_last_links = {}
            self._ask_ai_last_error = message
            self._resume_ask_ai_if_hidden(flyout)
        except Exception:
            pass

    def _resume_ask_ai_if_hidden(self, flyout) -> None:
        """A late answer must not vanish: re-show the flyout if it was dismissed."""
        try:
            if flyout.isVisible():
                return
            anchor = getattr(self, "_ask_ai_anchor", None)
            if anchor is not None:
                flyout.reshow(anchor)
        except Exception:
            pass

    # -- series header context menu ---------------------------------------------

    def _tr_ui(self, key: str, default: str) -> str:
        """Gallery i18n lookup for widget-level strings (fail-open to default)."""
        ctx = getattr(self, "_context", None)
        if ctx is None:
            return default
        try:
            return ctx._tr(key, default)
        except Exception:
            return default

    def _retranslate_overlays(self) -> None:
        """Refresh the lazily-created overlays on a live language switch.

        Reuses this widget's context translator (same ``tr`` the toolbar and
        stats strip got at construction). No-op while an overlay has not been
        created yet — the next ``show_*`` builds it with the current tr.
        """
        ctx = getattr(self, "_context", None)
        tr = getattr(ctx, "_tr", None) if ctx is not None else None
        for attr in ("_clean_overlay", "_quick_look_overlay"):
            overlay = getattr(self, attr, None)
            if overlay is None:
                continue
            try:
                overlay.retranslate(tr)
            except Exception:
                pass

    def _retranslate_chrome(self) -> None:
        """Re-render every gallery-owned string on a live language switch.

        The toolbar/stats strip captured ``translate`` at construction and
        their ``retranslate()`` hooks were never wired; the series headers and
        cards capture theirs per render. Re-applies all three in place — no
        teardown, selection/scroll/focus preserved (the grid reuses header and
        card widgets). Fail-open per surface.
        """
        self._retranslate_overlays()
        for attr in ("toolbar", "stats_strip"):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            try:
                widget.retranslate()
            except Exception:
                pass
        try:
            gv = getattr(self, "_grid_view", None)
            if gv is not None:
                gv.retranslate_headers()
        except Exception:
            pass

    def _series_names_map(self) -> dict:
        """Session custom-name map (series_id → name); lazily created."""
        names = getattr(self, "_series_names", None)
        if not isinstance(names, dict):
            names = {}
            self._series_names = names
        return names

    def _compute_series_hub_names(self, norm_series) -> list:
        """Per-series header names (``SERIES i · <hub> · n VARIANTS``).

        Hub = rank-1 member's file name uppercased, unless a session rename
        override exists for the cluster's stable ``series_id`` (override wins
        verbatim; the header upper-cases it for display).
        """
        names_map = self._series_names_map()
        hub_names: list = []
        try:
            for cl in [c for c in (norm_series or []) if len(c) >= 2]:
                hub_item = None
                try:
                    ranked = sorted(cl, key=lambda it: int(getattr(it, "rank", 999) or 999))
                    hub_item = ranked[0] if ranked else cl[0]
                except Exception:
                    hub_item = cl[0] if cl else None
                hub = None
                if hub_item is not None:
                    try:
                        hub = Path(hub_item.path).name.upper()
                    except Exception:
                        hub = str(getattr(hub_item, "name", "")).upper() or None
                sid = None
                try:
                    for m in cl:
                        _s = getattr(m, "series_id", None)
                        if _s:
                            sid = str(_s)
                            break
                except Exception:
                    sid = None
                if sid and names_map.get(sid):
                    hub = str(names_map[sid])
                hub_names.append(hub)
        except Exception:
            hub_names = []
        return hub_names

    def _on_series_context_menu(
        self, index, anchor, member_paths, label, series_id=None, global_pos=None
    ) -> None:
        """Series-header right-click → toolkit ``ContextMenu``.

        Ask AI / Rename / Delete over the whole series, then the manual-series
        tools (Reset / Re-cluster) as the tail. Popup surface via the app
        manager — parented to the header Button (a content widget), never the
        MainWindow (Wayland compositing trap; see the card menu).
        """
        paths = tuple(member_paths or ())
        owner = self._owner_for_triage()

        def _open_ask_ai_now() -> None:
            try:
                fn = getattr(owner, "open_ask_ai_for_series", None)
                if callable(fn):
                    fn(index, anchor, paths, str(label or ""))
            except Exception:
                pass

        def _do_ask_ai() -> None:
            # The context menu is an in-window registered flyout; the Ask AI
            # flyout's manager sequenced-cycle opt-in waits for it to close,
            # then replays the show — no app-side close/open chain needed.
            _open_ask_ai_now()

        def _do_rename() -> None:
            try:
                self._rename_series(series_id, label)
            except Exception:
                pass

        def _do_delete() -> None:
            try:
                from tabs.image_gallery.use_cases import triage as _triage

                if len(paths) > 1:
                    _triage.remove_paths_from_grid(owner, paths)
                elif paths:
                    _triage.remove_from_grid(owner, paths[0])
            except Exception:
                pass

        def _do_reset() -> None:
            try:
                fn = getattr(owner, "reset_series_overrides", None)
                if callable(fn):
                    fn()
            except Exception:
                pass

        def _do_recluster() -> None:
            try:
                fn = getattr(owner, "recluster_series", None)
                if callable(fn):
                    fn()
            except Exception:
                pass

        try:
            from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator
        except Exception:
            return

        try:
            from tabs.image_gallery.icons import Icon as _GalleryIcon
        except Exception:
            _GalleryIcon = None  # type: ignore[assignment]
        has_reset = callable(getattr(owner, "reset_series_overrides", None))
        has_recluster = callable(getattr(owner, "recluster_series", None))
        entries: list = [
            ContextMenuAction(
                "gallery.series.ask_ai",
                self._tr_ui("image_gallery.series.ask_ai", "Ask AI"),
                icon=getattr(_GalleryIcon, "AI", None),
            ),
            ContextMenuAction(
                "gallery.series.rename",
                self._tr_ui("image_gallery.series.rename", "Rename"),
                icon="text_filename.svg",
                enabled=bool(series_id),
            ),
            ContextMenuAction(
                "gallery.series.delete",
                self._tr_ui("image_gallery.series.delete", "Delete"),
                icon="delete",
                danger=True,
            ),
        ]
        tail: list = []
        if has_reset:
            tail.append(
                ContextMenuAction(
                    "gallery.series.reset",
                    self._tr_ui("image_gallery.series.reset", "Reset manual series"),
                    icon="undo.svg",
                )
            )
        if has_recluster:
            tail.append(
                ContextMenuAction(
                    "gallery.series.recluster",
                    self._tr_ui("image_gallery.series.recluster", "Re-cluster series"),
                    icon="sync.svg",
                )
            )
        if tail:
            entries.append(ContextMenuSeparator())
            entries.extend(tail)

        def _on_triggered(action_id: str, _data: object) -> None:
            if action_id == "gallery.series.ask_ai":
                _do_ask_ai()
            elif action_id == "gallery.series.rename":
                _do_rename()
            elif action_id == "gallery.series.delete":
                _do_delete()
            elif action_id == "gallery.series.reset":
                _do_reset()
            elif action_id == "gallery.series.recluster":
                _do_recluster()

        source = anchor if anchor is not None else self
        pos = global_pos
        if pos is None:
            try:
                from PySide6.QtGui import QCursor

                pos = QCursor.pos()
            except Exception:
                pos = None
        try:
            from ui.context_menu.manager import open_context_menu_entries

            open_context_menu_entries(
                source_widget=source,
                global_pos=pos,
                entries=tuple(entries),
                key=("gallery-series", int(index), str(series_id or "")),
                on_triggered=_on_triggered,
            )
        except Exception:
            logger.debug("series header context menu failed", exc_info=True)

    def _rename_series(self, series_id, label) -> None:
        """Prompt for a session-only custom series name and repaint headers."""
        sid = str(series_id) if series_id else ""
        if not sid:
            return
        try:
            from tabs.host_helpers import AppTextInputDialog
        except Exception:
            return
        names = self._series_names_map()
        current = names.get(sid) or str(label or "")
        title = self._tr_ui("image_gallery.series.rename_title", "Rename series")
        prompt = self._tr_ui("image_gallery.series.rename_prompt", "Series name")
        try:
            parent = self.window() or self
        except Exception:
            parent = self
        value, ok = AppTextInputDialog.get_text(parent, title, prompt, current)
        if not ok:
            return
        name = str(value or "").strip()
        if name:
            names[sid] = name
        else:
            names.pop(sid, None)  # empty → fall back to the derived hub name
        self._refresh_series_names()

    def _refresh_series_names(self) -> None:
        """Repaint series headers with the current custom names (no teardown)."""
        try:
            norm_series = list(self._series or [])
        except Exception:
            return
        try:
            collapsed = dict(self._collapsed or {})
        except Exception:
            collapsed = {}
        try:
            self._rebuild_series_view(
                norm_series, self._compute_series_hub_names(norm_series), collapsed
            )
        except Exception:
            logger.debug("series rename repaint failed", exc_info=True)

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

    # -- keyboard: Space/Delete remove card, B make best, Enter compare, Esc close/back, arrows navigate
    # widget keyPressEvent -> triage functions (design.md:129) ----------------

    def attach_controller(self, controller) -> None:
        """Attach the owning ``GalleryController`` (first wins, fail-open).

        Called once by ``ImageGalleryTab.create_page`` (G1 side of the
        gallery-contracts seam). A second call is a protocol violation:
        logged at debug and ignored — last wins is forbidden.
        """
        try:
            if self._attached_controller is not None:
                logger.debug(
                    "ImageGalleryWidget.attach_controller: already attached, ignoring double-attach"
                )
                return
        except AttributeError:
            pass
        self._attached_controller = controller
        # Refresh the zone-drop binding with the now-known controller.
        try:
            from tabs.image_gallery.ui import drag_drop as _drag_drop

            _drag_drop.install_zone_drop_forwarding(self, controller)
        except Exception:
            pass

    def _owner_for_triage(self):
        """Return the attached controller, or self when unattached (fail-open).

        Storeless unit tests construct the widget bare (no tab wiring), so
        ``None`` attachment falls back to the widget itself, which carries
        ``state``-compatible reads. No other fallback chain — no attribute
        scan, no window walk (G2 gallery contract).
        """
        try:
            ctrl = self._attached_controller
        except AttributeError:
            ctrl = None
        if ctrl is not None:
            return ctrl
        return self

    def keyPressEvent(self, event) -> None:  # noqa: N802
        from tabs.image_gallery.use_cases import triage_ui

        # While the toolbar filter has focus, arrows/Home/End belong to the
        # text field — keep the triage_ui typing guard intact (it also runs
        # inside handle_key, but navigation would steal the keys first).
        try:
            from PySide6.QtWidgets import QApplication

            fw = QApplication.focusWidget()
            filter_edit = getattr(self, "_filter_edit", None)
            if fw is not None and fw is filter_edit and event.key() != Qt.Key.Key_Escape:
                return triage_ui.handle_key(self, event)
        except Exception:
            pass
        # Card-grid navigation (arrows / Home / End / Menu) is owned by the
        # grid view — mirrors session_picker/recent/items_view. When no card
        # holds focus yet, an arrow bootstraps onto the first card. Everything
        # else (Space/Delete remove, Enter compare, Esc, B) stays in triage_ui.
        try:
            if self._grid_view.handle_navigation_key(event):
                event.accept()
                return
        except Exception:
            pass
        return triage_ui.handle_key(self, event)

    # -- S3 clean review helpers -----------------------------------------------

    def show_clean_review(self, owner=None) -> None:
        """Open S3 clean review overlay (TopLevelInWindowOverlay + Toast Undo)."""
        try:
            from tabs.image_gallery.ui.clean_review import CleanReviewOverlay

            actual_owner = owner if owner is not None else self._owner_for_triage()
            # Ensure overlay exists. Owner travels via constructor / show_for
            # (both take owner) — never re-poked afterwards (G2 contract).
            _ctx = getattr(self, "_context", None)
            _tr = getattr(_ctx, "_tr", None) if _ctx is not None else None
            overlay = getattr(self, "_clean_overlay", None)
            if overlay is None:
                parent = self.window() or self
                overlay = CleanReviewOverlay(parent, actual_owner, translate=_tr)
                self._clean_overlay = overlay
            elif _tr is not None:
                # Created before a language switch: re-apply the current tr.
                try:
                    overlay.retranslate(_tr)
                except Exception:
                    pass
            overlay.show_for(actual_owner)
        except Exception:
            pass

    # -- A1 scanning/triage done (toolbar + empty state) ---------------------

    def set_scanning(self, n: int, total: int) -> None:
        """Thin delegator to ``ui/widget_parts.status.set_scanning``."""
        from tabs.image_gallery.ui.widget_parts import status

        return status.set_scanning(self, n, total)

    def set_background_scanning(self, n: int, total: int) -> None:
        """Thin delegator to ``ui/widget_parts.status.set_background_scanning``.

        S1 progress without hiding the grid (append path): the current
        series view stays visible — appending one image must not tear
        down good groups behind a spinner while the pool retriages.
        """
        from tabs.image_gallery.ui.widget_parts import status

        return status.set_background_scanning(self, n, total)

    def set_triage_done(self) -> None:
        """Thin delegator to ``ui/widget_parts.status.set_triage_done``."""
        from tabs.image_gallery.ui.widget_parts import status

        return status.set_triage_done(self)

    def reset_session_view(self) -> None:
        """Thin delegator to ``ui/widget_parts.status.reset_session_view``.

        Called by ``GalleryController.clear_to_empty`` when a restore finds
        an empty/absent slot: drops the series view, hides the stats strip,
        stops the spinner, clears the filter edit (signal-blocked, no loop)
        and lands on the default empty state.
        """
        from tabs.image_gallery.ui.widget_parts import status

        return status.reset_session_view(self)

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
            # Also allow the flat (pre-triage) case: a pure pool growth with
            # no live series view yet must still group the fresh card(s)
            # immediately (append_new_cards promotes the flat pool to one
            # UNGROUPED section) — bug 2, first-drop grouping delay.
            if pre_paths and (items or []):
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
        try:
            self._refresh_action_states()
        except Exception:
            pass
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
                self._grid_view.rebuild_grid(
                    items,
                    paint_selection=saved_series is None,
                    flat_ungrouped=saved_series is None,
                )
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
        alive path is new) also lands under one UNGROUPED section, so a
        fresh folder never paints nameless while triage runs.

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
                _dbg("view-cycle restore dissolved added=%d → UNGROUPED (replacement pool)", len(added))
                try:
                    self._grid_view.set_series([], hub_names=[], collapsed={})
                except Exception:
                    return False
                try:
                    self._series = []
                except Exception:
                    pass
                return True
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

    def set_series_attention(self, series_ids) -> None:
        """Forward the cross-series routing hint to the grid (series-header marker).

        Additive: it never changes a card, its rank or the selection.
        """
        try:
            self._grid_view.set_series_attention(series_ids)
        except Exception:
            pass

    def set_rank_provenance(self, source: str | None = None, *, domain: str | None = None) -> None:
        """Show which ranker produced the series ranks (stats-strip chip).

        *source* is a ``rank_source`` token (``fusion``/``jev``/``manual``); when
        absent, *domain* ("algorithms"|"ai") picks the label. The strip hides the
        chip when neither is known (never a fabricated ranker).
        """
        try:
            self.stats_strip.set_rank_provenance(source, domain=domain)
        except Exception:
            pass

    def refresh_card(self, item: GalleryItem) -> None:
        # Re-stamp the display badge (rank/source may have changed since the
        # last triage) before the card renders it — same single computation.
        try:
            from tabs.image_gallery.services.rank_badge import stamp_badges

            stamp_badges([item], getattr(self, "_source_path", None))
        except Exception:
            pass
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
                # Single line: the full file name (the analysis second line was
                # removed — a hover tooltip must not add extra lines).
                card.setToolTip(str(item.name))
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
            from tabs.image_gallery.services.rank_badge import stamp_badges

            stamp_badges(list(items or []), getattr(self, "_source_path", None))
        except Exception:
            pass
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

    def sync_source_badge(self, source) -> None:
        """Move the SOURCE badge the instant the source changes.

        A source change is a pure badge move, so it must not be chained to
        the heavy comparison pass: ``stamp_badges`` is cheap (no decode, no
        Qt) and only the two affected cards — the previous and the new
        source — need a repaint. The background fidelity pass then re-stamps
        everything in ``set_triage`` when it lands. Without this, pressing
        "Make source" showed the old badge until every item had been
        compared against the new source.
        """
        try:
            try:
                old = getattr(self, "_source_path", None)
            except Exception:
                old = None
            try:
                new = Path(source) if source is not None else None
            except Exception:
                new = None
            try:
                self._source_path = new
            except Exception:
                pass
            from tabs.image_gallery.services.rank_badge import stamp_badges

            items: list = []
            try:
                items.extend(list(self._items or []))
            except Exception:
                pass
            try:
                for cluster in getattr(self, "_series", None) or []:
                    items.extend(list(cluster))
            except Exception:
                pass
            stamp_badges(items, new)
            want = {str(p) for p in (old, new) if p is not None}
            if not want:
                return
            changed = []
            seen: set[str] = set()
            for item in items:
                try:
                    key = str(getattr(item, "path", ""))
                except Exception:
                    continue
                if key in want and key not in seen:
                    seen.add(key)
                    changed.append(item)
            if changed:
                self.refresh_cards(changed)
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

        _drag_drop.drop_event(self, event, self._owner_for_triage())

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
                from tabs.image_gallery.use_cases.triage import is_rejected as _is_rejected

                st = getattr(owner, "state", None) or getattr(self, "_state", None)
                items = list(getattr(st, "items", []) or []) if st is not None else list(self._items or [])
                n = sum(1 for it in items if _is_rejected(it))
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

    def _refresh_action_states(self) -> None:
        """Gate Keep best / Compare finalists on live content (fail-open).

        Keep best needs a 2+ survivor cluster (or show-mode, where the
        button reads "Show all"); compare needs 2+ surviving items.
        Anything unresolvable leaves the buttons as-is (never strand a
        live action disabled, never arm a dead one on error).
        """
        try:
            strip = self.stats_strip
            items = list(getattr(self, "_items", None) or [])
            series = list(getattr(self, "_series", None) or [])
        except Exception:
            return

        def _members(cluster):
            if hasattr(cluster, "members"):
                return list(getattr(cluster, "members", None) or [])
            try:
                return list(cluster)
            except Exception:
                return []

        def _alive(members) -> int:
            try:
                from tabs.image_gallery.use_cases.triage import is_rejected as _is_rejected
            except Exception:
                _is_rejected = None  # type: ignore[assignment]
            count = 0
            for m in members or []:
                try:
                    if _is_rejected is None or not _is_rejected(m):
                        count += 1
                except Exception:
                    count += 1
            return count

        try:
            keep_mode = str(getattr(strip, "_keep_mode", "keep") or "keep")
        except Exception:
            keep_mode = "keep"
        try:
            keep = keep_mode.strip().lower().startswith("show") or any(
                _alive(_members(cl)) >= 2 for cl in series if len(_members(cl)) >= 2
            )
        except Exception:
            return
        try:
            compare = _alive(items) >= 2
        except Exception:
            return
        try:
            strip.set_action_states(keep_best=keep, compare_finalists=compare)
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
        # Single source of truth for the display badge: compute it ONCE here
        # (triage/mode/source all converge in set_triage) so every surface
        # renders item.badge verbatim and never re-derives it.
        try:
            from tabs.image_gallery.services.rank_badge import stamp_badges

            _all_items = list(self._items or [])
            for _cluster in norm_series:
                _all_items.extend(_cluster)
            stamp_badges(_all_items, self._source_path)
        except Exception:
            pass
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
                from tabs.image_gallery.use_cases.triage import is_rejected as _is_rejected

                rejected_n = sum(1 for it in (self._items or []) if _is_rejected(it))
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
        try:
            self._refresh_action_states()
        except Exception:
            pass

        # Hub names + collapsed for grid_view (A1 parity: SERIES i · hub · n VARIANTS ▼)
        hub_names = self._compute_series_hub_names(norm_series)

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
