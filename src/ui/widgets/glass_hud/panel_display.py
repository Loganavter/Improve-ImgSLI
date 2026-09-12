from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402


class GlassPanelDisplayWidget(QWidget):
    """Glass-panel display widget: paints one HUD's already-fully-composited
    sprite (blur, tint, border, rounded crop, real alpha — all computed
    canvas-side by ``shared.rendering.glass_panel.GlassPanelRenderer``)
    via plain ``QPainter``, from a CPU-side ``QImage`` copy of the sprite
    (``source_widget._glass_panel_images``, a GPU→CPU readback the renderer
    already issues once per frame — see that module's ``ready_images``).

    A plain ``QWidget`` is used instead of ``QRhiWidget``/``QOpenGLWidget``
    because *-class widgets are always composited as their own base layer
    and never truly alpha-blend into arbitrary sibling z-order (confirmed
    live — see docs/dev/rendering/investigations/glass-panel-backdrop-self-reference.md).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._source_widget = None
        self._panel_key: int | None = None

    def set_source(self, source_widget, panel_key: int) -> None:
        """``source_widget`` is the canvas whose
        ``source_widget._glass_panel_images`` dict (populated by
        ``RhiCanvasRenderer`` before its own main pass, see
        ``shared.rendering.glass_panel``) this widget reads ``panel_key``'s
        ready sprite image from every frame."""
        self._source_widget = source_widget
        self._panel_key = panel_key
        self.update()

    def sizeHint(self) -> QSize:  # noqa: D401 - Qt override
        return QSize(1, 1)

    def paintEvent(self, event) -> None:  # noqa: D401 - Qt override
        images = getattr(self._source_widget, "_glass_panel_images", None)
        image = images.get(self._panel_key) if images else None
        if image is None or image.isNull():
            return
        painter = QPainter(self)
        # drawImage(QPoint, image), not drawImage(QRect, image): the image
        # already carries the correct devicePixelRatio (set alongside its
        # readback, see GlassPanelRenderer.render_backdrops), so Qt
        # places it 1:1 in device pixels here.
        if os.environ.get("IMGSLI_GLASS_PANEL_DEBUG_SIZE"):
            print(
                f"[glass_panel_display size] widget_logical={self.size()} "
                f"widget_dpr={self.devicePixelRatioF()} image_px={image.size()} "
                f"image_dpr={image.devicePixelRatio()}",
                flush=True,
            )
        painter.drawImage(QPoint(0, 0), image)


def create_glass_panel_display_widget(parent: QWidget | None = None) -> QWidget:
    """Factory GlassHUD uses instead of constructing a display widget class
    directly — always returns the CPU/QPainter path."""
    return GlassPanelDisplayWidget(parent)


GlassPanelDisplayWidget.inspect_spec = InspectSpec(
    family="GlassPanelDisplayWidget",
    docs="docs/dev/widgets/glass_panel_display.md",
    regions=True,
    layers=True,
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
GlassPanelDisplayWidget.widget_descriptor = WidgetDescriptor(
    family=GlassPanelDisplayWidget.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(GlassPanelDisplayWidget.inspect_spec, 'config', ()),
        state=GlassPanelDisplayWidget.inspect_spec.state,
        token_family=getattr(GlassPanelDisplayWidget.inspect_spec, 'token_family', ()),
        regions=getattr(GlassPanelDisplayWidget.inspect_spec, 'regions', False),
        layers=getattr(GlassPanelDisplayWidget.inspect_spec, 'layers', False),
        docs=getattr(GlassPanelDisplayWidget.inspect_spec, 'docs', ''),
        preview_seed=getattr(GlassPanelDisplayWidget.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(GlassPanelDisplayWidget.inspect_spec, 'apply_config_refresh', None),
    ),
)
