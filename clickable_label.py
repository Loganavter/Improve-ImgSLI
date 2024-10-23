from PyQt6.QtWidgets import QLabel

class ClickableLabel(QLabel):
    def mousePressEvent(self, event):
        self.parent().on_mouse_move(event)

    def mouseMoveEvent(self, event):
        self.parent().on_mouse_move(event)
