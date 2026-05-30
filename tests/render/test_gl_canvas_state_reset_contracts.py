"""GL canvas frames reset persistent viewport/scissor state before painting.

Dogma source: docs/dev/CANVAS_FEATURES.md §Render/export parity.
"""

from __future__ import annotations

from types import SimpleNamespace


def test_paint_gl_resets_scissor_and_viewport_each_frame(monkeypatch):
    import ui.widgets.gl_canvas.render_passes as render_passes

    calls = []
    monkeypatch.setattr(
        render_passes.gl,
        "glDisable",
        lambda flag: calls.append(("disable", flag)),
    )
    monkeypatch.setattr(
        render_passes.gl,
        "glViewport",
        lambda x, y, w, h: calls.append(("viewport", (x, y, w, h))),
    )
    monkeypatch.setattr(render_passes, "_flush_pending_uploads", lambda _widget: None)
    monkeypatch.setattr(
        render_passes,
        "build_render_runtime_context",
        lambda _widget: SimpleNamespace(
            scene_frame=SimpleNamespace(blank_white=False),
            images_uploaded=[False, False],
        ),
    )
    monkeypatch.setattr(render_passes, "clear_with_widget_background", lambda _widget: None)
    monkeypatch.setattr(
        render_passes,
        "execute_render_passes",
        lambda *_args, **_kwargs: calls.append(("passes", None)),
    )

    widget = SimpleNamespace(
        shader_program=object(),
        width=lambda: 320,
        height=lambda: 180,
        devicePixelRatioF=lambda: 1.25,
        runtime_state=SimpleNamespace(
            _content_scissor_depth=2,
            _pending_texture_uploads=[],
        ),
    )

    render_passes.paint_gl(widget)

    assert widget.runtime_state._content_scissor_depth == 0
    assert ("disable", render_passes.gl.GL_SCISSOR_TEST) in calls
    assert ("viewport", (0, 0, 400, 225)) in calls
    assert ("passes", None) in calls


def test_gpu_export_normalizes_high_dpi_grab_to_plan_size(monkeypatch):
    from PIL import Image

    from plugins.export.services.gpu_export_proxy import GpuExportProxy
    from plugins.export.services import gpu_export_proxy as proxy_module

    class FakeWidget:
        def resize(self, width, height):
            self.size = (width, height)

        def show(self):
            pass

        def grabFramebuffer(self):
            return object()

        def upload_diff_source_pil_image(self, _image):
            pass

    widget = FakeWidget()
    plan = SimpleNamespace(canvas_w=320, canvas_h=180)
    proxy = GpuExportProxy.__new__(GpuExportProxy)
    proxy._last_widget_size = None

    monkeypatch.setattr(proxy_module.QApplication, "processEvents", lambda: None)
    monkeypatch.setattr(
        proxy,
        "_render_widget_frame",
        lambda _widget: None,
    )
    monkeypatch.setattr(
        "ui.canvas_presentation.plan_applicator.apply_render_plan_to_canvas",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        proxy_module,
        "qimage_to_pil",
        lambda _qimage: Image.new("RGBA", (400, 225), (1, 2, 3, 255)),
    )

    image = proxy._render_plan_frame(widget, plan, None, {})

    assert image.size == (320, 180)
