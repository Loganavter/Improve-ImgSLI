"""Image Gallery tab contract implementation — Stage 1 browse & dispatch.
Audit-Meta: pattern=thin-owner size=exempt reason="tab contract — lifecycle wiring delegates to controller/widget"
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS
from tabs.contract import TabContext, TabContract, TabTransitionHint
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log

from PySide6.QtCore import QObject

from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.state.models import (
    GalleryItemMeta,
    GallerySlotState,
    fresh_gallery_slot_state,
)

logger = logging.getLogger("ImproveImgSLI")


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


# Legacy folder-only slot (pre-Redux sessions). Read-only fallback for
# foreign/legacy restores — never written; the ``gallery`` slot above is
# the single source of truth.
_LEGACY_STATE_SLOT = "image_gallery.state"

_SERIALIZE_VERSION = 2


class ImageGalleryTab(TabContract):
    """Self-contained folder gallery with on-demand AI tagging (Stage 1)."""

    startup_tier = "deferred"

    def __init__(self):
        self._widget = None
        self._controller = None
        self._active_session_id: str | None = None
        self._nav_section = None

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
        _dnd_log("create_page: EXIT widget=%s controller=%s", self._widget, self._controller)
        # Allow widget DnD to open folder directly without extra signal round-trip
        try:
            self._widget._controller = self._controller  # type: ignore[attr-defined]
        except Exception:
            pass

        # If a session was already active before the deferred page was built,
        # restore its folder now (mirrors multi_compare.create_page re-read).
        session_id = self._active_session_id or self._resolve_active_session_id(context)
        if session_id is not None:
            self._active_session_id = session_id
            self._restore_from(context, session_id)

        self._install_modal_lifetime_watch()
        return self._widget

    @property
    def widget(self):
        return self._widget

    # -- activation / session wiring ---------------------------------------

    def on_activated(self, context: TabContext) -> None:
        session_id = self._resolve_active_session_id(context)
        if session_id is not None:
            self.on_active_session_changed(session_id, context)
        if self._widget is not None:
            self._register_nav_section()
            from PySide6.QtCore import Qt

            try:
                from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

                reason = (
                    Qt.FocusReason.OtherFocusReason
                    if NavigationManager.get_instance().last_input_was_keyboard()
                    else Qt.FocusReason.MouseFocusReason
                )
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
        # Gallery toolbar is inside the widget; expose it if present, else the
        # widget itself as a single focus row.
        toolbar = getattr(w, "_pick_button", None)
        # Return widget-level rows for host navigation manager.
        return [getattr(w, "_filter_edit", None), toolbar, w]

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

    def on_active_session_changed(self, session_id: str, context: TabContext) -> None:
        if session_id == self._active_session_id:
            return
        # No snapshot: the ``gallery`` slot is already current — every pool /
        # selection / filter / triage mutation dispatches synchronously, so
        # there is no controller-local truth left to flush.
        self._active_session_id = session_id
        self._restore_from(context, session_id)

    def on_deactivated(self, context: TabContext) -> None:
        if self._widget is not None:
            try:
                from core.navigation import NavigationManager

                NavigationManager.get_instance().unregister(self._widget)
            except Exception:
                pass
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
        # Slot is auto-allocated by SessionBlueprint.state_slots; nothing to do.
        return

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None
        self._dismiss_tab_modals()

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

    # -- snapshot / restore ------------------------------------------------
    #
    # The ``gallery`` session slot (GallerySlotState) is the single source of
    # truth: pool membership, selection, filter, folder and triage summary.
    # Restore rebuilds the controller mirror from the slot WITHOUT rescanning
    # the disk when the slot carries pool data; a disk rescan happens only
    # for empty/absent/foreign slots (legacy sessions).

    def _restore_from(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None or self._controller is None:
            return
        store = getattr(context, "store", None)
        if store is None:
            return
        try:
            slot = store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=session_id)
        except Exception:
            slot = None
        if isinstance(slot, GallerySlotState) and slot.items:
            # Pool data present — rebuild the mirror from the slot, no rescan.
            # The controller resolves the slot via the *active* session, so
            # only sync when this session is the active one; otherwise the
            # slot persists untouched and activation restores it.
            try:
                active = store.get_active_workspace_session()
                active_id = getattr(active, "id", None)
            except Exception:
                active_id = None
            if active_id is not None and active_id != session_id:
                return
            try:
                self._controller._sync_from_slot()
            except Exception:
                logger.debug("ImageGalleryTab slot restore failed", exc_info=True)
            return
        # Empty / absent / foreign slot — legacy rescan path. Folder comes
        # from the (possibly empty) slot, else the legacy folder-only slot.
        folder_raw = slot.folder if isinstance(slot, GallerySlotState) else None
        if not folder_raw and isinstance(slot, dict):
            folder_raw = slot.get("folder")
        if not folder_raw:
            try:
                legacy = store.get_session_state_slot(_LEGACY_STATE_SLOT, session_id=session_id)
            except Exception:
                legacy = None
            if isinstance(legacy, dict):
                folder_raw = legacy.get("folder")
        if not folder_raw:
            return
        folder = Path(folder_raw)
        if folder.is_dir():
            try:
                self._controller.open_folder(folder)
            except Exception:
                logger.debug("ImageGalleryTab restore failed for %s", folder, exc_info=True)

    # -- project persistence -----------------------------------------------

    def serialize_session(self, session_id: str, context: TabContext) -> dict | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        try:
            session = store.get_workspace_session(session_id)
        except Exception:
            return None
        if session is None or getattr(session, "session_type", None) != self.session_type:
            return None
        # No snapshot: the slot is already current (dispatch-only mutation).
        try:
            slot = store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=session_id)
        except Exception:
            slot = None
        if isinstance(slot, GallerySlotState):
            return {
                "version": _SERIALIZE_VERSION,
                "folder": slot.folder,
                "filter_text": slot.filter_text,
                "selection": list(slot.selection),
                "triage_state": slot.triage_state,
                "mode": slot.mode,
                "source_path": slot.source_path,
                "items": [
                    {
                        "path": it.path,
                        "mtime_ns": it.mtime_ns,
                        "status": it.status,
                        "rank": it.rank,
                    }
                    for it in slot.items
                ],
            }
        # Foreign/legacy slot value — persist whatever folder we can find.
        folder = slot.get("folder") if isinstance(slot, dict) else None
        if folder is None:
            try:
                legacy = store.get_session_state_slot(_LEGACY_STATE_SLOT, session_id=session_id)
            except Exception:
                legacy = None
            if isinstance(legacy, dict):
                folder = legacy.get("folder")
        if folder is None and self._controller is not None:
            ctrl_folder = getattr(getattr(self._controller, "state", None), "folder", None)
            folder = str(ctrl_folder) if ctrl_folder else None
        return {"version": 1, "folder": folder}

    def deserialize_session(self, session_id: str, data: dict, context: TabContext) -> None:
        store = getattr(context, "store", None)
        if store is None or not data:
            return
        if data.get("version", 1) >= _SERIALIZE_VERSION and data.get("items") is not None:
            items = []
            for e in data.get("items") or []:
                if not isinstance(e, dict):
                    continue
                try:
                    items.append(
                        GalleryItemMeta(
                            path=str(e.get("path", "")),
                            mtime_ns=int(e.get("mtime_ns", 0) or 0),
                            status=str(e.get("status", "not_loaded") or "not_loaded"),
                            rank=e.get("rank") if e.get("rank") is None else int(e.get("rank")),
                        )
                    )
                except Exception:
                    continue
            state = GallerySlotState(
                items=items,
                selection=[str(s) for s in (data.get("selection") or [])],
                filter_text=str(data.get("filter_text") or ""),
                folder=data.get("folder"),
                triage_state=str(data.get("triage_state") or "idle"),
                mode=data.get("mode"),
                source_path=data.get("source_path"),
            )
        else:
            # Legacy v1 (folder only): empty pool forces a rescan on restore.
            state = fresh_gallery_slot_state()
            state.folder = data.get("folder")
        try:
            store.set_session_state_slot(GALLERY_SLOT_NAME, state, session_id=session_id, emit_scope=None)
        except Exception:
            pass
        # If this session is currently visible, rebuild from the slot now.
        active = None
        try:
            getter = getattr(store, "get_active_workspace_session", None)
            if callable(getter):
                active = getter()
        except Exception:
            active = None
        if session_id == self._active_session_id or (active is not None and getattr(active, "id", None) == session_id):
            self._restore_from(context, session_id)

    def duplicate_session(self, source_session_id: str, context: TabContext) -> dict | None:
        return self.serialize_session(source_session_id, context)

    def rehydrate_session(self, session_id: str, context: TabContext) -> None:
        # Pool data lives in the slot — restore rebuilds from it without a
        # disk rescan; only empty/legacy slots rescan.
        self._restore_from(context, session_id)

    # -- drag & drop -------------------------------------------------------

    def accepts_drop(self, paths: list[Path]) -> bool:
        _dnd_log("accepts_drop: %d paths %r", len(paths), paths[:3])
        # Accept both image files and directories (for folder triage) — fixes folder DnD
        for p in paths:
            pp = Path(p)
            try:
                ok = pp.suffix.lower() in _IMAGE_EXTENSIONS or pp.is_dir()
            except Exception:
                ok = False
            _dnd_log("  accepts_drop check %s suffix=%s is_dir=%s -> %s", p, pp.suffix.lower(), pp.is_dir() if p.exists() else "?", ok)
            if ok:
                return True
            # also accept url string that may be dir without suffix
            try:
                if Path(str(p)).is_dir():
                    return True
            except Exception:
                pass
        return False

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> bool:
        _dnd_log("handle_drop: ENTER %d paths %r hint=%r", len(paths), paths[:5], hint)
        if self._widget is None or self._controller is None:
            _dnd_log("handle_drop: no widget/controller -> False")
            return False
        _dnd_log("handle_drop: %d paths %r", len(paths), paths[:5])
        for p in paths[:5]:
            try:
                _dnd_log("  handle_drop path %s exists=%s is_file=%s is_dir=%s suffix=%s", p, p.exists(), p.is_file(), p.is_dir(), p.suffix.lower())
            except Exception:
                pass
        # Accept if at least one path is a supported image or a directory.
        accepted = [Path(p) for p in paths if Path(p).suffix.lower() in _IMAGE_EXTENSIONS or Path(p).is_dir()]
        if not accepted:
            if not self.accepts_drop([Path(p) for p in paths]):
                _dbg("handle_drop: no accepted paths")
                return False
            accepted = [Path(p) for p in paths if Path(p).suffix.lower() in _IMAGE_EXTENSIONS]
            if not accepted:
                return False
        # If all dropped are image files (single or multiple), open just them — don't scan parent
        try:
            all_files = all(p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS for p in accepted if p.exists()) and any(
                p.is_file() for p in accepted
            )
            has_dir = any(p.is_dir() for p in accepted)
        except Exception:
            all_files = False
            has_dir = False
        if all_files and not has_dir:
            _dbg("handle_drop: single/multi image %d -> open_paths", len(accepted))
            try:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, lambda ps=list(accepted): self._controller.open_paths(ps))
                return True
            except Exception:
                try:
                    self._controller.open_paths(list(accepted))
                    return True
                except Exception:
                    _dbg("open_paths failed", exc_info=True)
                    return False
        # Prefer a dropped directory; otherwise open the parent of the first image.
        folder: Path | None = None
        for p in accepted:
            if p.is_dir():
                folder = p
                break
        if folder is None:
            first = accepted[0]
            folder = first.parent if first.is_file() or first.suffix else first.parent
        if folder is None or not folder.is_dir():
            _dbg("handle_drop: no folder found")
            return False
        _dbg("handle_drop: folder %s", folder)
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda f=folder: self._controller.open_folder(f))
        except Exception:
            try:
                self._controller.open_folder(folder)
            except Exception:
                _dbg("open_folder failed", exc_info=True)
                return False
        return True

    # -- services / cleanup ------------------------------------------------

    def create_service(self, service_id: str, *args, **kwargs):
        if service_id == "topology_overlays":
            # Topology conformity hook: build + show this tab's
            # grandfathered window-parented modals, return them as a list.
            # Fail-open: no parent means no overlay.
            parent = args[0] if args else kwargs.get("parent")
            if parent is None:
                return []
            from tabs.image_gallery.ui.clean_review import CleanReviewOverlay
            from tabs.image_gallery.ui.quick_look import QuickLookOverlay

            overlays = [QuickLookOverlay(parent), CleanReviewOverlay(parent)]
            for overlay in overlays:
                overlay.show_overlay()
            return overlays
        if service_id == "clipboard_paste_service":
            if self._controller is None:
                return None
            from tabs.image_gallery.services.clipboard import ClipboardService

            store = args[0] if args else kwargs.get("store")
            main_controller = args[1] if len(args) > 1 else kwargs.get("main_controller")
            return ClipboardService(store, main_controller, self._controller)
        if service_id == "contribute_settings":
            legacy_registry = args[0] if args else kwargs.get("registry")
            if legacy_registry is not None:
                from tabs.image_gallery.use_cases.registration import register_settings

                register_settings(self, legacy_registry)
                return True
            from tabs.image_gallery.use_cases.registration import build_settings_contribution

            return build_settings_contribution(self)
        if service_id == "contribute_actions":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            # Find Action ids stubs: gallery.keep-best-of-series etc (design.md:129).
            # Thin delegation to use_cases/triage; widget handles keyPressEvent too.
            # Register real descriptors when a page exists; otherwise stubs.
            try:
                from tabs.image_gallery.actions import (
                    GALLERY_CLEAN_REJECTED,
                    GALLERY_KEEP_BEST,
                    GALLERY_RUN_TRIAGE,
                    GALLERY_SET_AS_SOURCE,
                )
                from core.actions.types import ActionDescriptor, ActionTarget

                # Helper to get controller/widget if available.
                ctrl = self._controller
                wid = self._widget
                # keep-best
                registry.register(
                    ActionDescriptor(
                        action_id=GALLERY_KEEP_BEST,
                        label_key="image_gallery.action.keep_best",
                        description_key="image_gallery.action.keep_best_desc",
                        breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                        owner_tab=self.session_type,
                        topic="triage",
                        shortcut=None,
                        help_page=None,
                        run=lambda: getattr(ctrl, "keep_best_of_series", lambda: None)(),
                        target=ActionTarget(widget=wid) if wid is not None else None,
                    )
                )
                # clean-rejected → open S3 overlay
                registry.register(
                    ActionDescriptor(
                        action_id=GALLERY_CLEAN_REJECTED,
                        label_key="image_gallery.action.clean_rejected",
                        description_key="image_gallery.action.clean_rejected_desc",
                        breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                        owner_tab=self.session_type,
                        topic="triage",
                        shortcut=None,
                        help_page=None,
                        run=lambda: getattr(ctrl, "show_clean_review", lambda: None)(),
                        target=ActionTarget(widget=wid) if wid is not None else None,
                    )
                )
                # run-triage → reopen folder (rerun clustering)
                def _run_triage():
                    try:
                        if ctrl is not None and getattr(ctrl.state, "folder", None) is not None:
                            ctrl.open_folder(ctrl.state.folder)
                    except Exception:
                        pass

                registry.register(
                    ActionDescriptor(
                        action_id=GALLERY_RUN_TRIAGE,
                        label_key="image_gallery.action.run_triage",
                        description_key=None,
                        breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                        owner_tab=self.session_type,
                        topic="triage",
                        shortcut=None,
                        help_page=None,
                        run=_run_triage,
                        target=ActionTarget(widget=wid) if wid is not None else None,
                    )
                )
                # set-as-source — same hooks path as the overlay setSource
                # signal and the card context menu: stale-keys + fidelity
                # re-run (never a bare state write; action id/UX unchanged).
                def _set_as_source():
                    try:
                        sel = None
                        if ctrl is not None and hasattr(ctrl.state, "selected_paths"):
                            sel = next(iter(ctrl.state.selected_paths), None)
                        if sel is None:
                            return
                        try:
                            from tabs.image_gallery.ui.quick_look_hooks import (
                                on_quick_set_source as _ql_set_source,
                            )

                            owner = wid if wid is not None else ctrl
                            _ql_set_source(owner, sel)
                        except Exception:
                            # Fallback: preserve the legacy direct write.
                            try:
                                ctrl.state.source_path = sel  # type: ignore[attr-defined]
                            except Exception:
                                pass
                    except Exception:
                        pass

                registry.register(
                    ActionDescriptor(
                        action_id=GALLERY_SET_AS_SOURCE,
                        label_key="image_gallery.action.set_as_source",
                        description_key=None,
                        breadcrumb=("image_gallery.action.breadcrumb.triage", "Image Gallery"),
                        owner_tab=self.session_type,
                        topic="triage",
                        shortcut=None,
                        help_page=None,
                        run=_set_as_source,
                        target=ActionTarget(widget=wid) if wid is not None else None,
                    )
                )
                return True
            except Exception:
                # Fallback: ensure stubs exist via actions helper.
                try:
                    from tabs.image_gallery.actions import register_gallery_action_stubs

                    register_gallery_action_stubs(registry)
                    return True
                except Exception:
                    return None
        return None

    def dispose(self) -> None:
        if self._widget is not None:
            try:
                from core.navigation import NavigationManager

                NavigationManager.get_instance().unregister(self._widget)
            except Exception:
                pass
        self._controller = None
        self._widget = None
        self._active_session_id = None
