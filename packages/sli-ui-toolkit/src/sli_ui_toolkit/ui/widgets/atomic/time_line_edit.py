from PyQt6.QtCore import QEvent, QRectF, Qt, QTime, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QTimeEdit, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline

class TimeLineEdit(QWidget):
    RADIUS = 6

    textChanged = pyqtSignal(str)
    editingFinished = pyqtSignal()
    returnPressed = pyqtSignal()

    def __init__(self, initial_time: str = "00:05", parent=None):
        super().__init__(parent)
        self.setObjectName("TimeLineEdit")

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

        self._time_edit = QTimeEdit(self)
        self._time_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(QTime.fromString(initial_time, "HH:mm"))

        self._time_edit.timeChanged.connect(self._on_internal_time_changed)
        self._time_edit.editingFinished.connect(self.editingFinished)
        self._time_edit.editingFinished.connect(self.returnPressed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._time_edit)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocusProxy(self._time_edit)

        self._time_edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._time_edit and event.type() in (
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        ):
            QTimer.singleShot(0, self.update)
        return super().eventFilter(obj, event)

    def _on_internal_time_changed(self, time_obj: QTime):
        self.textChanged.emit(time_obj.toString("HH:mm"))

    def text(self) -> str:
        return self._time_edit.time().toString("HH:mm")

    def setText(self, text: str):
        time_obj = QTime.fromString(text, "HH:mm")
        if time_obj.isValid():
            self._time_edit.setTime(time_obj)

    def selectAll(self):
        self._time_edit.setCurrentSection(QTimeEdit.Section.HourSection)

    def timeEdit(self) -> QTimeEdit:
        return self._time_edit

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = self.theme_manager.get_color("dialog.input.background")
        painter.setBrush(bg_color)
        painter.setPen(QColor("transparent"))
        painter.drawRoundedRect(self.rect(), self.RADIUS, self.RADIUS)

        rr = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        thin_border_color = QColor(self.theme_manager.get_color("input.border.thin"))
        alpha = max(8, int(thin_border_color.alpha() * 0.66))
        thin_border_color.setAlpha(alpha)
        pen = QPen(thin_border_color)
        pen.setWidthF(0.66)
        painter.setPen(pen)
        painter.setBrush(QColor("transparent"))
        painter.drawRoundedRect(rr, self.RADIUS, self.RADIUS)

        if self._time_edit.hasFocus():
            underline_config = UnderlineConfig(
                color=self.theme_manager.get_color("accent"),
                alpha=255,
                thickness=1.0,
            )
        else:
            underline_config = UnderlineConfig(alpha=120, thickness=1.0)

        draw_bottom_underline(
            painter,
            self.rect(),
            self.theme_manager,
            underline_config,
        )
