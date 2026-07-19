from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import ContextMenuEntry

ContextMenuSurface = Literal["in_window", "popup"]


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
    # None → manager policy (rmb_context_menu_surface). Prefer leaving unset
    # so Image Compare and Multi Compare share the same popup/parent path.
    surface: ContextMenuSurface | None = None
    # Optional QWidget parent for the toolkit ContextMenu. Leave unset to use
    # source_widget (required for Multi Compare: MainWindow parent caused a
    # one-frame QRhi clear wipe on Wayland).
    menu_parent: QWidget | None = None


class ContextMenuProvider(Protocol):
    def entries_for(self, request: ContextMenuRequest) -> tuple[ContextMenuEntry, ...]:
        ...

    def execute(self, action_id: str, request: ContextMenuRequest, data: object) -> bool:
        ...
