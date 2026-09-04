"""Multi-compare tab contract implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS
from tabs.contract import TabContext, TabContract, TabTransitionHint
from tabs.multi_compare.use_cases import persistence
from tabs.multi_compare.use_cases.persistence import _STATE_SLOT

logger = logging.getLogger("ImproveImgSLI")


def _default_state():
    from tabs.multi_compare.models import MultiCompareState

    global _last_session_settings
    if _last_session_settings is None:
        _last_session_settings = _load_last_settings()
    if _last_session_settings is not None:
        divider, label = _last_session_settings
        logger.warning(
            "[divider-color-debug] _default_state: using cached/loaded color_rgba=%s",
            divider.color_rgba,
        )
        return MultiCompareState(divider_settings=divider, label_settings=label)
    logger.warning("[divider-color-debug] _default_state: falling back to built-in default")
    return MultiCompareState()


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
            # Phase2 stale-flush: MC composition may have been deferred.
            try:
                canvas = getattr(self._widget, "canvas", None)
                if canvas is not None and hasattr(canvas, "flush_stale_composition"):
                    # only flush if page is now current (mirrors appearance.py)
                    try:
                        if hasattr(canvas, "is_current_stack_page") and canvas.is_current_stack_page():
                            canvas.flush_stale_composition()
                        elif getattr(canvas, "_composition_stale", False):
                            canvas.flush_stale_composition()
                    except Exception:
                        canvas.flush_stale_composition()
            except Exception:
                pass
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
        from tabs.host_helpers import declare_toolbar_navigation

        self._nav_section = declare_toolbar_navigation(
            self._widget, self._toolbar_rows(), tag="multi-compare"
        )

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
        from ui.actions.binder import resync_action_shortcuts
        from ui.helpers.window_resolver import find_main_window

        window = find_main_window()
        if window is not None:
            resync_action_shortcuts(window, active_tab=self.session_type)

    def _build_settings_contribution(self):  # type: ignore[no-untyped-def]
        from plugins.settings.registry import SettingsContribution

        # No tab-owned settings pages yet — empty but typed contribution.
        return SettingsContribution(owner_tab=self.session_type, sections=(), extras=())

    def create_service(self, service_id: str, *args, **kwargs):
        if service_id == "contribute_settings":
            legacy_registry = args[0] if args else kwargs.get("registry")
            if legacy_registry is not None:
                # Legacy mutate path (no sections)
                return True
            return self._build_settings_contribution()
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
            legacy_registry = args[0] if args else kwargs.get("registry")
            if legacy_registry is not None:
                from tabs.multi_compare.help import contribute_help

                contribute_help(legacy_registry)
                return True
            from tabs.multi_compare.help import build_help_contribution

            return build_help_contribution()
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
                p if isinstance(p, Path) else Path(p) for p in paths
            ]
            image_paths = [
                p for p in image_paths if p.suffix.lower() in _IMAGE_EXTENSIONS
            ]
            if not image_paths:
                return False
            # P3A: load directly like IC instead of arming begin_pending_paste
            # (no click-to-place, no Esc cancel); carry drops carry no canvas
            # position, so placement is auto (load_external_paths).
            if self._controller is not None:
                return bool(self._controller.load_external_paths(image_paths))
            self._widget.images_dropped.emit(
                list(image_paths), (None, False), None
            )
            return True
        if service_id == "toast_anchor_widget":
            if self._widget is None:
                return None
            return self._widget.canvas
        if service_id == "capture_preview_image":
            canvas = self._canvas()
            if canvas is None:
                return None
            try:
                if hasattr(canvas, "grabFramebuffer"):
                    try:
                        canvas.update()
                        from PySide6.QtWidgets import QApplication

                        app = QApplication.instance()
                        if app is not None:
                            app.processEvents()
                    except Exception:
                        pass
                    from PySide6.QtGui import QImage

                    image = canvas.grabFramebuffer()
                    if isinstance(image, QImage) and not image.isNull():
                        return image
                pix = canvas.grab()
                if pix is not None and not pix.isNull():
                    return pix.toImage()
            except Exception:
                return None
            return None
        return None

    def accepts_drop(self, paths: list[Path]) -> bool:
        from tabs.multi_compare.debug import mc_dnd_debug

        mc_dnd_debug("Tab accepts_drop: %d paths", len(paths))
        ok = any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)
        mc_dnd_debug("Tab accepts_drop -> %s", ok)
        return ok

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> None:
        from tabs.multi_compare.debug import mc_dnd_debug

        mc_dnd_debug("Tab handle_drop: ENTER %d paths hint=%r", len(paths), hint)
        if self._widget is None:
            mc_dnd_debug("Tab handle_drop: widget is None -> ignored")
            return
        image_paths = [p for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if not image_paths:
            mc_dnd_debug("Tab handle_drop: no supported image paths -> ignored")
            return
        # P3A: load directly like IC — auto-place via the P2 async path
        # (imageless slot + toast now, preview worker decode). No
        # begin_pending_paste arming, so no click-to-place and no Esc
        # cancel; the chrome/carry hint carries no canvas position and is
        # ignored for placement. Same placement UX as external canvas DnD.
        # P7: this runs synchronously inside the window's
        # acceptProposedAction window (window_event_handler accepts right
        # after route_drop returns), so only the suffix-only verdict stays
        # synchronous — slot/toast/worker-start move past accept via
        # singleShot, otherwise the DnD source holds its busy cursor.
        if self._controller is not None:
            mc_dnd_debug("Tab handle_drop: direct-load %d paths (deferred past accept)", len(image_paths))
            from PySide6.QtCore import QTimer

            controller = self._controller
            deferred = list(image_paths)
            QTimer.singleShot(
                0, lambda: controller.load_external_paths(deferred)
            )
        else:
            mc_dnd_debug("Tab handle_drop: no controller -> images_dropped signal")
            self._widget.images_dropped.emit(list(image_paths), (None, False), None)

    def dispose(self) -> None:
        if self._widget is not None:
            from core.navigation import NavigationManager

            NavigationManager.get_instance().unregister(self._widget)
        self._controller = None
        self._widget = None