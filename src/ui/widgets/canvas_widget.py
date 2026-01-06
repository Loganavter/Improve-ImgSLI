from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QRect
from PyQt6.QtGui import QPainter, QPixmap, QMouseEvent, QKeyEvent, QWheelEvent, QPaintEvent, QColor, QPen, QBrush, QFont, QFontMetrics
from PyQt6.QtWidgets import QWidget, QSizePolicy

class CanvasWidget(QWidget):

    mousePressed = pyqtSignal(QMouseEvent)
    mouseMoved = pyqtSignal(QMouseEvent)
    mouseReleased = pyqtSignal(QMouseEvent)
    keyPressed = pyqtSignal(QKeyEvent)
    keyReleased = pyqtSignal(QKeyEvent)
    wheelScrolled = pyqtSignal(QWheelEvent)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(1, 1)

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)

        self._pixmap_left: QPixmap | None = None
        self._pixmap_right: QPixmap | None = None
        self._background_pixmap: QPixmap | None = None

        self._overlay_pixmap: QPixmap | None = None
        self._overlay_pos: QPoint = QPoint(0, 0)

        self._block_paint = False
        self._last_full_pixmap: QPixmap | None = None

        self._ui_data = {
            "capture_rect": None,
            "capture_color": None,
            "lasers": [],
            "divider_visible": False,
            "divider_pos": 0,
            "divider_horizontal": False,
            "divider_color": None,
            "divider_thickness": 0,
            "split_pos_rel": 0.5,
            "img_rect": QRect(),
            "text_data": None
        }

    def set_layers(self, left: QPixmap | None, right: QPixmap | None):
        self._pixmap_left = left
        self._pixmap_right = right

        if left and right:
            self._background_pixmap = None

        if not self._block_paint:
            self.update()

    def set_background_pixmap(self, pixmap: QPixmap):
        self._background_pixmap = pixmap

        if not self._block_paint:
            if pixmap and not pixmap.isNull():
                self._last_full_pixmap = pixmap.copy()

        self._pixmap_left = None
        self._pixmap_right = None

        if not self._block_paint:
            self.update()

    def set_overlay_pixmap(self, pixmap: QPixmap | None, pos: QPoint = QPoint(0, 0)):
        self._overlay_pixmap = pixmap
        self._overlay_pos = pos
        if not self._block_paint:
            self.update()

    def set_ui_overlays(self, ui_data: dict):
        if ui_data:
            self._ui_data.update(ui_data)
        else:
            self._ui_data = {
                "capture_rect": None,
                "capture_color": None,
                "lasers": [],
                "divider_visible": False,
                "divider_pos": 0,
                "divider_horizontal": False,
                "divider_color": None,
                "divider_thickness": 0,
                "split_pos_rel": 0.5,
                "img_rect": QRect(),
                "text_data": None
            }
        if not self._block_paint:
            self.update()

    def clear(self):
        self._background_pixmap = None
        self._pixmap_left = None
        self._pixmap_right = None
        self._overlay_pixmap = None
        self._ui_data = {
            "capture_rect": None,
            "capture_color": None,
            "lasers": [],
            "divider_visible": False,
            "divider_pos": 0,
            "divider_horizontal": False,
            "divider_color": None,
            "divider_thickness": 0,
            "split_pos_rel": 0.5,
            "img_rect": QRect()
        }
        if not self._block_paint:
            self.update()

    def setPixmap(self, pixmap: QPixmap | None):
        if pixmap:
            self.set_background_pixmap(pixmap)
            self.set_overlay_pixmap(None)
        else:
            self.clear()

    def sizeHint(self):
        return QSize(1, 1)

    def minimumSizeHint(self):
        return QSize(1, 1)

    def paintEvent(self, event: QPaintEvent):

        if self._block_paint:
            if self._last_full_pixmap and not self._last_full_pixmap.isNull():
                painter = QPainter(self)

                painter.drawPixmap(0, 0, self._last_full_pixmap)
                painter.end()
            return

        painter = QPainter(self)

        img_rect = self._ui_data.get("img_rect")
        if not img_rect or img_rect.isEmpty():
            img_rect = self.rect()

        if self._pixmap_left and self._pixmap_right:
            is_horizontal = self._ui_data.get("divider_horizontal", False)

            split_abs = self._ui_data.get("divider_pos", 0)

            if not is_horizontal:

                w_left = split_abs - img_rect.x()
                if w_left > 0:

                    painter.drawPixmap(
                        img_rect.x(), img_rect.y(),
                        self._pixmap_left,
                        0, 0, w_left, self._pixmap_left.height()
                    )

                if w_left < img_rect.width():
                    w_right = img_rect.width() - w_left
                    painter.drawPixmap(
                        split_abs, img_rect.y(),
                        self._pixmap_right,
                        w_left, 0, w_right, self._pixmap_right.height()
                    )
            else:

                h_top = split_abs - img_rect.y()

                if h_top > 0:
                    painter.drawPixmap(
                        img_rect.x(), img_rect.y(),
                        self._pixmap_left,
                        0, 0, self._pixmap_left.width(), h_top
                    )

                if h_top < img_rect.height():
                    h_bottom = img_rect.height() - h_top
                    painter.drawPixmap(
                        img_rect.x(), split_abs,
                        self._pixmap_right,
                        0, h_top, self._pixmap_right.width(), h_bottom
                    )

        elif self._background_pixmap and not self._background_pixmap.isNull():
            painter.drawPixmap(0, 0, self._background_pixmap)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        if self._ui_data.get("divider_visible"):
            d_pos = self._ui_data.get("divider_pos", 0)
            d_th = self._ui_data.get("divider_thickness", 1)
            d_col = self._ui_data.get("divider_color")

            if d_col:
                pen = QPen(d_col)
                pen.setWidth(d_th)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)

                if not self._ui_data.get("divider_horizontal"):
                    painter.drawLine(d_pos, img_rect.top(), d_pos, img_rect.bottom())
                else:
                    painter.drawLine(img_rect.left(), d_pos, img_rect.right(), d_pos)

        self._draw_text_labels(painter)

        for laser_data in self._ui_data.get("lasers", []):
            if len(laser_data) >= 4:
                p1, p2, color, width = laser_data[0], laser_data[1], laser_data[2], laser_data[3]
                if p1 and p2 and color and isinstance(p1, QPoint) and isinstance(p2, QPoint):
                    pen = QPen(color)
                    pen.setWidth(max(1, width))
                    painter.setPen(pen)
                    painter.drawLine(p1, p2)

        cap_rect = self._ui_data.get("capture_rect")
        cap_color = self._ui_data.get("capture_color")
        if cap_rect and cap_color:
            pen = QPen(cap_color)

            import math
            CAPTURE_THICKNESS_FACTOR = 0.1
            MIN_CAPTURE_THICKNESS = 2.0
            MAX_CAPTURE_THICKNESS = 8.0

            size = max(cap_rect.width(), cap_rect.height())
            thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(size)))
            thickness_clamped = max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness_float))
            thickness = max(2, int(round(thickness_clamped)))

            pen.setWidth(thickness)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawEllipse(cap_rect)

        if self._overlay_pixmap and not self._overlay_pixmap.isNull():
            painter.drawPixmap(self._overlay_pos, self._overlay_pixmap)

    def mousePressEvent(self, event: QMouseEvent):
        self.mousePressed.emit(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.mouseMoved.emit(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.mouseReleased.emit(event)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        self.keyPressed.emit(event)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        self.keyReleased.emit(event)
        super().keyReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.wheelScrolled.emit(event)
        event.accept()

    def _draw_text_labels(self, painter: QPainter):
        data = self._ui_data.get("text_data")
        if not data or not data.get("visible"):
            return

        img_rect = self._ui_data.get("img_rect")
        if not img_rect or img_rect.isEmpty():
            img_rect = self.rect()

        divider_visible = self._ui_data.get("divider_visible", False)
        divider_pos = self._ui_data.get("divider_pos", 0)
        line_th = self._ui_data.get("divider_thickness", 2) if divider_visible else 0

        ref_size = min(img_rect.width(), img_rect.height())
        base_font_ratio = 0.03
        font_scale = data.get("font_size_percent", 100) / 100.0
        font_size = max(10, int(ref_size * base_font_ratio * font_scale))

        font = painter.font()
        font.setPixelSize(font_size)
        weight = data.get("font_weight", 0)
        if weight > 0:
            if weight > 50:
                font.setWeight(QFont.Weight.Bold)
            else:
                font.setWeight(QFont.Weight.DemiBold)
        else:
            font.setWeight(QFont.Weight.Normal)

        painter.setFont(font)
        fm = QFontMetrics(font)

        text_color = data.get("color", QColor(255, 0, 0))
        bg_color = data.get("bg_color", QColor(0, 0, 0, 128))
        draw_bg = data.get("draw_bg", True)
        placement = data.get("placement", "edges")
        is_horizontal = data.get("is_horizontal", False)
        max_name_length = data.get("max_name_length", 50)

        safe_gap = 10
        padding = 6

        def draw_single_label(text, slot):
            if not text:
                return

            available_w = 0

            if not is_horizontal:

                if not divider_visible:

                    available_w = (img_rect.width() // 2) - safe_gap * 2
                else:
                    if slot == 1:

                        width_segment = divider_pos - img_rect.left()
                        available_w = width_segment - (line_th // 2) - safe_gap * 2
                    else:

                        width_segment = img_rect.right() - divider_pos
                        available_w = width_segment - (line_th // 2) - safe_gap * 2
            else:

                available_w = img_rect.width() - safe_gap * 2

            text_avail_w = available_w - (padding * 2)

            if text_avail_w < 20:
                return

            # Сохраняем исходную длину текста для проверки
            original_text = text
            was_truncated_by_length = False
            
            # Сначала ограничиваем текст по максимальной длине символов из настроек
            if max_name_length > 0 and len(text) > max_name_length:
                text = text[:max_name_length]
                was_truncated_by_length = True
            
            # Затем применяем elidedText для учета доступной ширины
            # Qt автоматически добавит троеточие, если обрезанный текст не помещается в доступную ширину
            elided_text = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(text_avail_w))
            
            # Если текст был обрезан по длине символов, но Qt не добавил троеточие (текст помещается в ширину),
            # нужно проверить, был ли исходный текст длиннее max_name_length, и если да, добавить троеточие вручную
            if was_truncated_by_length and len(original_text) > max_name_length:
                # Проверяем, было ли добавлено троеточие Qt
                if not (elided_text.endswith("...") or elided_text.endswith("..") or elided_text.endswith(".")):
                    # Если троеточия нет, но текст был обрезан по длине, добавляем его
                    # Но сначала проверяем, помещается ли текст с троеточием в доступную ширину
                    text_with_ellipsis = text + "..."
                    if fm.horizontalAdvance(text_with_ellipsis) <= text_avail_w:
                        elided_text = text_with_ellipsis
                    else:
                        # Если не помещается, применяем elidedText еще раз
                        elided_text = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(text_avail_w))

            text_w = fm.horizontalAdvance(elided_text)
            text_h = fm.height()

            box_w = text_w + padding * 2
            box_h = text_h + padding * 2

            x, y = 0, 0
            half_line = (line_th + 1) // 2

            if not is_horizontal:

                y = img_rect.bottom() - safe_gap - box_h

                if slot == 1:
                    if placement == "split_line" and divider_visible:
                        x = divider_pos - half_line - safe_gap - box_w
                    else:
                        x = img_rect.left() + safe_gap
                else:
                    if placement == "split_line" and divider_visible:
                        x = divider_pos + half_line + safe_gap
                    else:
                        x = img_rect.right() - safe_gap - box_w
            else:

                x = img_rect.left() + (img_rect.width() - box_w) // 2

                if slot == 1:
                    if placement == "split_line" and divider_visible:
                        y = divider_pos - half_line - safe_gap - box_h
                    else:
                        y = img_rect.top() + safe_gap
                else:
                    if placement == "split_line" and divider_visible:
                        y = divider_pos + half_line + safe_gap
                    else:
                        y = img_rect.bottom() - safe_gap - box_h

            x = max(img_rect.left(), min(x, img_rect.right() - box_w))
            y = max(img_rect.top(), min(y, img_rect.bottom() - box_h))

            rect = QRect(int(x), int(y), int(box_w), int(box_h))

            if draw_bg:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(bg_color)
                painter.drawRoundedRect(rect, 6, 6)

            painter.setPen(text_color)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, elided_text)

        draw_single_label(data.get("text1"), 1)
        draw_single_label(data.get("text2"), 2)
