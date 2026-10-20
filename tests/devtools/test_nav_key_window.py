"""``nav_key`` aims at the anchor's **own** window, not always the main window.

A dialog (Settings, Help, any modal) is its own top-level window: its navigation
sections are registered against it and its focus chain is its own. Delivering an
anchored key to the injected main window made the instrument report the *main*
window's routing — live 2026-10-20, a ``Down`` anchored at the Settings dialog's
keyboard-page filter was reported as ``section:SessionPickerSection`` with focus
moving inside the main window, so the routing half of ``spec.nav.coverage`` was
unmeasurable on a dialog.

The rule pinned here:

* ``anchor`` (or ``from`` / ``element_id``) → the anchor's top-level window,
  reported as ``window_source: "anchor"``;
* no anchor → the injected main window exactly as before, ``window_source:
  "main"`` (existing callers and tests rely on that);
* an unknown id still raises ``MethodError`` and must not silently deliver to
  the main window (another process/instance keeps failing the way it did).

Falsification (RED before the fix): with two windows each owning a section that
moves focus Down inside its own row, a dialog-anchored ``Down`` that is delivered
to the main window reports ``section:_MainRowSection`` (and moves the main
window's focus) — the assertions below demand ``section:_DialogRowSection`` and
the dialog's own next button.

Runs offscreen only — no Xvfb (the supervisor runs the live proof).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget
from sli_ui_toolkit.widgets import Button

from core.control import nav_state
from core.control.discovery import MethodError
from core.control.handlers import ControlHandlers
from ui.actions.registry import ActionRegistry


class _MainRowSection:
    """Owns the main window's button row; Down/Up move inside it."""

    def __init__(self, row: list[Button], window: QWidget) -> None:
        self._row = row
        self._window = window

    def owns(self, widget) -> bool:  # noqa: ANN001 (duck-typed)
        return widget in self._row

    def _move(self, delta: int) -> bool:
        # Window-scoped on purpose: the point of this module is that two windows
        # each have their own focus chain, so a section must not read the
        # app-wide focus widget of the *other* window.
        focused = self._window.focusWidget()
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


class _DialogRowSection(_MainRowSection):
    """The dialog's own section — a different name, same row mechanics."""


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication) -> None:
    app.processEvents()
    app.processEvents()


def _handlers(window: QWidget) -> ControlHandlers:
    return ControlHandlers(
        window=window, app=QApplication.instance(), registry_provider=ActionRegistry
    )


def _elements_by_id(payload: dict) -> dict[str, dict]:
    return {row["id"]: row for row in payload["elements"]}


def _button_id(handlers: ControlHandlers, label: str) -> str:
    elements = _elements_by_id(handlers.ui_elements({}))
    return next(
        row["id"]
        for row in elements.values()
        if row["role"] == "button" and row["label"] == label
    )


class _Harness:
    """A main window plus (optionally) a dialog, each with its own section."""

    def __init__(self, app: QApplication, *, with_dialog: bool = True) -> None:
        self.manager = nav_state.nav_manager()
        self.window = QWidget()
        self.window.resize(320, 240)
        layout = QVBoxLayout(self.window)
        self.row = [Button(text=f"main{i}", parent=self.window) for i in range(2)]
        for button in self.row:
            layout.addWidget(button)
        self.window.show()
        self.section = _MainRowSection(self.row, self.window)
        self.manager.register(self.window, self.section)
        self.row[0].setFocus(Qt.FocusReason.OtherFocusReason)

        self.dialog: QDialog | None = None
        self.dialog_row: list[Button] = []
        self.dialog_section = None
        if with_dialog:
            self.dialog = QDialog(self.window)
            self.dialog.resize(240, 160)
            dialog_layout = QVBoxLayout(self.dialog)
            self.dialog_row = [
                Button(text=f"dialog{i}", parent=self.dialog) for i in range(2)
            ]
            for button in self.dialog_row:
                dialog_layout.addWidget(button)
            self.dialog.show()
            self.dialog_section = _DialogRowSection(self.dialog_row, self.dialog)
            self.manager.register(self.dialog, self.dialog_section)
            self.dialog_row[0].setFocus(Qt.FocusReason.OtherFocusReason)
        _pump(app)

    def close(self) -> None:
        for surface in (self.dialog, self.window):
            if surface is None:
                continue
            try:
                self.manager.unregister(surface)
            except Exception:
                pass
            surface.close()
        _pump(QApplication.instance())


def test_dialog_anchor_drives_the_dialog_window() -> None:
    """A dialog-anchored key must report the *dialog's* section and its focus.

    Falsification: before the fix the key went to the main window, so the step
    read ``section:_MainRowSection`` and the dialog's focus never moved.
    """
    app = _qapp()
    harness = _Harness(app)
    try:
        assert harness.dialog is not None
        handlers = _handlers(harness.window)
        first = _button_id(handlers, "dialog0")
        second = _button_id(handlers, "dialog1")

        result = handlers.nav_key({"keys": "Down", "anchor": first})

        assert result["window_source"] == "anchor", result["window_source"]
        assert result["window"]["widget"] == "QDialog", result["window"]
        step = result["steps"][0]
        assert step["handled"] == "section:_DialogRowSection", step["handled"]
        assert step["focus_after"]["element_id"] == second, step["focus_after"]
        # The dialog's own cursor moved; the main window's did not.
        assert harness.dialog.focusWidget() is harness.dialog_row[1]
        assert harness.window.focusWidget() is harness.row[0]
    finally:
        harness.close()


def test_main_window_anchor_still_reports_main_sections() -> None:
    """Regression: an anchor inside the main window keeps main-window routing."""
    app = _qapp()
    harness = _Harness(app)
    try:
        handlers = _handlers(harness.window)
        first = _button_id(handlers, "main0")
        second = _button_id(handlers, "main1")

        result = handlers.nav_key({"keys": "Down", "anchor": first})

        assert result["window_source"] == "anchor", result["window_source"]
        assert result["window"]["widget"] == "QWidget", result["window"]
        step = result["steps"][0]
        assert step["handled"] == "section:_MainRowSection", step["handled"]
        assert step["focus_after"]["element_id"] == second, step["focus_after"]
    finally:
        harness.close()


def test_no_anchor_keeps_the_main_window_delivery() -> None:
    """Without an anchor the injected main window is still the target."""
    app = _qapp()
    harness = _Harness(app, with_dialog=False)
    try:
        handlers = _handlers(harness.window)
        second = _button_id(handlers, "main1")

        result = handlers.nav_key({"keys": "Down"})

        assert result["window_source"] == "main", result["window_source"]
        assert result["window"]["widget"] == "QWidget", result["window"]
        assert result["steps"][0]["handled"] == "section:_MainRowSection"
        assert result["steps"][0]["focus_after"]["element_id"] == second
    finally:
        harness.close()


def test_unresolvable_anchor_fails_without_falling_back_to_main() -> None:
    """An id from another process/instance must error, never deliver silently."""
    app = _qapp()
    harness = _Harness(app, with_dialog=False)
    try:
        handlers = _handlers(harness.window)
        focused_before = harness.window.focusWidget()
        try:
            handlers.nav_key({"keys": "Down", "anchor": "nope@nowhere"})
        except MethodError as exc:
            assert "nope@nowhere" in str(exc), str(exc)
        else:  # pragma: no cover - the resolver must fail loudly
            raise AssertionError("an unknown anchor must fail, not deliver to the main window")
        assert harness.window.focusWidget() is focused_before
    finally:
        harness.close()
