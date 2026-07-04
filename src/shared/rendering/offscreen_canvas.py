"""Shared primitives for offscreen ``QRhiWidget`` rendering.

Both the main-compare (:class:`plugins.export.services.gpu_export_proxy.GpuExportProxy`)
and multi-compare (:class:`tabs.multi_compare.services.gpu_export.MultiCompareGpuExporter`)
exporters instantiate a hidden canvas widget, resize it, apply a
``CanvasRenderPlan`` and read back the framebuffer. The Qt-boilerplate is
identical between them; only widget creation and post-processing differ.
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


def render_widget_frame(widget: QWidget) -> None:
    """Request a repaint and flush events so ``grabFramebuffer`` sees the frame.

    ``QRhiWidget`` renders in its own ``render(cb)`` callback; ``update()`` +
    ``processEvents()`` is what schedules the frame before the sync grab.
    """
    widget.update()
    QApplication.processEvents()


def shutdown_offscreen_widget(widget: QWidget | None) -> None:
    """Best-effort teardown of an offscreen canvas widget."""
    if widget is None:
        return
    for op in (widget.hide, widget.close, widget.deleteLater):
        try:
            op()
        except Exception:
            pass
