"""Keyboard-navigation state + key delivery (``core.control.nav_state`` + ``nav_keys``).

The control channel must be able to answer "can a **keyboard** reach this
control?", and Qt focus cannot answer it: arrow keys belong to the toolkit's
``NavigationManager`` sections, and whole surfaces (the Quick Look overlay)
handle keys in their own ``keyPressEvent`` while being owned by no section.
These tests pin the two tools that expose that model over a **real** widget
tree:

* ``ui_nav_state`` lists the registered sections, attributes the focused
  widget to its owning section, and reports an overlay's focusable children
  with ``owned_by_section: null`` — the honest "no section drives this" signal;
* ``nav_key`` delivers a key to the widget a user's key would reach, focuses an
  ``anchor`` element first with the app's own focus reason, and reports the
  layer that took the key (``step:<section>`` / ``focus`` / ``unhandled``).

Falsification (written to be RED against a stub that reports Qt focus only):
* the section-owned assertion requires reading ``NavigationManager``'s graph, so
  returning ``QApplication.focusWidget()`` alone fails;
* the overlay assertion requires the ownership walk — a tool that lists
  focusable children without ``owned_by_section`` fails;
* ``nav_key`` must move focus through the section's own ``navigate()``, so a
  re-implementation that focuses widgets itself fails the section verdict.

Runs offscreen only — no Xvfb (the supervisor runs the live proof).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from sli_ui_toolkit.widgets import Button

from core.control import nav_state
from core.control.nav_keys import NavMethodsMixin  # noqa: F401 (import check)
from core.control.handlers import ControlHandlers
from ui.actions.registry import ActionRegistry


class _RowSection:
    """Minimal section: owns a button row and moves focus Down/Up inside it."""

    def __init__(self, row: list[Button]) -> None:
        self._row = row

    def owns(self, widget) -> bool:  # noqa: ANN001 (duck-typed)
        return widget in self._row

    def _move(self, delta: int) -> bool:
        focused = QApplication.focusWidget()
        if focused not in self._row:
            self._row[0].setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        index = (self._row.index(focused) + delta) % len(self._row)
        self._row[index].setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def navigate(self, key: int, widget) -> bool:  # noqa: ANN001
        if key == Qt.Key.Key_Down:
            return self._move(1)
        if key == Qt.Key.Key_Up:
            return self._move(-1)
        return False

    def focus_first(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason) -> bool:  # noqa: ANN001
        self._row[0].setFocus(reason)
        return True

    def focus_last(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason) -> bool:  # noqa: ANN001
        self._row[-1].setFocus(reason)
        return True


class _TestOverlay(QWidget):
    """A visible in-window overlay with focusable children no section owns."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.first = Button(text="first", parent=self)
        self.second = Button(text="second", parent=self)
        layout.addWidget(self.first)
        layout.addWidget(self.second)


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, seconds: float = 0.05) -> None:
    app.processEvents()
    app.processEvents()
    del seconds


def _handlers(window: QWidget) -> ControlHandlers:
    return ControlHandlers(window=window, app=QApplication.instance(), registry_provider=ActionRegistry)


def _elements_by_id(payload: dict) -> dict[str, dict]:
    return {row["id"]: row for row in payload["elements"]}


class _Harness:
    """A window with a section-owned row plus an unowned overlay."""

    def __init__(self, app: QApplication) -> None:
        self.window = QWidget()
        self.window.resize(320, 240)
        layout = QVBoxLayout(self.window)
        self.row = [Button(text=f"row{i}", parent=self.window) for i in range(2)]
        for button in self.row:
            layout.addWidget(button)
        self.overlay = _TestOverlay(self.window)
        self.overlay.show()
        self.window.show()
        self.section = _RowSection(self.row)
        self.manager = nav_state.nav_manager()
        self.manager.register(self.window, self.section)
        self.row[0].setFocus(Qt.FocusReason.OtherFocusReason)
        _pump(app)

    def close(self) -> None:
        try:
            self.manager.unregister(self.window)
        except Exception:
            pass
        self.window.close()
        _pump(QApplication.instance())


