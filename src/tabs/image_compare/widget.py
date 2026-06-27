"""Root widget for the image_compare tab.

The widget is constructed empty by the tab during ``create_page`` (early,
before the host has built the primitive widgets it owns). The host calls
``assemble(ui)`` once those primitives exist; the builder then populates
this widget with the full image-compare layout tree.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext


class ImageCompareWidget(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        context: TabContext | None = None,
    ):
        super().__init__(parent)
        self._context = context
        self._assembled = False

    def assemble(self, ui) -> None:
        if self._assembled:
            return
        from tabs.image_compare.ui.layout import ImageCompareLayoutBuilder

        ImageCompareLayoutBuilder(ui).build_into(self)
        self._assembled = True
        self._wire_transition_mask_release(ui)

    def _wire_transition_mask_release(self, ui) -> None:
        canvas = getattr(ui, "image_label", None)
        signal = getattr(canvas, "firstVisualFrameReady", None)
        if signal is None:
            return
        try:
            signal.connect(self._on_first_visual_frame)
        except Exception:
            pass

    def _on_first_visual_frame(self) -> None:
        context = self._context
        services = getattr(context, "services", None) if context else None
        if not services:
            return
        mask = services.get("workspace.transition_mask")
        if mask is None:
            return
        try:
            mask.release()
        except Exception:
            pass
