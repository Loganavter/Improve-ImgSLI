import logging
from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QListView

from toolkit.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar

logger = logging.getLogger("ImproveImgSLI")

class OverlayListView(QListView):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar_width = 10
        self._scrollbar_gap = 0

        self.verticalScrollBar().valueChanged.connect(self.custom_v_scrollbar.setValue)
        self.custom_v_scrollbar.valueChanged.connect(self.verticalScrollBar().setValue)

        self.verticalScrollBar().rangeChanged.connect(self.custom_v_scrollbar.setRange)
        self.verticalScrollBar().rangeChanged.connect(self._sync_steps_from_native)

        self.custom_v_scrollbar.setVisible(False)
        self._sync_steps_from_native()

        self.custom_v_scrollbar.installEventFilter(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scrollbar()
        self._sync_steps_from_native()
        self._update_scrollbar_visibility()

    def _sync_steps_from_native(self):
        native = self.verticalScrollBar()
        try:
            self.custom_v_scrollbar.setPageStep(native.pageStep())
            self.custom_v_scrollbar.setSingleStep(native.singleStep())
        except Exception:
            pass

    def _update_scrollbar_visibility(self):

        scrollbar = self.verticalScrollBar()
        viewport_height = self.viewport().height()
        max_value = scrollbar.maximum()

        need_scrollbar = max_value > 0

        if need_scrollbar:

            self.setViewportMargins(0, 0, self._scrollbar_width + self._scrollbar_gap, 0)
            self.custom_v_scrollbar.setVisible(True)
        else:
            self.setViewportMargins(0, 0, 0, 0)
            self.custom_v_scrollbar.setVisible(False)

        self._position_scrollbar()

    def _position_scrollbar(self):
        x = self.width() - self._scrollbar_width
        self.custom_v_scrollbar.setGeometry(x, 0, self._scrollbar_width, self.height())
        self.custom_v_scrollbar.raise_()

    def updateGeometries(self):
        super().updateGeometries()
        self._update_scrollbar_visibility()

    def eventFilter(self, obj, event):
        if obj == self.custom_v_scrollbar:
            if event.type() == QEvent.Type.MouseButtonPress:
                logger.debug(f"[OverlayListView] Mouse press on scrollbar at {event.pos()}")
            elif event.type() == QEvent.Type.MouseButtonRelease:
                logger.debug(f"[OverlayListView] Mouse release on scrollbar at {event.pos()}")
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.pos()
        if self.custom_v_scrollbar.isVisible():
            scrollbar_rect = QRect(
                self.custom_v_scrollbar.x(),
                self.custom_v_scrollbar.y(),
                self.custom_v_scrollbar.width(),
                self.custom_v_scrollbar.height()
            )
            if scrollbar_rect.contains(pos):
                logger.debug(f"[OverlayListView] Click on scrollbar at {pos}, scrollbar_rect={scrollbar_rect}")

                scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(event.globalPosition().toPoint())
                scrollbar_event = QMouseEvent(
                    event.type(),
                    scrollbar_pos,
                    event.globalPosition(),
                    event.button(),
                    event.buttons(),
                    event.modifiers()
                )
                result = QApplication.sendEvent(self.custom_v_scrollbar, scrollbar_event)
                logger.debug(f"[OverlayListView] Sent event to scrollbar, result={result}")
                if result:
                    event.accept()
                    return
        super().mousePressEvent(event)

