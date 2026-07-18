"""Flyout list right-click exposes a context menu instead of deleting."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.widgets import ContextMenuAction

from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.ui.context_menu import ImageCompareContextMenuProvider
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget


def _store_with_lists():
    document = DocumentModel(
        image_list1=[
            ImageItem(path="/tmp/a.png", display_name="a.png", rating=2),
            ImageItem(path="/tmp/b.png", display_name="b.png", rating=1),
        ],
        image_list2=[
            ImageItem(path="/tmp/c.png", display_name="c.png", rating=0),
        ],
        current_index1=0,
        current_index2=0,
        image1_path="/tmp/a.png",
        image2_path="/tmp/c.png",
    )
    return SimpleNamespace(
        get_session_state_slot=lambda _name: document,
        document=document,
        emit_state_change=lambda *_a, **_k: None,
        viewport=SimpleNamespace(view_state=SimpleNamespace(is_horizontal=False)),
    )


def test_list_item_menu_exposes_copy_properties_remove(qapp):
    canvas = QWidget()
    flyout = QWidget()
    store = _store_with_lists()
    provider = ImageCompareContextMenuProvider(canvas, store, flyout=flyout)
    request = ContextMenuRequest(
        source_widget=flyout,
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="image_compare",
        target=ContextMenuTarget(
            kind="image_compare_list_item",
            id=(1, 1),
            payload={"list_num": 1, "index": 1},
        ),
    )

    entries = [
        entry
        for entry in provider.entries_for(request)
        if isinstance(entry, ContextMenuAction)
    ]
    assert [entry.action_id for entry in entries] == [
        "image_compare.rename_list_item",
        "image_compare.copy_path",
        "image_compare.show_properties",
        "image_compare.carry_list_item",
        "image_compare.remove_list_item",
    ]


def test_list_item_remove_calls_specific_index(qapp):
    canvas = QWidget()
    flyout = QWidget()
    store = _store_with_lists()
    provider = ImageCompareContextMenuProvider(canvas, store, flyout=flyout)
    ctrl = MagicMock()
    provider.attach_session_controller(ctrl)

    request = ContextMenuRequest(
        source_widget=flyout,
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="image_compare",
        target=ContextMenuTarget(
            kind="image_compare_list_item",
            id=(2, 0),
            payload={"list_num": 2, "index": 0},
        ),
    )
    handled = provider.execute(
        "image_compare.remove_list_item", request, (2, 0)
    )

    assert handled is True
    ctrl.remove_specific_image_from_list.assert_called_once_with(2, 0)
    ctrl.remove_current_image_from_list.assert_not_called()


def test_unified_flyout_right_click_emits_context_menu_signal(qapp):
    from sli_ui_toolkit.ui.widgets.composite.unified_flyout import UnifiedFlyout

    host = QWidget()
    left = QWidget(host)
    right = QWidget(host)
    flyout = UnifiedFlyout.create_double_list(
        host,
        left,
        right,
        left_items=["a.png", "b.png"],
        right_items=["c.png"],
        current_left=0,
        current_right=0,
    )
    # Disconnect standalone remove fallback so we only see the signal.
    try:
        flyout.item_context_menu_requested.disconnect()
    except TypeError:
        pass
    received: list[tuple[int, int]] = []
    flyout.item_context_menu_requested.connect(
        lambda list_num, index: received.append((list_num, index))
    )
    flyout._on_item_right_clicked(1, 1)
    assert received == [(1, 1)]
    flyout.deleteLater()
    host.deleteLater()
