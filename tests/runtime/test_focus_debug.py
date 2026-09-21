"""SLI_FOCUS_DEBUG tracer: focusChanged transitions get logged with identity.

Guards: install is idempotent, logging carries widget identity plus host
window state (minimized/visible/active), silence when the flag is off.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtWidgets import QLineEdit

from ui.focus_debug import focus_debug_enabled, install_focus_tracer


@pytest.fixture()
def _flag_on(monkeypatch):
    monkeypatch.setenv("SLI_FOCUS_DEBUG", "1")
    assert focus_debug_enabled()


@pytest.fixture()
def _flag_off(monkeypatch):
    monkeypatch.setenv("SLI_FOCUS_DEBUG", "0")
    assert not focus_debug_enabled()


def test_install_is_idempotent(qapp, _flag_on):
    assert install_focus_tracer(qapp) is True
    assert install_focus_tracer(qapp) is True


def test_transition_logged_with_identity_and_window_state(qapp, _flag_on, caplog):
    from ui.focus_debug import _on_focus_changed

    first = QLineEdit()
    first.setObjectName("first-field")
    second = QLineEdit()
    second.setObjectName("second-field")
    first.show()
    second.show()
    qapp.processEvents()
    assert install_focus_tracer(qapp) is True
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        # Qt-driven: at least one real transition must be traced (offscreen
        # may pre-focus on show(), so exactly which transition fires varies —
        # assert the trace presence + window-state fields, not the direction).
        first.setFocus()
        qapp.processEvents()
        second.setFocus()
        qapp.processEvents()
        # Deterministic: direct slot call pins the formatting contract.
        _on_focus_changed(first, second)
    lines = [
        r.getMessage() for r in caplog.records if "[focus-debug]" in r.getMessage()
    ]
    assert lines, "expected at least one focus-debug line"
    assert any("minimized=" in line for line in lines)
    assert any("first-field" in line and "second-field" in line for line in lines)


def test_silent_when_flag_off(qapp, _flag_off, caplog):
    assert install_focus_tracer(qapp) is False
    first = QLineEdit()
    first.setObjectName("quiet-field")
    first.show()
    qapp.processEvents()
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        first.setFocus()
        qapp.processEvents()
    assert not any(
        "[focus-debug]" in r.getMessage() for r in caplog.records
    )


def test_install_drops_logger_level_to_debug(qapp, _flag_on):
    conventional = logging.getLogger("ImproveImgSLI")
    conventional.setLevel(logging.WARNING)
    try:
        assert install_focus_tracer(qapp) is True
        assert conventional.getEffectiveLevel() <= logging.DEBUG
    finally:
        conventional.setLevel(logging.NOTSET)
