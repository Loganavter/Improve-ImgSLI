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
        # Rank/BEST pills are shown only once the ranking is FINAL for the
        # folder (``GalleryController`` flips this via ``set_ranks_visible``).
        # Default True preserves storeless/stub behaviour; the controller sets
        # it False while a folder's analysis is in flight.
        self._ranks_visible = True
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
        """Thin delegator to ``ui/widget_parts.card_actions._on_card_toggle``."""
        from tabs.image_gallery.ui.widget_parts import card_actions

        return card_actions._on_card_toggle(self, path, additive=additive)

    def _on_empty_host_context(self, global_pos) -> None:
        """Thin delegator to ``ui/widget_parts.card_actions._on_empty_host_context``."""
        from tabs.image_gallery.ui.widget_parts import card_actions

        return card_actions._on_empty_host_context(self, global_pos)

    def _on_card_context(self, path: Path) -> None:
        """Thin delegator to ``ui/widget_parts.card_actions._on_card_context``."""
        from tabs.image_gallery.ui.widget_parts import card_actions

        return card_actions._on_card_context(self, path)

    def _on_empty_file_dropped(self, path_str: str) -> None:
        """Thin delegator to ``ui/widget_parts.card_actions._on_empty_file_dropped``."""
        from tabs.image_gallery.ui.widget_parts import card_actions

        return card_actions._on_empty_file_dropped(self, path_str)

    # -- Ask AI (A3 surface; async lives in the controller) ----------------------

    def _ensure_ask_ai_flyout(self):
        """Thin delegator to ``ui/widget_parts.ask_ai_surface._ensure_ask_ai_flyout``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface._ensure_ask_ai_flyout(self)

    def _on_ask_ai_image_activated(self, path: str) -> None:
        """Thin delegator to ``ui/widget_parts.ask_ai_surface._on_ask_ai_image_activated``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface._on_ask_ai_image_activated(self, path)

    def open_ask_ai(
        self, anchor, scope, *, default_prompt: str = "What matters here?", texts=None, grow_up: bool = False, show_images_toggle: bool = True
    ) -> None:
        """Thin delegator to ``ui/widget_parts.ask_ai_surface.open_ask_ai``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface.open_ask_ai(self, anchor, scope, default_prompt=default_prompt, texts=texts, grow_up=grow_up, show_images_toggle=show_images_toggle)

    @staticmethod
    def _ask_scope_key(scope):
        """Thin delegator to ``ui/widget_parts.ask_ai_surface._ask_scope_key``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface._ask_scope_key(None, scope)

    def _submit_ask_ai(self, scope, question: str) -> None:
        """Thin delegator to ``ui/widget_parts.ask_ai_surface._submit_ask_ai``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface._submit_ask_ai(self, scope, question)

    def show_ask_ai_busy(self) -> None:
        """Thin delegator to ``ui/widget_parts.ask_ai_surface.show_ask_ai_busy``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface.show_ask_ai_busy(self)

    def show_ask_ai_result(self, result, model: str = "", links: dict | None = None) -> None:
        """Thin delegator to ``ui/widget_parts.ask_ai_surface.show_ask_ai_result``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface.show_ask_ai_result(self, result, model, links)

    def show_ask_ai_error(self, message: str) -> None:
        """Thin delegator to ``ui/widget_parts.ask_ai_surface.show_ask_ai_error``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface.show_ask_ai_error(self, message)

    def _resume_ask_ai_if_hidden(self, flyout) -> None:
        """Thin delegator to ``ui/widget_parts.ask_ai_surface._resume_ask_ai_if_hidden``."""
        from tabs.image_gallery.ui.widget_parts import ask_ai_surface

        return ask_ai_surface._resume_ask_ai_if_hidden(self, flyout)

    # -- series header context menu ---------------------------------------------

    def _tr_ui(self, key: str, default: str) -> str:
        """Thin delegator to ``ui/widget_parts.series_headers._tr_ui``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._tr_ui(self, key, default)

    def _retranslate_overlays(self) -> None:
        """Thin delegator to ``ui/widget_parts.series_headers._retranslate_overlays``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._retranslate_overlays(self)

    def _retranslate_chrome(self) -> None:
        """Thin delegator to ``ui/widget_parts.series_headers._retranslate_chrome``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._retranslate_chrome(self)

    def _series_names_map(self) -> dict:
        """Thin delegator to ``ui/widget_parts.series_headers._series_names_map``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._series_names_map(self)

    def _compute_series_hub_names(self, norm_series) -> list:
        """Thin delegator to ``ui/widget_parts.series_headers._compute_series_hub_names``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._compute_series_hub_names(self, norm_series)

    def _on_series_context_menu(
        self, index, anchor, member_paths, label, series_id=None, global_pos=None
    ) -> None:
        """Thin delegator to ``ui/widget_parts.series_headers._on_series_context_menu``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._on_series_context_menu(self, index, anchor, member_paths, label, series_id, global_pos)

    def _rename_series(self, series_id, label) -> None:
        """Thin delegator to ``ui/widget_parts.series_headers._rename_series``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._rename_series(self, series_id, label)

    def _refresh_series_names(self) -> None:
        """Thin delegator to ``ui/widget_parts.series_headers._refresh_series_names``."""
        from tabs.image_gallery.ui.widget_parts import series_headers

        return series_headers._refresh_series_names(self)

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
        """Thin delegator to ``ui/widget_parts.keys.attach_controller``."""
        from tabs.image_gallery.ui.widget_parts import keys

        return keys.attach_controller(self, controller)

    def _owner_for_triage(self):
        """Thin delegator to ``ui/widget_parts.keys._owner_for_triage``."""
        from tabs.image_gallery.ui.widget_parts import keys

        return keys._owner_for_triage(self)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Thin delegator to ``ui/widget_parts.keys.key_press_event``.

        Qt looks this up by name; the body (card-grid navigation vs
        triage keys) lives in the module.
        """
        from tabs.image_gallery.ui.widget_parts import keys

        return keys.key_press_event(self, event)

    # -- S3 clean review helpers -----------------------------------------------

    def show_clean_review(self, owner=None) -> None:
        """Thin delegator to ``ui/widget_parts.triage_actions.show_clean_review``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions.show_clean_review(self, owner)

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
        """Thin delegator to ``ui/widget_parts.grid_api.set_folder_label``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.set_folder_label(self, folder)

    def rebuild_grid(self, items: list[GalleryItem]) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api.rebuild_grid``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.rebuild_grid(self, items)

    def _restore_series_view(self, saved, pre_paths=None) -> bool:
        """Thin delegator to ``ui/widget_parts.grid_api._restore_series_view``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api._restore_series_view(self, saved, pre_paths=pre_paths)

    def _sample_view_frame(self) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api._sample_view_frame``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api._sample_view_frame(self)

    def _stats_sync_after_dissolve(self) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api._stats_sync_after_dissolve``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api._stats_sync_after_dissolve(self)

    def set_series_attention(self, series_ids) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api.set_series_attention``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.set_series_attention(self, series_ids)

    def set_rank_provenance(self, source: str | None = None, *, domain: str | None = None) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api.set_rank_provenance``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.set_rank_provenance(self, source=source, domain=domain)

    def set_ranks_visible(self, visible: bool) -> None:
        """Show/hide the rank/BEST pills (delegator to ``grid_api``).

        The controller hides them while a folder is analysing and shows them
        once the ranking is final; the single badge-stamp point blanks the
        card/strip/list pills together.
        """
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.set_ranks_visible(self, visible)

    def refresh_card(self, item: GalleryItem) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api.refresh_card``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.refresh_card(self, item)

    def _refresh_tooltip(self, item: GalleryItem) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api._refresh_tooltip``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api._refresh_tooltip(self, item)

    def _refresh_rebuilt_cards(self, items, *, sweep: bool) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api._refresh_rebuilt_cards``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api._refresh_rebuilt_cards(self, items, sweep=sweep)

    def refresh_cards(self, items) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api.refresh_cards``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.refresh_cards(self, items)

    def sync_source_badge(self, source) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api.sync_source_badge``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.sync_source_badge(self, source)

    def set_card_visible(self, path: Path, visible: bool) -> None:
        """Thin delegator to ``ui/widget_parts.grid_api.set_card_visible``."""
        from tabs.image_gallery.ui.widget_parts import grid_api

        return grid_api.set_card_visible(self, path, visible)

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
        """Thin delegator to ``ui/widget_parts.triage_actions._on_keep_best``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions._on_keep_best(self)

    def _on_show_all(self) -> None:
        """Thin delegator to ``ui/widget_parts.triage_actions._on_show_all``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions._on_show_all(self)

    def _on_clean_rejected(self) -> None:
        """Thin delegator to ``ui/widget_parts.triage_actions._on_clean_rejected``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions._on_clean_rejected(self)

    def _on_compare_finalists(self) -> None:
        """Thin delegator to ``ui/widget_parts.triage_actions._on_compare_finalists``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions._on_compare_finalists(self)

    def _series_view_matches(self, norm_series, prev_mode, prev_source, mode, source) -> bool:
        """Thin delegator to ``ui/widget_parts.triage_actions._series_view_matches``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions._series_view_matches(self, norm_series, prev_mode, prev_source, mode, source)

    def _rebuild_series_view(self, norm_series, hub_names, collapsed) -> None:
        """Thin delegator to ``ui/widget_parts.triage_actions._rebuild_series_view``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions._rebuild_series_view(self, norm_series, hub_names, collapsed)

    def _refresh_action_states(self) -> None:
        """Thin delegator to ``ui/widget_parts.triage_actions._refresh_action_states``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions._refresh_action_states(self)

    def set_triage(self, series, mode, source) -> None:
        """Thin delegator to ``ui/widget_parts.triage_actions.set_triage``."""
        from tabs.image_gallery.ui.widget_parts import triage_actions

        return triage_actions.set_triage(self, series, mode, source)
