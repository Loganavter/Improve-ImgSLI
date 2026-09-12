"""RMB context menu surface selection.

Every context menu in the app is a real ``Qt.Popup`` top-level (``"popup"``)
so it stacks above ``UnifiedFlyout`` and behaves like a native menu. The
historical platform fallbacks (in-window on Wayland / pre-3.1.4 Windows) were
removed by request; the multi-compare ``IMGSLI_MC_RMB_SURFACE`` env override
still allows forcing ``in_window`` for A/B debugging.
"""

from __future__ import annotations

from ui.context_menu import manager as context_menu_manager


def test_rmb_surface_is_always_popup(monkeypatch):
    # Wayland / Windows env must not change the result anymore.
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert context_menu_manager.rmb_context_menu_surface() == "popup"


def test_rmb_surface_popup_on_x11(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert context_menu_manager.rmb_context_menu_surface() == "popup"
