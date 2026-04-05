from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image as PilImage
from PyQt6.QtCore import QPoint, QPointF, QRectF, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPainterPath, QPalette, QPen, QPixmap, QWheelEvent
from PyQt6.QtQuickWidgets import QQuickWidget

from .quick_bridge import QuickCanvasBridge
from .quick_geometry import (
    QuickContentRect,
    build_content_rect,
    compute_display_split_position,
    map_screen_to_image_rel,
)
from .quick_image_provider import QuickCanvasImageProvider
from .quick_overlay_state import QuickOverlayState
from .quick_scene_sync import apply_scene_to_bridge, scene_signature
from .scene import build_gl_render_scene
from .interaction import compute_split_position_for_view_transform

logger = logging.getLogger("ImproveImgSLI")

def _float_attr(obj, attr: str, default: float) -> float:
    if obj is None:
        return float(default)
    value = getattr(obj, attr, None)
    if value is None:
        return float(default)
    return float(value)

def _pil_to_qimage(image: PilImage.Image | None) -> QImage | None:
    if image is None:
        return None
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()

def _to_qcolor(value) -> QColor:
    if isinstance(value, QColor):
        return QColor(value)
    if isinstance(value, tuple) and len(value) in {3, 4}:
        if any(isinstance(component, float) and component <= 1.0 for component in value):
            rgba = [int(max(0.0, min(1.0, float(component))) * 255.0) for component in value]
        else:
            rgba = [int(component) for component in value]
        while len(rgba) < 4:
            rgba.append(255)
        return QColor(rgba[0], rgba[1], rgba[2], rgba[3])
    return QColor(255, 255, 255, 255)

