"""Multi-compare tab contract implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS
from tabs.contract import TabContext, TabContract, TabTransitionHint
from tabs.multi_compare.use_cases import persistence

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareTab(TabContract):
    """Self-contained multi-image comparison tab."""

    def __init__(self):
        self._controller = None
        self._widget = None
        self._active_session_id: str | None = None
        self._nav_section = None

    @property
    def session_type(self) -> str:
        return "multi_compare"

    @property
    def display_name(self) -> str:
        return "Multi Compare"

    @property
    def icon(self) -> QIcon | None:
        from tabs.multi_compare.icons import Icon, get_icon

        return get_icon(Icon.GRID)

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "multi_compare"

    def localized_display_name(self, language: str) -> str:
        from sli_ui_toolkit.i18n import tr

        key = "tab_name"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    def transition_hint(self) -> TabTransitionHint:
        # No cover mask on enter: the WorkspaceTransitionMask overlay blocks
        # the QRhiWidget's first expose/initialize while it covers the stack
        # (measured again 2026-08-09: initialize starts only after the mask
        # force-releases at max_duration -> 400ms blank cover + transition_hint
        # contract-violation error, so the mask just trades one blank window
        # for another). The first-present transparency is instead handled by
        # the canvas's own startup placeholder, which is gated on the genuinely
        # compositor-visible present (#2, see canvas_widget._first_visual_present_count)
        # and hides only after that frame is on screen.
        return TabTransitionHint(cover_on_enter=False)

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        from tabs.multi_compare.controller import MultiCompareController
        from tabs.multi_compare.widget import MultiCompareWidget

        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        def _lang() -> str:
            settings = getattr(context, "settings", None) or getattr(
                getattr(context, "store", None), "settings", None
            )
            return getattr(settings, "current_language", "en") if settings else "en"

        self._widget = MultiCompareWidget(
            page,
            translate=context.tr,
            lang_provider=_lang,
            context=context,
        )
        def open_export_dialog(**kwargs):
            return context.call_service("open_image_export_dialog", **kwargs)

        self._controller = MultiCompareController(
            self._widget,
            store=context.store,
            translate=context.tr,
            dialog_parent=context.main_window or page,
            open_export_dialog=open_export_dialog,
            context=context,
        )
        self._widget.store.subscribe(self._on_widget_state_changed)
        layout.addWidget(self._widget)

        # Session may already be active before the deferred page exists. With
        # the slot authoritative, binding is a re-read, not a replace_state.
        session_id = self._active_session_id or self._resolve_active_session_id(context)
        if session_id is not None:
            self._active_session_id = session_id
            self._widget.refresh_from_session()

        return page

    def apply_host_session_mode(self, ui, session_title: str | None = None) -> bool:
        return True

    def _resolve_active_session_id(self, context: TabContext) -> str | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        if session is None:
            return None
        if getattr(session, "session_type", None) != self.session_type:
            return None
        return getattr(session, "id", None)

    def _on_widget_state_changed(self, action, state) -> None:
        persistence.on_widget_state_changed(self, action, state)

    def on_activated(self, context: TabContext) -> None:
        session_id = self._resolve_active_session_id(context)
        if session_id is not None:
            self.on_active_session_changed(session_id, context)
        if self._widget:
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
            self._widget.setFocus(reason)
        from ui.actions.registry import get_action_registry

        self._register_actions(get_action_registry())

    def _toolbar_rows(self) -> list[QWidget | None]:
        w = self._widget
        if w is None:
            return []
        return [getattr(w, "toolbar", None), getattr(w, "footer", None)]

    def _register_nav_section(self) -> None:
        if self._widget is None:
            return
        from sli_ui_toolkit.managers import declare_toolbar_navigation

        declare_toolbar_navigation(self._widget, self._toolbar_rows(), tag="multi-compare")
        from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

        for owner, sec in NavigationManager.get_instance()._sections:
            if owner is self._widget:
                self._nav_section = sec
                break

    def on_active_session_changed(self, session_id: str, context: TabContext) -> None:
        # The session slot is authoritative; the bound facade re-reads it.
        if self._widget is not None:
            self._active_session_id = session_id
            self._widget.refresh_from_session()
        else:
            self._active_session_id = session_id

    def on_deactivated(self, context: TabContext) -> None:
        if self._widget is not None:
            from core.navigation import NavigationManager

            NavigationManager.get_instance().unregister(self._widget)
        # The slot already holds the session state (written on every dispatch).
        pass

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        persistence.on_session_created(self, session_id, context)

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None

    def serialize_session(self, session_id: str, context: TabContext) -> dict | None:
        return persistence.serialize_session(self, session_id, context)

    def collect_pixel_cache_sources(self, session_id: str, context: TabContext) -> dict:
        return persistence.collect_pixel_cache_sources(self, session_id, context)

    def deserialize_session(self, session_id: str, data: dict, context: TabContext) -> None:
        persistence.deserialize_session(self, session_id, data, context)

    def rehydrate_session(self, session_id: str, context: TabContext) -> None:
        persistence.rehydrate_session(self, session_id, context)

    def register_canvas_features(self) -> None:
        import tabs.multi_compare.canvas.features as features_pkg
        from ui.canvas_infra.scene.registry import register_canvas_feature_package

        register_canvas_feature_package("multi_compare", features_pkg)

    def _canvas(self):
        if self._widget is None:
            return None
        return self._widget.canvas

    def get_canvas_geometry_provider(self):
        if self._widget is None:
            return None
        from tabs.multi_compare.canvas_geometry_provider import (
            MultiCompareCanvasGeometryProvider,
        )

        return MultiCompareCanvasGeometryProvider(self._canvas)

    def apply_appearance(self, host_window) -> None:
        canvas = self._canvas()
        if canvas is None:
            return
        theme_manager = getattr(host_window, "theme_manager", None)
        if theme_manager is None:
            return
        from PySide6.QtGui import QColor

        from ui.theming import resolve_theme_color

        bg = resolve_theme_color(theme_manager, "label.image.background")
        canvas.apply_theme_background(QColor(bg))
        canvas.update()

    def _register_actions(self, registry) -> None:
        if self._widget is None:
            return
        from tabs.multi_compare.actions import register_multi_compare_actions

        register_multi_compare_actions(
            toolbar=getattr(self._widget, "toolbar", None),
            footer=getattr(self._widget, "footer", None),
            registry=registry,
        )
        self._resync_action_shortcuts()

    def _resync_action_shortcuts(self) -> None:
        from PySide6.QtWidgets import QApplication

        from ui.actions.binder import resync_action_shortcuts

        for widget in QApplication.topLevelWidgets():
            if getattr(widget, "presenter", None) is not None:
                resync_action_shortcuts(widget, active_tab=self.session_type)
                return

    def create_service(self, service_id: str, *args, **kwargs):
        if service_id == "contribute_settings":
            # No tab-owned settings pages yet.
            return True
        if service_id == "contribute_actions":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            self._register_actions(registry)
            return True
        if service_id == "contribute_keymap_defaults":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            from tabs.multi_compare.actions import contribute_keymap_defaults

            contribute_keymap_defaults(registry)
            return True
        if service_id == "contribute_help":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            from tabs.multi_compare.help import contribute_help

            contribute_help(registry)
            return True
        if service_id == "clipboard_paste_service":
            if self._controller is None:
                return None
            from tabs.multi_compare.services.clipboard import ClipboardService

            return ClipboardService(*args, controller=self._controller, **kwargs)
        if service_id == "requires_first_run_onboarding":
            return True
        if service_id == "begin_pending_image_insert":
            paths = args[0] if args else kwargs.get("paths")
            if paths is None or self._widget is None:
                return False
            image_paths = [
                p for p in (Path(x) for x in paths) if p.suffix.lower() in _IMAGE_EXTENSIONS
            ]
            if not image_paths:
                return False
            self._widget.begin_pending_paste(image_paths)
            return True
        if service_id == "toast_anchor_widget":
            if self._widget is None:
                return None
            return self._widget.canvas
        return None

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> None:
        if self._widget is None:
            return
        image_paths = [p for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if image_paths:
            # Same placement UX as external DnD / clipboard paste.
            self._widget.begin_pending_paste(image_paths)

    def dispose(self) -> None:
        if self._widget is not None:
            from core.navigation import NavigationManager

            NavigationManager.get_instance().unregister(self._widget)
        self._controller = None
        self._widget = None