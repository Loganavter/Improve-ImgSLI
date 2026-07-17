from __future__ import annotations

import logging

from sli_ui_toolkit.widgets import (
    ContextMenu,
    ContextMenuEntry,
    ContextMenuSeparator,
)

from ui.context_menu.models import ContextMenuProvider, ContextMenuRequest

logger = logging.getLogger("ImproveImgSLI")


class ContextMenuManager:
    """Application-level router for native toolkit context menus."""

    def __init__(self):
        self._providers: list[ContextMenuProvider] = []
        self._active_request: ContextMenuRequest | None = None
        self._active_menu: ContextMenu | None = None
        self._active_key: tuple[object, object] | None = None
        self._ignore_outside_close = False

    def register_provider(self, provider: ContextMenuProvider) -> None:
        if provider not in self._providers:
            self._providers.append(provider)

    def unregister_provider(self, provider: ContextMenuProvider) -> None:
        if provider in self._providers:
            self._providers.remove(provider)

    def entries_for(self, request: ContextMenuRequest) -> tuple[ContextMenuEntry, ...]:
        entries: list[ContextMenuEntry] = []
        for provider in tuple(self._providers):
            try:
                provided = tuple(provider.entries_for(request))
            except Exception:
                logger.exception("context menu provider failed: %s", provider)
                continue
            if not provided:
                continue
            if entries and not isinstance(entries[-1], ContextMenuSeparator):
                entries.append(ContextMenuSeparator())
            entries.extend(provided)
        return tuple(entries)

    def open(self, request: ContextMenuRequest) -> ContextMenu | None:
        entries = self.entries_for(request)
        if not entries:
            return None
        key = (request.source_widget, ("request", request.target.kind, request.target.id))
        return self._open_menu(
            source_widget=request.source_widget,
            global_pos=request.global_pos,
            entries=entries,
            key=key,
            on_triggered=lambda action_id, data: self.execute(action_id, request, data),
            request=request,
        )

    def open_entries(
        self,
        *,
        source_widget,
        global_pos,
        entries: tuple[ContextMenuEntry, ...],
        key: object,
        on_triggered=None,
    ) -> ContextMenu | None:
        if not entries:
            return None
        return self._open_menu(
            source_widget=source_widget,
            global_pos=global_pos,
            entries=entries,
            key=(source_widget, key),
            on_triggered=on_triggered,
            request=None,
        )

    def _open_menu(
        self,
        *,
        source_widget,
        global_pos,
        entries: tuple[ContextMenuEntry, ...],
        key: tuple[object, object],
        on_triggered,
        request: ContextMenuRequest | None,
    ) -> ContextMenu | None:
        active = self._active_menu
        if active is not None and active.isVisible():
            if self._active_key == key:
                active.hide()
                self._clear_active_menu()
                return None
            active.hide()
            self._clear_active_menu()
        self._active_request = request
        self._active_key = key
        # Arm guard before popup_at: popup can process events re-entrantly.
        self._ignore_outside_close = True
        # Right-click menus only: separate Qt popup so they stack above
        # UnifiedFlyout without overlay raise hacks. Button-anchored menus
        # (show_aligned / popup_context_menu_for_anchor) stay in-window.
        menu = ContextMenu(
            source_widget,
            entries=entries,
            on_triggered=on_triggered,
            surface="popup",
        )
        self._active_menu = menu
        menu.aboutToHide.connect(lambda: self._on_menu_hidden(menu))
        menu.popup_at(global_pos)
        self.raise_active_menus()
        return menu

    def _on_menu_hidden(self, menu: ContextMenu) -> None:
        if self._active_menu is menu:
            self._clear_active_menu()

    def _clear_active_menu(self) -> None:
        self._active_menu = None
        self._active_request = None
        self._active_key = None

    def hide_active_menu(self) -> None:
        active = self._active_menu
        if active is not None and active.isVisible():
            active.hide()
        self._clear_active_menu()

    def raise_active_menus(self) -> None:
        """Keep the open context menu (and submenu) above sibling flyouts."""
        active = self._active_menu
        if active is None:
            return
        try:
            if not active.isVisible():
                return
            from PySide6.QtWidgets import QWidget

            QWidget.raise_(active)
            submenu = getattr(active, "_open_submenu", None)
            if submenu is not None and submenu.isVisible():
                QWidget.raise_(submenu)
        except RuntimeError:
            self._clear_active_menu()
        except Exception:
            logger.exception("raise_active_menus failed")

    def hide_active_menu_if_outside(self, global_pos) -> None:
        if self._ignore_outside_close:
            self._ignore_outside_close = False
            return
        if not self.active_menu_contains_global(global_pos):
            self.hide_active_menu()

    def active_menu_contains_global(self, global_pos) -> bool:
        active = self._active_menu
        if active is None or not active.isVisible():
            return False
        try:
            return bool(active.contains_global(global_pos))
        except Exception:
            return False

    def active_menu_has_focus_inside(self, widget) -> bool:
        active = self._active_menu
        if active is None or not active.isVisible() or widget is None:
            return False
        current = widget
        while current is not None:
            if current is active:
                return True
            parent = getattr(current, "parentWidget", None)
            current = parent() if callable(parent) else None
        return False

    def execute(self, action_id: str, request: ContextMenuRequest, data: object = None) -> bool:
        for provider in tuple(self._providers):
            try:
                if provider.execute(action_id, request, data):
                    return True
            except Exception:
                logger.exception(
                    "context menu action failed: action=%s provider=%s",
                    action_id,
                    provider,
                )
        return False


_manager: ContextMenuManager | None = None


def get_context_menu_manager() -> ContextMenuManager:
    global _manager
    if _manager is None:
        _manager = ContextMenuManager()
    return _manager


def open_context_menu(request: ContextMenuRequest) -> ContextMenu | None:
    return get_context_menu_manager().open(request)


def open_context_menu_entries(
    *,
    source_widget,
    global_pos,
    entries: tuple[ContextMenuEntry, ...],
    key: object,
    on_triggered=None,
) -> ContextMenu | None:
    return get_context_menu_manager().open_entries(
        source_widget=source_widget,
        global_pos=global_pos,
        entries=entries,
        key=key,
        on_triggered=on_triggered,
    )


def install_context_menu_provider(provider: ContextMenuProvider) -> ContextMenuProvider:
    get_context_menu_manager().register_provider(provider)
    return provider
