"""Canvas slot menu must not depend on the lazily-built FlyoutController.

Regression: the provider used to be installed only by
``FlyoutController.__init__`` (lazy transient service), so sessions that never
opened the list flyout had zero providers registered and RMB on the canvas
silently did nothing. The provider is now installed at canvas-wiring time via
``ensure_image_compare_context_menu``; the controller reuses it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtCore import Signal as QtSignal
from PySide6.QtWidgets import QWidget

from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.ui.context_menu import (
    ImageCompareContextMenuProvider,
    ensure_image_compare_context_menu,
)
from tabs.image_compare.ui.transient_flyouts import FlyoutController
from ui.context_menu import manager as context_menu_manager
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget


class _FakeFlyout(QWidget):
    item_context_menu_requested = QtSignal(int, int)


@pytest.fixture
def _isolated_menu_manager():
    manager = context_menu_manager.get_context_menu_manager()
    saved = list(manager._providers)
    manager._providers.clear()
    try:
        yield manager
    finally:
        manager._providers[:] = saved


def _fake_canvas():
    canvas = SimpleNamespace(_context_menu_provider=None)

    def _set_provider(provider):
        canvas._context_menu_provider = provider

    canvas.set_context_menu_provider = _set_provider
    return canvas


def _store_with_images():
    document = DocumentModel(
        image_list1=[ImageItem(path="/tmp/a.png", display_name="a.png")],
        image_list2=[ImageItem(path="/tmp/b.png", display_name="b.png")],
        current_index1=0,
        current_index2=0,
    )
    return SimpleNamespace(
        get_session_state_slot=lambda _name: document,
        document=document,
    )


def _slot_request(canvas, slot=1):
    return ContextMenuRequest(
        source_widget=canvas,
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="image_compare",
        target=ContextMenuTarget(kind="image_compare_slot", id=slot),
    )


def _ic_providers(manager):
    return [
        p
        for p in tuple(manager._providers)
        if isinstance(p, ImageCompareContextMenuProvider)
    ]


def test_ensure_installs_single_provider_with_slot_entries(
    qapp, _isolated_menu_manager
):
    canvas = _fake_canvas()
    store = _store_with_images()

    provider = ensure_image_compare_context_menu(canvas, store)

    assert provider is not None
    assert canvas._context_menu_provider is provider
    assert _ic_providers(_isolated_menu_manager) == [provider]
    # Loaded slot resolves to the full slot menu (was empty before the fix:
    # zero providers registered → open_context_menu() → None).
    assert len(provider.entries_for(_slot_request(canvas))) == 7


def test_ensure_is_idempotent_and_reused_by_flyout_controller(
    qapp, _isolated_menu_manager
):
    canvas = _fake_canvas()
    store = _store_with_images()
    sessions = SimpleNamespace()

    first = ensure_image_compare_context_menu(canvas, store, sessions=sessions)
    host = SimpleNamespace(store=store, unified_flyout=None, main_controller=None)
    controller = FlyoutController.__new__(FlyoutController)
    controller.manager = SimpleNamespace(host=host)
    controller.widget = SimpleNamespace(image_label=canvas)
    controller._install_context_menu()

    assert _ic_providers(_isolated_menu_manager) == [first]
    assert canvas._context_menu_provider is first
    assert first._session_ctrl is sessions


def test_flyout_controller_reinstall_delivers_signal_once(
    qapp, _isolated_menu_manager
):
    canvas = _fake_canvas()
    store = _store_with_images()
    flyout = _FakeFlyout()
    host = SimpleNamespace(store=store, unified_flyout=flyout, main_controller=None)
    controller = FlyoutController.__new__(FlyoutController)
    controller.manager = SimpleNamespace(host=host)
    controller.widget = SimpleNamespace(image_label=canvas)

    controller._install_context_menu()
    controller._install_context_menu()

    provider = canvas._context_menu_provider
    assert isinstance(provider, ImageCompareContextMenuProvider)
    assert provider.flyout is flyout
    assert _ic_providers(_isolated_menu_manager) == [provider]
    received: list[tuple[int, int]] = []
    flyout.item_context_menu_requested.connect(
        lambda list_num, index: received.append((list_num, index))
    )
    flyout.item_context_menu_requested.emit(1, 0)
    assert received == [(1, 0)]
