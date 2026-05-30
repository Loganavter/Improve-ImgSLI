"""GPU export readback uses render-plan pixels, not platform-scaled widget pixels.

Dogma source: docs/dev/CANVAS_FEATURES.md §Render/export parity.
"""

from __future__ import annotations

def test_gpu_export_readback_uses_plan_size(monkeypatch):
    from plugins.export.services.gpu_export_proxy import GpuExportProxy
    from plugins.export.services import gpu_export_proxy as proxy_module

    calls = []

    monkeypatch.setattr(
        proxy_module.gl,
        "glPixelStorei",
        lambda *args: calls.append(("store", args)),
    )
    monkeypatch.setattr(proxy_module.gl, "glFinish", lambda: calls.append(("finish", ())))

    def fake_read_pixels(x, y, width, height, fmt, typ):
        calls.append(("read", (x, y, width, height, fmt, typ)))
        return bytes([10, 20, 30, 255] * width * height)

    monkeypatch.setattr(proxy_module.gl, "glReadPixels", fake_read_pixels)

    image = GpuExportProxy._read_widget_framebuffer_to_pil(320, 180)

    assert image.size == (320, 180)
    assert image.getpixel((0, 0)) == (10, 20, 30, 255)
    assert [name for name, _args in calls] == ["store", "finish", "read"]
    assert calls[-1][1][2:4] == (320, 180)


def test_gpu_export_frame_forces_logical_viewport_and_dpr(monkeypatch):
    from plugins.export.services.gpu_export_proxy import GpuExportProxy
    from plugins.export.services import gpu_export_proxy as proxy_module

    events = []

    class FakeWidget:
        def __init__(self):
            self._forced_device_pixel_ratio = None

        def makeCurrent(self):
            events.append(("make", None))

        def doneCurrent(self):
            events.append(("done", getattr(self, "_forced_device_pixel_ratio", None)))

        def update(self):
            events.append(("update", None))

        def devicePixelRatioF(self):
            forced = getattr(self, "_forced_device_pixel_ratio", None)
            return float(forced) if forced is not None else 1.25

    widget = FakeWidget()
    monkeypatch.setattr(
        proxy_module.gl,
        "glViewport",
        lambda x, y, w, h: events.append(("viewport", (x, y, w, h))),
    )
    monkeypatch.setattr(
        proxy_module,
        "paint_gl",
        lambda w: events.append(("paint_dpr", w.devicePixelRatioF())),
    )
    monkeypatch.setattr(
        proxy_module.QApplication,
        "processEvents",
        lambda: events.append(("events", None)),
    )

    proxy = GpuExportProxy.__new__(GpuExportProxy)
    proxy._render_widget_frame(widget, (320, 180))

    assert ("viewport", (0, 0, 320, 180)) in events
    assert ("paint_dpr", 1.0) in events
    assert getattr(widget, "_forced_device_pixel_ratio", None) is None


def test_gpu_export_readback_runs_with_current_context(monkeypatch):
    from plugins.export.services.gpu_export_proxy import GpuExportProxy

    events = []

    class FakeWidget:
        def makeCurrent(self):
            events.append("make")

        def doneCurrent(self):
            events.append("done")

    proxy = GpuExportProxy.__new__(GpuExportProxy)
    monkeypatch.setattr(
        proxy,
        "_read_widget_framebuffer_to_pil",
        lambda width, height: events.append(("read", width, height)) or object(),
    )

    result = proxy._grab_rendered_frame(FakeWidget(), (320, 180))

    assert result is not None
    assert events == ["make", ("read", 320, 180), "done"]
