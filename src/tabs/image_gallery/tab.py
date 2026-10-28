"""Image Gallery tab contract implementation — Stage 1 browse & dispatch.
Audit-Meta: pattern=thin-owner size=exempt reason="tab contract — lifecycle wiring delegates to controller/widget"
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract, TabTransitionHint
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log

from PySide6.QtCore import QObject

from tabs.image_gallery.use_cases import drag_drop as _drag_drop
from tabs.image_gallery.use_cases import persistence as _persistence
from tabs.image_gallery.use_cases import registration as _registration
from tabs.use_cases.session_state import SessionState


class _ModalLifetimeHideFilter(QObject):
    """Fail-open page-Hide watcher (modal-lifetime W1).

    Explicit page hide (``isHidden()``) means the tab left the visible
    stack — dismiss its modals. Ancestor-driven hides (window minimize:
    ``isHidden()`` False) are ignored. Page-local only: never an app
    filter, no focus calls.
    """

    def __init__(self, on_hidden, parent=None):
        super().__init__(parent)
        self._on_hidden = on_hidden

    def eventFilter(self, watched, event):  # noqa: N802
        try:
            from PySide6.QtCore import QEvent

            if event.type() == QEvent.Type.Hide and watched.isHidden():
                try:
                    self._on_hidden()
                except Exception:
                    pass
        except Exception:
            pass
        return False


# Legacy folder-only slot (pre-Redux sessions) + snapshot version live in
# use_cases.persistence (canonical home); re-exported here so
# ``tabs.image_gallery.tab._LEGACY_STATE_SLOT`` / ``._SERIALIZE_VERSION``
# keep resolving for any dynamic access.
_LEGACY_STATE_SLOT = _persistence._LEGACY_STATE_SLOT
_SERIALIZE_VERSION = _persistence._SERIALIZE_VERSION


def _durable_domain_reader(controller):
    """Reader for the warm-up: the controller's DURABLE judgment domain.

    Goes through ``use_cases.action_context.current_backend`` — the one resolver
    that locates/spells the domain — so the follow-the-domain rule never grows a
    second ad-hoc read. Callable at any time (the timer fires after the session
    restore), and ``None`` when the controller cannot answer yet, which keeps
    the historical "warm on open" behaviour.
    """

    def _read():
        try:
            from tabs.image_gallery.use_cases.action_context import current_backend

            if controller is None:
                return None
            return current_backend(controller)
        except Exception:
            return None

    return _read


class ImageGalleryTab(TabContract):
    """Self-contained folder gallery with on-demand AI tagging (Stage 1)."""

    startup_tier = "deferred"

    def __init__(self):
        self._widget = None
        self._controller = None
        self._active_session_id: str | None = None
        self._nav_section = None
        self._grid_nav_section = None
        self._session_state = SessionState.bind(
            self,
            namespace="image_gallery",
            fields={
                "view_list": (bool, False),
                "judgment_domain": (str, "algorithms"),
                "sort_index": (int, 0),
            },
            apply=self._apply_chrome,
        )

    def _apply_chrome(self, values: dict) -> None:
        widget = self._widget
        if widget is None:
            return
        widget.apply_view_prefs(
            view_list=bool(values.get("view_list", False)),
            judgment_domain=str(values.get("judgment_domain") or "algorithms"),
            sort_index=int(values.get("sort_index", 0) or 0),
        )

    def apply_appearance(self, host_window) -> None:
        """Repaint gallery chrome on a theme flip (host-driven hook).

        The page paints its own background and subscribes to ``theme_changed``
        already; this also re-drives the whole subtree through the toolkit
        contract so a child that only repaints on the *hook* (not the signal)
        still refreshes — mirrors image_compare/multi_compare.
        """
        widget = self._widget
        if widget is None:
            return
        try:
            from sli_ui_toolkit.ui.managers.theme_manager import refresh_theme_subtree

            refresh_theme_subtree(widget)
        except Exception:
            pass
        try:
            widget.update()
        except Exception:
            pass

    @property
    def session_type(self) -> str:
        return "image_gallery"

    @property
    def display_name(self) -> str:
        return "Image Gallery"

    @property
    def icon(self) -> QIcon | None:
        from tabs.image_gallery.icons import Icon, get_icon

        return get_icon(Icon.GALLERY)

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "image_gallery"

    def localized_display_name(self, language: str) -> str:
        from sli_ui_toolkit.i18n import tr

        key = "image_gallery.tab_name"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    def transition_hint(self) -> TabTransitionHint:
        # No cover mask on enter — gallery has no heavy first-frame canvas
        # cost; same choice as image_compare/multi_compare to avoid blocking
        # the compositor on Wayland. See image_compare/tab.py transition_hint
        # comment for the mask-delay rationale.
        return TabTransitionHint(cover_on_enter=False)

    # -- page lifecycle ----------------------------------------------------

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        _dnd_log("create_page: ENTER parent=%s", parent)
        from tabs.image_gallery.controller import GalleryController
        from tabs.image_gallery.widget import ImageGalleryWidget

        self._widget = ImageGalleryWidget(parent, context=context)
        self._controller = GalleryController(
            self._widget,
            thread_pool=getattr(context, "thread_pool", None),
            context=context,
        )
        # One-time background warm-up of the LOCAL detection stack, started when
        # the page is built (a restored session builds it during startup), so
        # the first folder does not pay the ~3 s torch/piq import inside its
        # analysis window (owner log, 2026-10-22). Once per process; a later
        # activation is a no-op; kill-switch IMGSLI_GALLERY_NO_WARMUP=1.
        # The warm-up follows the DURABLE judgment domain (owner 2026-10-27):
        # the tab installs the reader and lets ``schedule_warmup`` ask it at
        # fire time, so a restored ``ai`` session schedules nothing.
        try:
            from PySide6.QtCore import QTimer as _QTimer

            from tabs.image_gallery.services import warmup as _warmup

            _warmup.set_domain_provider(_durable_domain_reader(self._controller))
            _QTimer.singleShot(0, lambda: _warmup.schedule_warmup("page created"))
        except Exception:
            pass

        _dnd_log("create_page: EXIT widget=%s controller=%s", self._widget, self._controller)
        # Explicit owner: the tab wires controller -> widget once via the
        # attach protocol. Implemented by G2 on the widget side —
        # ``attach_controller(controller: GalleryController) -> None``,
        # stored once as the attached ref; no other writes to that ref.
        try:
            self._widget.attach_controller(self._controller)
        except Exception:
            pass

        # If a session was already active before the deferred page was built,
        # restore its folder now (mirrors multi_compare.create_page re-read).
        session_id = self._active_session_id or self._resolve_active_session_id(context)
        if session_id is not None:
            self._active_session_id = session_id
        self._session_state.attach(context)
        self._widget.attach_session_state(self._session_state)
        self._bind_gallery_copies(session_id)
        _persistence.restore_from(self, context, session_id)
        # Series live only in controller memory: a pool restored from the
        # slot comes back FLAT — regroup quietly so returning to a tab
        # restores its sections, not an UNGROUPED pile (no-op when idle
        # pool empty or triage already running).
        self._regroup_restored_pool()

        self._install_modal_lifetime_watch()
        # Register the tab's Find Action rows HERE, not only through the host's
        # `contribute_actions` hook. That hook resolves against the ACTIVE tab
        # and runs once at window setup, when the active session is the session
        # picker — so a tab that relies on it alone never reaches the palette
        # (measured 2026-10-28 on a live lease: 170 actions listed, ZERO
        # `gallery.*`, while the same `register_actions` call in-process
        # registers all six). Image Compare registers after its page is built
        # for the same reason. The widget exists by now, so each descriptor
        # carries a real target, and `ActionRegistry.register` is idempotent
        # (a dict write), so a later host refresh is harmless.
        try:
            from ui.actions.registry import get_action_registry

            _registration.register_actions(self, get_action_registry())
        except Exception:
            pass
        return self._widget

    def _regroup_restored_pool(self) -> None:
        """Kick a quiet regroup of the current mirror (all entry paths)."""
        try:
            ctrl = self._controller
            regroup = getattr(ctrl, "retriage_quiet", None)
            if callable(regroup):
                regroup()
        except Exception:
            pass

    @property
    def widget(self):
        return self._widget

    # -- activation / session wiring ---------------------------------------

    def on_activated(self, context: TabContext) -> None:
        # One-time background warm-up of the LOCAL detection stack: the first
        # folder used to pay a ~3 s torch/piq import inside the analysis window
        # (owner log, 2026-10-22). Off the critical path, once per process,
        # kill-switch IMGSLI_GALLERY_NO_WARMUP=1. The durable domain decides
        # (owner 2026-10-27): an ``ai`` gallery schedules nothing here.
        try:
            from tabs.image_gallery.services import warmup as _warmup

            if self._controller is not None:
                _warmup.set_domain_provider(_durable_domain_reader(self._controller))
            _warmup.schedule_warmup("gallery tab activated")
        except Exception:
            pass

        session_id = self._resolve_active_session_id(context)
        if session_id is not None:
            if session_id != self._active_session_id:
                self.on_active_session_changed(session_id, context)
            else:
                # Same session, but emits were skipped while inactive —
                # refresh from the OWN slot (Wave ISO activation refresh).
                self._refresh_active_gallery_slot(context, session_id)
        if self._widget is not None:
            self._register_nav_section()
            from PySide6.QtCore import Qt

            try:
                from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

                # Ring modality from the manager (never a literal reason) so a
                # keyboard-driven activation shows the ring and a mouse-driven
                # one does not.
                reason = NavigationManager.get_instance().current_focus_reason()
            except Exception:
                reason = Qt.FocusReason.OtherFocusReason
            try:
                self._widget.setFocus(reason)
            except Exception:
                pass

    def _toolbar_rows(self) -> list[QWidget | None]:
        w = self._widget
        if w is None:
            return []
        # CONTAINER rows, not bare controls: ToolbarRowsSection clusters each
        # row's StrongFocus descendants by y, so a bare control (a single
        # widget with no focusable children) is an INERT row — focus_first/
        # focus_last return False and Up/Down never leave the filter. The
        # toolbar container holds filter + pick + sort/view/domain controls;
        # the stats strip is the second row. Cards live in the grid, which is
        # its own registered section (``_register_nav_section``), so this
        # section never claims them.
        return [
            getattr(w, "toolbar", None),
            getattr(w, "stats_strip", None),
        ]

    def _register_nav_section(self) -> None:
        if self._widget is None:
            return
        try:
            from tabs.host_helpers import declare_toolbar_navigation

            self._nav_section = declare_toolbar_navigation(
                self._widget,
                self._toolbar_rows(),
                tag="image-gallery",
            )
        except Exception:
            pass
        # Grid section — registered AFTER the toolbar so NavigationManager's
        # trial-dispatch neighbours are toolbar (above) and grid (below): Up at
        # the first row hands off to the toolbar, Down from the toolbar enters
        # the first card.
        try:
            grid_view = getattr(self._widget, "_grid_view", None)
            section = getattr(grid_view, "nav_section", None)
            if grid_view is not None and section is not None:
                from sli_ui_toolkit.managers import NavigationManager

                NavigationManager.get_instance().register(grid_view, section)
                self._grid_nav_section = section
        except Exception:
            pass

    def on_active_session_changed(self, session_id: str, context: TabContext) -> None:
        if session_id == self._active_session_id:
            return
        # No snapshot: the ``gallery`` slot is already current — every pool /
        # selection / filter / triage mutation dispatches synchronously, so
        # there is no controller-local truth left to flush.
        self._active_session_id = session_id
        # Session isolation (Wave ISO): the single live copy now serves the
        # new session — rebind BEFORE restoring so slot reads address it.
        self._bind_gallery_copies(session_id)
        _persistence.restore_from(self, context, session_id)
        # Same regroup as the activation path: a restored pool comes back
        # FLAT (series live only in controller memory). Gallery→gallery
        # switches land here, not in on_activated.
        self._regroup_restored_pool()

    def _bind_gallery_copies(self, session_id: str) -> None:
        """Bind both live copies (controller + widget) to their OWN session.

        The ONLY writer of ``_gallery_session_id`` outside construction —
        slot reads never re-resolve per read (Wave ISO frozen seam).
        """
        for owner in (self._controller, self._widget):
            try:
                bind = getattr(owner, "bind_gallery_session", None)
                if callable(bind):
                    bind(session_id)
            except Exception:
                pass

    def _refresh_active_gallery_slot(self, context: TabContext, session_id: str) -> None:
        """Re-render the live copy from its OWN slot on (re)activation.

        Emits arriving while this copy was inactive were skipped by the
        is-active gate, so the mirror may be stale — restore re-syncs it
        (no-op when already current). Rebinds first so a page built while
        inactive still addresses the right session.
        """
        self._bind_gallery_copies(session_id)
        _persistence.restore_from(self, context, session_id)
        self._regroup_restored_pool()

    def on_deactivated(self, context: TabContext) -> None:
        if self._widget is not None:
            try:
                from core.navigation import NavigationManager

                grid_view = getattr(self._widget, "_grid_view", None)
                if grid_view is not None:
                    NavigationManager.get_instance().unregister(grid_view)
                NavigationManager.get_instance().unregister(self._widget)
            except Exception:
                pass
            self._grid_nav_section = None
        # No snapshot (see on_active_session_changed): slot is authoritative.
        self._dismiss_tab_modals()

    def _dismiss_tab_modals(self) -> None:
        """Modal-lifetime (W1): QuickLook/CleanReview must not outlive the tab."""
        try:
            if self._widget is None:
                return
            from tabs.image_gallery.use_cases import triage_ui

            triage_ui.dismiss_gallery_modals(self._widget)
        except Exception:
            pass

    def _install_modal_lifetime_watch(self) -> None:
        """Watch explicit page hides (stack switches bypassing lifecycle)."""
        try:
            if self._widget is None:
                return
            if getattr(self._widget, "_modal_lifetime_watch", None) is not None:
                return
            filt = _ModalLifetimeHideFilter(self._dismiss_tab_modals, self._widget)
            self._widget.installEventFilter(filt)
            self._widget._modal_lifetime_watch = filt  # type: ignore[attr-defined]
        except Exception:
            pass

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        # Slot is auto-allocated by SessionBlueprint.state_slots; a NEW session
        # inherits the last-used toolbar chrome (QSettings) so it does not
        # reset the switches.
        self._session_state.seed_slot(context, session_id)

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None
        self._dismiss_tab_modals()
        # Session-isolation contract: when no gallery session remains active
        # (last one closed), drop the stale view instead of showing the
        # closed session's pool with no session behind it. Guarded on the
        # live active session (not the closed id) so a close→switch ordering
        # never wipes the newly activated session — its own restore follows.
        try:
            store = getattr(context, "store", None)
            active = (
                store.get_active_workspace_session() if store is not None else None
            )
            if active is None or getattr(active, "session_type", None) != self.session_type:
                if self._controller is not None:
                    self._controller.clear_to_empty()
        except Exception:
            pass

    def _resolve_active_session_id(self, context: TabContext) -> str | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        if session is None or getattr(session, "session_type", None) != self.session_type:
            return None
        return getattr(session, "id", None)

    # -- snapshot / restore + project persistence ------------------------------
    # Bodies live in use_cases.persistence (thin delegates below); the
    # ``gallery`` slot stays the single source of truth there.

    def serialize_session(self, session_id: str, context: TabContext) -> dict | None:
        return _persistence.serialize_session(self, session_id, context)

    def deserialize_session(self, session_id: str, data: dict, context: TabContext) -> None:
        return _persistence.deserialize_session(self, session_id, data, context)

    def duplicate_session(self, source_session_id: str, context: TabContext) -> dict | None:
        return _persistence.duplicate_session(self, source_session_id, context)

    def rehydrate_session(self, session_id: str, context: TabContext) -> None:
        return _persistence.rehydrate_session(self, session_id, context)

    # -- drag & drop -------------------------------------------------------

    def accepts_drop(self, paths: list[Path]) -> bool:
        return _drag_drop.accepts_drop(paths)

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> bool:
        return _drag_drop.handle_drop(self, paths, hint)

    # -- services / cleanup ------------------------------------------------

    def create_service(self, service_id: str, *args, **kwargs):
        # Thin delegates (G4): bodies live in use_cases.registration —
        # mirrors image_compare/service_factory.py thin shape.
        if service_id == "topology_overlays":
            return _registration.build_topology_overlays(self, args[0] if args else kwargs.get("parent"))
        if service_id == "clipboard_paste_service":
            return _registration.build_clipboard_service(
                self,
                args[0] if args else kwargs.get("store"),
                args[1] if len(args) > 1 else kwargs.get("main_controller"),
            )
        if service_id == "contribute_settings":
            legacy_registry = args[0] if args else kwargs.get("registry")
            if legacy_registry is not None:
                _registration.register_settings(self, legacy_registry)
                return True
            return _registration.build_settings_contribution(self)
        if service_id == "contribute_actions":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            return _registration.register_actions(self, registry)
        if service_id == "contribute_help":
            from tabs.image_gallery.help import build_help_hub_contribution

            return build_help_hub_contribution()
        return None

    def dispose(self) -> None:
        if self._widget is not None:
            try:
                from core.navigation import NavigationManager

                grid_view = getattr(self._widget, "_grid_view", None)
                if grid_view is not None:
                    NavigationManager.get_instance().unregister(grid_view)
                NavigationManager.get_instance().unregister(self._widget)
            except Exception:
                pass
        self._controller = None
        self._widget = None
        self._active_session_id = None
        self._grid_nav_section = None
