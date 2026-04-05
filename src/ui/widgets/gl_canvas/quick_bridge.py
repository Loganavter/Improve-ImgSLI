from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor

class QuickCanvasBridge(QObject):
    backgroundColorChanged = pyqtSignal()
    sourceLeftChanged = pyqtSignal()
    sourceRightChanged = pyqtSignal()
    splitPositionChanged = pyqtSignal()
    isHorizontalChanged = pyqtSignal()
    showDividerChanged = pyqtSignal()
    dividerColorChanged = pyqtSignal()
    dividerThicknessChanged = pyqtSignal()
    contentXChanged = pyqtSignal()
    contentYChanged = pyqtSignal()
    contentWidthChanged = pyqtSignal()
    contentHeightChanged = pyqtSignal()
    zoomLevelChanged = pyqtSignal()
    panOffsetXChanged = pyqtSignal()
    panOffsetYChanged = pyqtSignal()
    magnifierSourceChanged = pyqtSignal()
    magnifierVisibleChanged = pyqtSignal()
    magnifierXChanged = pyqtSignal()
    magnifierYChanged = pyqtSignal()
    captureVisibleChanged = pyqtSignal()
    captureXChanged = pyqtSignal()
    captureYChanged = pyqtSignal()
    captureRadiusChanged = pyqtSignal()
    captureColorChanged = pyqtSignal()
    guidesVisibleChanged = pyqtSignal()
    guidesColorChanged = pyqtSignal()
    guidesThicknessChanged = pyqtSignal()
    overlayCentersChanged = pyqtSignal()
    overlayRadiusChanged = pyqtSignal()
    dragOverlayVisibleChanged = pyqtSignal()
    dragOverlayHorizontalChanged = pyqtSignal()
    dragOverlayPrimaryTextChanged = pyqtSignal()
    dragOverlaySecondaryTextChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._background_color = QColor(32, 32, 32)
        self._source_left = ""
        self._source_right = ""
        self._split_position = 0.5
        self._is_horizontal = False
        self._show_divider = False
        self._divider_color = QColor(255, 255, 255, 255)
        self._divider_thickness = 2.0
        self._content_x = 0.0
        self._content_y = 0.0
        self._content_width = 0.0
        self._content_height = 0.0
        self._zoom_level = 1.0
        self._pan_offset_x = 0.0
        self._pan_offset_y = 0.0
        self._magnifier_source = ""
        self._magnifier_visible = False
        self._magnifier_x = 0.0
        self._magnifier_y = 0.0
        self._capture_visible = False
        self._capture_x = 0.0
        self._capture_y = 0.0
        self._capture_radius = 0.0
        self._capture_color = QColor(255, 50, 100, 230)
        self._guides_visible = False
        self._guides_color = QColor(255, 255, 255, 120)
        self._guides_thickness = 1.0
        self._overlay_centers = []
        self._overlay_radius = 0.0
        self._drag_overlay_visible = False
        self._drag_overlay_horizontal = False
        self._drag_overlay_primary_text = ""
        self._drag_overlay_secondary_text = ""

    def _set_value(self, attr: str, value, signal):
        if getattr(self, attr) == value:
            return
        setattr(self, attr, value)
        signal.emit()

    @pyqtProperty(QColor, notify=backgroundColorChanged)
    def backgroundColor(self):
        return self._background_color

    def set_background_color(self, color: QColor):
        self._set_value("_background_color", QColor(color), self.backgroundColorChanged)

    @pyqtProperty(str, notify=sourceLeftChanged)
    def sourceLeft(self):
        return self._source_left

    def set_source_left(self, value: str):
        self._set_value("_source_left", value or "", self.sourceLeftChanged)

    @pyqtProperty(str, notify=sourceRightChanged)
    def sourceRight(self):
        return self._source_right

    def set_source_right(self, value: str):
        self._set_value("_source_right", value or "", self.sourceRightChanged)

    @pyqtProperty(float, notify=splitPositionChanged)
    def splitPosition(self):
        return self._split_position

    def set_split_position(self, value: float):
        self._set_value("_split_position", float(value or 0.0), self.splitPositionChanged)

    @pyqtProperty(bool, notify=isHorizontalChanged)
    def isHorizontal(self):
        return self._is_horizontal

    def set_is_horizontal(self, value: bool):
        self._set_value("_is_horizontal", bool(value), self.isHorizontalChanged)

    @pyqtProperty(bool, notify=showDividerChanged)
    def showDivider(self):
        return self._show_divider

    def set_show_divider(self, value: bool):
        self._set_value("_show_divider", bool(value), self.showDividerChanged)

    @pyqtProperty(QColor, notify=dividerColorChanged)
    def dividerColor(self):
        return self._divider_color

    def set_divider_color(self, value: QColor):
        self._set_value("_divider_color", QColor(value), self.dividerColorChanged)

    @pyqtProperty(float, notify=dividerThicknessChanged)
    def dividerThickness(self):
        return self._divider_thickness

    def set_divider_thickness(self, value: float):
        self._set_value(
            "_divider_thickness",
            float(value or 0.0),
            self.dividerThicknessChanged,
        )

    @pyqtProperty(float, notify=contentXChanged)
    def contentX(self):
        return self._content_x

    def set_content_x(self, value: float):
        self._set_value("_content_x", float(value or 0.0), self.contentXChanged)

    @pyqtProperty(float, notify=contentYChanged)
    def contentY(self):
        return self._content_y

    def set_content_y(self, value: float):
        self._set_value("_content_y", float(value or 0.0), self.contentYChanged)

    @pyqtProperty(float, notify=contentWidthChanged)
    def contentWidth(self):
        return self._content_width

    def set_content_width(self, value: float):
        self._set_value("_content_width", float(value or 0.0), self.contentWidthChanged)

    @pyqtProperty(float, notify=contentHeightChanged)
    def contentHeight(self):
        return self._content_height

    def set_content_height(self, value: float):
        self._set_value("_content_height", float(value or 0.0), self.contentHeightChanged)

    @pyqtProperty(float, notify=zoomLevelChanged)
    def zoomLevel(self):
        return self._zoom_level

    def set_zoom_level(self, value: float):
        self._set_value("_zoom_level", float(value or 1.0), self.zoomLevelChanged)

    @pyqtProperty(float, notify=panOffsetXChanged)
    def panOffsetX(self):
        return self._pan_offset_x

    def set_pan_offset_x(self, value: float):
        self._set_value("_pan_offset_x", float(value or 0.0), self.panOffsetXChanged)

    @pyqtProperty(float, notify=panOffsetYChanged)
    def panOffsetY(self):
        return self._pan_offset_y

    def set_pan_offset_y(self, value: float):
        self._set_value("_pan_offset_y", float(value or 0.0), self.panOffsetYChanged)

    @pyqtProperty(str, notify=magnifierSourceChanged)
    def magnifierSource(self):
        return self._magnifier_source

    def set_magnifier_source(self, value: str):
        self._set_value("_magnifier_source", value or "", self.magnifierSourceChanged)

    @pyqtProperty(bool, notify=magnifierVisibleChanged)
    def magnifierVisible(self):
        return self._magnifier_visible

    def set_magnifier_visible(self, value: bool):
        self._set_value("_magnifier_visible", bool(value), self.magnifierVisibleChanged)

    @pyqtProperty(float, notify=magnifierXChanged)
    def magnifierX(self):
        return self._magnifier_x

    def set_magnifier_x(self, value: float):
        self._set_value("_magnifier_x", float(value or 0.0), self.magnifierXChanged)

    @pyqtProperty(float, notify=magnifierYChanged)
    def magnifierY(self):
        return self._magnifier_y

    def set_magnifier_y(self, value: float):
        self._set_value("_magnifier_y", float(value or 0.0), self.magnifierYChanged)

    @pyqtProperty(bool, notify=captureVisibleChanged)
    def captureVisible(self):
        return self._capture_visible

    def set_capture_visible(self, value: bool):
        self._set_value("_capture_visible", bool(value), self.captureVisibleChanged)

    @pyqtProperty(float, notify=captureXChanged)
    def captureX(self):
        return self._capture_x

    def set_capture_x(self, value: float):
        self._set_value("_capture_x", float(value or 0.0), self.captureXChanged)

    @pyqtProperty(float, notify=captureYChanged)
    def captureY(self):
        return self._capture_y

    def set_capture_y(self, value: float):
        self._set_value("_capture_y", float(value or 0.0), self.captureYChanged)

    @pyqtProperty(float, notify=captureRadiusChanged)
    def captureRadius(self):
        return self._capture_radius

    def set_capture_radius(self, value: float):
        self._set_value("_capture_radius", float(value or 0.0), self.captureRadiusChanged)

    @pyqtProperty(QColor, notify=captureColorChanged)
    def captureColor(self):
        return self._capture_color

    def set_capture_color(self, value: QColor):
        self._set_value("_capture_color", QColor(value), self.captureColorChanged)

    @pyqtProperty(bool, notify=guidesVisibleChanged)
    def guidesVisible(self):
        return self._guides_visible

    def set_guides_visible(self, value: bool):
        self._set_value("_guides_visible", bool(value), self.guidesVisibleChanged)

    @pyqtProperty(QColor, notify=guidesColorChanged)
    def guidesColor(self):
        return self._guides_color

    def set_guides_color(self, value: QColor):
        self._set_value("_guides_color", QColor(value), self.guidesColorChanged)

    @pyqtProperty(float, notify=guidesThicknessChanged)
    def guidesThickness(self):
        return self._guides_thickness

    def set_guides_thickness(self, value: float):
        self._set_value("_guides_thickness", float(value or 0.0), self.guidesThicknessChanged)

    @pyqtProperty("QVariantList", notify=overlayCentersChanged)
    def overlayCenters(self):
        return self._overlay_centers

    def set_overlay_centers(self, value):
        self._set_value("_overlay_centers", list(value or []), self.overlayCentersChanged)

    @pyqtProperty(float, notify=overlayRadiusChanged)
    def overlayRadius(self):
        return self._overlay_radius

    def set_overlay_radius(self, value: float):
        self._set_value("_overlay_radius", float(value or 0.0), self.overlayRadiusChanged)

    @pyqtProperty(bool, notify=dragOverlayVisibleChanged)
    def dragOverlayVisible(self):
        return self._drag_overlay_visible

    def set_drag_overlay_visible(self, value: bool):
        self._set_value(
            "_drag_overlay_visible",
            bool(value),
            self.dragOverlayVisibleChanged,
        )

    @pyqtProperty(bool, notify=dragOverlayHorizontalChanged)
    def dragOverlayHorizontal(self):
        return self._drag_overlay_horizontal

    def set_drag_overlay_horizontal(self, value: bool):
        self._set_value(
            "_drag_overlay_horizontal",
            bool(value),
            self.dragOverlayHorizontalChanged,
        )

    @pyqtProperty(str, notify=dragOverlayPrimaryTextChanged)
    def dragOverlayPrimaryText(self):
        return self._drag_overlay_primary_text

    def set_drag_overlay_primary_text(self, value: str):
        self._set_value(
            "_drag_overlay_primary_text",
            value or "",
            self.dragOverlayPrimaryTextChanged,
        )

    @pyqtProperty(str, notify=dragOverlaySecondaryTextChanged)
    def dragOverlaySecondaryText(self):
        return self._drag_overlay_secondary_text

    def set_drag_overlay_secondary_text(self, value: str):
        self._set_value(
            "_drag_overlay_secondary_text",
            value or "",
            self.dragOverlaySecondaryTextChanged,
        )

    def reset(self):
        self.set_source_left("")
        self.set_source_right("")
        self.set_zoom_level(1.0)
        self.set_pan_offset_x(0.0)
        self.set_pan_offset_y(0.0)
        self.set_magnifier_source("")
        self.set_magnifier_visible(False)
        self.set_magnifier_x(0.0)
        self.set_magnifier_y(0.0)
        self.set_capture_visible(False)
        self.set_capture_x(0.0)
        self.set_capture_y(0.0)
        self.set_capture_radius(0.0)
        self.set_overlay_centers([])
        self.set_overlay_radius(0.0)
        self.set_drag_overlay_visible(False)
        self.set_drag_overlay_horizontal(False)
        self.set_drag_overlay_primary_text("")
        self.set_drag_overlay_secondary_text("")
