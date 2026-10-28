"""Contract identity + page-construction smoke test for the Image Gallery tab."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext
from tabs.image_gallery.tab import ImageGalleryTab


def test_contract_identity():
    tab = ImageGalleryTab()
    assert tab.session_type == "image_gallery"
    assert tab.startup_tier == "deferred"
    assert tab.is_bootstrap_default is False
    assert tab.i18n_namespace == "image_gallery"
    assert tab.resources_dir is not None


def test_create_page_returns_widget(qtbot):
    tab = ImageGalleryTab()
    parent = QWidget()
    qtbot.addWidget(parent)

    context = TabContext()
    page = tab.create_page(parent, context)
    qtbot.addWidget(page)

    assert isinstance(page, QWidget)
    assert tab._widget is not None
    assert tab._controller is not None

def test_create_page_registers_the_find_action_rows(qtbot):
    """The palette rows must exist after the page is built, without the host hook.

    Measured 2026-10-28 on a live lease: the app listed 170 Find Action rows and
    ZERO `gallery.*`, because the host's `contribute_actions` hook runs once at
    window setup and resolves against the ACTIVE tab (the session picker). The
    same `register_actions` call in-process answered True with all six rows, so
    the loss was the call site, not the registration. This pins the call site:
    building the page is enough.
    """
    from ui.actions.registry import ActionRegistry, get_action_registry
    from tabs.image_gallery.actions import ALL_GALLERY_ACTION_IDS

    registry = get_action_registry()
    for action_id in ALL_GALLERY_ACTION_IDS:
        registry.unregister(action_id)

    tab = ImageGalleryTab()
    parent = QWidget()
    qtbot.addWidget(parent)
    page = tab.create_page(parent, TabContext())
    qtbot.addWidget(page)

    live = {action.action_id for action in registry.all_actions()}
    missing = [action_id for action_id in ALL_GALLERY_ACTION_IDS if action_id not in live]
    assert not missing, f"Find Action rows missing after create_page: {missing}"
    assert isinstance(registry, ActionRegistry)
