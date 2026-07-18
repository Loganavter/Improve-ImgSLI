"""All QRhi widgets use the same process-level backend selection."""

from ui.widgets.canvas.rhi_backend import (
    RHI_BACKEND_ENV,
    configure_rhi_process_environment,
    configure_rhi_widget,
    platform_fallback_rhi_backend,
    requested_rhi_backend_name,
    resolve_rhi_backend_with_fallback,
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


def test_resolve_falls_back_when_vulkan_probe_fails(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_vulkan_available", lambda: False)
    monkeypatch.setattr(mod.sys, "platform", "win32")

    effective, reason = resolve_rhi_backend_with_fallback("vulkan")

    assert effective == "d3d11"
    assert reason is not None
    assert "d3d11" in reason


def test_resolve_keeps_vulkan_when_probe_ok(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_vulkan_available", lambda: True)

    effective, reason = resolve_rhi_backend_with_fallback("vulkan")

    assert effective == "vulkan"
    assert reason is None


def test_resolve_skips_probe_when_unavailable(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_vulkan_available", lambda: None)

    effective, reason = resolve_rhi_backend_with_fallback("vulkan")

    assert effective == "vulkan"
    assert reason is None


def test_platform_fallback_windows(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    assert platform_fallback_rhi_backend() == "d3d11"
    monkeypatch.setattr(mod.sys, "platform", "darwin")
    assert platform_fallback_rhi_backend() == "metal"
    monkeypatch.setattr(mod.sys, "platform", "linux")
    assert platform_fallback_rhi_backend() == "opengl"


def test_render_failed_persists_fallback(monkeypatch):
    persisted: list[str] = []
    monkeypatch.setenv(RHI_BACKEND_ENV, "vulkan")
    monkeypatch.setattr(
        "ui.widgets.canvas.rhi_backend.platform_fallback_rhi_backend",
        lambda: "d3d11",
    )
    monkeypatch.setattr(
        "ui.widgets.canvas.rhi_backend.persist_rhi_backend_setting",
        persisted.append,
    )
    widget = _Widget()
    configure_rhi_widget(widget)

    widget.renderFailed.callback()

    assert persisted == ["d3d11"]
