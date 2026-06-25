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
        self._active_request = request
        menu = ContextMenu(
            request.source_widget,
            entries=entries,
            on_triggered=lambda action_id, data: self.execute(action_id, request, data),
        )
        self._active_menu = menu
        menu.popup_at(request.global_pos)
        return menu

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


def install_context_menu_provider(provider: ContextMenuProvider) -> ContextMenuProvider:
    get_context_menu_manager().register_provider(provider)
    return provider
