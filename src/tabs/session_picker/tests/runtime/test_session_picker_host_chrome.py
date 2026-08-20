"""Session picker host chrome + workspace.new_* runners (no class-name lookup)."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QStackedWidget


@pytest.fixture
def tab_registry(monkeypatch):
    """Fresh TabRegistry singleton for isolation."""
    import tabs.registry as reg_mod

    monkeypatch.setattr(reg_mod.TabRegistry, "_instance", None)
    monkeypatch.setattr(reg_mod, "_shared_registry", None)
    registry = reg_mod.TabRegistry()
    registry.discover(tier="bootstrap")
    return registry


def test_session_picker_host_chrome_via_create_service_for(qtbot, tab_registry):
    from core.store import INITIAL_WORKSPACE_SESSION_TYPE
    from tabs.contract import TabContext
    from tabs.session_picker.host_chrome import SessionPickerHostChrome

    stack = QStackedWidget()
    qtbot.addWidget(stack)
    context = TabContext(
        store=SimpleNamespace(get_active_workspace_session=lambda: None),
        event_bus=SimpleNamespace(emit=lambda *_a, **_k: None),
        main_window=None,
    )
    tab_registry.install_pages(stack, context)
    # install_pages is lazy — force page creation so get_page returns it.
    tab_registry._ensure_page(INITIAL_WORKSPACE_SESSION_TYPE)

    chrome = tab_registry.create_service_for(
        INITIAL_WORKSPACE_SESSION_TYPE,
        "session_picker.host_chrome",
    )
    assert chrome is not None
    assert isinstance(chrome, SessionPickerHostChrome)

    opened: list[str] = []
    chrome.set_open_project_handler(lambda path: opened.append(path))
    chrome.refresh_recent()
    # Extension object must expose card_for without host getattr on the page.
    assert callable(chrome.card_for)


def test_workspace_new_session_runners_use_get_tab(tab_registry):
    from ui.actions.workspace_new_sessions import runner_for

    created: list[str] = []
    runner_for("image_compare", created.append)()
    assert created == ["image_compare"]

    # multi_compare is deferred — runner no-ops until discovered
    runner_for("multi_compare", created.append)()
    assert created == ["image_compare"]

    tab_registry.discover(tier="deferred")
    runner_for("multi_compare", created.append)()
    assert created == ["image_compare", "multi_compare"]


def test_menu_controller_avoids_tab_class_name_lookup():
    """Soft-isolation: host must not resolve tabs by Python class name."""
    import inspect

    from ui.main_window import menu_controller as mc

    src = inspect.getsource(mc)
    assert "_tab_by_class_name" not in src
    assert "ImageCompareTab" not in src
    assert "MultiCompareTab" not in src
    assert 'getattr(page, "refresh_recent"' not in src
    assert 'getattr(page, "card_for"' not in src