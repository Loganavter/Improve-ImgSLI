"""Wave W3: kill the color-picker raise-war (multi_compare divider side).

The divider color dialog used ``raise_()`` + ``activateWindow()`` when an
existing instance was re-requested — an xdg-activation kick on every click
while the picker was already open.

Pinned here (headless with fakes):
- fresh open shows without activation;
- single-instance re-request only raises (no new dialog, no activation);
- dialog still opens (registered) and closes (unregistered);
- the divider path source contains no window-activation or focus-reason grab.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

import pytest

import ui.widgets.color as color_widgets
from tabs.multi_compare.controller import MultiCompareController


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Signal:
    def __init__(self):
        self.handlers = []

    def connect(self, handler):
        self.handlers.append(handler)

    def emit(self, *args):
        for handler in list(self.handlers):
            handler(*args)


class _FakeDialog:
    """Stand-in for ColorPickerDialog; counts show/raise/activation."""

    def __init__(self, *args, **kwargs):
        self.show_calls = 0
        self.raise_calls = 0
        self.activate_calls = 0
        self.visible = False
        self.colorSelected = _Signal()
        self.finished = _Signal()

    def setModal(self, _value):
        pass

    def show(self):  # noqa: N802 — Qt API
        self.show_calls += 1
        self.visible = True

    def raise_(self):  # noqa: N802 — Qt API
        self.raise_calls += 1

    def activateWindow(self):  # noqa: N802 — Qt API, spy only (must stay 0)
        self.activate_calls += 1

    def isVisible(self):  # noqa: N802 — Qt API
        return self.visible

    def close(self):
        self.visible = False
        self.finished.emit(0)


def _controller():
    """Thin-owner instance without the full widget tree."""
    applied = []
    widget = SimpleNamespace(
        state=SimpleNamespace(
            divider_settings=SimpleNamespace(color_rgba=(255, 0, 0, 255))
        ),
        window=lambda: None,
        apply_divider_color=lambda color: applied.append(color),
    )
    controller = object.__new__(MultiCompareController)
    controller.widget = widget
    controller.store = None
    controller.translate = lambda key, default=None: default or key
    controller._divider_color_dialog = None
    controller.applied_colors = applied
    return controller


def test_divider_picker_opens_without_activation(qapp, monkeypatch):
    """Fresh open: dialog registered + shown, zero activation steal."""
    created = []
    monkeypatch.setattr(
        color_widgets,
        "ColorPickerDialog",
        lambda *a, **k: created.append(_FakeDialog()) or created[-1],
    )
    controller = _controller()

    controller._on_divider_color_picker_requested()

    assert len(created) == 1
    dialog = created[0]
    assert controller._divider_color_dialog is dialog
    assert dialog.show_calls == 1
    assert dialog.activate_calls == 0

    # Dialog still closes: finished clears the single-instance slot.
    dialog.close()
    assert controller._divider_color_dialog is None


def test_divider_picker_single_instance_only_raises(qapp, monkeypatch):
    """Re-request while visible: existing instance raised, never activated."""
    created = []
    monkeypatch.setattr(
        color_widgets,
        "ColorPickerDialog",
        lambda *a, **k: created.append(_FakeDialog()) or created[-1],
    )
    controller = _controller()
    existing = _FakeDialog()
    existing.show()
    controller._divider_color_dialog = existing

    controller._on_divider_color_picker_requested()

    assert created == []
    assert controller._divider_color_dialog is existing
    assert existing.raise_calls == 1
    assert existing.activate_calls == 0


def test_no_activation_steal_in_divider_path_source():
    """Source pin: divider path has no activateWindow / focus-reason grab."""
    src = inspect.getsource(
        MultiCompareController._on_divider_color_picker_requested
    )
    assert "activateWindow" not in src
    assert "ActiveWindow" + "FocusReason" not in src
    assert "Popup" + "FocusReason" not in src
