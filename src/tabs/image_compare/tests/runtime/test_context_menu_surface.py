"""RMB context menu surface selection (native popup vs in-window widget).

On Wayland, a real Qt.Popup requests a compositor-level xdg_popup pointer
grab. A fast right-click landing near the previous popup's grab teardown can
be dropped by the compositor before it ever reaches Qt's event queue (no
mousePressEvent, no contextMenuEvent -- confirmed via RMB debug logging).
in_window menus have no native grab, so they don't hit this race.
"""

from __future__ import annotations

from ui.context_menu import manager as context_menu_manager


def test_wayland_session_forces_in_window_surface(monkeypatch):
    monkeypatch.setattr(context_menu_manager.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    assert context_menu_manager.rmb_context_menu_surface() == "in_window"


def test_wayland_display_env_forces_in_window_surface(monkeypatch):
    monkeypatch.setattr(context_menu_manager.sys, "platform", "linux")
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    assert context_menu_manager.rmb_context_menu_surface() == "in_window"


def test_x11_session_keeps_popup_surface(monkeypatch):
    monkeypatch.setattr(context_menu_manager.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    assert context_menu_manager.rmb_context_menu_surface() == "popup"