class GLCanvas(QQuickWidget):
    supports_legacy_gl_magnifier = False
    uses_quick_canvas_overlay = True

    mousePressed = pyqtSignal(object)
    mouseMoved = pyqtSignal(object)
    mouseReleased = pyqtSignal(object)
    wheelScrolled = pyqtSignal(object)
    zoomChanged = pyqtSignal(float)
    keyPressed = pyqtSignal(object)
    keyReleased = pyqtSignal(object)
    pasteOverlayDirectionSelected = pyqtSignal(str)
    pasteOverlayCancelled = pyqtSignal()
    firstFrameRendered = pyqtSignal()
    firstVisualFrameReady = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = None
        self._render_scene = None
        self._split_position_sync = None
        self._alignment = Qt.AlignmentFlag.AlignCenter
        self._drag_overlay_visible = False
        self._first_frame_rendered_emitted = False
        self._first_visual_frame_emitted = False
        self._base_revision_ref = [0]
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.split_position = 0.5
        self.is_horizontal = False
        self._apply_channel_mode_in_shader = True
        self._store_change_callback = None
        self._stored_qimages = [None, None]
        self._source_qimages = [None, None]
        self._diff_source_qimage = None
        self._content_rect_override = None
        self._last_scene_debug_signature = None
        self._pan_dragging = False
        self._pan_last_pos = QPointF()
        self._provider_id = f"canvas_{id(self)}"
        self._image_provider = QuickCanvasImageProvider()
        self._bridge = QuickCanvasBridge(self)
        self._overlay_state = QuickOverlayState(
            bridge=self._bridge,
            image_provider=self._image_provider,
            provider_id=self._provider_id,
            base_revision_ref=self._base_revision_ref,
        )

        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.engine().addImageProvider(self._provider_id, self._image_provider)
        self.rootContext().setContextProperty("canvasBridge", self._bridge)
        self._sync_palette_background()
        qml_path = Path(__file__).with_name("qml") / "QuickCanvasProbe.qml"
        self.setSource(QUrl.fromLocalFile(str(qml_path)))
        self.destroyed.connect(self._dispose)
        QTimer.singleShot(0, self._sync_root_state)

    def _dispose(self, *_args):
        try:
            self._bridge.reset()
            self._image_provider.clear()
            self.setSource(QUrl())
        except Exception:
            logger.exception("Quick canvas dispose failed")

    def closeEvent(self, event):
        self._dispose()
        super().closeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        self._emit_first_visual_frame_ready()

    def _set_source_urls(self):
        self._base_revision_ref[0] += 1
        revision = self._base_revision_ref[0]
        self._bridge.set_source_left(f"image://{self._provider_id}/left?v={revision}")
        self._bridge.set_source_right(f"image://{self._provider_id}/right?v={revision}")
        self.update()
        QTimer.singleShot(0, self._emit_first_frame_rendered)

    def _sync_root_state(self):
        self._bridge.set_split_position(self.split_position)
        self._bridge.set_is_horizontal(self.is_horizontal)
        self._bridge.set_zoom_level(self.zoom_level)
        self._bridge.set_pan_offset_x(self.pan_offset_x)
        self._bridge.set_pan_offset_y(self.pan_offset_y)
        self._bridge.set_drag_overlay_visible(self._drag_overlay_visible)
        self._sync_palette_background()
        if self._render_scene is not None:
            self._apply_render_scene(self._render_scene)
        self.update()

    def _emit_first_frame_rendered(self):
        if self._first_frame_rendered_emitted:
            return
        self._first_frame_rendered_emitted = True
        self.firstFrameRendered.emit()

    def _emit_first_visual_frame_ready(self):
        if self._first_visual_frame_emitted:
            return
        self._first_visual_frame_emitted = True
        self.firstVisualFrameReady.emit()

    def setAlignment(self, alignment):
        self._alignment = alignment

    def alignment(self):
        return self._alignment

    def setPalette(self, palette):
        super().setPalette(palette)
        self._sync_palette_background()

    def _sync_palette_background(self):
        bg = self.palette().color(QPalette.ColorRole.Window)
        if not bg.isValid():
            bg = self.palette().color(QPalette.ColorRole.Base)
        if not bg.isValid():
            bg = QColor(32, 32, 32)
        self.setClearColor(QColor(bg))
        self.setStyleSheet(
            f"background-color: {bg.name(QColor.NameFormat.HexArgb)};"
        )
        self._bridge.set_background_color(bg)

    def set_store(self, store):
        self._store = store
        self._refresh_render_scene()
        if hasattr(store, "on_change") and self._store_change_callback is None:
            self._store_change_callback = lambda _scope: self._refresh_render_scene()
            store.on_change(self._store_change_callback)

    def _refresh_render_scene(self):
        if self._store is None:
            return
        self.set_render_scene(
            build_gl_render_scene(
                self._store,
                apply_channel_mode_in_shader=self._apply_channel_mode_in_shader,
            )
        )

    def set_render_scene(self, scene):
        self._render_scene = scene
        signature = scene_signature(scene, self.split_position, self.is_horizontal)
        if signature != self._last_scene_debug_signature:
            self._last_scene_debug_signature = signature
        self._apply_render_scene(scene)
        self.update()

    def _apply_render_scene(self, scene):
        if scene is None:
            return
        left = self._stored_qimages[0]
        image_width = 0 if left is None or left.isNull() else left.width()
        image_height = 0 if left is None or left.isNull() else left.height()
        if self._content_rect_override is not None:
            self.is_horizontal = bool(getattr(scene, "is_horizontal", False))
            split_visual = _float_attr(
                scene, "split_position_visual", self.split_position
            )
            content_rect = self._content_rect_override
            self._bridge.set_is_horizontal(self.is_horizontal)
            self._bridge.set_show_divider(bool(getattr(scene, "show_divider", False)))
            self._bridge.set_divider_color(
                QColor(getattr(scene, "divider_color", QColor(255, 255, 255, 255)))
            )
            self._bridge.set_divider_thickness(
                float(max(1, int(getattr(scene, "divider_thickness", 2) or 2)))
            )
            self._bridge.set_content_x(float(content_rect.x))
            self._bridge.set_content_y(float(content_rect.y))
            self._bridge.set_content_width(float(content_rect.width))
            self._bridge.set_content_height(float(content_rect.height))
            if self.is_horizontal:
                base = (
                    float(content_rect.y) + (float(content_rect.height) * split_visual)
                ) / max(1.0, float(self.height()))
                pan = self.pan_offset_y
            else:
                base = (
                    float(content_rect.x) + (float(content_rect.width) * split_visual)
                ) / max(1.0, float(self.width()))
                pan = self.pan_offset_x
            self.split_position = max(
                0.0,
                min(1.0, (base - 0.5 + pan) * self.zoom_level + 0.5),
            )
            self._bridge.set_split_position(self.split_position)
        else:
            self.is_horizontal, self.split_position = apply_scene_to_bridge(
                bridge=self._bridge,
                scene=scene,
                image_width=image_width,
                image_height=image_height,
                widget_width=self.width(),
                widget_height=self.height(),
                zoom_level=self.zoom_level,
                pan_offset_x=self.pan_offset_x,
                pan_offset_y=self.pan_offset_y,
            )
        self.update()

    def _compute_display_split_position(self, scene, split_visual: float | None = None) -> float:
        if split_visual is None:
            split_visual = _float_attr(
                scene, "split_position_visual", self.split_position
            )
        img = self._stored_qimages[0]
        w = self.width()
        h = self.height()
        if img is None or img.isNull() or w <= 0 or h <= 0:
            return split_visual
        return compute_display_split_position(
            widget_width=w,
            widget_height=h,
            image_width=img.width(),
            image_height=img.height(),
            split_visual=split_visual,
            is_horizontal=bool(getattr(scene, "is_horizontal", False)),
            zoom_level=self.zoom_level,
            pan_offset_x=self.pan_offset_x,
            pan_offset_y=self.pan_offset_y,
        )

    def map_cursor_to_image_rel(self, cursor_pos: QPointF) -> tuple[float | None, float | None]:
        image = self._stored_qimages[0]
        if image is None or image.isNull():
            return None, None
        return map_screen_to_image_rel(
            cursor_x=float(cursor_pos.x()),
            cursor_y=float(cursor_pos.y()),
            widget_width=self.width(),
            widget_height=self.height(),
            image_width=image.width(),
            image_height=image.height(),
            zoom_level=self.zoom_level,
            pan_offset_x=self.pan_offset_x,
            pan_offset_y=self.pan_offset_y,
        )

    def set_split_position_sync(self, sync_callback):
        self._split_position_sync = sync_callback

    def set_apply_channel_mode_in_shader(self, enabled: bool):
        self._apply_channel_mode_in_shader = bool(enabled)
        self._refresh_render_scene()

    def begin_update_batch(self):
        return None

    def end_update_batch(self):
        return None

    def _set_images(self, left: QImage | None, right: QImage | None):
        self._stored_qimages[0] = left
        self._stored_qimages[1] = right if right is not None else left
        self._image_provider.set_image("left", left)
        self._image_provider.set_image("right", right if right is not None else left)
        if left is None and right is None:
            self._bridge.set_source_left("")
            self._bridge.set_source_right("")
            return
        if self._render_scene is not None:
            self._apply_render_scene(self._render_scene)
        self._set_source_urls()

    def _set_source_images(self, left: QImage | None, right: QImage | None):
        self._source_qimages[0] = left
        self._source_qimages[1] = right if right is not None else left

    def set_layers(self, background: QPixmap | None, magnifier: QPixmap | None, mag_pos: QPoint | None, coords_snapshot=None):
        self._content_rect_override = None
        image = background.toImage() if background is not None and not background.isNull() else None
        self._set_images(image, image)
        self.set_magnifier_content(magnifier, mag_pos)

    def setPixmap(self, pixmap: QPixmap | None):
        self._content_rect_override = None
        image = pixmap.toImage() if pixmap is not None and not pixmap.isNull() else None
        self._set_images(image, image)

    def clear(self):
        self._content_rect_override = None
        self._set_images(None, None)

    def set_pil_layers(
        self,
        pil_image1=None,
        pil_image2=None,
        magnifier=None,
        mag_pos=None,
        source_image1=None,
        source_image2=None,
        source_key=None,
        shader_letterbox: bool = False,
    ):
        self._content_rect_override = None
        left = _pil_to_qimage(pil_image1 or source_image1)
        right = _pil_to_qimage(pil_image2 or source_image2 or pil_image1 or source_image1)
        src_left = _pil_to_qimage(source_image1 or pil_image1)
        src_right = _pil_to_qimage(source_image2 or pil_image2 or source_image1 or pil_image1)
        self._set_source_images(src_left, src_right)
        self._set_images(left, right)
        if magnifier is not None and hasattr(magnifier, "isNull"):
            self.set_magnifier_content(magnifier, mag_pos)
        else:
            self.set_magnifier_content(None, None)

    def set_magnifier_content(self, pixmap: QPixmap | None, top_left: QPoint | None):
        self._overlay_state.set_magnifier_content(pixmap, top_left)
        self.update()

    def set_overlay_coords(
        self,
        capture_center: QPointF | None,
        capture_radius: float,
        mag_centers: list[QPointF],
        mag_radius: float,
    ):
        self._overlay_state.set_overlay_coords(
            capture_center, capture_radius, mag_centers, mag_radius
        )
        self.update()

    def _current_content_rect(self):
        if self._content_rect_override is not None:
            return self._content_rect_override
        img = self._stored_qimages[0]
        if img is None or img.isNull():
            return None
        return build_content_rect(
            widget_width=self.width(),
            widget_height=self.height(),
            image_width=img.width(),
            image_height=img.height(),
        )

    def set_split_line_params(
        self,
        visible: bool,
        pos: int,
        is_horizontal: bool,
        color: QColor,
        thickness: int,
    ):
        self._bridge.set_show_divider(bool(visible))
        self._bridge.set_is_horizontal(bool(is_horizontal))
        old_split = float(self.split_position)
        content_rect = self._current_content_rect()
        if content_rect is not None:
            axis_start = content_rect.y if is_horizontal else content_rect.x
            axis_size = max(1.0, content_rect.height if is_horizontal else content_rect.width)
            local_pos = float(pos or 0) - float(axis_start)
            self.split_position = max(0.0, min(1.0, local_pos / axis_size))
        else:
            axis_size = max(1, self.height() if is_horizontal else self.width())
            axis_start = 0.0
            local_pos = float(pos or 0)
            self.split_position = max(0.0, min(1.0, float(pos or 0) / float(axis_size)))
        self._bridge.set_split_position(self.split_position)
        self._bridge.set_divider_color(
            QColor(color) if color is not None else QColor(255, 255, 255, 255)
        )
        self._bridge.set_divider_thickness(float(max(1, int(thickness or 1))))
        self.update()

    def set_guides_params(self, visible: bool, color: QColor, thickness: int):
        self._overlay_state.set_guides_params(visible, color, thickness)
        self.update()

    def set_capture_color(self, color: QColor):
        self._overlay_state.set_capture_color(color)
        self.update()

    def set_capture_area(self, center: QPoint | QPointF | None, size: int | float, color: QColor | None = None):
        if color is not None:
            self.set_capture_color(color)
        self.set_overlay_coords(
            QPointF(float(center.x()), float(center.y())) if center is not None else None,
            float(size or 0.0) / 2.0,
            self._overlay_state.magnifier_centers,
            self._overlay_state.magnifier_radius,
        )

    def upload_diff_source_pil_image(self, pil_image):
        self._diff_source_qimage = _pil_to_qimage(pil_image)

    def _draw_slot_source(
        self,
        painter: QPainter,
        target_rect: QRectF,
        image: QImage | None,
        uv_rect,
    ) -> None:
        if image is None or image.isNull() or not uv_rect:
            return
        left = max(0.0, min(1.0, float(uv_rect[0])))
        top = max(0.0, min(1.0, float(uv_rect[1])))
        right = max(left, min(1.0, float(uv_rect[2])))
        bottom = max(top, min(1.0, float(uv_rect[3])))
        src_rect = QRectF(
            left * image.width(),
            top * image.height(),
            max(1.0, (right - left) * image.width()),
            max(1.0, (bottom - top) * image.height()),
        )
        painter.drawImage(target_rect, image, src_rect)

    def _render_magnifier_overlay(self, slots, border_color: QColor, border_width: float):
        width = max(1, self.width())
        height = max(1, self.height())
        overlay = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        overlay.fill(Qt.GlobalColor.transparent)
        painter = QPainter(overlay)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        try:
            for slot in slots or []:
                if not slot:
                    continue
                center = slot.get("center")
                radius = float(slot.get("radius", 0.0) or 0.0)
                if center is None or radius <= 0.0:
                    continue
                target_rect = QRectF(
                    float(center.x()) - radius,
                    float(center.y()) - radius,
                    radius * 2.0,
                    radius * 2.0,
                )
                clip_path = QPainterPath()
                clip_path.addEllipse(target_rect)
                painter.save()
                painter.setClipPath(clip_path)
                if slot.get("is_combined"):
                    split = max(0.0, min(1.0, float(slot.get("internal_split", 0.5) or 0.5)))
                    horizontal = bool(slot.get("horizontal", False))
                    if horizontal:
                        first_rect = QRectF(target_rect.x(), target_rect.y(), target_rect.width(), target_rect.height() * split)
                        second_rect = QRectF(target_rect.x(), target_rect.y() + target_rect.height() * split, target_rect.width(), target_rect.height() - first_rect.height())
                    else:
                        first_rect = QRectF(target_rect.x(), target_rect.y(), target_rect.width() * split, target_rect.height())
                        second_rect = QRectF(target_rect.x() + target_rect.width() * split, target_rect.y(), target_rect.width() - first_rect.width(), target_rect.height())
                    self._draw_slot_source(painter, first_rect, self._source_qimages[0], slot.get("uv_rect"))
                    self._draw_slot_source(painter, second_rect, self._source_qimages[1], slot.get("uv_rect2") or slot.get("uv_rect"))
                    if slot.get("divider_visible"):
                        pen = QPen(
                            _to_qcolor(slot.get("divider_color", (255, 255, 255, 230))),
                            float(max(1.0, slot.get("divider_thickness_px", 1.0))),
                        )
                        pen.setCosmetic(True)
                        painter.setPen(pen)
                        if horizontal:
                            y = target_rect.y() + target_rect.height() * split
                            painter.drawLine(target_rect.x(), y, target_rect.x() + target_rect.width(), y)
                        else:
                            x = target_rect.x() + target_rect.width() * split
                            painter.drawLine(x, target_rect.y(), x, target_rect.y() + target_rect.height())
                else:
                    source_index = int(slot.get("source", 0) or 0)
                    if source_index == 2:
                        image = self._diff_source_qimage
                    elif source_index == 1:
                        image = self._source_qimages[1]
                    else:
                        image = self._source_qimages[0]
                    self._draw_slot_source(painter, target_rect, image, slot.get("uv_rect"))
                painter.restore()
                pen = QPen(border_color, float(max(1.0, border_width)))
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(target_rect)
        finally:
            painter.end()
        self.set_magnifier_content(QPixmap.fromImage(overlay), QPoint(0, 0))

    def configure_offscreen_render(
        self,
        *,
        stored_images,
        source_images,
        content_rect: tuple[int, int, int, int],
        shader_letterbox: bool = False,
    ):
        del shader_letterbox
        x, y, w, h = content_rect
        self._content_rect_override = QuickContentRect(
            x=float(x),
            y=float(y),
            width=float(max(1, w)),
            height=float(max(1, h)),
        )
        left = _pil_to_qimage(stored_images[0])
        right = _pil_to_qimage(stored_images[1])
        src_left = _pil_to_qimage(source_images[0])
        src_right = _pil_to_qimage(source_images[1])
        self._set_source_images(src_left, src_right)
        self._set_images(left, right)

    def set_drag_overlay_state(
        self,
        visible: bool,
        horizontal: bool = False,
        text1: str = "",
        text2: str = "",
    ):
        self._drag_overlay_visible = bool(visible)
        self._bridge.set_drag_overlay_visible(self._drag_overlay_visible)
        self._bridge.set_drag_overlay_horizontal(bool(horizontal))
        self._bridge.set_drag_overlay_primary_text(text1 or "")
        self._bridge.set_drag_overlay_secondary_text(text2 or "")
        self.update()

    def is_drag_overlay_visible(self) -> bool:
        return bool(self._drag_overlay_visible)

    def set_paste_overlay_state(self, visible: bool, is_horizontal: bool = False, texts: dict | None = None):
        return None

    def is_paste_overlay_visible(self) -> bool:
        return False

    def _paste_overlay_button_at(self, pos: QPointF | QPoint) -> str | None:
        return None

    def _set_paste_overlay_hover(self, hovered: str | None):
        return None

    def set_split_pos(self, pos: float):
        split_visual = max(0.0, min(1.0, float(pos or 0.0)))
        self.split_position = split_visual
        self._bridge.set_split_position(self.split_position)
        self.update()

    def set_zoom(self, zoom: float):
        new_zoom = float(zoom or 1.0)
        self._sync_split_for_view_transform(
            new_zoom,
            float(self.pan_offset_x),
            float(self.pan_offset_y),
        )
        self.zoom_level = new_zoom
        self._bridge.set_zoom_level(self.zoom_level)
        if self._render_scene is not None:
            self._apply_render_scene(self._render_scene)
        self.zoomChanged.emit(self.zoom_level)
        self.update()

    def set_pan(self, x: float, y: float):
        new_pan_x = float(x or 0.0)
        new_pan_y = float(y or 0.0)
        self._sync_split_for_view_transform(
            float(self.zoom_level),
            new_pan_x,
            new_pan_y,
        )
        self.pan_offset_x = new_pan_x
        self.pan_offset_y = new_pan_y
        self._bridge.set_pan_offset_x(self.pan_offset_x)
        self._bridge.set_pan_offset_y(self.pan_offset_y)
        if self._render_scene is not None:
            self._apply_render_scene(self._render_scene)
        self.update()

    def reset_view(self):
        self.set_zoom(1.0)
        self.set_pan(0.0, 0.0)

    def _sync_split_for_view_transform(self, new_zoom: float, new_pan_x: float, new_pan_y: float):
        if self._render_scene is None or self._split_position_sync is None:
            return
        img = self._stored_qimages[0]
        if img is None or img.isNull():
            return
        new_split = compute_split_position_for_view_transform(
            widget_width=self.width(),
            widget_height=self.height(),
            image_width=img.width(),
            image_height=img.height(),
            is_horizontal=bool(getattr(self._render_scene, "is_horizontal", False)),
            split_position_visual=_float_attr(
                self._render_scene, "split_position_visual", self.split_position
            ),
            current_zoom=float(self.zoom_level),
            current_pan_x=float(self.pan_offset_x),
            current_pan_y=float(self.pan_offset_y),
            new_zoom=float(new_zoom),
            new_pan_x=float(new_pan_x),
            new_pan_y=float(new_pan_y),
        )
        if new_split is None:
            return
        try:
            self._split_position_sync(float(new_split))
        except Exception:
            logger.exception("Quick canvas split sync failed during view transform")

    def clear_magnifier_gpu(self):
        self.set_magnifier_content(None, None)
        return None

    def set_magnifier_gpu_params(
        self,
        slots,
        channel_mode_int,
        diff_mode_int,
        diff_threshold,
        border_color,
        border_width,
        interp_mode_int,
    ):
        del channel_mode_int, diff_mode_int, diff_threshold, interp_mode_int
        self._render_magnifier_overlay(
            slots,
            QColor(border_color) if border_color is not None else QColor(255, 255, 255, 248),
            float(border_width or 2.0),
        )
        return None

    def upload_magnifier_crop(self, *args, **kwargs):
        return None

    def upload_combined_magnifier(self, *args, **kwargs):
        return None

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.1 if angle > 0 else 0.9
            new_zoom = max(1.0, min(self.zoom_level * factor, 50.0))
            if abs(new_zoom - self.zoom_level) > 1e-6:
                w, h = self.width(), self.height()
                new_pan_x = self.pan_offset_x
                new_pan_y = self.pan_offset_y
                if w > 0 and h > 0:
                    mx = event.position().x() / w
                    my = event.position().y() / h
                    uv_x = (mx - 0.5) / self.zoom_level + 0.5 - self.pan_offset_x
                    uv_y = (my - 0.5) / self.zoom_level + 0.5 - self.pan_offset_y
                    uv_x = max(0.0, min(1.0, uv_x))
                    uv_y = max(0.0, min(1.0, uv_y))
                    new_pan_x = 0.5 - uv_x + (mx - 0.5) / new_zoom
                    new_pan_y = 0.5 - uv_y + (my - 0.5) / new_zoom
                    if new_zoom < 1.5:
                        t = max(0.0, (new_zoom - 1.0) / 0.5)
                        new_pan_x *= t
                        new_pan_y *= t
                self._sync_split_for_view_transform(new_zoom, new_pan_x, new_pan_y)
                self.zoom_level = float(new_zoom)
                self.pan_offset_x = float(new_pan_x)
                self.pan_offset_y = float(new_pan_y)
                self._bridge.set_zoom_level(self.zoom_level)
                self._bridge.set_pan_offset_x(self.pan_offset_x)
                self._bridge.set_pan_offset_y(self.pan_offset_y)
                if self._render_scene is not None:
                    self._apply_render_scene(self._render_scene)
                self.zoomChanged.emit(self.zoom_level)
                self.update()
            event.accept()
            return
        self.wheelScrolled.emit(event)
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        self.keyPressed.emit(event)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self.keyReleased.emit(event)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_dragging = True
            self._pan_last_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        self.mousePressed.emit(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._pan_dragging and self.zoom_level > 1.0:
            w, h = self.width(), self.height()
            if w > 0 and h > 0:
                dx = (event.position().x() - self._pan_last_pos.x()) / (w * self.zoom_level)
                dy = (event.position().y() - self._pan_last_pos.y()) / (h * self.zoom_level)
                new_pan_x = self.pan_offset_x + dx
                new_pan_y = self.pan_offset_y + dy
                self._sync_split_for_view_transform(self.zoom_level, new_pan_x, new_pan_y)
                self.pan_offset_x = float(new_pan_x)
                self.pan_offset_y = float(new_pan_y)
                self._pan_last_pos = event.position()
                self._bridge.set_pan_offset_x(self.pan_offset_x)
                self._bridge.set_pan_offset_y(self.pan_offset_y)
                if self._render_scene is not None:
                    self._apply_render_scene(self._render_scene)
                self.update()
            event.accept()
            return
        self.mouseMoved.emit(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_dragging:
            self._pan_dragging = False
            self.unsetCursor()
            event.accept()
            return
        self.mouseReleased.emit(event)
        super().mouseReleaseEvent(event)