def test_nav_state_reports_sections_and_ownership() -> None:
    app = _qapp()
    harness = _Harness(app)
    try:
        handlers = _handlers(harness.window)
        state = handlers.ui_nav_state({})
        names = [row["section"] for row in state["sections"]]
        assert "_RowSection" in names, names
        assert state["sections_count"] == len(state["sections"])
        # The focused widget is attributed to the section that owns it: the one
        # signal Qt focus alone cannot give.
        assert state["focus"] is not None
        assert state["owner_section"] == "_RowSection"
        assert state["focus"]["owned_by_section"] == "_RowSection"
        assert state["focus"]["focus_policy"] == "StrongFocus"
    finally:
        harness.close()


def test_overlay_children_are_listed_and_unowned() -> None:
    app = _qapp()
    harness = _Harness(app)
    try:
        handlers = _handlers(harness.window)
        state = handlers.ui_nav_state({})
        overlays = [
            row for row in state["overlays"] if row["widget"] == "_TestOverlay"
        ]
        assert overlays, [row["widget"] for row in state["overlays"]]
        overlay = overlays[0]
        assert overlay["children_total"] >= 2
        assert overlay["children"], "focusable children must be listed"
        for child in overlay["children"]:
            assert child["focus_policy"] != "NoFocus"
            assert child["owned_by_section"] is None, (
                f"{child['widget']} must read as unowned — no section drives it"
            )
    finally:
        harness.close()


def test_nav_key_delivers_through_the_owning_section() -> None:
    app = _qapp()
    harness = _Harness(app)
    try:
        handlers = _handlers(harness.window)
        elements = _elements_by_id(handlers.ui_elements({}))
        first = next(
            row["id"]
            for row in elements.values()
            if row["role"] == "button" and row["label"] == "row0"
        )
        second = next(
            row["id"]
            for row in elements.values()
            if row["role"] == "button" and row["label"] == "row1"
        )
        result = handlers.nav_key({"keys": "Down", "anchor": first})
        assert result["count"] == 1
        step = result["steps"][0]
        assert step["handled"].startswith("section:"), step["handled"]
        assert step["focus_after"]["element_id"] == second, step["focus_after"]
        assert result["focus_is_ours"] is True
    finally:
        harness.close()


class _KeySink(QWidget):
    """A control whose own keyPressEvent accepts a key (the overlay pattern).

    Faster than a real overlay and pins the one case focus alone cannot show: a
    surface reacts *without* moving focus, so a verdict built only from focus
    and section ownership reports ``unhandled`` for a key that demonstrably did
    something.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.hits = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.key() == Qt.Key.Key_Right:
            self.hits += 1
            event.accept()
            return
        super().keyPressEvent(event)


def test_nav_key_reports_a_surface_keypress_as_surface_not_unhandled() -> None:
    """A key a widget/surface itself handles must not read as 'lost'.

    Falsification: a verdict built from focus + section ownership alone returns
    ``unhandled`` here — the live Quick Look case (arrows walking the series
    while a lower control holds focus) was reported exactly that way before
    ``accepted`` was added.
    """
    app = _qapp()
    harness = _Harness(app)
    try:
        sink = _KeySink(harness.window)
        sink.show()
        sink.setFocus(Qt.FocusReason.OtherFocusReason)
        _pump(app)
        handlers = _handlers(harness.window)
        result = handlers.nav_key({"keys": "Right"})
        step = result["steps"][0]
        assert sink.hits == 1, "the surface's own handler must have run"
        assert step["accepted"] is True
        assert step["handled"] == "surface", step["handled"]
    finally:
        harness.close()


def test_nav_key_on_an_unowned_widget_is_reported_unhandled() -> None:
    app = _qapp()
    harness = _Harness(app)
    try:
        handlers = _handlers(harness.window)
        elements = _elements_by_id(handlers.ui_elements({}))
        target = next(
            row["id"]
            for row in elements.values()
            if row["role"] == "button" and row["label"] == "first"
        )
        result = handlers.nav_key({"keys": "Down", "anchor": target})
        step = result["steps"][0]
        assert step["owner_after"] is None
        assert step["handled"] in ("unhandled", "focus"), step["handled"]
    finally:
        harness.close()


def test_nav_key_rejects_an_unknown_element() -> None:
    app = _qapp()
    harness = _Harness(app)
    try:
        handlers = _handlers(harness.window)
        try:
            handlers.nav_key({"keys": "Down", "anchor": "nope@nowhere"})
        except Exception as exc:  # MethodError from resolve_element
            assert "nope@nowhere" in str(exc)
        else:  # pragma: no cover - the resolver must fail loudly
            raise AssertionError("an unknown anchor must fail, not silently focus nothing")
    finally:
        harness.close()
