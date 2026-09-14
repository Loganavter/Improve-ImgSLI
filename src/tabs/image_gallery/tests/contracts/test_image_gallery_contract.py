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