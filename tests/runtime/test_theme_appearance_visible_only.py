"""Visible-only theme appearance avoids work on hidden workspace pages."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_apply_appearance_skips_hidden_tab_pages(monkeypatch):
    _app()
    from tabs.registry import TabRegistry

    registry = TabRegistry.__new__(TabRegistry)
    registry._initialized = True
    registry._tabs = {}
    registry._pages = {}
    registry._appearance_stale = set()
    registry._context = None
    registry._active_session_type = None
    registry._active_session_id = None
    registry._discovered_tiers = set()

    visible = QWidget()
    hidden = QWidget()
    stack = QStackedWidget()
    stack.addWidget(visible)
    stack.addWidget(hidden)
    stack.setCurrentWidget(visible)

    calls: list[str] = []

    class _Tab:
        def __init__(self, name: str):
            self.session_type = name

        def apply_appearance(self, _host):
            calls.append(self.session_type)

    registry._tabs = {"visible": _Tab("visible"), "hidden": _Tab("hidden")}
    registry._pages = {"visible": visible, "hidden": hidden}

    host = SimpleNamespace(ui=SimpleNamespace(workspace_stack=stack))
    registry.apply_appearance(host)

    assert calls == ["visible"]
    assert registry._appearance_stale == {"hidden"}

    stack.setCurrentWidget(hidden)
    registry.flush_stale_appearance(host)
    assert calls == ["visible", "hidden"]
    assert registry._appearance_stale == set()
