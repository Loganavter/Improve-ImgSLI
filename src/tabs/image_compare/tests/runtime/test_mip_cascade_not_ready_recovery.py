"""A typed "not ready" render failure must not escape a QRhiWidget override.

Measured live on 2026-10-21 (default OpenGL/llvmpipe, two images in Image
Compare): ``MipCascadeNotReady`` escaped ``QRhiWidget::render()`` — PySide
printed ``Error calling Python override of QRhiWidget::render()`` twice, the
canvas never placed content, and on that run the process stayed up (the audit
saw exit 139 from the same escape). The gallery quick-look canvas already
treats the condition as transient (keep the last frame, retry with backoff);
this pins the same contract for the two tab canvases through one shared helper.

Red-before: without ``render_or_defer`` the exception leaves ``render()``.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import QObject

from engine.gpu.mip_cascade import MipCascadeNotReady


class _CountingWidget(QObject):
    """Minimal widget stand-in: only ``update`` is used by the retry path.

    A ``QObject`` because ``QTimer.singleShot`` needs a receiver with a thread;
    ``processEvents`` after the backoff proves the retry actually fires.
    """

    def __init__(self):
        super().__init__()
        self.updates = 0

    def update(self):  # noqa: N802 - Qt spelling
        self.updates += 1


def _not_ready() -> MipCascadeNotReady:
    return MipCascadeNotReady(
        "Failed to create canvas probe mip render target (test)",
        attempt=1,
        details="backend=OpenGL",
    )


def test_render_or_defer_absorbs_the_typed_condition(qapp):
    import time

    from ui.canvas_infra.rhi.rhi_render import render_or_defer

    widget = _CountingWidget()

    def render():
        raise _not_ready()

    assert render_or_defer(widget, "test-canvas", render) is False
    assert widget._not_ready_retries == 1
    time.sleep(0.08)
    qapp.processEvents()
    assert widget.updates >= 1  # a retry actually fired


def test_render_or_defer_backs_off_and_resets_on_success(qapp):
    from ui.canvas_infra.rhi.rhi_render import render_or_defer

    widget = _CountingWidget()

    def boom():
        raise _not_ready()

    for expected in (1, 2, 3):
        render_or_defer(widget, "test-canvas", boom)
        assert widget._not_ready_retries == expected
    assert widget._not_ready_delay_ms > 50
    assert render_or_defer(widget, "test-canvas", lambda: True) is True
    assert widget._not_ready_retries == 0
    assert widget._not_ready_delay_ms == 50


def test_render_or_defer_passes_through_a_non_typed_error(qapp):
    from ui.canvas_infra.rhi.rhi_render import render_or_defer

    widget = _CountingWidget()

    def broken():
        raise RuntimeError("a real bug, not a transient condition")

    with pytest.raises(RuntimeError):
        render_or_defer(widget, "test-canvas", broken)


def test_ic_canvas_render_defers_instead_of_escaping(qapp):
    from tabs.image_compare.canvas.widget import CanvasWidget

    canvas = CanvasWidget()
    calls = {"n": 0}

    class _Renderer:
        def render(self, widget, command_buffer, clear_color):
            calls["n"] += 1
            raise _not_ready()

    canvas._rhi_renderer = _Renderer()
    try:
        canvas.render(None)  # must not raise
        assert calls["n"] == 1
        assert canvas._not_ready_retries == 1
    finally:
        canvas.deleteLater()


def test_multi_compare_canvas_render_defers_instead_of_escaping(qapp):
    from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget

    canvas = MultiCompareCanvasWidget()
    calls = {"n": 0}

    class _Renderer:
        def render(self, command_buffer):
            calls["n"] += 1
            raise _not_ready()

    canvas._renderer = _Renderer()
    try:
        canvas.render(None)  # must not raise
        assert calls["n"] == 1
        assert canvas._not_ready_retries == 1
    finally:
        canvas.deleteLater()
