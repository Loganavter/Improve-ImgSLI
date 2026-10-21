"""Multi Compare: a drop hint's ``side`` reaches the direct-load placement.

``tab.handle_drop`` normally has no placement position for MC (the drop
overlay is chrome-wide), so its hint used to be ignored and every folder
stacked in the auto column. The control surface's ``open_folder(side=...)``
does know the intent, so the side has to survive the whole chain:
``handle_drop`` → ``controller.load_external_paths(paths, side=...)`` →
``on_images_dropped(..., side)``.

Falsification: each assertion fails if ``side`` stops at the tab (dropped
before the controller call), if the no-hint call invents a side, or if the
no-controller signal fallback keeps emitting ``None``. Runs offscreen.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtWidgets import QApplication

from tabs.multi_compare.tab import MultiCompareTab


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, until, seconds: float = 2.0) -> bool:
    """Spin the event loop until *until* holds (the tab defers past accept)."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if until():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(until())


class _FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Path], str | None]] = []

    def load_external_paths(self, paths, side=None) -> int:
        self.calls.append((list(paths), side))
        return len(list(paths))


def _mc_tab(controller) -> MultiCompareTab:
    tab = MultiCompareTab()
    tab._controller = controller
    tab._widget = SimpleNamespace(
        images_dropped=SimpleNamespace(emit=lambda *args: None)
    )
    return tab


#: Suffix-only acceptance: the tab filters by extension, no stat here.
_PATHS = [Path("/nonexistent/a.png")]


def test_mc_handle_drop_passes_the_side_to_the_direct_load(qapp) -> None:
    controller = _FakeController()
    tab = _mc_tab(controller)

    assert tab.handle_drop(list(_PATHS), {"side": "right"}) is True
    assert _pump(qapp, lambda: bool(controller.calls)), "deferred load never ran"
    assert controller.calls == [(_PATHS, "right")]


def test_mc_handle_drop_without_a_hint_passes_none(qapp) -> None:
    controller = _FakeController()
    tab = _mc_tab(controller)

    assert tab.handle_drop(list(_PATHS)) is True
    assert _pump(qapp, lambda: bool(controller.calls)), "deferred load never ran"
    assert controller.calls == [(_PATHS, None)]


def test_mc_handle_drop_ignores_a_hint_it_does_not_know(qapp) -> None:
    """A host hint from another feature must not fail a real drop."""
    controller = _FakeController()
    tab = _mc_tab(controller)

    assert tab.handle_drop(list(_PATHS), {"is_left_area": True}) is True
    assert _pump(qapp, lambda: bool(controller.calls))
    assert controller.calls == [(_PATHS, None)]


def test_mc_handle_drop_signal_fallback_carries_the_side() -> None:
    emitted: list[tuple] = []
    tab = MultiCompareTab()
    tab._controller = None
    tab._widget = SimpleNamespace(
        images_dropped=SimpleNamespace(emit=lambda *args: emitted.append(args))
    )

    assert tab.handle_drop(list(_PATHS), {"side": "bottom"}) is True
    assert emitted == [(_PATHS, (None, False), "bottom")]


def test_load_external_paths_forwards_the_side(monkeypatch, tmp_path) -> None:
    from tabs.multi_compare.use_cases import loading

    seen: list[tuple] = []
    monkeypatch.setattr(
        loading,
        "on_images_dropped",
        lambda controller, paths, target, side: seen.append((list(paths), target, side)),
    )
    image = tmp_path / "a.png"
    image.write_bytes(b"x")
    controller = SimpleNamespace(widget=SimpleNamespace(state=SimpleNamespace(slots=[])))

    loading.load_external_paths(controller, [image], side="top")

    assert seen == [([image], (None, False), "top")]


def test_load_external_paths_without_a_side_keeps_auto_placement(
    monkeypatch, tmp_path
) -> None:
    from tabs.multi_compare.use_cases import loading

    seen: list[tuple] = []
    monkeypatch.setattr(
        loading,
        "on_images_dropped",
        lambda controller, paths, target, side: seen.append((list(paths), target, side)),
    )
    image = tmp_path / "a.png"
    image.write_bytes(b"x")
    controller = SimpleNamespace(widget=SimpleNamespace(state=SimpleNamespace(slots=[])))

    loading.load_external_paths(controller, [image])

    assert seen == [([image], (None, False), None)]
