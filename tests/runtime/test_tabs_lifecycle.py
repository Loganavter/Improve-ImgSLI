"""Tab lifecycle behavior.

Drop routing must respect ``accepts_drop`` (a tab only sees a drop it claimed)
and ``dispose()`` must be idempotent.

Dogma source: docs/dev/tabs/isolation.md.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from tabs.contract import TabContext, TabContract
from tabs.registry import TabRegistry

class _RecordingTab(TabContract):
    def __init__(self, accept: bool):
        self._accept = accept
        self.handled: list[list[Path]] = []
        self.hints: list[dict | None] = []
        self.lifecycle_calls: list[str] = []
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

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> None:
        self.handled.append(paths)
        self.hints.append(hint)

    def on_activated(self, context: TabContext) -> None:
        self.lifecycle_calls.append("activated")

    def on_deactivated(self, context: TabContext) -> None:
        self.lifecycle_calls.append("deactivated")

    def dispose(self) -> None:
        self.dispose_calls += 1

def _registry_with(tab: TabContract) -> TabRegistry:
    registry = TabRegistry()
    registry._tabs[tab.session_type] = tab
    registry._context = TabContext()
    return registry

def test_drop_routed_when_accepted():
    tab = _RecordingTab(accept=True)
    registry = _registry_with(tab)
    handled = registry.route_drop("recording", ["/tmp/a.png"], hint={"slot": 2})
    assert handled is True
    assert tab.handled == [[Path("/tmp/a.png")]]
    assert tab.hints == [{"slot": 2}]

def test_drop_not_routed_when_rejected():
    tab = _RecordingTab(accept=False)
    registry = _registry_with(tab)
    handled = registry.route_drop("recording", ["/tmp/a.png"])
    assert handled is False
    assert tab.handled == []
    assert tab.hints == []

def test_drop_to_unknown_session_is_noop():
    tab = _RecordingTab(accept=True)
    registry = _registry_with(tab)
    assert registry.route_drop("does_not_exist", ["/tmp/a.png"]) is False
    assert tab.handled == []

def test_dispose_is_idempotent():
    tab = _RecordingTab(accept=True)
    tab.dispose()
    tab.dispose()
    assert tab.dispose_calls == 2

def test_registry_dispose_all_is_idempotent():
    tab = _RecordingTab(accept=True)
    registry = _registry_with(tab)
    registry.dispose_all()
    registry.dispose_all()
    assert registry.list_tabs() == []

def test_registry_deactivates_previous_tab_before_activating_next():
    first = _RecordingTab(accept=True)

    class _SecondTab(_RecordingTab):
        @property
        def session_type(self) -> str:
            return "second"

    second = _SecondTab(accept=True)
    registry = _registry_with(first)
    registry._tabs[second.session_type] = second

    registry.activate("recording")
    registry.activate("second")

    assert first.lifecycle_calls == ["activated", "deactivated"]
    assert second.lifecycle_calls == ["activated"]

def test_registry_forwards_appearance_and_shutdown_hooks():
    tab = _RecordingTab(accept=True)
    registry = _registry_with(tab)
    host = object()

    tab.apply_appearance = lambda window: tab.lifecycle_calls.append(
        "appearance" if window is host else "wrong"
    )
    tab.on_window_shutdown = lambda window: tab.lifecycle_calls.append(
        "shutdown" if window is host else "wrong"
    )

    registry.apply_appearance(host)
    registry.notify_window_shutdown(host)

    assert tab.lifecycle_calls == ["appearance", "shutdown"]

def test_image_compare_drop_uses_presenter_main_controller_when_window_has_no_direct_controller():
    from types import SimpleNamespace

    from tabs.image_compare.tab import ImageCompareTab

    QApplication.instance() or QApplication([])
    calls = []
    sessions = SimpleNamespace(
        load_images_from_paths=lambda paths, slot: calls.append((paths, slot))
    )
    main_window = SimpleNamespace(
        main_controller=None,
        presenter=SimpleNamespace(main_controller=SimpleNamespace(sessions=sessions)),
    )
    tab = ImageCompareTab()
    tab._widget = SimpleNamespace(_context=SimpleNamespace(main_window=main_window))

    handled = tab.handle_drop([Path("/tmp/right.png")], hint={"slot": 2})
    QApplication.processEvents()

    assert handled is True
    assert calls == [(["/tmp/right.png"], 2)]
