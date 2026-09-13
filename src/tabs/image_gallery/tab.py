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

logger = logging.getLogger("ImproveImgSLI")


_STATE_SLOT = "image_gallery.state"


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
        self._snapshot_into(context, self._active_session_id)
        self._active_session_id = session_id
        self._restore_from(context, session_id)

    def on_deactivated(self, context: TabContext) -> None:
        if self._widget is not None:
            try:
                from core.navigation import NavigationManager

                NavigationManager.get_instance().unregister(self._widget)
            except Exception:
                pass
        self._snapshot_into(context, self._active_session_id)

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        # Slot is auto-allocated by SessionBlueprint.state_slots; nothing to do.
        return

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None

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

    def _resolve_saved_folder(self, context: TabContext) -> Path | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        session = context.get_active_session()
        if session is None or getattr(session, "session_type", None) != self.session_type:
            return None
        saved = session.state_slots.get(_STATE_SLOT) if hasattr(session, "state_slots") else None
        if not saved:
            return None
        raw = saved.get("folder")
        return Path(raw) if raw else None

    # -- snapshot / restore ------------------------------------------------

    def _snapshot_into(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None or self._controller is None:
            return
        store = getattr(context, "store", None)
        if store is None or not hasattr(store, "set_session_state_slot"):
            return
        folder = getattr(getattr(self._controller, "state", None), "folder", None)
        try:
            store.set_session_state_slot(
                _STATE_SLOT,
                {"folder": str(folder) if folder else None},
                session_id=session_id,
                emit_scope=None,
            )
        except Exception:
            pass

    def _restore_from(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None or self._controller is None:
            return
        store = getattr(context, "store", None)
        if store is None:
            return
        saved = None
        try:
            if hasattr(store, "ensure_session_state_slot"):
                saved = store.ensure_session_state_slot(
                    _STATE_SLOT, session_id=session_id, factory=lambda: {"folder": None}
                )
            else:
                session = store.get_workspace_session(session_id) if hasattr(store, "get_workspace_session") else None
                if session is not None and hasattr(session, "state_slots"):
                    saved = session.state_slots.get(_STATE_SLOT)
        except Exception:
            return
        if not saved:
            return
        raw = saved.get("folder")
        if not raw:
            return
        folder = Path(raw)
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
        if session_id == self._active_session_id:
            self._snapshot_into(context, session_id)
            try:
                session = store.get_workspace_session(session_id) or session
            except Exception:
                pass
        slot = session.state_slots.get(_STATE_SLOT) if hasattr(session, "state_slots") else None
        if slot is None:
            folder = getattr(getattr(self._controller, "state", None), "folder", None) if self._controller else None
            return {"version": 1, "folder": str(folder) if folder else None}
        return {"version": 1, "folder": slot.get("folder")}

    def deserialize_session(self, session_id: str, data: dict, context: TabContext) -> None:
        store = getattr(context, "store", None)
        if store is None or not data:
            return
        try:
            store.set_session_state_slot(_STATE_SLOT, dict(data), session_id=session_id, emit_scope=None)
        except Exception:
            pass
        # If this session is currently visible, apply folder immediately.
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
        # Folder contents are re-scanned from disk; nothing to decode beyond restore.
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
                # set-as-source
                def _set_as_source():
                    try:
                        sel = None
                        if ctrl is not None and hasattr(ctrl.state, "selected_paths"):
                            sel = next(iter(ctrl.state.selected_paths), None)
                        if sel is not None:
                            ctrl.state.source_path = sel  # type: ignore[attr-defined]
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
