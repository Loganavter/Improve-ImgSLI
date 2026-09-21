"""Shared primitives for offscreen ``QRhiWidget`` rendering.

Canvas exporters instantiate a hidden canvas widget, resize it, apply a
``CanvasRenderPlan`` and read back the framebuffer. The Qt-boilerplate is
identical between callers; only widget creation and post-processing differ.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget


def configure_offscreen_widget(widget: QWidget) -> None:
    """Apply attributes required for an offscreen render surface."""
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    widget.setAutoFillBackground(False)


def show_offscreen_widget(widget: QWidget) -> None:
    """Show ``widget`` and flush pending events so QRhi is ready."""
    widget.show()
    QApplication.processEvents()


def resize_offscreen_widget(widget: QWidget, target_size: tuple[int, int]) -> None:
    """Resize the canvas surface and flush events so the RHI target follows."""
    widget.resize(*target_size)
    QApplication.processEvents()


def resize_and_show_offscreen_widget(widget: QWidget, target_size: tuple[int, int]) -> None:
    """Resize and show with double flush — QRhiWidget needs two event loops to reallocate swapchain."""
    widget.resize(*target_size)
    widget.show()
    QApplication.processEvents()
    QApplication.processEvents()


def render_widget_frame(widget: QWidget) -> None:
    """Request a repaint and flush events so ``grabFramebuffer`` sees the frame.

    ``QRhiWidget`` renders in its own ``render(cb)`` callback; ``update()`` +
    ``processEvents()`` is what schedules the frame before the sync grab.
    Double flush is required — single leaves grabFramebuffer transparent.
    """
    widget.update()
    QApplication.processEvents()
    QApplication.processEvents()


def export_widget_more_pending(widget: object) -> bool:
    """Fail-open quiescence query for offscreen export widgets.

    The live tile-residency pass publishes its budget-limited progress on
    the widget every frame (``runtime_state._tile_more_pending`` plus the
    fallback-LOD snapshot on the renderer); an export grab must wait for
    both to drain or it reads back a partial tier (blank/previous-content
    tiles on a cold first frame). Unknown widgets (fakes, non-canvas
    surfaces) read as quiescent so callers keep today's single-grab
    behavior bit-identically.
    """
    try:
        state = getattr(widget, "runtime_state", None)
        if bool(getattr(state, "_tile_more_pending", False)):
            return True
        renderer = getattr(widget, "_rhi_renderer", None)
        if bool(getattr(renderer, "_fallback_more_pending_snapshot", False)):
            return True
    except Exception:
        pass
    return False


def pump_offscreen_to_quiescence(widget: QWidget, *, max_frames: int = 10) -> int:
    """Pump progressive tile residency to quiescence before a grab.

    Each pumped frame is one ``render_widget_frame`` (the residency pass
    uploads its next budget slice and re-arms via ``widget.update()`` while
    work remains). Returns the number of extra frames pumped (0 when the
    widget was already quiescent). Bounded by ``max_frames`` — pyramid
    builds are asynchronous with no progress signal here, so an unbounded
    loop could spin; the caller still grabs whatever is resident.
    """
    pumped = 0
    for _ in range(max(0, int(max_frames))):
        if not export_widget_more_pending(widget):
            break
        render_widget_frame(widget)
        pumped += 1
    return pumped


def shutdown_offscreen_widget(widget: QWidget | None) -> None:
    """Best-effort teardown of an offscreen canvas widget."""
    if widget is None:
        return
    for op in (widget.hide, widget.close, widget.deleteLater):
        try:
            op()
        except Exception:
            pass
