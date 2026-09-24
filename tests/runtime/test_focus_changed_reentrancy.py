"""focusChanged must not recurse to RecursionError.

Regression for: RecursionError dying inside logging.format, reached via
UIManager._on_app_focus_changed -> TransientUIManager -> PopupClosingController.
The focusChanged signal is synchronous, so any downstream focus move re-enters
the slot before it returns (A->B->A->...). The slot must drop nested entries
and must never propagate exceptions into Qt signal machinery.
"""

from __future__ import annotations

from types import SimpleNamespace

from ui.managers.transient_ui_parts.closing import _safe_widget_label
from ui.managers.ui_manager import UIManager


def _stub_manager(transient):
    manager = UIManager.__new__(UIManager)
    manager.transient = transient
    return manager


def test_reentrant_focus_changed_returns_early():
    calls = []

    manager = _stub_manager(SimpleNamespace())

    def _reentrant(old, new):
        calls.append((old, new))
        # Simulate a downstream focus move emitting focusChanged synchronously.
        manager._on_app_focus_changed(old, new)

    manager.transient.on_app_focus_changed = _reentrant
    manager._on_app_focus_changed("a", "b")
    assert calls == [("a", "b")]
    assert manager._in_focus_changed is False


def test_focus_changed_exception_does_not_propagate():
    def _boom(old, new):
        raise RuntimeError("downstream died")

    manager = _stub_manager(SimpleNamespace(on_app_focus_changed=_boom))
    manager._on_app_focus_changed("a", "b")  # must not raise
    assert manager._in_focus_changed is False


def test_safe_widget_label_never_touches_qt():
    assert _safe_widget_label(None) is None
    assert _safe_widget_label(object()) == "object"

    class _Evil:
        @property
        def __class__(self):  # noqa: D105 - excercise defensive path
            raise RuntimeError("nope")

    assert _safe_widget_label(_Evil()) == "_Evil"
