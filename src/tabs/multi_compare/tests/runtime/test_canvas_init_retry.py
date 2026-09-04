"""Cold canvas must not wait for the first DnD to initialize RHI.

If ``initialize()`` aborts (surface not realized yet) and nothing retries,
presents stay 0 until a drag drives the first frame — and that frame pays
the full cold-init cost (~160ms GUI stall → lag + frozen DnD cursor).
``MultiCompareCanvasWidget.initialize`` therefore reschedules itself,
bounded (~5s), resetting the budget once init succeeds.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from tabs.multi_compare.ui import canvas_widget as canvas_widget_module
from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget


def _fake_self(monkeypatch, *, initialized: bool):
    scheduled = []
    fake_timer = SimpleNamespace(singleShot=lambda ms, fn: scheduled.append((ms, fn)))
    monkeypatch.setattr(canvas_widget_module, "QTimer", fake_timer)
    self = SimpleNamespace(
        _renderer=SimpleNamespace(initialized=initialized, initialize=MagicMock()),
        _schedule_init_retry=MagicMock(),
        update=MagicMock(),
    )
    return self, scheduled


def test_aborted_init_schedules_bounded_retry(monkeypatch):
    self, scheduled = _fake_self(monkeypatch, initialized=False)
    MultiCompareCanvasWidget.initialize(self, MagicMock())
    assert self._init_retry_count == 1
    assert [ms for ms, _ in scheduled] == [100]


def test_retry_budget_exhausts(monkeypatch):
    self, scheduled = _fake_self(monkeypatch, initialized=False)
    self._init_retry_count = 50
    MultiCompareCanvasWidget.initialize(self, MagicMock())
    assert self._init_retry_count == 50
    assert scheduled == []


def test_successful_init_resets_budget(monkeypatch):
    self, scheduled = _fake_self(monkeypatch, initialized=True)
    self._init_retry_count = 7
    MultiCompareCanvasWidget.initialize(self, MagicMock())
    assert self._init_retry_count == 0
    assert scheduled == []


def test_retry_tick_updates_only_until_ready(monkeypatch):
    self, _ = _fake_self(monkeypatch, initialized=False)
    MultiCompareCanvasWidget._schedule_init_retry(self)
    self.update.assert_called_once_with()
    self._renderer.initialized = True
    self.update.reset_mock()
    MultiCompareCanvasWidget._schedule_init_retry(self)
    self.update.assert_not_called()
