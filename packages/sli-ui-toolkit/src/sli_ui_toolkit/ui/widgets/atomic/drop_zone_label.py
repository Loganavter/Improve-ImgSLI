import os

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.atomic.text_labels import AdaptiveLabel

def _file_path_from_url(url: QUrl) -> str:
    path = url.toLocalFile()
    if path:
        return path
    value = url.toString().strip()
    if value.startswith("file:///"):
        path = value[8:].lstrip("/").replace("|", ":", 1).replace("/", os.sep)
        return os.path.normpath(path) if path else ""
    if value.startswith("file://"):
        path = value[7:].replace("|", ":", 1).replace("/", os.sep)
        return os.path.normpath(path) if path else ""
    return ""

def _paths_from_urls_and_uri_list(mime, urls: list) -> list[str]:
    paths = [_file_path_from_url(url) for url in urls]
    if any(paths):
        return paths
    if not mime.hasFormat("text/uri-list"):
        return []
    raw = mime.data("text/uri-list").data().decode("utf-8", errors="replace")
    for line in raw.splitlines():
        part = line.strip()
        if not part or not part.startswith("file:"):
            continue
        path = _file_path_from_url(QUrl(part))
        if path and path not in paths:
            paths.append(path)
    return paths

class DropZoneLabel(AdaptiveLabel):
    file_dropped = pyqtSignal(str)
    drop_zone_drag_active = pyqtSignal(bool)
    drop_zone_hover_state_changed = pyqtSignal(bool)

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

    def _accept_drag(self, event):
        if event.source() is not None:
            return False
        mime = event.mimeData()
        return mime.hasUrls() or mime.hasFormat("text/uri-list")

    def dragEnterEvent(self, event):
        if not self._accept_drag(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()
        self.drop_zone_drag_active.emit(True)

    def dragMoveEvent(self, event):
        if not self._accept_drag(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()

    def dragLeaveEvent(self, event):
        self.drop_zone_drag_active.emit(False)
        event.accept()

    def dropEvent(self, event):
        self.drop_zone_drag_active.emit(False)
        if not self._accept_drag(event):
            event.ignore()
            return

        mime = event.mimeData()
        urls = list(mime.urls()) if mime.hasUrls() else []
        if not urls and mime.hasFormat("text/uri-list"):
            raw = mime.data("text/uri-list").data().decode("utf-8", errors="replace")
            for line in raw.splitlines():
                part = line.strip()
                if part.startswith("file:"):
                    urls.append(QUrl(part))

        paths = _paths_from_urls_and_uri_list(mime, urls)
        if paths and paths[0]:
            local_path = paths[0]
            QTimer.singleShot(0, lambda path=local_path: self.file_dropped.emit(path))
        event.acceptProposedAction()
        event.accept()

    def enterEvent(self, event):
        self.drop_zone_hover_state_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.drop_zone_hover_state_changed.emit(False)
        super().leaveEvent(event)
