from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from sli_ui_toolkit.ui.inspector.spec import InspectSpec  # noqa: E402

import os
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QRhiShaderResourceBindings,
    QPainter,
    QRhiCommandBuffer,
    QRhiDepthStencilClearValue,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiViewport,
    QShader,
)
from PySide6.QtWidgets import QRhiWidget, QWidget

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"

# IMGSLI_GLASS_PANEL_DISPLAY_BACKEND=rhi: use the original QRhiWidget-based
# display path (GlassPanelDisplayWidgetRhi) instead of the default CPU/
# QPainter one (GlassPanelDisplayWidgetCpu). Kept as a fallback, not deleted,
# in case the CPU readback path turns out to have its own problems (perf,
# readback stalls on some backend, ...) -- see create_glass_panel_display_widget.
_USE_RHI_DISPLAY = os.environ.get("IMGSLI_GLASS_PANEL_DISPLAY_BACKEND", "").strip().lower() in (
    "rhi",
    "qrhiwidget",
)


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Failed to load shader: {name}")
    return shader


class GlassPanelDisplayWidgetCpu(QWidget):
    """Default glass-panel display widget: paints one HUD's already-fully-
    composited sprite (blur, tint, border, rounded crop, real alpha -- all
    computed canvas-side by ``shared.rendering.glass_panel.GlassPanelRenderer``)
    via plain ``QPainter``, from a CPU-side ``QImage`` copy of the sprite
    (``source_widget._glass_panel_images``, a GPU->CPU readback the renderer
    already issues once per frame -- see that module's ``ready_images``).

    Replaces the original ``QRhiWidget``-based ``GlassPanelDisplayWidgetRhi``
    (kept below, selectable via ``IMGSLI_GLASS_PANEL_DISPLAY_BACKEND=rhi``):
    ``QOpenGLWidget``/``QQuickWidget``/``QRhiWidget``-class widgets are always
    composited as their own base layer and never truly alpha-blend into
    arbitrary sibling z-order the way a plain ``QWidget`` does -- confirmed
    live (a flat premultiplied semi-transparent debug fill covering this
    widget's *entire* rect rendered fully *opaque* on screen regardless of
    QRhi backend or windowing platform, and neither ``QWidget.setMask()``
    nor removing every ``QGraphicsEffect`` from the window changed that).
    Qt's own docs/forums confirm this is inherent: the one attribute that
    does make such a widget blend against its siblings,
    ``WA_AlwaysStackOnTop``, does so by unconditionally forcing it to paint
    above *everything* in the window -- incompatible with this widget
    needing to stay under the flyout's own text/buttons. A plain ``QWidget``
    has none of these restrictions: real per-pixel (here, premultiplied)
    alpha in a ``QImage`` just blends correctly via ordinary
    ``QPainter.drawImage()``, no clip/mask trick needed for the rounded
    corners either -- the sprite's own alpha (0 outside the rounded shape,
    baked in by ``glass_composite.frag``) already does that.

    See docs/dev/rendering/investigations/glass-panel-backdrop-self-reference.md
    for the full investigation.
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
        # places it 1:1 in device pixels here. Scaling it into an explicit
        # logical-px rect instead reintroduced a resample pass that visibly
        # thickened the rounded corners (a sub-pixel size mismatch between
        # this widget's own rect and the sprite's native size barely shows
        # on a straight edge, but compounds across both axes at the tight
        # curvature of a corner).
        if os.environ.get("IMGSLI_GLASS_PANEL_DEBUG_SIZE"):
            print(
                f"[glass_panel_display size] widget_logical={self.size()} "
                f"widget_dpr={self.devicePixelRatioF()} image_px={image.size()} "
                f"image_dpr={image.devicePixelRatio()}",
                flush=True,
            )
        painter.drawImage(QPoint(0, 0), image)


class GlassPanelDisplayWidgetRhi(QRhiWidget):
    """Original QRhiWidget-based display path -- kept as a fallback (see
    ``IMGSLI_GLASS_PANEL_DISPLAY_BACKEND=rhi``), not the default anymore.
    See ``GlassPanelDisplayWidgetCpu``'s docstring for why: this class's own
    on-screen alpha compositing against sibling widgets does not work
    (confirmed live), and its "outside the shape" region renders as an
    opaque platform-dependent fallback color instead of true transparency.

    Deliberately the *only* GPU work this widget does: no blur, no tint, no
    cropping, no coordinate mapping of any kind -- those all happen once,
    canvas-side, from the canvas's own (always glass-free) ``colorTexture()``
    -- see ``shared.rendering.glass_panel``'s module docstring for why the
    canvas's own texture must never itself contain any glass panel's
    rendering.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._source_widget = None
        self._panel_key: int | None = None
        self._sampler: QRhiSampler | None = None
        self._pipeline: QRhiGraphicsPipeline | None = None
        self._pipeline_created = False
        self._srb: QRhiShaderResourceBindings | None = None
        self._bound_texture_id: int | None = None

    def set_source(self, source_widget, panel_key: int) -> None:
        """``source_widget`` is the canvas whose
        ``source_widget._glass_panel_sprites`` dict (populated by
        ``RhiCanvasRenderer`` before its own main pass, see
        ``shared.rendering.glass_panel``) this widget reads ``panel_key``'s
        ready sprite from every frame."""
        self._source_widget = source_widget
        self._panel_key = panel_key
        self.update()

    def sizeHint(self) -> QSize:  # noqa: D401 - Qt override
        return QSize(1, 1)

    def initialize(self, command_buffer: QRhiCommandBuffer) -> None:
        if self._pipeline is not None:
            return
        rhi = self.rhi()
        self._sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self._sampler.create():
            raise RuntimeError("Failed to create GlassPanelDisplayWidgetRhi sampler")

        pipeline = rhi.newGraphicsPipeline()
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    _load_shader("glass_panel_display.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    _load_shader("glass_panel_display.frag.qsb"),
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
        pipeline.setRenderPassDescriptor(self.renderTarget().renderPassDescriptor())
        # No blend needed: this widget's own target is cleared to
        # transparent every frame (see render()), so a plain overwrite of
        # the sprite's own (already-correct) alpha is equivalent to
        # blending over a fully-transparent destination.
        self._pipeline = pipeline
        self._pipeline_created = False
        # setShaderResourceBindings + pipeline.create() deferred to
        # render(), once a real sprite texture exists to bind -- an SRB
        # referencing no texture yet is invalid (same deferred-creation
        # pattern as the old sli_ui_toolkit LiquidGlassFillWidget's
        # composite pipeline).

    def releaseResources(self) -> None:
        for res in (self._pipeline, self._srb, self._sampler):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self._pipeline = None
        self._pipeline_created = False
        self._srb = None
        self._sampler = None
        self._bound_texture_id = None

    def _ensure_srb(self, texture) -> None:
        if self._srb is not None and self._bound_texture_id == id(texture):
            return
        rhi = self.rhi()
        assert self._sampler is not None
        if self._srb is not None:
            try:
                self._srb.destroy()
            except RuntimeError:
                pass
        srb = rhi.newShaderResourceBindings()
        srb.setBindings(
            [
                QRhiShaderResourceBinding.sampledTexture(
                    1, QRhiShaderResourceBinding.StageFlag.FragmentStage, texture, self._sampler
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create GlassPanelDisplayWidgetRhi SRB")
        self._srb = srb
        self._bound_texture_id = id(texture)
        assert self._pipeline is not None
        self._pipeline.setShaderResourceBindings(srb)
        if not self._pipeline_created:
            if not self._pipeline.create():
                raise RuntimeError("Failed to create GlassPanelDisplayWidgetRhi pipeline")
            self._pipeline_created = True

    def render(self, command_buffer: QRhiCommandBuffer) -> None:  # type: ignore[override]  # RHI fallback entrypoint, shadows QWidget.render
        rhi = self.rhi()
        target = self.renderTarget()
        if rhi is None or target is None:
            return

        sprites = getattr(self._source_widget, "_glass_panel_sprites", None)
        entry = sprites.get(self._panel_key) if sprites else None
        if entry is not None and self._pipeline is not None:
            texture, _rect_logical = entry
            self._ensure_srb(texture)

        updates = rhi.nextResourceUpdateBatch()
        command_buffer.beginPass(
            target, QColor(0, 0, 0, 0), QRhiDepthStencilClearValue(1.0, 0), updates
        )
        if entry is not None and self._pipeline_created:
            size = target.pixelSize()
            assert self._pipeline is not None
            command_buffer.setGraphicsPipeline(self._pipeline)
            command_buffer.setViewport(
                QRhiViewport(0.0, 0.0, float(size.width()), float(size.height()))
            )
            command_buffer.setShaderResources(self._srb)
            command_buffer.draw(3)
        command_buffer.endPass()


def create_glass_panel_display_widget(parent: QWidget | None = None) -> QWidget:
    """Factory GlassHUD uses instead of constructing a display widget class
    directly -- picks the CPU/QPainter path by default, or the original
    QRhiWidget path if ``IMGSLI_GLASS_PANEL_DISPLAY_BACKEND=rhi`` is set (see
    module-level docstrings on both classes for why CPU is the default now
    and RHI is kept only as an escape hatch)."""
    if _USE_RHI_DISPLAY:
        return GlassPanelDisplayWidgetRhi(parent)
    return GlassPanelDisplayWidgetCpu(parent)


# Backwards-compatible alias: existing call sites/tests referring to
# GlassPanelDisplayWidget get the CPU path (the new default).
GlassPanelDisplayWidget = GlassPanelDisplayWidgetCpu

GlassPanelDisplayWidgetCpu.inspect_spec = InspectSpec(
    family="GlassPanelDisplayWidgetCpu",
    docs="docs/dev/widgets/glass_panel_display.md",
    regions=True,
    layers=True,
)
