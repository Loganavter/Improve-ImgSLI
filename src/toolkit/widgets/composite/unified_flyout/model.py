from PyQt6.QtCore import QAbstractListModel, QMimeData, QModelIndex, Qt

NameRole = Qt.ItemDataRole.UserRole + 1
RatingRole = Qt.ItemDataRole.UserRole + 2
PathRole = Qt.ItemDataRole.UserRole + 3
IndexRole = Qt.ItemDataRole.UserRole + 4
IsCurrentRole = Qt.ItemDataRole.UserRole + 5

class ImageListModel(QAbstractListModel):

    def __init__(self, image_list=None, image_number: int = 1, store=None, parent=None):
        super().__init__(parent)

        self._data = image_list if image_list is not None else []
        self._image_number = image_number
        self._store = store
        self._current_index = -1

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._data)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._data)):
            return None

        item = self._data[index.row()]

        if role == NameRole or role == Qt.ItemDataRole.DisplayRole:
            return item.display_name if hasattr(item, 'display_name') else str(item)
        elif role == RatingRole:
            return item.rating if hasattr(item, 'rating') else 0
        elif role == PathRole:
            return item.path if hasattr(item, 'path') else ""
        elif role == IndexRole:
            return index.row()
        elif role == IsCurrentRole:
            return index.row() == self._current_index

        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or not (0 <= index.row() < len(self._data)):
            return False

        if role == RatingRole:
            item = self._data[index.row()]
            if hasattr(item, 'rating'):
                item.rating = value
                self.dataChanged.emit(index, index, [RatingRole])
                return True

        return False

    def setRating(self, row, new_rating):
        if 0 <= row < len(self._data):
            item = self._data[row]
            if hasattr(item, 'rating'):
                item.rating = new_rating
                index = self.index(row)
                self.dataChanged.emit(index, index, [RatingRole])
                return True
        return False

    def setCurrentIndex(self, current_index: int):
        old_index = self._current_index
        self._current_index = current_index

        if 0 <= old_index < len(self._data):
            old_model_index = self.index(old_index)
            self.dataChanged.emit(old_model_index, old_model_index, [IsCurrentRole])

        if 0 <= current_index < len(self._data):
            new_model_index = self.index(current_index)
            self.dataChanged.emit(new_model_index, new_model_index, [IsCurrentRole])

    def updateData(self, image_list, current_index: int = -1):
        self.beginResetModel()
        self._data = image_list if image_list is not None else []
        self._current_index = current_index
        self.endResetModel()

    def getItem(self, row: int):
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled

    def mimeTypes(self):
        return ["application/x-imagelist-item"]

    def mimeData(self, indexes):
        mime_data = QMimeData()
        if indexes:
            index = indexes[0]
            row = index.row()

            data_dict = {
                "list_num": self._image_number,
                "index": row,
            }

            mime_data.setData("application/x-imagelist-item", f"{self._image_number}:{row}".encode())
        return mime_data

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

