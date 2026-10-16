"""Large-drop AI cost guard: threshold + domain + suppress gating.

The dialog itself is a thin wrapper over the shared ``AppMessageDialog``;
these tests pin the decision logic and the "don't ask again" persistence so a
big drop is confirmed exactly once, only in the AI domain.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from tabs.image_gallery.use_cases import large_drop_guard as guard


class _FakeController:
    def __init__(self, domain: str = "ai") -> None:
        self._judgment_domain = domain

    def _tr(self, key: str, default: str) -> str:
        return default


def _no_suppress(monkeypatch) -> None:
    monkeypatch.setattr(guard, "is_suppressed", lambda: False)


def test_threshold_is_inclusive_boundary(monkeypatch):
    _no_suppress(monkeypatch)
    ctrl = _FakeController("ai")
    assert guard.should_warn(ctrl, 35) is False
    assert guard.should_warn(ctrl, 36) is True
    assert guard.LARGE_DROP_THRESHOLD == 35


def test_only_warns_in_ai_domain(monkeypatch):
    _no_suppress(monkeypatch)
    assert guard.should_warn(_FakeController("algorithms"), 100) is False
    assert guard.should_warn(_FakeController("ai"), 100) is True


def test_suppressed_skips_warning(monkeypatch):
    monkeypatch.setattr(guard, "is_suppressed", lambda: True)
    assert guard.should_warn(_FakeController("ai"), 100) is False


def test_guard_passes_through_when_not_applicable(monkeypatch):
    _no_suppress(monkeypatch)

    def _boom(*a, **k):  # dialog must NOT be reached
        raise AssertionError("dialog shown for a non-applicable drop")

    monkeypatch.setattr(guard.AppMessageDialog, "show_modal_ex", _boom)
    assert guard.guard_large_drop(None, _FakeController("algorithms"), 100) is True
    assert guard.guard_large_drop(None, _FakeController("ai"), 10) is True


def test_confirm_proceeds_without_persisting(monkeypatch):
    _no_suppress(monkeypatch)
    saved = []
    monkeypatch.setattr(guard, "set_suppressed", lambda v=True: saved.append(v))
    monkeypatch.setattr(
        guard.AppMessageDialog,
        "show_modal_ex",
        staticmethod(lambda *a, **k: (QDialog.DialogCode.Accepted, False)),
    )
    assert guard.guard_large_drop(None, _FakeController("ai"), 40) is True
    assert saved == []


def test_confirm_and_dont_ask_persists(monkeypatch):
    _no_suppress(monkeypatch)
    saved = []
    monkeypatch.setattr(guard, "set_suppressed", lambda v=True: saved.append(v))
    monkeypatch.setattr(
        guard.AppMessageDialog,
        "show_modal_ex",
        staticmethod(lambda *a, **k: (QDialog.DialogCode.Accepted, True)),
    )
    assert guard.guard_large_drop(None, _FakeController("ai"), 40) is True
    assert saved == [True]


def test_cancel_aborts_and_does_not_persist(monkeypatch):
    _no_suppress(monkeypatch)
    saved = []
    monkeypatch.setattr(guard, "set_suppressed", lambda v=True: saved.append(v))
    monkeypatch.setattr(
        guard.AppMessageDialog,
        "show_modal_ex",
        staticmethod(lambda *a, **k: (QDialog.DialogCode.Rejected, False)),
    )
    assert guard.guard_large_drop(None, _FakeController("ai"), 40) is False
    assert saved == []
