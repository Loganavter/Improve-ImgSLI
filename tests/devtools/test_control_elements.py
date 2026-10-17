"""Element inventory + in-process interaction (``core.control.elements``).

Covers the MCP v2 P1 app-side surface over a **real** widget tree and a fake
``ActionRegistry``:

* ``ui_elements`` lists a bound button with its id/role/label/rects, and the
  ids are stable across calls;
* an open ``QMenu`` appears in-process with non-degenerate rows;
* ``ui_click button=right`` reaches the same handler a user right-click does
  (``customContextMenuRequested``);
* retry-until-rendered finds an element created ~200 ms after the call starts,
  while a genuinely absent id fails with close matches in the hint;
* ``ui_hover`` / ``ui_focus`` reach the resolved widget.

Falsification (written to be RED against a naive stub):
* the menu-row rects are asserted non-degenerate — a collapsed popup (the
  motivating gallery-card bug) fails here;
* the retry test creates the target *after* the call starts, so a
  single-scan resolver fails;
* the right-click test asserts the context-menu slot actually fired, so
  left-button injection fails.

Runs offscreen only — no Xvfb (the supervisor runs the live proof).
"""

from __future__ import annotations

import time

import pytest

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QVBoxLayout, QWidget

from core.actions.types import ActionDescriptor, ActionTarget
from core.control import elements
from core.control.handlers import ControlHandlers, MethodError
from ui.actions.registry import ActionRegistry

_ELEMENT_KEYS = {
    "id",
    "role",
    "label",
    "rect",
    "screen_rect",
    "window",
    "owner_tab",
    "action_id",
    "enabled",
    "visible",
}


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _registry(*actions: ActionDescriptor) -> ActionRegistry:
    registry = ActionRegistry()
    for action in actions:
        registry.register(action)
    return registry


def _descriptor(action_id: str, run=None, **kwargs) -> ActionDescriptor:
    return ActionDescriptor(
        action_id=action_id,
        label_key=f"action.{action_id}",
        description_key=f"action.{action_id}_desc",
        run=run,
        **kwargs,
    )


def _handlers(window, registry, tmp_path) -> ControlHandlers:
    return ControlHandlers(
        window=window,
        app=QApplication.instance(),
        artifacts_dir=tmp_path / "artifacts",
        log_ring=None,
        registry_provider=lambda: registry,
    )


def _find(payload: dict, **match) -> dict:
    for row in payload["elements"]:
        if all(row.get(key) == value for key, value in match.items()):
            return row
    raise AssertionError(f"no element matching {match!r} in {payload['count']} rows")


# -- inventory ----------------------------------------------------------------


def test_inventory_lists_bound_button_with_id_role_label_and_rects(tmp_path):
    app = _qapp()
    window = QWidget()
    window.setObjectName("InventoryWindow")
    layout = QVBoxLayout(window)
    button = QPushButton("Click me", window)
    button.setObjectName("target-button")
    layout.addWidget(button)
    window.resize(240, 120)
    window.show()
    _pump(app, 0.05)

    registry = _registry(_descriptor("test.click", target=ActionTarget(widget=button)))
    handlers = _handlers(window, registry, tmp_path)
    try:
        payload = handlers.ui_elements({})

        row = _find(payload, action_id="test.click")
        assert set(row) == _ELEMENT_KEYS
        assert row["role"] == "button"
        assert row["label"] == "Click me"
        assert row["window"]
        assert row["visible"] is True and row["enabled"] is True
        assert row["rect"][2] > 0 and row["rect"][3] > 0
        assert row["screen_rect"][2] > 0 and row["screen_rect"][3] > 0
        assert "@test.click" in row["id"]

        # Stable ids: an unchanged UI yields identical ids on a second scan.
        first = [element["id"] for element in payload["elements"]]
        second = [element["id"] for element in handlers.ui_elements({})["elements"]]
        assert first == second

        # The id is resolvable by the mutating methods.
        result = handlers.ui_click({"id": row["id"]})
        assert result["clicked"] is True and result["id"] == row["id"]
        assert result["target"] == "QPushButton"

        # scope filters to a window identity (or owner tab); an unrelated
        # scope yields nothing.
        scoped = handlers.ui_elements({"scope": "InventoryWindow"})
        assert any(element["action_id"] == "test.click" for element in scoped["elements"])
        assert handlers.ui_elements({"scope": "NoSuchWindow"})["count"] == 0
    finally:
        window.close()


# -- popups / menus -----------------------------------------------------------


def test_open_menu_appears_with_non_degenerate_distinguishable_rows(tmp_path):
    app = _qapp()
    window = QWidget()
    window.setObjectName("MenuWindow")
    window.resize(320, 200)
    menu = QMenu(window)
    for text in ("alpha", "beta", "gamma"):
        menu.addAction(text)
    window.show()
    _pump(app, 0.05)
    menu.popup(window.mapToGlobal(QPoint(20, 20)))
    _pump(app, 0.08)

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        assert menu.isVisible() is True
        payload = handlers.ui_elements({})

        menu_rows = {
            element["label"]: element
            for element in payload["elements"]
            if element["role"] == "menu"
            or element["role"] == "menu-row"
        }
        # The popup still has to be present even with no bound actions.
        assert any(
            element["role"] == "menu" for element in payload["elements"]
        ), "an open popup is discoverable while open"

        for text in ("alpha", "beta", "gamma"):
            row = menu_rows.get(text)
            assert row is not None, f"menu row {text!r} missing"
            assert row["role"] == "menu-row"
            assert row["rect"][2] > 0 and row["rect"][3] > 0, "collapsed row rect"
            assert row["screen_rect"][2] > 0 and row["screen_rect"][3] > 0
    finally:
        menu.close()
        window.close()


