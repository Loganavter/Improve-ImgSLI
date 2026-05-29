"""Tab lifecycle behavior.

Drop routing must respect ``accepts_drop`` (a tab only sees a drop it claimed)
and ``dispose()`` must be idempotent.

Dogma source: docs/dev/TAB_CONTRACT.md.
"""

from __future__ import annotations

from pathlib import Path

from tabs.contract import TabContext, TabContract
from tabs.registry import TabRegistry

class _RecordingTab(TabContract):
    def __init__(self, accept: bool):
        self._accept = accept
        self.handled: list[list[Path]] = []
        self.dispose_calls = 0

    @property
    def session_type(self) -> str:
        return "recording"

    @property
    def display_name(self) -> str:
        return "Recording"

    def create_page(self, parent, context):  # pragma: no cover - unused here
        raise NotImplementedError

    def accepts_drop(self, paths: list[Path]) -> bool:
        return self._accept

    def handle_drop(self, paths: list[Path]) -> None:
        self.handled.append(paths)

    def dispose(self) -> None:
        self.dispose_calls += 1

def _registry_with(tab: TabContract) -> TabRegistry:
    registry = TabRegistry()
    registry._tabs[tab.session_type] = tab
    return registry

def test_drop_routed_when_accepted():
    tab = _RecordingTab(accept=True)
    registry = _registry_with(tab)
    handled = registry.route_drop("recording", ["/tmp/a.png"])
    assert handled is True
    assert tab.handled == [[Path("/tmp/a.png")]]

def test_drop_not_routed_when_rejected():
    tab = _RecordingTab(accept=False)
    registry = _registry_with(tab)
    handled = registry.route_drop("recording", ["/tmp/a.png"])
    assert handled is False
    assert tab.handled == []

def test_drop_to_unknown_session_is_noop():
    tab = _RecordingTab(accept=True)
    registry = _registry_with(tab)
    assert registry.route_drop("does_not_exist", ["/tmp/a.png"]) is False
    assert tab.handled == []

def test_dispose_is_idempotent():
    tab = _RecordingTab(accept=True)
    tab.dispose()
    tab.dispose()
    assert tab.dispose_calls == 2  # no exception on repeat calls

def test_registry_dispose_all_is_idempotent():
    tab = _RecordingTab(accept=True)
    registry = _registry_with(tab)
    registry.dispose_all()
    registry.dispose_all()
    assert registry.list_tabs() == []
