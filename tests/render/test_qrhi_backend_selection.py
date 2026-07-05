"""All QRhi widgets use the same process-level backend selection."""

from ui.widgets.canvas.rhi_backend import (
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


def test_configure_rhi_process_environment_sets_backend_env(monkeypatch):
    monkeypatch.delenv(RHI_BACKEND_ENV, raising=False)

    configure_rhi_process_environment("vulkan")

    assert requested_rhi_backend_name() == "vulkan"