# -- click fidelity -----------------------------------------------------------


def test_right_click_reaches_the_context_menu_handler(tmp_path):
    app = _qapp()
    window = QWidget()
    window.setObjectName("CtxWindow")
    button = QPushButton("ctx", window)
    button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    requested: list[QPoint] = []
    button.customContextMenuRequested.connect(requested.append)
    clicks: list[bool] = []
    button.clicked.connect(lambda: clicks.append(True))
    window.resize(220, 120)
    window.show()
    _pump(app, 0.05)

    registry = _registry(_descriptor("test.ctx", target=ActionTarget(widget=button)))
    handlers = _handlers(window, registry, tmp_path)
    try:
        row = _find(handlers.ui_elements({}), action_id="test.ctx")

        result = handlers.ui_click({"id": row["id"], "button": "right"})
        assert requested, "customContextMenuRequested fired like a user right-click"
        assert result["clicked"] is True
        assert result["target"] == "QPushButton"
        assert result["surface"] in ("window", "popup")

        assert clicks == []
        handlers.ui_click({"id": row["id"], "button": "left"})
        assert clicks == [True], "left click reached the button's own handler"
    finally:
        window.close()


# -- retry + close-match failures ---------------------------------------------


def test_retry_finds_element_created_after_the_call_starts(tmp_path, monkeypatch):
    app = _qapp()
    window = QWidget()
    window.setObjectName("RetryWindow")
    layout = QVBoxLayout(window)
    container = QWidget(window)
    layout.addWidget(container)
    window.resize(220, 120)
    window.show()
    _pump(app, 0.05)

    monkeypatch.setattr(elements, "RETRY_TIMEOUT_MS", 1500, raising=False)
    handlers = _handlers(window, _registry(), tmp_path)

    # Realize the element once to learn its id, then remove it so the retry
    # path is genuinely exercised.
    probe = QPushButton("late", container)
    probe.setGeometry(0, 0, 60, 24)
    probe.show()
    _pump(app, 0.05)
    late_id = _find(handlers.ui_elements({}), label="late")["id"]
    probe.setParent(None)
    probe.deleteLater()
    _pump(app, 0.05)

    clicked: list[bool] = []

    def recreate() -> None:
        button = QPushButton("late", container)
        button.setGeometry(0, 0, 60, 24)
        button.clicked.connect(lambda: clicked.append(True))
        button.show()

    QTimer.singleShot(200, recreate)
    try:
        result = handlers.ui_click({"id": late_id})
        assert result["clicked"] is True, "the element was found after it appeared"
        assert clicked == [True]
    finally:
        window.close()


def test_absent_id_fails_with_close_matches_in_the_hint(tmp_path, monkeypatch):
    app = _qapp()
    window = QWidget()
    window.setObjectName("AbsentWindow")
    layout = QVBoxLayout(window)
    button = QPushButton("present", window)
    layout.addWidget(button)
    window.resize(220, 120)
    window.show()
    _pump(app, 0.05)

    monkeypatch.setattr(elements, "RETRY_TIMEOUT_MS", 250, raising=False)
    handlers = _handlers(window, _registry(), tmp_path)
    try:
        row = _find(handlers.ui_elements({}), label="present")
        with pytest.raises(MethodError) as exc:
            handlers.ui_click({"id": row["id"] + "zzz"})
        assert "no element with id" in exc.value.message
        assert exc.value.hint and "did you mean" in exc.value.hint
        assert "ui_elements" in exc.value.hint
    finally:
        window.close()

    with pytest.raises(MethodError):
        handlers.ui_click({})


# -- hover + focus ------------------------------------------------------------


class _RecordingButton(QPushButton):
    """Records real enter events (proves hover reached the resolved widget)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.enters = 0

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.enters += 1
        super().enterEvent(event)


def test_hover_and_focus_reach_the_resolved_widget(tmp_path):
    app = _qapp()
    window = QWidget()
    window.setObjectName("HoverWindow")
    layout = QVBoxLayout(window)
    button = _RecordingButton("hover me", window)
    layout.addWidget(button)
    window.resize(220, 120)
    window.show()
    window.activateWindow()
    button.setFocus()
    _pump(app, 0.05)

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        row = _find(handlers.ui_elements({}), label="hover me")

        hover = handlers.ui_hover({"id": row["id"]})
        assert hover["hovered"] is True and hover["target"] == "_RecordingButton"
        assert button.enters >= 1, "the enter event reached the resolved widget"

        focus = handlers.ui_focus({"id": row["id"]})
        assert focus["focused"] is True
        assert "focus_widget" in focus
        assert app.focusWidget() is button, "focusWidget identity"
    finally:
        window.close()
