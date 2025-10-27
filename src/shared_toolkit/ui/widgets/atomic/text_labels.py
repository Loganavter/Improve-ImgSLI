
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QLabel, QSizePolicy

class BodyLabel(QLabel):

    def __init__(self, parent=None, text: str = ""):
        super().__init__(parent)
        if text:
            self.setText(text)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        font = QFont(self.font())
        font.setPointSize(max(10, font.pointSize()))
        self.setFont(font)

class CaptionLabel(QLabel):

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        font = QFont(self.font())

        size = font.pointSize()
        if size > 0:
            font.setPointSize(max(9, size - 1))
        self.setFont(font)

class AdaptiveLabel(QLabel):

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._original_text = text
        self._min_width = 50
        self._preferred_width_cache = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(self._min_width)

    def setText(self, text):
        self._original_text = text
        self._preferred_width_cache = None
        super().setText(text)
        self._update_text()
        self.updateGeometry()

    def setMinimumWidth(self, width):
        self._min_width = width
        super().setMinimumWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()

    def _update_text(self):
        if not self._original_text:
            return

        available_width = self.width() - 10
        if available_width <= 0:
            return

        font_metrics = QFontMetrics(self.font())

        if font_metrics.horizontalAdvance(self._original_text) <= available_width:
            super().setText(self._original_text)
            return

        elided_text = font_metrics.elidedText(
            self._original_text, Qt.TextElideMode.ElideRight, available_width
        )
        super().setText(elided_text)

    def sizeHint(self):
        hint = super().sizeHint()

        if self._preferred_width_cache is None:
            font_metrics = QFontMetrics(self.font())
            self._preferred_width_cache = (
                font_metrics.horizontalAdvance(self._original_text) + 10
            )

        hint.setWidth(max(self._preferred_width_cache, self._min_width))
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(self._min_width)
        return hint

    def get_original_text(self):
        return self._original_text

    def invalidate_size_cache(self):
        self._preferred_width_cache = None
        self.updateGeometry()

class CompactLabel(AdaptiveLabel):

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._min_width = 80
        self.setMinimumWidth(self._min_width)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

class GroupTitleLabel(AdaptiveLabel):

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._group_widget = None
        self.setObjectName("StyledGroupTitle")

    def set_group_widget(self, group_widget):
        self._group_widget = group_widget

    def setText(self, text):
        super().setText(text)
        self._update_group_size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_group_size()

    def _update_group_size(self):
        if self._group_widget and self._original_text:
            font_metrics = QFontMetrics(self.font())
            text_width = font_metrics.horizontalAdvance(self._original_text)
            min_width = text_width + 40

            self._group_widget.setMinimumWidth(min_width)

            self.adjustSize()
            self.move(25, 0)

            self._group_widget.updateGeometry()
            self._group_widget.update()

            if self._group_widget.parent():
                parent_layout = self._group_widget.parent().layout()
                if parent_layout:
                    parent_layout.invalidate()
                    parent_layout.activate()

