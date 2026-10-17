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
from pathlib import Path

import pytest

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QVBoxLayout, QWidget
from sli_ui_toolkit.widgets import Button, ContextMenu, ContextMenuAction, Slider

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


# -- toolkit widgets are first-class ------------------------------------------


def test_toolkit_button_and_slider_are_inventoried_and_zero_area_is_skipped(tmp_path):
    """Real sli-ui-toolkit widgets (not stock-Qt stand-ins) must be seen.

    The live app's UI is toolkit ``QWidget`` subclasses, invisible to an
    ``isinstance``-only inventory. A hidden, zero-height slider (the live noise
    rows ``[0,0,160,0]``) must not pollute the default inventory.
    """
    app = _qapp()
    window = QWidget()
    window.setObjectName("ToolkitWindow")
    layout = QVBoxLayout(window)
    button = Button(text="Toolkit Go", parent=window)
    layout.addWidget(button)
    slider = Slider(parent=window)
    layout.addWidget(slider)
    ghost = Slider(parent=window)
    ghost.setGeometry(0, 0, 160, 0)
    ghost.hide()
    window.resize(320, 240)
    window.show()
    _pump(app, 0.05)

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        payload = handlers.ui_elements({})

        row = _find(payload, label="Toolkit Go")
        assert row["role"] == "button", "toolkit Button is first-class"
        assert row["rect"][2] > 0 and row["rect"][3] > 0
        assert row["visible"] is True

        inputs = [e for e in payload["elements"] if e["role"] == "input"]
        assert len(inputs) == 1, "the live slider is an input"
        assert inputs[0]["rect"][2] > 0 and inputs[0]["rect"][3] > 0

        assert all(
            e["rect"][2] > 0 and e["rect"][3] > 0 for e in payload["elements"]
        ), "zero-area widgets (hidden sliders) are dropped"
    finally:
        window.close()


def test_toolkit_button_without_text_falls_back_to_action_label(tmp_path):
    """An icon-only toolkit button reports its action caption, not ``Button``."""
    app = _qapp()
    window = QWidget()
    window.setObjectName("IconButtonWindow")
    layout = QVBoxLayout(window)
    button = Button(parent=window)  # no caption of its own
    layout.addWidget(button)
    window.resize(240, 120)
    window.show()
    _pump(app, 0.05)

    registry = _registry(
        _descriptor("test.icon", target=ActionTarget(widget=button))
    )
    handlers = _handlers(window, registry, tmp_path)
    try:
        from devtools.app_snapshot import _display

        row = _find(handlers.ui_elements({}), action_id="test.icon")
        assert row["role"] == "button"
        assert row["label"] == _display("action.test.icon")
        assert row["label"] != "Button", "class-name fallback was replaced"
    finally:
        window.close()


# -- gallery card -------------------------------------------------------------


def test_gallery_card_role_and_right_click_reach_the_real_handler(tmp_path):
    """A real toolkit card inside ``GalleryGridView`` is a ``card`` element.

    Right-click must reach the app's *own* context-menu opener (the generic
    toolkit ``rightClicked`` path), proving the click seam without
    special-casing the gallery in ``core/control``.
    """
    app = _qapp()
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    grid = GalleryGridView()
    grid.setObjectName("TestGalleryGrid")
    grid.resize(720, 380)
    grid.show()
    items = [
        GalleryItem(path=Path(f"/gallery/card_{index}.png"), mtime_ns=index)
        for index in range(2)
    ]
    grid.rebuild_grid(items)
    _pump(app, 0.08)

    opened: list[Path] = []
    grid._on_context_menu = lambda path: opened.append(path)  # type: ignore[method-assign]
    handlers = _handlers(grid, _registry(), tmp_path)
    try:
        cards = [
            e for e in handlers.ui_elements({})["elements"] if e["role"] == "card"
        ]
        assert len(cards) >= 2, "gallery cards are inventoried as cards"
        assert all(c["rect"][2] > 0 and c["rect"][3] > 0 for c in cards)

        result = handlers.ui_click({"id": cards[0]["id"], "button": "right"})
        assert result["clicked"] is True
        assert result["target"] == "Button"
        assert opened, "right-click reached the card's context-menu handler"
    finally:
        grid.close()
        grid.deleteLater()


# -- real toolkit context menu ------------------------------------------------


def test_open_toolkit_context_menu_rows_are_inventoried_and_clickable(tmp_path):
    """A toolkit ``ContextMenu`` is a plain child widget — not ``QMenu``.

    While open it and its row Buttons must appear with ``menu``/``menu-row``
    roles, non-degenerate rects, distinct labels, and a row click must fire the
    menu's ``actionTriggered`` (the in-window surface the gallery uses).
    """
    app = _qapp()
    window = QWidget()
    window.setObjectName("ToolkitMenuWindow")
    QVBoxLayout(window)
    window.resize(360, 240)
    window.show()
    _pump(app, 0.05)

    fired: list[str] = []
    menu = ContextMenu(
        window,
        entries=(
            ContextMenuAction("alpha", "Alpha"),
            ContextMenuAction("beta", "Beta"),
        ),
        on_triggered=lambda action_id, _data: fired.append(action_id),
        surface="in_window",
    )
    menu.popup_at(window.mapToGlobal(QPoint(20, 20)))
    _pump(app, 0.1)

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        assert menu.isVisible() is True
        payload = handlers.ui_elements({})

        assert any(
            e["role"] == "menu" for e in payload["elements"]
        ), "an open toolkit ContextMenu is discoverable"

        rows = {
            e["label"]: e
            for e in payload["elements"]
            if e["role"] == "menu-row"
        }
        assert set(rows) >= {"Alpha", "Beta"}
        for label in ("Alpha", "Beta"):
            assert rows[label]["rect"][2] > 0 and rows[label]["rect"][3] > 0
        assert rows["Alpha"]["id"] != rows["Beta"]["id"]

        handlers.ui_click({"id": rows["Alpha"]["id"]})
        assert fired == ["alpha"], "clicking a menu row fired actionTriggered"
    finally:
        menu.hide()
        menu.deleteLater()
        window.close()


# -- scope = tab page containment ---------------------------------------------


def test_scope_is_tab_page_containment_and_closed_scope_is_empty(tmp_path):
    """``scope`` filters to the open tab's page subtree; closed → empty, no raise."""
    app = _qapp()
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    page = QWidget()
    page.setObjectName("ScopePage")
    page_layout = QVBoxLayout(page)
    inside = Button(text="inside-scope", parent=page)
    page_layout.addWidget(inside)
    page.resize(300, 200)
    page.show()

    outside_window = QWidget()
    outside_window.setObjectName("OutsideWindow")
    outside_layout = QVBoxLayout(outside_window)
    outside = Button(text="outside-scope", parent=outside_window)
    outside_layout.addWidget(outside)
    outside_window.resize(300, 200)
    outside_window.show()
    _pump(app, 0.05)

    registry._pages["scope_tab"] = page  # type: ignore[attr-defined]
    handlers = _handlers(outside_window, _registry(), tmp_path)
    try:
        scoped = handlers.ui_elements({"scope": "scope_tab"})
        labels = [e["label"] for e in scoped["elements"]]
        assert "inside-scope" in labels, "the page subtree is returned"
        assert "outside-scope" not in labels, "only the page subtree is returned"

        # A registered-but-closed scope is an honest empty list, not an error.
        closed = handlers.ui_elements({"scope": "scope_tab_closed"})
        assert closed["count"] == 0
        assert closed["elements"] == []
    finally:
        registry._pages.pop("scope_tab", None)  # type: ignore[attr-defined]
        page.close()
        outside_window.close()
