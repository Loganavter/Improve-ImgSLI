"""Preview pane for the export dialog: the source is stretched, not rebaked.

Split out of ``dialog_sections.py`` when the pane grew a paint path of its own
(the module crossed the 500-line file-size policy). ``build_preview_pane`` still
attaches ``preview_label`` / ``export_preview_title`` / ``export_preview_frame``
to the dialog, exactly as before.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from plugins.export import layout_geometry as export_geo
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Text

#: Row-label typography for the preview caption. The app registers
#: ``group-title`` as 14 design px / regular — the same scale the video editor's
#: export labels use (``dialog_sections._LABEL_VARIANT``).
_PREVIEW_TITLE_VARIANT = "group-title"


class ExportPreviewLabel(QLabel):
    """Preview surface that stretches its source at paint time.

    ``sizeHint`` deliberately ignores the pixmap: a normal QLabel reports the
    pixmap size as sizeHint, and after CSD ``adjustSize`` that blows the dialog
    up to hundreds of px, making ``export_preview_min_width()`` look like a
    no-op.

    The image is never ``setPixmap``-ed. The source stays on the label and
    ``paintEvent`` draws it aspect-fitted into the *current* contents rect —
    the same shape as the compare canvases, which draw their scene at the
    current size every frame and therefore resize as a stretch.

    Do not reintroduce a per-resize rebake (owner report 2026-10-28: "вместо
    растягивания его будто просто убивают и заново создают каждый кадр").
    ``ExportDialog`` used to run ``QPixmap.scaled(SmoothTransformation)`` on the
    full-size source from ``resizeEvent`` and hand each result to ``setPixmap``:
    a brand-new bitmap per frame, so the pane popped frame-by-frame instead of
    following the window edge. ``bake_preview`` keeps only the useful half —
    one smooth raster for the *settled* size, keyed by source/size/DPR/fill so a
    stale bake can never be painted at another size (same keyed-cache shape as
    the toolkit's ``buttons/content.py``).
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._preview_source: QPixmap | None = None
        self._preview_source_key: int | None = None
        self._preview_fill: QColor | None = None
        self._baked: QPixmap | None = None
        self._baked_key: tuple | None = None

    def sizeHint(self) -> QSize:
        return QSize(
            max(self.minimumWidth(), export_geo.export_preview_min_width()),
            max(self.minimumHeight(), export_geo.export_preview_min_height()),
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # -- source / fill -----------------------------------------------------

    def set_preview_source(self, source: QPixmap | None, fill: QColor | None = None) -> None:
        """Point the pane at *source*, painted at whatever size it gets."""
        source_key = None if source is None else source.cacheKey()
        fill_key = None if fill is None else fill.rgba()
        if source_key == self._preview_source_key and fill_key == self._fill_key():
            # Same picture: a settled bake for this size is still valid, and a
            # stale one is simply not painted (paintEvent compares the key).
            return
        self._preview_source = None if source is None or source.isNull() else source
        self._preview_source_key = source_key
        self._preview_fill = None if fill is None else QColor(fill)
        self._baked = None
        self._baked_key = None
        self.update()

    def clear_preview(self) -> None:
        self.set_preview_source(None, None)

    # -- geometry ----------------------------------------------------------

    def preview_target_rect(self) -> QRect:
        """Aspect-fitted destination box inside the current contents rect.

        Same three-step target the dialog always resolved: the live size, then
        the label minimum, then the design-px floor from
        ``plugins.export.layout_geometry``. An empty target simply paints
        nothing.
        """
        rect = self.contentsRect()
        if rect.isEmpty():
            size = self.minimumSize()
            if size.isEmpty():
                size = QSize(
                    export_geo.export_preview_min_width(),
                    export_geo.export_preview_min_height(),
                )
            rect = QRect(0, 0, size.width(), size.height())
        source = self._preview_source
        if source is None or source.isNull() or rect.isEmpty():
            return QRect()
        ratio = max(1.0, float(source.devicePixelRatio() or 1.0))
        logical = QSize(
            max(1, int(round(source.width() / ratio))),
            max(1, int(round(source.height() / ratio))),
        )
        fitted = logical.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect(
            rect.x() + (rect.width() - fitted.width()) // 2,
            rect.y() + (rect.height() - fitted.height()) // 2,
            fitted.width(),
            fitted.height(),
        )

    def baked_preview_size(self) -> QSize:
        """Logical size of the settled raster (empty when not baked yet)."""
        if self._baked is None or self._baked.isNull():
            return QSize()
        ratio = max(1.0, float(self._baked.devicePixelRatio() or 1.0))
        return QSize(
            int(round(self._baked.width() / ratio)),
            int(round(self._baked.height() / ratio)),
        )

    # -- settled raster ----------------------------------------------------

    def _fill_key(self) -> int | None:
        return None if self._preview_fill is None else self._preview_fill.rgba()

    def _device_ratio(self) -> float:
        return max(1.0, float(self.devicePixelRatioF()))

    def _bake_key_for(self, target: QRect) -> tuple:
        return (
            self._preview_source_key,
            target.width(),
            target.height(),
            round(self._device_ratio(), 3),
            self._fill_key(),
        )

    def bake_preview(self) -> None:
        """Rasterize one smooth frame for the settled size (paint shortcut)."""
        source = self._preview_source
        target = self.preview_target_rect()
        if source is None or source.isNull() or target.isEmpty():
            self._baked = None
            self._baked_key = None
            self.update()
            return
        key = self._bake_key_for(target)
        if key == self._baked_key and self._baked is not None:
            return
        ratio = self._device_ratio()
        baked = source.scaled(
            max(1, int(round(target.width() * ratio))),
            max(1, int(round(target.height() * ratio))),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if baked.isNull():
            self._baked = None
            self._baked_key = None
            return
        baked.setDevicePixelRatio(ratio)
        if self._preview_fill is not None:
            # Fill only the export frame (virtual canvas), like the export does.
            composed = QPixmap(baked.size())
            composed.setDevicePixelRatio(ratio)
            composed.fill(self._preview_fill)
            painter = QPainter(composed)
            try:
                painter.drawPixmap(0, 0, baked)
            finally:
                painter.end()
            baked = composed
        self._baked = baked
        self._baked_key = key
        self.update()

    # -- paint -------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        source = self._preview_source
        if source is None or source.isNull():
            return
        target = self.preview_target_rect()
        if target.isEmpty():
            return
        painter = QPainter(self)
        try:
            baked = self._baked
            if baked is not None and self._baked_key == self._bake_key_for(target):
                # Settled size: blit the smooth raster 1:1, no resample.
                painter.drawPixmap(target.topLeft(), baked)
                return
            if self._preview_fill is not None:
                painter.fillRect(target, self._preview_fill)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(target, source)
        finally:
            painter.end()


def build_preview_pane(dialog) -> QFrame:
    left_frame = QFrame()
    left_frame.setObjectName("ExportPreviewFrame")
    dialog.export_preview_frame = left_frame
    left_layout = QVBoxLayout(left_frame)
    left_layout.setContentsMargins(scaled_px(8), scaled_px(8), scaled_px(8), scaled_px(8))
    left_layout.setSpacing(scaled_px(8))

    dialog.export_preview_title = Text(
        dialog._tr("export.preview", "Preview"),
        mode="plain",
        variant=_PREVIEW_TITLE_VARIANT,
    )
    dialog.export_preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.preview_label = ExportPreviewLabel()
    dialog.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.preview_label.setMinimumSize(
        QSize(
            export_geo.export_preview_min_width(),
            export_geo.export_preview_min_height(),
        )
    )
    dialog.preview_label.setFrameShape(QFrame.Shape.NoFrame)
    dialog.preview_label.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )

    left_layout.addWidget(dialog.export_preview_title)
    left_layout.addWidget(dialog.preview_label, 1)
    return left_frame
