"""Wave W3: kill the color-picker raise-war (image_compare side).

The settings color pickers used to fight the compositor for activation:
``activateWindow()`` on single-instance re-open and on fresh open, plus a
post-close re-raise of the transient host (which stole activation after the
user had already closed the dialog and possibly moved on).

Pinned here (headless with fakes):
- fresh open shows + raises, never activates;
- single-instance re-open only raises (no new dialog, no activation);
- closing pops the registry and never re-raises the transient host;
- dialog still opens (registered) and closes (unregistered);
- source contains no window-activation or focus-reason grabs.
"""

from __future__ import annotations

import inspect

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

import pytest

from tabs.image_compare.ui import settings_color_pickers as pickers


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

    def setWindowModality(self, _value):
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


class _FakeHost:
    """Transient parent window; counts post-close re-raise attempts."""

    def __init__(self, *, visible=True, active=False):
        self._visible = visible
        self._active = active
        self.raise_calls = 0
        self.activate_calls = 0

    def isVisible(self):  # noqa: N802 — Qt API
        return self._visible

    def isActiveWindow(self):  # noqa: N802 — Qt API
        return self._active

    def raise_(self):  # noqa: N802 — Qt API
        self.raise_calls += 1

    def activateWindow(self):  # noqa: N802 — Qt API, spy only (must stay 0)
        self.activate_calls += 1


def _coordinator(monkeypatch, factory):
    monkeypatch.setattr(pickers, "ColorPickerDialog", factory)
    monkeypatch.setattr(pickers, "color_to_qcolor", lambda color: color)
    return pickers.SettingsColorPickerCoordinator(
        store=None,
        main_controller=None,
        main_window_app=None,
        tr_func=lambda key: key,
    )


def test_fresh_open_shows_and_raises_without_activation(qapp, monkeypatch):
    """Fresh open: show + raise, zero activation steal."""
    created = []
    coord = _coordinator(monkeypatch, lambda *a, **k: created.append(_FakeDialog()) or created[-1])

    coord.show_color_picker(
        key="divider",
        current_color=QColor(255, 0, 0, 255),
        title_key="title",
        on_selected=lambda _color: None,
    )

    assert len(created) == 1
    dialog = created[0]
    assert dialog.show_calls == 1
    assert dialog.raise_calls == 1
    assert dialog.activate_calls == 0
    # Dialog still opens: registered as the single instance.
    assert coord._dialogs["divider"] is dialog


def test_single_instance_reopen_only_raises(qapp, monkeypatch):
    """Re-open while visible: single instance raised, never activated."""
    created = []
    coord = _coordinator(monkeypatch, lambda *a, **k: created.append(_FakeDialog()) or created[-1])
    existing = _FakeDialog()
    existing.show()
    coord._dialogs["divider"] = existing

    coord.show_color_picker(
        key="divider",
        current_color=QColor(0, 255, 0, 255),
        title_key="title",
        on_selected=lambda _color: None,
    )

    assert created == []
    assert existing.raise_calls == 1
    assert existing.activate_calls == 0
    assert coord._dialogs["divider"] is existing


def test_close_never_reraises_transient_host(qapp, monkeypatch):
    """Post-close: registry popped, transient host left alone (no re-raise)."""
    created = []
    coord = _coordinator(monkeypatch, lambda *a, **k: created.append(_FakeDialog()) or created[-1])
    host = _FakeHost(visible=True, active=False)

    coord.show_color_picker(
        key="transient",
        current_color=QColor(0, 0, 255, 255),
        title_key="title",
        on_selected=lambda _color: None,
        parent_window=host,
    )
    dialog = created[0]
    assert coord._dialogs["transient"] is dialog

    dialog.close()

    assert "transient" not in coord._dialogs
    assert host.raise_calls == 0
    assert host.activate_calls == 0


def test_smart_magnifier_single_instance_only_raises(qapp, monkeypatch):
    """Smart-magnifier fast path: visible instance raised, never activated."""
    created = []
    coord = _coordinator(monkeypatch, lambda *a, **k: created.append(_FakeDialog()) or created[-1])
    existing = _FakeDialog()
    existing.show()
    coord._dialogs["smart_magnifier"] = existing

    coord.apply_smart_magnifier_colors()

    assert created == []
    assert existing.raise_calls == 1
    assert existing.activate_calls == 0


def test_no_activation_steal_in_source():
    """Source pin: no activateWindow / focus-reason grabs on these paths."""
    src = inspect.getsource(pickers)
    assert "activateWindow" not in src
    assert "ActiveWindow" + "FocusReason" not in src
    assert "Popup" + "FocusReason" not in src
