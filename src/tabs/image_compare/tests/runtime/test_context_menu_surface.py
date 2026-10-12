"""RMB context menu surface selection.

Every context menu in the app is now an in-window overlay child
(``"in_window"``): a native ``Qt.Popup`` tears down its ``xdg_popup`` surface
on close, and a widget shown right after that teardown (e.g. the Ask AI flyout
opened from a menu action) hits Mutter's stale/zero xdg-activation serial and
flashes the global busy cursor for several frames. In-window menus have no
native popup surface to tear down, so the sequenced close→open stays clean.
The multi-compare ``IMGSLI_MC_RMB_SURFACE`` env override still allows forcing
``popup`` for A/B debugging.
"""

from __future__ import annotations

from ui.context_menu import manager as context_menu_manager


def test_rmb_surface_is_always_in_window(monkeypatch):
    # Wayland / Windows env must not change the result.
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert context_menu_manager.rmb_context_menu_surface() == "in_window"


def test_rmb_surface_in_window_on_x11(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert context_menu_manager.rmb_context_menu_surface() == "in_window"
