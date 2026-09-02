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
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen show ENTER size=%s visible=%s", (widget.width(), widget.height()), widget.isVisible() if widget else False)
    except Exception:
        pass
    widget.show()
    QApplication.processEvents()
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen show EXIT size=%s visible=%s isHidden=%s", (widget.width(), widget.height()), widget.isVisible(), widget.isHidden())
    except Exception:
        pass


def resize_offscreen_widget(widget: QWidget, target_size: tuple[int, int]) -> None:
    """Resize the canvas surface and flush events so the RHI target follows."""
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen resize ENTER target=%s cur=%s", target_size, (widget.width(), widget.height()))
    except Exception:
        pass
    widget.resize(*target_size)
    QApplication.processEvents()
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen resize EXIT target=%s cur=%s", target_size, (widget.width(), widget.height()))
    except Exception:
        pass


def resize_and_show_offscreen_widget(widget: QWidget, target_size: tuple[int, int]) -> None:
    """Resize and show with double flush — QRhiWidget needs two event loops to reallocate swapchain."""
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen resize_and_show ENTER target=%s cur=%s vis=%s", target_size, (widget.width(), widget.height()), widget.isVisible())
    except Exception:
        pass
    widget.resize(*target_size)
    widget.show()
    QApplication.processEvents()
    QApplication.processEvents()
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen resize_and_show EXIT target=%s cur=%s vis=%s grab_size=%s", target_size, (widget.width(), widget.height()), widget.isVisible(), (widget.width(), widget.height()))
    except Exception:
        pass


def render_widget_frame(widget: QWidget) -> None:
    """Request a repaint and flush events so ``grabFramebuffer`` sees the frame.

    ``QRhiWidget`` renders in its own ``render(cb)`` callback; ``update()`` +
    ``processEvents()`` is what schedules the frame before the sync grab.
    Double flush is required — single leaves grabFramebuffer transparent (see /tmp/thumb_debug_0.png 136B).
    """
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen render_frame ENTER size=%s", (widget.width(), widget.height()))
    except Exception:
        pass
    widget.update()
    QApplication.processEvents()
    QApplication.processEvents()
    try:
        from tabs.image_compare.debug import ic_thumbnail_debug
        ic_thumbnail_debug("offscreen render_frame EXIT size=%s", (widget.width(), widget.height()))
    except Exception:
        pass


def shutdown_offscreen_widget(widget: QWidget | None) -> None:
    """Best-effort teardown of an offscreen canvas widget."""
    if widget is None:
        return
    for op in (widget.hide, widget.close, widget.deleteLater):
        try:
            op()
        except Exception:
            pass
