from __future__ import annotations

import logging
from typing import Literal

from sli_ui_toolkit.widgets import (
    ContextMenu,
    ContextMenuEntry,
    ContextMenuSeparator,
)

from ui.context_menu.models import ContextMenuProvider, ContextMenuRequest
from ui.host_debug import ctx_menu_debug

logger = logging.getLogger("ImproveImgSLI")

ContextMenuSurface = Literal["in_window", "popup"]


def rmb_context_menu_surface() -> ContextMenuSurface:
    """Surface for right-click menus opened via ``ContextMenuManager``.

    Always ``"in_window"``: RMB menus are in-window overlay children. A native
    ``Qt.Popup`` top-level tears down its ``xdg_popup`` surface on close; a
    widget shown right after that teardown (e.g. the Ask AI flyout opened from
    a context-menu action) hits Mutter's stale/zero xdg-activation serial and
    flashes the global busy cursor for several frames. In-window menus have no
    native popup surface to tear down, so the sequenced close→open stays clean.
    (The old in-window→popup change was made for stacking above UnifiedFlyout;
    the in-window overlay keeps that via ``ensure_overlay_stacking``.) The
    multi-compare ``IMGSLI_MC_RMB_SURFACE`` env override still allows forcing
    ``popup`` for A/B debugging.
    """
    return "in_window"


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
        active = self._live_active_menu()
        if active is not None and active.isVisible():
            if self._active_key == key:
                ctx_menu_debug("reopen same key=%r -> toggle hide", key)
                active.hide()
                self._clear_active_menu()
                return None
            ctx_menu_debug(
                "reopen other key=%r (was %r) -> replace",
                key,
                self._active_key,
            )
            active.hide()
            self._clear_active_menu()
        self._active_request = request
        self._active_key = key
        self._ignore_outside_close = True
        surface = (
            request.surface
            if request is not None and request.surface is not None
            else rmb_context_menu_surface()
        )
        menu_parent = source_widget
        if request is not None and request.menu_parent is not None:
            menu_parent = request.menu_parent
        menu = ContextMenu(
            menu_parent,
            entries=entries,
            on_triggered=on_triggered,
            surface=surface,
        )
        self._active_menu = menu
        menu.aboutToHide.connect(lambda: self._on_menu_hidden(menu))
        try:
            from ui.canvas_infra.rhi.rhi_focus import park_keyboard_focus_off_qrhi

            park_keyboard_focus_off_qrhi()
        except Exception:
            pass
        try:
            action_ids = [
                getattr(e, "action_id", "?")
                for e in entries
                if hasattr(e, "action_id")
            ]
        except Exception:
            action_ids = ["<unreadable>"]
        ctx_menu_debug(
            "open key=%r surface=%s pos=%s actions=%s",
            key[1],
            surface,
            global_pos,
            action_ids,
        )
        menu.popup_at(global_pos)
        self.raise_active_menus()
        return menu

    def _on_menu_hidden(self, menu: ContextMenu) -> None:
        ctx_menu_debug("hidden key=%r", self._active_key)
        if self._active_menu is menu:
            self._clear_active_menu()

    def _live_active_menu(self) -> ContextMenu | None:
        """Return the tracked active menu, or ``None`` when it is already gone.

        The popup is parented to its source widget (card / series header /
        canvas). A rebuild that destroys that widget deletes the popup's C++
        object while this singleton still holds the Python wrapper — every
        later ``isVisible()`` / ``hide()`` / attribute access on the dead
        wrapper raises ``RuntimeError: ... already deleted``. Detect it here
        and drop the stale ref so callers only ever see a live menu.
        """
        active = self._active_menu
        if active is None:
            return None
        try:
            import shiboken6

            if not shiboken6.isValid(active):
                self._clear_active_menu()
                return None
        except Exception:
            # isValid itself is best-effort; callers keep their own guards.
            pass
        return active

    def _clear_active_menu(self) -> None:
        self._active_menu = None
        self._active_request = None
        self._active_key = None

    def hide_active_menu(self) -> None:
        active = self._live_active_menu()
        ctx_menu_debug(
            "hide_active key=%r visible=%s",
            self._active_key,
            bool(active is not None and active.isVisible()),
        )
        if active is not None and active.isVisible():
            active.hide()
        self._clear_active_menu()

    def raise_active_menus(self) -> None:
        """Keep the open context menu (and submenu) above sibling flyouts."""
        active = self._live_active_menu()
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
            ctx_menu_debug(
                "outside-close skipped pos=%s (open-click grace)",
                global_pos,
            )
            self._ignore_outside_close = False
            return
        inside = self.active_menu_contains_global(global_pos)
        live = self._live_active_menu()
        submenu_open = bool(getattr(live, "_open_submenu", None) is not None)
        ctx_menu_debug(
            "outside-close check pos=%s inside=%s submenu_open=%s",
            global_pos,
            inside,
            submenu_open,
        )
        if not inside:
            self.hide_active_menu()

    def active_menu_contains_global(self, global_pos) -> bool:
        active = self._live_active_menu()
        if active is None or not active.isVisible():
            return False
        try:
            return bool(active.contains_global(global_pos))
        except Exception:
            return False

    def active_menu_has_focus_inside(self, widget) -> bool:
        active = self._live_active_menu()
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


def find_context_menu_provider(predicate) -> ContextMenuProvider | None:
    """Return the first registered provider matching ``predicate``, or None.

    Tab-agnostic lookup for find-or-create install sites: a provider coupled
    to a lazily-constructed controller (e.g. a flyout controller) must be
    reusable by an eager wiring path instead of registering a duplicate
    (duplicates surface as repeated menu sections). The predicate owns all
    tab-specific matching; this module stays free of tab names.
    """
    for provider in tuple(get_context_menu_manager()._providers):
        try:
            if predicate(provider):
                return provider
        except Exception:
            continue
    return None