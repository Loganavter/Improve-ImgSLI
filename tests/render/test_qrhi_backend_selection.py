"""All QRhi widgets use the same process-level backend selection."""

from ui.widgets.gl_canvas.rhi_backend import (
    RHI_BACKEND_ENV,
    configure_rhi_process_environment,
    configure_rhi_widget,
    requested_rhi_backend_name,
)


class _Signal:
    def connect(self, callback):
        self.callback = callback


class _Widget:
    renderFailed = _Signal()

    def __init__(self):
        self.selected = None

    def setApi(self, api):
        self.selected = api

    def api(self):
        return self.selected


def test_vulkan_backend_is_applied(monkeypatch):
    from PySide6.QtWidgets import QRhiWidget

    monkeypatch.setenv(RHI_BACKEND_ENV, "vulkan")
    widget = _Widget()

    configure_rhi_widget(widget)

    assert requested_rhi_backend_name() == "vulkan"
    assert widget.selected == QRhiWidget.Api.Vulkan


def test_unknown_backend_falls_back_to_platform_default(monkeypatch):
    monkeypatch.setenv(RHI_BACKEND_ENV, "unknown")
    widget = _Widget()

    configure_rhi_widget(widget)

    assert requested_rhi_backend_name() == "default"
    assert widget.selected is None


def test_vulkan_uses_xcb_in_wayland_session(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    changed = configure_rhi_process_environment("vulkan")

    assert changed is True
    assert requested_rhi_backend_name() == "vulkan"
    assert __import__("os").environ["QT_QPA_PLATFORM"] == "xcb"


def test_explicit_qpa_platform_is_not_overridden(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")

    changed = configure_rhi_process_environment("vulkan")

    assert changed is False
    assert __import__("os").environ["QT_QPA_PLATFORM"] == "wayland"
