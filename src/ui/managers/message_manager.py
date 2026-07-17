from PySide6.QtCore import Qt

from shared_toolkit.ui.message_dialog import MessageKind, open_non_modal_message


class MessageManager:
    def __init__(self, host):
        self.host = host

    def show_non_modal_message(self, kind: MessageKind, title: str, text: str):
        dialog = open_non_modal_message(
            self.host.parent_widget,
            kind=kind,
            title=title,
            text=text,
        )

        self.host._active_message_boxes.append(dialog)
        dialog.finished.connect(
            lambda: self.host._active_message_boxes.remove(dialog)
            if dialog in self.host._active_message_boxes
            else None
        )
