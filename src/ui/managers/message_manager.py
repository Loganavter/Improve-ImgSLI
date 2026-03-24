from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

class MessageManager:
    def __init__(self, host):
        self.host = host

    def show_non_modal_message(self, icon, title: str, text: str):
        msg_box = QMessageBox(self.host.parent_widget)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowType.Window)
        msg_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        msg_box.setModal(False)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)

        self.host.app_ref.theme_manager.apply_theme_to_dialog(msg_box)

        self.host._active_message_boxes.append(msg_box)
        msg_box.finished.connect(
            lambda: self.host._active_message_boxes.remove(msg_box)
            if msg_box in self.host._active_message_boxes
            else None
        )

        msg_box.show()
        msg_box.raise_()
        msg_box.activateWindow()
