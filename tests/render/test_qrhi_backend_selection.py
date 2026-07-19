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
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: True)
    monkeypatch.setattr(mod.sys, "platform", "win32")
    monkeypatch.setattr(mod, "_vulkan_rejected_for_process", False)

    effective, reason = resolve_rhi_backend_with_fallback("vulkan")

    assert effective == "d3d11"
    assert reason is not None
    assert "d3d11" in reason
    assert mod._vulkan_rejected_for_process is True


def test_resolve_keeps_vulkan_when_probe_ok(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_vulkan_available", lambda: True)
    monkeypatch.setattr(mod, "_vulkan_rejected_for_process", False)

    effective, reason = resolve_rhi_backend_with_fallback("vulkan")

    assert effective == "vulkan"
    assert reason is None


def test_resolve_falls_back_when_probe_unavailable_on_windows(monkeypatch):
    """Windows + missing probe API must not leave setApi(Vulkan) active."""
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_vulkan_available", lambda: None)
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: True)
    monkeypatch.setattr(mod.sys, "platform", "win32")
    monkeypatch.setattr(mod, "_vulkan_rejected_for_process", False)

    effective, reason = resolve_rhi_backend_with_fallback("vulkan")

    assert effective == "d3d11"
    assert reason is not None
    assert mod._vulkan_rejected_for_process is True


def test_resolve_keeps_vulkan_when_probe_unavailable_on_linux(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_vulkan_available", lambda: None)
    monkeypatch.setattr(mod.sys, "platform", "linux")
    monkeypatch.setattr(mod, "_vulkan_rejected_for_process", False)

    effective, reason = resolve_rhi_backend_with_fallback("vulkan")

    assert effective == "vulkan"
    assert reason is None
    assert mod._vulkan_rejected_for_process is False


def test_resolve_leaves_linux_auto_alone_even_if_probe_false(monkeypatch):
    """Auto must not be rewritten to OpenGL by a speculative Vulkan probe."""
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_vulkan_available", lambda: False)
    monkeypatch.setattr(mod.sys, "platform", "linux")
    monkeypatch.setattr(mod, "_vulkan_rejected_for_process", False)

    effective, reason = resolve_rhi_backend_with_fallback("default")

    assert effective == "default"
    assert reason is None
    assert mod._vulkan_rejected_for_process is False


def test_resolve_windows_auto_uses_explicit_d3d11(monkeypatch):
    """Windows Auto must not land on legacy OpenGL (GLSL 120/130)."""
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: True)

    effective, reason = resolve_rhi_backend_with_fallback("default")

    assert effective == "d3d11"
    assert reason is None


def test_resolve_windows_auto_falls_back_when_d3d11_missing(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: False)
    monkeypatch.setattr(mod, "probe_opengl_usable_for_shaders", lambda: True)

    effective, reason = resolve_rhi_backend_with_fallback("default")

    assert effective == "opengl"
    assert reason is not None
    assert "Direct3D 11" in reason


def test_resolve_exhausted_backends_use_null(monkeypatch):
    """Only D3D9 / ancient GL: every candidate fails → Null + unsupported notice."""
    import ui.widgets.canvas.rhi_backend as mod
    from ui.widgets.canvas.rhi_backend import (
        RHI_NOTICE_UNSUPPORTED,
        record_rhi_fallback_notice,
        take_rhi_fallback_notice,
    )

    monkeypatch.setattr(mod.sys, "platform", "win32")
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: False)
    monkeypatch.setattr(mod, "probe_opengl_usable_for_shaders", lambda: False)
    monkeypatch.setattr(mod, "probe_d3d12_available", lambda: False)

    effective, reason = resolve_rhi_backend_with_fallback("default")

    assert effective == "null"
    assert reason is not None
    assert "No usable QRhi backend" in reason

    take_rhi_fallback_notice()
    notice = record_rhi_fallback_notice("default", effective, reason)
    assert notice.kind == RHI_NOTICE_UNSUPPORTED


def test_resolve_falls_back_when_d3d12_missing(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    monkeypatch.setattr(mod, "probe_d3d12_available", lambda: False)
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: True)

    effective, reason = resolve_rhi_backend_with_fallback("d3d12")

    assert effective == "d3d11"
    assert reason is not None


