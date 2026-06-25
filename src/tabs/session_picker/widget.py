"""Browser-style new-session picker page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class SessionPickerWidget(QWidget):
    def __init__(self, parent=None, *, context):
        super().__init__(parent)
        self._context = context
        self._grid: QGridLayout | None = None
        self._populated = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)

        title = QLabel(self._context.tr("session_picker.title", "Choose a workspace"))
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setProperty("class", "section-title")
        layout.addWidget(title)

        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        layout.addLayout(self._grid)
        layout.addStretch(1)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        if self._populated or self._grid is None:
            return
        for index, blueprint in enumerate(self._session_blueprints()):
            button = QPushButton(self._label_for(blueprint))
            button.setMinimumSize(180, 72)
            button.clicked.connect(
                lambda _checked=False, st=blueprint.session_type: self._create(st)
            )
            self._grid.addWidget(button, index // 3, index % 3)
        self._populated = True

    def _session_blueprints(self):
        try:
            blueprints = self._context.call_service("list_session_blueprints")
        except RuntimeError:
            return []
        return [bp for bp in blueprints if bp.session_type != "session_picker"]

    def _label_for(self, blueprint) -> str:
        key = f"session_picker.types.{blueprint.session_type}"
        fallback = blueprint.resolved_title() or blueprint.session_type.replace("_", " ").title()
        return self._context.tr(key, fallback)

    def _create(self, session_type: str) -> None:
        picker_session = self._context.get_active_session()
        self._context.call_service("create_workspace_session", session_type, True)
        if picker_session is not None:
            self._context.call_service("close_workspace_session", picker_session.id)
