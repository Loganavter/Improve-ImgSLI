from core.constants import AppConstants
from shared.untested_export_resolution import (
    confirm_untested_export_resolution,
    exceeds_tested_export_edge,
)


def test_exceeds_tested_export_edge_boundary():
    edge = int(AppConstants.EXPORT_TESTED_MAX_EDGE)
    assert not exceeds_tested_export_edge(edge, edge)
    assert not exceeds_tested_export_edge(edge, 1)
    assert exceeds_tested_export_edge(edge + 1, 100)
    assert exceeds_tested_export_edge(100, edge + 1)


def test_confirm_skips_when_suppressed(monkeypatch):
    calls = {"dialog": 0}

    def _boom(*_a, **_k):
        calls["dialog"] += 1
        raise AssertionError("dialog should not open when suppressed")

    monkeypatch.setattr(
        "shared.untested_export_resolution.AppMessageDialog.show_modal_ex",
        _boom,
    )
    assert confirm_untested_export_resolution(
        None,
        20000,
        100,
        translate=lambda key, default=None: default or key,
        suppressed=True,
    )
    assert calls["dialog"] == 0


def test_confirm_persists_dont_show_again(monkeypatch):
    from PySide6.QtWidgets import QDialog

    suppressed = {"done": False}

    def _fake_show(*_a, **_k):
        return QDialog.DialogCode.Accepted, True

    monkeypatch.setattr(
        "shared.untested_export_resolution.AppMessageDialog.show_modal_ex",
        _fake_show,
    )
    assert confirm_untested_export_resolution(
        None,
        20000,
        100,
        translate=lambda key, default=None: default or key,
        on_suppress=lambda: suppressed.__setitem__("done", True),
    )
    assert suppressed["done"] is True