def test_resolve_falls_back_when_metal_missing(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod.sys, "platform", "linux")
    monkeypatch.setattr(mod, "probe_metal_available", lambda: False)
    monkeypatch.setattr(mod, "probe_opengl_usable_for_shaders", lambda: True)

    effective, reason = resolve_rhi_backend_with_fallback("metal")

    assert effective == "opengl"
    assert reason is not None


def test_resolve_keeps_d3d11_when_probe_ok(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: True)

    effective, reason = resolve_rhi_backend_with_fallback("d3d11")

    assert effective == "d3d11"
    assert reason is None


def test_resolve_falls_back_when_opengl_too_old(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_opengl_usable_for_shaders", lambda: False)
    monkeypatch.setattr(mod, "probe_d3d11_available", lambda: True)
    monkeypatch.setattr(mod.sys, "platform", "win32")

    effective, reason = resolve_rhi_backend_with_fallback("opengl")

    assert effective == "d3d11"
    assert reason is not None
    assert "GLSL 330" in reason


def test_resolve_keeps_opengl_when_probe_ok(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod, "probe_opengl_usable_for_shaders", lambda: True)

    effective, reason = resolve_rhi_backend_with_fallback("opengl")

    assert effective == "opengl"
    assert reason is None


def test_configure_rhi_widget_refuses_rejected_vulkan(monkeypatch):
    from PySide6.QtWidgets import QRhiWidget

    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setenv(RHI_BACKEND_ENV, "vulkan")
    monkeypatch.setattr(mod, "_vulkan_rejected_for_process", True)
    monkeypatch.setattr(mod.sys, "platform", "win32")
    widget = _Widget()

    configure_rhi_widget(widget)

    assert widget.selected == QRhiWidget.Api.Direct3D11
    assert requested_rhi_backend_name() == "d3d11"


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


def test_platform_rhi_requirement_keys_are_os_filtered(monkeypatch):
    import ui.widgets.canvas.rhi_backend as mod

    monkeypatch.setattr(mod.sys, "platform", "win32")
    assert mod.platform_rhi_requirement_keys() == ("d3d11", "opengl", "vulkan")
    monkeypatch.setattr(mod.sys, "platform", "linux")
    assert mod.platform_rhi_requirement_keys() == ("opengl", "vulkan")
    monkeypatch.setattr(mod.sys, "platform", "darwin")
    assert mod.platform_rhi_requirement_keys() == ("metal", "opengl")


def test_format_platform_rhi_requirements_omits_foreign_apis(monkeypatch):
    from ui.widgets.canvas import rhi_backend as mod
    from ui.widgets.canvas.rhi_fallback_notice import format_platform_rhi_requirements

    monkeypatch.setattr(mod.sys, "platform", "linux")
    text = format_platform_rhi_requirements("en")
    assert "OpenGL" in text
    assert "Vulkan" in text
    assert "Metal" not in text
    assert "Direct3D" not in text

    monkeypatch.setattr(mod.sys, "platform", "win32")
    text = format_platform_rhi_requirements("en")
    assert "Direct3D" in text
    assert "Metal" not in text


def test_record_and_take_fallback_notice():
    from ui.widgets.canvas.rhi_backend import (
        RHI_NOTICE_FALLBACK,
        RHI_NOTICE_UNSUPPORTED,
        record_rhi_fallback_notice,
        take_rhi_fallback_notice,
    )

    # Clear any leftover from earlier tests.
    take_rhi_fallback_notice()
    notice = record_rhi_fallback_notice("vulkan", "d3d11", "probe failed")
    assert notice.requested == "vulkan"
    assert notice.effective == "d3d11"
    assert notice.kind == RHI_NOTICE_FALLBACK
    assert take_rhi_fallback_notice() is notice
    assert take_rhi_fallback_notice() is None

    unsupported = record_rhi_fallback_notice(
        "default", "null", "exhausted", kind=RHI_NOTICE_UNSUPPORTED
    )
    assert unsupported.kind == RHI_NOTICE_UNSUPPORTED
    take_rhi_fallback_notice()
