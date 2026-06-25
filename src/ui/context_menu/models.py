from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import ContextMenuEntry


@dataclass(frozen=True, slots=True)
class ContextMenuTarget:
    kind: str
    id: object = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextMenuRequest:
    source_widget: QWidget
    global_pos: QPoint
    local_pos: QPoint
    session_type: str
    target: ContextMenuTarget


class ContextMenuProvider(Protocol):
    def entries_for(self, request: ContextMenuRequest) -> tuple[ContextMenuEntry, ...]:
        ...

    def execute(self, action_id: str, request: ContextMenuRequest, data: object) -> bool:
        ...
