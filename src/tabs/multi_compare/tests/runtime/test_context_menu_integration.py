from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.widgets import ContextMenuAction

from ui.context_menu.manager import ContextMenuManager
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget


class _Provider:
    def __init__(self):
        self.executed = []

    def entries_for(self, request):
        if request.target.kind != "thing":
            return ()
        return (ContextMenuAction("thing.rename", "Rename", data=request.target.id),)

    def execute(self, action_id, request, data):
        self.executed.append((action_id, request.target.id, data))
        return action_id == "thing.rename"


def test_context_menu_manager_routes_entries_and_actions(qapp):
    widget = QWidget()
    provider = _Provider()
    manager = ContextMenuManager()
    manager.register_provider(provider)
    request = ContextMenuRequest(
        source_widget=widget,
        global_pos=QPoint(10, 10),
        local_pos=QPoint(2, 2),
        session_type="image_compare",
        target=ContextMenuTarget(kind="thing", id=7),
    )

    entries = manager.entries_for(request)
    handled = manager.execute("thing.rename", request, 7)

    assert entries[0].action_id == "thing.rename"
    assert handled is True
    assert provider.executed == [("thing.rename", 7, 7)]


def test_multi_compare_provider_exposes_slot_actions(qapp):
    from pathlib import Path

    from tabs.multi_compare.context_menu import MultiCompareContextMenuProvider
    from tabs.multi_compare.models import CompareSlot, LeafNode, MultiCompareState
    from tabs.multi_compare.scene import MultiCompareStore
    from tabs.multi_compare.tests.pixel_fixtures import slot_image

    canvas = QWidget()
    store = MultiCompareStore(
        MultiCompareState(
            slots=[
                CompareSlot(
                    id=3,
                    path=Path("a.png"),
                    label="A",
                    image=slot_image(8, 8),
                )
            ],
            root=LeafNode(3),
        )
    )
    widget = SimpleNamespace(
        canvas=canvas,
        state=store.state,
        store=store,
        remove_slot=lambda slot_id: None,
        _translate=lambda _key, default=None: default or _key,
    )
    provider = MultiCompareContextMenuProvider(widget)
    request = ContextMenuRequest(
        source_widget=canvas,
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="multi_compare",
        target=ContextMenuTarget(kind="multi_compare_slot", id=3),
    )

    entries = [
        entry
        for entry in provider.entries_for(request)
        if isinstance(entry, ContextMenuAction)
    ]

    assert [entry.action_id for entry in entries] == [
        "multi_compare.rename_slot",
        "multi_compare.duplicate_slot",
        "multi_compare.show_slot_properties",
        "multi_compare.carry_slot",
        "multi_compare.remove_slot",
    ]
